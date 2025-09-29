from fastapi import FastAPI, Request, Form, BackgroundTasks, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
import jinja2
import markdown as md
import bleach
import os
from typing import Dict, Any
import threading
import time
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Check required environment variables
required_env_vars = [
    'FINNHUB_API_KEY',
    'OPENAI_API_KEY',
    #'REDDIT_CLIENT_ID',
    #'REDDIT_CLIENT_SECRET',
    #'REDDIT_USER_AGENT'
]

missing_vars = [var for var in required_env_vars if not os.getenv(var)]
if missing_vars:
    print(f"Error: Missing required environment variables: {', '.join(missing_vars)}")
    print("Please create a .env file with these variables or set them in your environment.")

from tradingagents.graph.trading_graph import TradingAgentsGraph

app = FastAPI()

# In-memory storage for the process state
# Using a lock for thread-safe access to app_state
app_state_lock = threading.Lock()
app_state: Dict[str, Any] = {
    "process_running": False,
    "company_symbol": None,
    "execution_tree": [],
    "overall_status": "idle", # idle, in_progress, completed, error
    "overall_progress": 0 # 0-100
}

# Define the strict sequential phase execution order
PHASE_SEQUENCE = [
    "data_collection_phase",
    "research_phase",
    "planning_phase",
    "execution_phase",
    "risk_analysis_phase",
    # New dedicated top-level phase for the final portfolio decision
    "final_decision_phase"
]

# Mount the static directory to serve CSS, JS, etc.
app.mount("/static", StaticFiles(directory="webapp/static"), name="static")

# Setup Jinja2 for templating
template_dir = os.path.join(os.path.dirname(__file__), "templates")
jinja_env = jinja2.Environment(loader=jinja2.FileSystemLoader(template_dir))

# Allowed tags and attributes for sanitized markdown rendering
ALLOWED_TAGS = list(bleach.sanitizer.ALLOWED_TAGS) + [
    "p", "pre", "span", "h1", "h2", "h3", "h4", "h5", "h6", "table", "thead", "tbody", "tr", "th", "td", "blockquote", "code"
]
ALLOWED_ATTRIBUTES = {**bleach.sanitizer.ALLOWED_ATTRIBUTES, "span": ["class"], "code": ["class"], "th": ["align"], "td": ["align"]}

def render_markdown(value: str) -> str:
    """Convert markdown text to sanitized HTML."""
    if not isinstance(value, str):
        value = str(value)
    html = md.markdown(
        value,
        extensions=["fenced_code", "tables", "codehilite", "toc", "sane_lists"],
        output_format="html5"
    )
    cleaned = bleach.clean(html, tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRIBUTES, strip=True)
    return cleaned

jinja_env.filters['markdown'] = render_markdown

def update_execution_state(state: Dict[str, Any]):
    """Callback function to update the app_state based on LangGraph's state."""
    print(f"📡 Callback received state keys: {list(state.keys())}")
    
    with app_state_lock:
        # Ensure execution tree is initialized
        if not app_state["execution_tree"]:
            app_state["execution_tree"] = initialize_complete_execution_tree()
        
        # Map LangGraph node names to our tracking system
        agent_state_mapping = {
            "Market Analyst": {
                "phase": "data_collection", 
                "agent_id": "market_analyst",
                "report_key": "market_report",
                "report_name": "Market Analysis Report"
            },
            "Social Analyst": {
                "phase": "data_collection", 
                "agent_id": "social_analyst",
                "report_key": "sentiment_report", 
                "report_name": "Sentiment Analysis Report"
            },
            "News Analyst": {
                "phase": "data_collection", 
                "agent_id": "news_analyst",
                "report_key": "news_report",
                "report_name": "News Analysis Report"
            },
            "Fundamentals Analyst": {
                "phase": "data_collection", 
                "agent_id": "fundamentals_analyst",
                "report_key": "fundamentals_report",
                "report_name": "Fundamentals Report"
            },
            "Bull Researcher": {
                "phase": "research", 
                "agent_id": "bull_researcher",
                "report_key": "investment_debate_state.bull_history",
                "report_name": "Bull Case Analysis"
            },
            "Bear Researcher": {
                "phase": "research", 
                "agent_id": "bear_researcher",
                "report_key": "investment_debate_state.bear_history",
                "report_name": "Bear Case Analysis"
            },
            "Research Manager": {
                "phase": "research", 
                "agent_id": "research_manager",
                "report_key": "investment_debate_state.judge_decision",
                "report_name": "Research Synthesis"
            },
            "Trade Planner": {
                "phase": "planning", 
                "agent_id": "trade_planner",
                "report_key": "trader_investment_plan",
                "report_name": "Trading Plan"
            },
            "Trader": {
                "phase": "execution", 
                "agent_id": "trader",
                "report_key": "investment_plan",
                "report_name": "Execution Report"
            },
            "Risky Analyst": {
                "phase": "risk_analysis", 
                "agent_id": "risky_analyst",
                "report_key": "risk_debate_state.risky_history",
                "report_name": "Risk Assessment (Aggressive)"
            },
            "Neutral Analyst": {
                "phase": "risk_analysis", 
                "agent_id": "neutral_analyst",
                "report_key": "risk_debate_state.neutral_history",
                "report_name": "Risk Assessment (Neutral)"
            },
            "Safe Analyst": {
                "phase": "risk_analysis", 
                "agent_id": "safe_analyst",
                "report_key": "risk_debate_state.safe_history",
                "report_name": "Risk Assessment (Conservative)"
            },
            "Risk Judge": {
                # Moved to its own dedicated phase for prominence
                "phase": "final_decision", 
                "agent_id": "risk_judge",
                "report_key": "final_trade_decision",
                "report_name": "Portfolio Manager's Decision"
            }
        }
        
        # Update agent statuses based on available reports
        for agent_name, agent_info in agent_state_mapping.items():
            # Check if this agent has completed (has report data)
            report_data = get_nested_value(state, agent_info["report_key"])
            if report_data:
                update_agent_status(agent_info, "completed", report_data, state)
        
        # Mark in-progress agent(s) sequentially BEFORE recalculating phase status
        mark_in_progress_agents(app_state["execution_tree"])
        # Recalculate phase statuses after setting agent in-progress markers
        recalc_phase_statuses(app_state["execution_tree"])
        # Update overall progress
        execution_tree = app_state["execution_tree"]
        total_agents = len(agent_state_mapping)
        completed_agents = count_completed_agents(execution_tree)
        app_state["overall_progress"] = min(100, int((completed_agents / max(total_agents, 1)) * 100))

        print(f"📊 Progress updated: {app_state['overall_progress']}% ({completed_agents}/{total_agents} agents)")

def initialize_complete_execution_tree():
    """Initialize the complete execution tree with all agents in pending state."""
    return [
        {
            "id": "data_collection_phase",
            "name": "📊 Data Collection Phase",
            "status": "pending",
            "content": "Collecting market data and analysis from various sources",
            "children": [
                create_agent_node("market_analyst", "📈 Market Analyst"),
                create_agent_node("social_analyst", "📱 Social Media Analyst"),
                create_agent_node("news_analyst", "📰 News Analyst"),
                create_agent_node("fundamentals_analyst", "📊 Fundamentals Analyst")
            ]
        },
        {
            "id": "research_phase",
            "name": "🔍 Research Phase",
            "status": "pending",
            "content": "Research and debate investment perspectives",
            "children": [
                create_agent_node("bull_researcher", "🐂 Bull Researcher"),
                create_agent_node("bear_researcher", "🐻 Bear Researcher"),
                create_agent_node("research_manager", "🔍 Research Manager")
            ]
        },
        {
            "id": "planning_phase",
            "name": "📋 Planning Phase", 
            "status": "pending",
            "content": "Develop trading strategy and execution plan",
            "children": [
                create_agent_node("trade_planner", "📋 Trade Planner")
            ]
        },
        {
            "id": "execution_phase",
            "name": "⚡ Execution Phase",
            "status": "pending", 
            "content": "Execute trades based on analysis and planning",
            "children": [
                create_agent_node("trader", "⚡ Trader")
            ]
        },
        {
            "id": "risk_analysis_phase",
            "name": "⚠️ Risk Management Phase",
            "status": "pending",
            "content": "Assess and manage investment risks",
            "children": [
                create_agent_node("risky_analyst", "🚨 Aggressive Risk Analyst"),
                create_agent_node("neutral_analyst", "⚖️ Neutral Risk Analyst"),
                create_agent_node("safe_analyst", "🛡️ Conservative Risk Analyst")
            ]
        },
        {
            "id": "final_decision_phase",
            "name": "🧠 Portfolio Manager's Decision",
            "status": "pending",
            "content": "Final portfolio / trade decision synthesized from all prior phases",
            "children": [
                create_agent_node("risk_judge", "🧠 Portfolio Manager")
            ]
        }
    ]

def create_agent_node(agent_id: str, agent_name: str):
    """Create a standardized agent node with report and messages sub-items."""
    return {
        "id": agent_id,
        "name": agent_name,
        "status": "pending",
        "content": f"Agent: {agent_name} - Awaiting execution",
        "children": [
            {
                "id": f"{agent_id}_messages",
                "name": "💬 Messages",
                "status": "pending", 
                "content": "No messages yet",
                "children": [],
                "timestamp": time.time()
            },
            {
                "id": f"{agent_id}_report",
                "name": "📄 Report",
                "status": "pending",
                "content": "Report not yet generated",
                "children": [],
                "timestamp": time.time()
            }
        ],
        "timestamp": time.time()
    }

def get_nested_value(data: dict, key_path: str):
    """Get value from nested dict using dot notation (e.g., 'investment_debate_state.bull_history')."""
    keys = key_path.split('.')
    value = data
    for key in keys:
        if isinstance(value, dict) and key in value:
            value = value[key]
        else:
            return None
    return value

def update_agent_status(agent_info: dict, status: str, report_data: any, full_state: dict):
    """Update an agent's status and content in the execution tree."""
    execution_tree = app_state["execution_tree"]
    
    # Find the agent in the tree
    agent_node = find_agent_in_tree(agent_info["agent_id"], execution_tree)
    if not agent_node:
        return
        
    # Update agent status
    if agent_node["status"] != "completed":
        agent_node["status"] = status
        agent_node["content"] = f"✅ {agent_node['name']} - Analysis completed"
        
        # Update report sub-item
        report_node = find_item_by_id(f"{agent_info['agent_id']}_report", agent_node["children"])
        if report_node:
            report_node["status"] = "completed"
            report_node["content"] = format_report_content(agent_info["report_name"], report_data)
            
        # Update messages sub-item (extract from state if available)
        messages_node = find_item_by_id(f"{agent_info['agent_id']}_messages", agent_node["children"])
        if messages_node:
            messages_node["status"] = "completed"
            messages_node["content"] = extract_agent_messages(full_state, agent_info["agent_id"])
    
    # Phase status recalculated globally in recalc_phase_statuses

def find_agent_in_tree(agent_id: str, tree: list):
    """Find an agent node in the execution tree."""
    for phase in tree:
        if phase.get("children"):
            for agent in phase["children"]:
                if agent["id"] == agent_id:
                    return agent
    return None

def find_item_by_id(item_id: str, items: list):
    """Find an item by ID in a list of items."""
    for item in items:
        if item["id"] == item_id:
            return item
    return None

def format_report_content(report_name: str, report_data: any) -> str:
    """Format report data for display."""
    if isinstance(report_data, str):
        return f"📄 {report_name}\n\n{report_data}"
    elif isinstance(report_data, dict):
        return f"📄 {report_name}\n\n{str(report_data)}"
    elif isinstance(report_data, list) and report_data:
        # For debate histories, show the latest message
        latest = report_data[-1] if report_data else "No data"
        return f"📄 {report_name}\n\n{str(latest)}"
    else:
        return f"📄 {report_name}\n\nReport generated successfully"

def extract_agent_messages(state: dict, agent_id: str) -> str:
    """Extract relevant messages for an agent from the state."""
    # Expecting state['messages'] to be a list of dicts with optional keys like
    # 'role', 'content', 'timestamp'. We'll display each in an expandable box.
    messages = state.get("messages", []) or []
    if not messages:
        return "💬 Agent Messages\n\nNo messages recorded for this agent."

    # Filter messages for this agent if agent_id field present
    filtered = []
    for m in messages:
        if isinstance(m, dict):
            msg_agent = m.get("agent_id") or m.get("agent")
            if msg_agent and msg_agent != agent_id:
                continue
            filtered.append(m)
        else:
            # Try common attributes used by message objects (e.g., langchain HumanMessage / AIMessage)
            msg_agent = getattr(m, "agent_id", None) or getattr(m, "agent", None)
            if msg_agent and msg_agent != agent_id:
                continue
            filtered.append(m)
    if not filtered:
        filtered = messages  # fallback to all if no agent-specific match

    parts = ["💬 Agent Messages", "", f"Total messages: {len(filtered)}", ""]
    for idx, m in enumerate(filtered, start=1):
        if isinstance(m, dict):
            role = m.get("role") or m.get("type") or "message"
            ts = m.get("timestamp")
            content = m.get("content") or m.get("text") or "(no content)"
        else:
            # Object-based message
            role = getattr(m, "role", None) or getattr(m, "type", None) or m.__class__.__name__
            ts = getattr(m, "timestamp", None)
            # LangChain messages often have a .content attribute
            content = getattr(m, "content", None) or getattr(m, "text", None) or str(m)
        # Escape triple backticks to avoid markdown parser confusion
        if isinstance(content, str):
            content = content.replace('```', '\u0060\u0060\u0060')
        header = f"{idx}. {role.title()}" + (f" – {ts}" if ts else "")
        # Use HTML <details> so user can expand long messages
        parts.append(
            f"<details class=\"message-box\" {'open' if idx <= 3 else ''}>")
        parts.append(f"  <summary>{header}</summary>")
        # Wrap content in pre for formatting
        parts.append("  <pre class=\"message-content\">" + str(content) + "</pre>")
        parts.append("</details>")

    return "\n".join(parts)

def recalc_phase_statuses(execution_tree: list):
    """Recalculate each phase's status: pending (no started), in_progress (some running/completed but not all), completed (all done), error if any child error."""
    for phase in execution_tree:
        if not phase.get("children"):
            continue
        child_statuses = [c["status"] for c in phase["children"]]
        if any(s == "error" for s in child_statuses):
            phase["status"] = "error"
            phase["content"] = f"❌ {phase['name']} - Error in sub-task"
        elif all(s == "completed" for s in child_statuses):
            phase["status"] = "completed"
            phase["content"] = f"✅ {phase['name']} - All agents completed successfully"
        elif any(s in ("in_progress", "completed") for s in child_statuses):
            # At least one started but not all done
            if phase["status"] != "in_progress":
                phase["status"] = "in_progress"
                phase["content"] = f"⏳ {phase['name']} - Running..."
        else:
            # All pending
            phase["status"] = "pending"


def count_completed_agents(execution_tree: list) -> int:
    """Count the number of completed agents across all phases."""
    count = 0
    for phase in execution_tree:
        if phase.get("children"):
            for agent in phase["children"]:
                if agent["status"] == "completed":
                    count += 1
    return count

def mark_in_progress_agents(execution_tree: list):
    """Sequentially activate only the earliest phase that still has pending agents.
    Rules:
      - A phase becomes active when all prior phases are completed.
      - Only the first such phase can have an in_progress agent.
      - Within that phase, mark exactly one first pending agent as in_progress.
    """
    # Build quick lookup by id
    phase_map = {p["id"]: p for p in execution_tree}

    # Determine which phase should be active
    active_phase = None
    for phase_id in PHASE_SEQUENCE:
        phase = phase_map.get(phase_id)
        if not phase:
            continue
        # If all previous phases completed, and this phase not fully completed, it's the active one
        prev_completed = all(
            (phase_map.get(prev_id) and all(c["status"] == "completed" for c in phase_map[prev_id].get("children", [])))
            for prev_id in PHASE_SEQUENCE[:PHASE_SEQUENCE.index(phase_id)]
        )
        phase_done = all(c["status"] == "completed" for c in phase.get("children", []))
        if prev_completed and not phase_done:
            active_phase = phase
            break

    if not active_phase:
        return

    # If an agent already in progress in the active phase, leave as-is
    if any(a["status"] == "in_progress" for a in active_phase.get("children", [])):
        return

    # Otherwise pick first pending agent
    for agent in active_phase.get("children", []):
        if agent["status"] == "pending":
            agent["status"] = "in_progress"
            agent["content"] = f"⏳ {agent['name']} - Running analysis..."
            for child in agent.get("children", []):
                if child["status"] == "pending":
                    child["status"] = "in_progress"
            break

def run_trading_process(company_symbol: str, config: Dict[str, Any]):
    """Runs the TradingAgentsGraph in a separate thread."""
    with app_state_lock:
        app_state["overall_status"] = "in_progress"
        app_state["overall_progress"] = 0

    try:
        # Import and create custom config
        from tradingagents.default_config import DEFAULT_CONFIG
        
        # Create custom configuration with user selections
        custom_config = DEFAULT_CONFIG.copy()
        custom_config["llm_provider"] = config["llm_provider"]
        custom_config["max_debate_rounds"] = config["max_debate_rounds"]
        custom_config["cost_per_trade"] = config["cost_per_trade"]
        
        # Set the appropriate LLM models based on provider
        if config["llm_provider"] == "google":
            custom_config["gemini_quick_think_llm"] = config["quick_think_llm"]
            custom_config["gemini_deep_think_llm"] = config["deep_think_llm"]
        else:
            custom_config["quick_think_llm"] = config["quick_think_llm"]
            custom_config["deep_think_llm"] = config["deep_think_llm"]
        
        # Set backend URL based on provider
        if config["llm_provider"] == "openrouter":
            custom_config["backend_url"] = "https://openrouter.ai/api/v1"
        elif config["llm_provider"] == "google":
            custom_config["backend_url"] = "https://generativelanguage.googleapis.com/v1"
        elif config["llm_provider"] == "anthropic":
            custom_config["backend_url"] = "https://api.anthropic.com/"
        elif config["llm_provider"] == "ollama":
            custom_config["backend_url"] = f"http://{os.getenv('OLLAMA_HOST', 'localhost')}:11434/v1"
        else:  # openai
            custom_config["backend_url"] = "https://api.openai.com/v1"
        
        print(f"🚀 Initializing TradingAgentsGraph for {company_symbol}")
        graph = TradingAgentsGraph(config=custom_config)
        analysis_date = config["analysis_date"]  # Use user-selected date
        print(f"🔄 Starting propagation for {company_symbol} on {analysis_date}")
        
        # Include user position context
        user_position = config.get("user_position", "none")
        init_sl = config.get("initial_stop_loss")
        init_tp = config.get("initial_take_profit")

        # The propagate method now accepts the callback and trade_date and we will inject user position.
        final_state, processed_signal = graph.propagate(
            company_symbol,
            trade_date=analysis_date,
            user_position=user_position,
            cost_per_trade=config.get("cost_per_trade", 0.0),
            on_step_callback=update_execution_state,
            initial_stop_loss=init_sl,
            initial_take_profit=init_tp,
        )
        print(f"✅ Propagation completed for {company_symbol}")
        
        with app_state_lock:
            app_state["overall_status"] = "completed"
            app_state["overall_progress"] = 100
            # Update the root node status to completed
            if app_state["execution_tree"]:
                app_state["execution_tree"][0]["status"] = "completed"
                app_state["execution_tree"][0]["content"] = f"✅ Analysis completed successfully!\n\nFinal Decision: {processed_signal}\n\nFull State: {str(final_state)}"

    except Exception as e:
        import traceback
        error_detail = traceback.format_exc()
        with app_state_lock:
            app_state["overall_status"] = "error"
            app_state["overall_progress"] = 100
            if app_state["execution_tree"]:
                app_state["execution_tree"][0]["status"] = "error"
                app_state["execution_tree"][0]["content"] = f"Error during execution: {str(e)}\n\n{error_detail}"
            # Add a specific error item to the tree
            app_state["execution_tree"].append({
                "id": "error",
                "name": "Process Error",
                "status": "error",
                "content": f"Error during execution: {str(e)}\n\n{error_detail}",
                "children": [],
                "timestamp": time.time()
            })
    finally:
        with app_state_lock:
            app_state["process_running"] = False


@app.get("/", response_class=HTMLResponse)
async def read_root():
    from datetime import date
    template = jinja_env.get_template("index.html")
    today_str = date.today().isoformat()
    return template.render(app_state=app_state, default_date=today_str)

@app.post("/start", response_class=HTMLResponse)
async def start_process(
    background_tasks: BackgroundTasks, 
    company_symbol: str = Form(...),
    llm_provider: str = Form(...), 
    quick_think_llm: str = Form(...),
    deep_think_llm: str = Form(...),
    max_debate_rounds: int = Form(...),
    cost_per_trade: float = Form(...),
    analysis_date: str = Form(...),
    position_status: str = Form("none"),
    current_stop_loss: str | None = Form(None),
    current_take_profit: str | None = Form(None)
):
    # Check if all required environment variables are set
    missing_vars = [var for var in required_env_vars if not os.getenv(var)]
    if missing_vars:
        app_state["overall_status"] = "error"
        app_state["execution_tree"] = [{
            "id": "error",
            "name": "Configuration Error",
            "status": "error",
            "content": f"Missing required environment variables: {', '.join(missing_vars)}. Please check .env.example file.",
            "children": [],
            "timestamp": time.time()
        }]
        template = jinja_env.get_template("_partials/left_panel.html")
        return template.render(tree=app_state["execution_tree"], app_state=app_state)

    with app_state_lock:
        if app_state["process_running"]:
            # Optionally, return an error or a message that a process is already running
            template = jinja_env.get_template("_partials/left_panel.html")
            return template.render(tree=app_state["execution_tree"], app_state=app_state)

        app_state["process_running"] = True
        app_state["company_symbol"] = company_symbol
        app_state["overall_status"] = "in_progress"
        app_state["overall_progress"] = 5  # Show initial progress
        
        # Store all configuration parameters
        # Validate and normalize position inputs
        position_status = (position_status or "none").lower()
        if position_status not in ("none", "long", "short"):
            position_status = "none"

        def _parse_level(val: str | None):
            if val is None or val == "":
                return None
            try:
                f = float(val)
                if f <= 0:
                    return None
                return f
            except ValueError:
                return None

        initial_stop_loss = _parse_level(current_stop_loss)
        initial_take_profit = _parse_level(current_take_profit)

        # If no open position, ignore provided levels
        if position_status == "none":
            initial_stop_loss = None
            initial_take_profit = None

        app_state["config"] = {
            "llm_provider": llm_provider,
            "quick_think_llm": quick_think_llm,
            "deep_think_llm": deep_think_llm,
            "max_debate_rounds": max_debate_rounds,
            "cost_per_trade": cost_per_trade,
            "analysis_date": analysis_date,
            "user_position": position_status,
            "initial_stop_loss": initial_stop_loss,
            "initial_take_profit": initial_take_profit
        }
        
        # Initialize execution tree with complete structure
        app_state["execution_tree"] = initialize_complete_execution_tree()

    background_tasks.add_task(run_trading_process, company_symbol, app_state["config"])
    
    template = jinja_env.get_template("_partials/left_panel.html")
    return template.render(tree=app_state["execution_tree"], app_state=app_state)

@app.get("/status", response_class=HTMLResponse)
async def get_status():
    with app_state_lock:
        template = jinja_env.get_template("_partials/left_panel.html")
        return template.render(tree=app_state["execution_tree"], app_state=app_state)


@app.get("/status-updates")
async def get_status_updates():
    """Return only the status updates as JSON for targeted updates."""
    with app_state_lock:
        status_updates = {}
        
        def extract_status_info(items, prefix=""):
            for item in items:
                item_id = item["id"]
                status_updates[item_id] = {
                    "status": item["status"],
                    "status_icon": get_status_icon(item["status"])
                }
                if item.get("children"):
                    extract_status_info(item["children"])
        
        extract_status_info(app_state["execution_tree"])
        
        return {
            "status_updates": status_updates,
            "overall_progress": app_state["overall_progress"],
            "overall_status": app_state["overall_status"]
        }

def get_status_icon(status: str) -> str:
    """Get the status icon for a given status."""
    if status == 'completed':
        return '✅'
    elif status == 'in_progress':
        return '⏳'
    elif status == 'error':
        return '❌'
    else:
        return '⏸️'

def find_item_in_tree(item_id: str, tree: list) -> Dict[str, Any] | None:
    """Recursively searches the execution tree for an item by its ID."""
    for item in tree:
        if item["id"] == item_id:
            return item
        if item["children"]:
            found_child = find_item_in_tree(item_id, item["children"])
            if found_child:
                return found_child
    return None

@app.get("/content/{item_id}", response_class=HTMLResponse)
async def get_item_content(item_id: str):
    with app_state_lock:
        item = find_item_in_tree(item_id, app_state["execution_tree"])
        if item:
            template = jinja_env.get_template("_partials/right_panel.html")
            return template.render(content=item.get("content", "No content available."))
        else:
            return HTMLResponse(content="<p>Item not found.</p>", status_code=404)

# To run this app:
# uvicorn webapp.main:app --reload
