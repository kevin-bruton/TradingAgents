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
    with app_state_lock:
        # Initialize the root node if it doesn't exist
        if not app_state["execution_tree"]:
            app_state["execution_tree"].append({
                "id": "root",
                "name": f"Trading Analysis for {app_state['company_symbol']}",
                "status": "in_progress",
                "content": f"Analyzing {app_state['company_symbol']} using multiple trading agents",
                "children": [],
                "timestamp": time.time()
            })
        
        root_node = app_state["execution_tree"][0]
        
        # Define the expected phases and their order
        phase_map = {
            "market_analyst": {"name": "Market Analysis", "phase": "data_collection"},
            "social_analyst": {"name": "Social Media Analysis", "phase": "data_collection"},
            "news_analyst": {"name": "News Analysis", "phase": "data_collection"},
            "fundamentals_analyst": {"name": "Fundamental Analysis", "phase": "data_collection"},
            "bull_researcher": {"name": "Bull Case Research", "phase": "research"},
            "bear_researcher": {"name": "Bear Case Research", "phase": "research"},
            "research_manager": {"name": "Research Synthesis", "phase": "research"},
            "trade_planner": {"name": "Trade Planning", "phase": "planning"},
            "trader": {"name": "Trade Execution", "phase": "execution"},
            "risky_analyst": {"name": "Risk Assessment (Aggressive)", "phase": "risk_analysis"},
            "neutral_analyst": {"name": "Risk Assessment (Neutral)", "phase": "risk_analysis"},
            "safe_analyst": {"name": "Risk Assessment (Conservative)", "phase": "risk_analysis"},
            "risk_judge": {"name": "Final Risk Evaluation", "phase": "risk_analysis"}
        }
        
        # Find which agent just completed by examining the state
        for key, value in state.items():
            if key in ["__end__", "messages"]:
                continue
                
            # Map the key to a more user-friendly name
            agent_key = key.lower().replace(" ", "_").replace("_agent", "").replace("_node", "")
            if agent_key in phase_map:
                phase_info = phase_map[agent_key]
                
                # Find or create phase category
                phase_category = None
                for child in root_node["children"]:
                    if child["id"] == phase_info["phase"]:
                        phase_category = child
                        break
                
                if not phase_category:
                    phase_names = {
                        "data_collection": "📊 Data Collection",
                        "research": "🔍 Research & Analysis", 
                        "planning": "📋 Trade Planning",
                        "execution": "⚡ Trade Execution",
                        "risk_analysis": "⚠️ Risk Management"
                    }
                    
                    phase_category = {
                        "id": phase_info["phase"],
                        "name": phase_names.get(phase_info["phase"], phase_info["phase"]),
                        "status": "in_progress",
                        "content": f"Phase: {phase_names.get(phase_info['phase'], phase_info['phase'])}",
                        "children": [],
                        "timestamp": time.time()
                    }
                    root_node["children"].append(phase_category)
                
                # Check if this specific step already exists
                step_exists = False
                for step in phase_category["children"]:
                    if step["name"] == phase_info["name"]:
                        step["status"] = "completed"
                        step["content"] = str(value) if value else "Completed successfully"
                        step_exists = True
                        break
                
                if not step_exists:
                    # Add new step
                    new_step = {
                        "id": f"{phase_info['phase']}_{agent_key}_{len(phase_category['children'])}",
                        "name": phase_info["name"],
                        "status": "completed",
                        "content": str(value) if value else "Completed successfully",
                        "children": [],
                        "timestamp": time.time()
                    }
                    phase_category["children"].append(new_step)
                
                # Check if phase is complete (simple heuristic)
                completed_steps = sum(1 for step in phase_category["children"] if step["status"] == "completed")
                if completed_steps >= len(phase_category["children"]):
                    phase_category["status"] = "completed"
                
                # Update overall progress based on completed phases
                total_phases = len([p for p in phase_map.values()])
                completed_agents = sum(len(child["children"]) for child in root_node["children"] 
                                     if child.get("children"))
                app_state["overall_progress"] = min(100, int((completed_agents / max(total_phases, 1)) * 100))

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
        
        graph = TradingAgentsGraph(config=custom_config)
        analysis_date = config["analysis_date"]  # Use user-selected date
        # The propagate method now accepts the callback and trade_date
        final_state = graph.propagate(company_symbol, trade_date=analysis_date, on_step_callback=update_execution_state)
        
        with app_state_lock:
            app_state["overall_status"] = "completed"
            app_state["overall_progress"] = 100
            # Update the root node status to completed
            if app_state["execution_tree"]:
                app_state["execution_tree"][0]["status"] = "completed"
                app_state["execution_tree"][0]["content"] = str(final_state)

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
        app_state["execution_tree"] = [] # Clear for new run
        app_state["overall_status"] = "in_progress"
        app_state["overall_progress"] = 0
        
        # Store all configuration parameters
        app_state["config"] = {
            "llm_provider": llm_provider,
            "quick_think_llm": quick_think_llm,
            "deep_think_llm": deep_think_llm,
            "max_debate_rounds": max_debate_rounds,
            "cost_per_trade": cost_per_trade,
            "analysis_date": analysis_date
        }

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
