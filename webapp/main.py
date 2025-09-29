from fastapi import FastAPI, Request, Form, BackgroundTasks, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
import jinja2
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

# Mount the static directory to serve CSS, JS, etc.
app.mount("/static", StaticFiles(directory="webapp/static"), name="static")

# Setup Jinja2 for templating
template_dir = os.path.join(os.path.dirname(__file__), "templates")
jinja_env = jinja2.Environment(loader=jinja2.FileSystemLoader(template_dir))

def update_execution_state(state: Dict[str, Any]):
    """Callback function to update the app_state based on LangGraph's state."""
    print(f"📡 Callback received state keys: {list(state.keys())}")
    
    with app_state_lock:
        # Initialize the root node if needed
        if not app_state["execution_tree"] or (
            len(app_state["execution_tree"]) == 1 and 
            app_state["execution_tree"][0]["id"] == "initialization"
        ):
            app_state["execution_tree"] = [{
                "id": "root",
                "name": f"Trading Analysis for {app_state['company_symbol']}",
                "status": "in_progress",
                "content": f"Analyzing {app_state['company_symbol']} using multiple trading agents",
                "children": [],
                "timestamp": time.time()
            }]
        
        root_node = app_state["execution_tree"][0]
        
        # Map LangGraph node names to user-friendly display info
        node_mapping = {
            "Market Analyst": {"name": "📈 Market Analysis", "phase": "data_collection"},
            "Social Analyst": {"name": "📱 Social Media Analysis", "phase": "data_collection"},
            "News Analyst": {"name": "📰 News Analysis", "phase": "data_collection"},
            "Fundamentals Analyst": {"name": "📊 Fundamental Analysis", "phase": "data_collection"},
            "Bull Researcher": {"name": "🐂 Bull Case Research", "phase": "research"},
            "Bear Researcher": {"name": "🐻 Bear Case Research", "phase": "research"},
            "Research Manager": {"name": "🔍 Research Synthesis", "phase": "research"},
            "Trade Planner": {"name": "📋 Trade Planning", "phase": "planning"},
            "Trader": {"name": "⚡ Trade Execution", "phase": "execution"},
            "Risky Analyst": {"name": "🚨 Risk Assessment (Aggressive)", "phase": "risk_analysis"},
            "Neutral Analyst": {"name": "⚖️ Risk Assessment (Neutral)", "phase": "risk_analysis"},
            "Safe Analyst": {"name": "🛡️ Risk Assessment (Conservative)", "phase": "risk_analysis"},
            "Risk Judge": {"name": "⚠️ Final Risk Evaluation", "phase": "risk_analysis"}
        }
        
        phase_names = {
            "data_collection": "📊 Data Collection",
            "research": "🔍 Research & Analysis", 
            "planning": "📋 Trade Planning",
            "execution": "⚡ Trade Execution",
            "risk_analysis": "⚠️ Risk Management"
        }
        
        # The state dict contains the current state of all nodes
        # We need to determine what has actually been executed
        current_step = None
        
        # LangGraph streams the full state each time, so we need to detect what's new
        # Look for populated report fields to determine what has been completed
        if state.get("market_report") and not any(child.get("id") == "data_collection_market" for phase in root_node["children"] for child in phase.get("children", [])):
            current_step = "Market Analyst"
        elif state.get("sentiment_report") and not any(child.get("id") == "data_collection_social" for phase in root_node["children"] for child in phase.get("children", [])):
            current_step = "Social Analyst"
        elif state.get("news_report") and not any(child.get("id") == "data_collection_news" for phase in root_node["children"] for child in phase.get("children", [])):
            current_step = "News Analyst"
        elif state.get("fundamentals_report") and not any(child.get("id") == "data_collection_fundamentals" for phase in root_node["children"] for child in phase.get("children", [])):
            current_step = "Fundamentals Analyst"
        elif state.get("investment_debate_state", {}).get("bull_history") and not any(child.get("id") == "research_bull" for phase in root_node["children"] for child in phase.get("children", [])):
            current_step = "Bull Researcher"
        elif state.get("investment_debate_state", {}).get("bear_history") and not any(child.get("id") == "research_bear" for phase in root_node["children"] for child in phase.get("children", [])):
            current_step = "Bear Researcher"
        elif state.get("investment_debate_state", {}).get("judge_decision") and not any(child.get("id") == "research_manager" for phase in root_node["children"] for child in phase.get("children", [])):
            current_step = "Research Manager"
        elif state.get("trader_investment_plan") and not any(child.get("id") == "planning_trade_planner" for phase in root_node["children"] for child in phase.get("children", [])):
            current_step = "Trade Planner"
        elif state.get("investment_plan") and not any(child.get("id") == "execution_trader" for phase in root_node["children"] for child in phase.get("children", [])):
            current_step = "Trader"
        elif state.get("risk_debate_state", {}).get("risky_history") and not any(child.get("id") == "risk_analysis_risky" for phase in root_node["children"] for child in phase.get("children", [])):
            current_step = "Risky Analyst"
        elif state.get("risk_debate_state", {}).get("neutral_history") and not any(child.get("id") == "risk_analysis_neutral" for phase in root_node["children"] for child in phase.get("children", [])):
            current_step = "Neutral Analyst"
        elif state.get("risk_debate_state", {}).get("safe_history") and not any(child.get("id") == "risk_analysis_safe" for phase in root_node["children"] for child in phase.get("children", [])):
            current_step = "Safe Analyst"
        elif state.get("final_trade_decision") and not any(child.get("id") == "risk_analysis_risk_judge" for phase in root_node["children"] for child in phase.get("children", [])):
            current_step = "Risk Judge"
        
        if current_step and current_step in node_mapping:
            print(f"🎯 Processing step: {current_step}")
            node_info = node_mapping[current_step]
            phase_id = node_info["phase"]
            
            # Find or create phase category
            phase_category = None
            for child in root_node["children"]:
                if child["id"] == phase_id:
                    phase_category = child
                    break
            
            if not phase_category:
                phase_category = {
                    "id": phase_id,
                    "name": phase_names.get(phase_id, phase_id),
                    "status": "in_progress",
                    "content": f"Phase: {phase_names.get(phase_id, phase_id)}",
                    "children": [],
                    "timestamp": time.time()
                }
                root_node["children"].append(phase_category)
            
            # Add new step
            step_id = f"{phase_id}_{current_step.lower().replace(' ', '_')}"
            new_step = {
                "id": step_id,
                "name": node_info["name"],
                "status": "completed",
                "content": f"✅ {node_info['name']} completed successfully",
                "children": [],
                "timestamp": time.time()
            }
            phase_category["children"].append(new_step)
            
            # Mark phase as completed if it has steps
            phase_category["status"] = "completed"
            
            # Update overall progress
            total_steps = len(node_mapping)
            completed_steps = sum(len(child["children"]) for child in root_node["children"])
            app_state["overall_progress"] = min(100, int((completed_steps / max(total_steps, 1)) * 100))
            
            print(f"📊 Progress updated: {app_state['overall_progress']}% ({completed_steps}/{total_steps} steps)")
        else:
            print(f"⏳ No new step detected or step already processed")

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
        
        # The propagate method now accepts the callback and trade_date
        final_state, processed_signal = graph.propagate(company_symbol, trade_date=analysis_date, on_step_callback=update_execution_state)
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
    template = jinja_env.get_template("index.html")
    return template.render(app_state=app_state)

@app.post("/start", response_class=HTMLResponse)
async def start_process(
    background_tasks: BackgroundTasks, 
    company_symbol: str = Form(...),
    llm_provider: str = Form(...), 
    quick_think_llm: str = Form(...),
    deep_think_llm: str = Form(...),
    max_debate_rounds: int = Form(...),
    cost_per_trade: float = Form(...),
    analysis_date: str = Form(...)
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
        app_state["config"] = {
            "llm_provider": llm_provider,
            "quick_think_llm": quick_think_llm,
            "deep_think_llm": deep_think_llm,
            "max_debate_rounds": max_debate_rounds,
            "cost_per_trade": cost_per_trade,
            "analysis_date": analysis_date
        }
        
        # Initialize execution tree with startup message
        app_state["execution_tree"] = [{
            "id": "initialization",
            "name": f"🚀 Initializing Trading Analysis for {company_symbol}",
            "status": "in_progress",
            "content": f"Starting comprehensive trading analysis for {company_symbol}...\n\nConfiguration:\n• LLM Provider: {llm_provider}\n• Quick Think Model: {quick_think_llm}\n• Deep Think Model: {deep_think_llm}\n• Max Debate Rounds: {max_debate_rounds}\n• Cost Per Trade: ${cost_per_trade}\n• Analysis Date: {analysis_date}\n\nInitializing trading agents and preparing analysis pipeline...",
            "children": [],
            "timestamp": time.time()
        }]

    background_tasks.add_task(run_trading_process, company_symbol, app_state["config"])
    
    template = jinja_env.get_template("_partials/left_panel.html")
    return template.render(tree=app_state["execution_tree"], app_state=app_state)

@app.get("/status", response_class=HTMLResponse)
async def get_status():
    with app_state_lock:
        template = jinja_env.get_template("_partials/left_panel.html")
        return template.render(tree=app_state["execution_tree"], app_state=app_state)

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
