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
        current_step_name = None
        # LangGraph state typically has a single key for the current node's output
        # We need to find which agent just ran
        for key, value in state.items():
            if key != "__end__": # Ignore the special __end__ key
                current_step_name = key
                break

        if current_step_name:
            # Find the root node or create it if it doesn't exist
            if not app_state["execution_tree"]:
                app_state["execution_tree"].append({
                    "id": "root",
                    "name": f"Trading Analysis for {app_state['company_symbol']}",
                    "status": "in_progress",
                    "content": "",
                    "children": [],
                    "timestamp": time.time()
                })
            
            root_node = app_state["execution_tree"][0]
            
            # Check if this step already exists (e.g., if an agent runs multiple times)
            # For simplicity, we'll just append for now. A more robust solution would update existing.
            new_item = {
                "id": f"{current_step_name}-{len(root_node['children'])}", # Simple unique ID
                "name": current_step_name,
                "status": "completed", # Assume completed for now
                "content": str(state.get(current_step_name, "No specific output")), # Store the agent's output
                "children": [],
                "timestamp": time.time()
            }
            root_node["children"].append(new_item)
            root_node["status"] = "in_progress" # Keep root in progress until final
            
            # Update overall progress (very basic, just increments)
            # In a real scenario, you'd have a predefined number of steps
            app_state["overall_progress"] = min(100, app_state["overall_progress"] + 5)

def run_trading_process(company_symbol: str):
    """Runs the TradingAgentsGraph in a separate thread."""
    with app_state_lock:
        app_state["overall_status"] = "in_progress"
        app_state["overall_progress"] = 0

    try:
        graph = TradingAgentsGraph()
        current_date = time.strftime("%Y-%m-%d")  # Use current date for analysis
        # The propagate method now accepts the callback and trade_date
        final_state = graph.propagate(company_symbol, trade_date=current_date, on_step_callback=update_execution_state)
        
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
async def start_process(background_tasks: BackgroundTasks, company_symbol: str = Form(...)):
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

    background_tasks.add_task(run_trading_process, company_symbol)
    
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
