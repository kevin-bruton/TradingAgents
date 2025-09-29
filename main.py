from dotenv import load_dotenv
load_dotenv()

from rich.panel import Panel
from rich.console import Console
from rich.align import Align
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

# Create a custom config
config = DEFAULT_CONFIG.copy()
config["ticker"] = "F"
config['analysis_date'] = "2025-09-28"
config["llm_provider"] = "openrouter"  # Use a different model
#config["backend_url"] = "https://generativelanguage.googleapis.com/v1"  # Use a different backend
config["backend_url"] = "https://openrouter.ai/api/v1"
config["deep_think_llm"] = "qwen/qwen3-235b-a22b:free"  # Use a different model
config["quick_think_llm"] = "x-ai/grok-4-fast:free"  # Use a different model
config["max_debate_rounds"] = 1  # Increase debate rounds
config["online_tools"] = True
config["cost_per_trade"] = 0.0


with open("./cli/static/welcome.txt", "r", encoding="utf-8") as f:
    welcome_ascii = f.read()

# Create welcome box content
welcome_content = f"{welcome_ascii}\n"
welcome_content += "[bold green]TradingAgents: Multi-Agents LLM Financial Trading Framework - CLI[/bold green]\n\n"
welcome_content += "[bold]Workflow Steps:[/bold]\n"
welcome_content += "I. Analyst Team -> II. Research Team -> III. Trader -> IV. Risk Management -> V. Portfolio Management\n\n"
welcome_content += (
    "[dim]Built by [Tauric Research](https://github.com/TauricResearch)[/dim]"
)

# Create and center the welcome box
welcome_box = Panel(
    welcome_content,
    border_style="green",
    padding=(1, 2),
    title="Welcome to TradingAgents",
    subtitle="Multi-Agents LLM Financial Trading Framework",
)
console = Console()
console.print(Align.center(welcome_box))
console.print()  # Add a blank line after the welcome box
    
# Initialize with custom config
ta = TradingAgentsGraph(debug=True, config=config)

# forward propagate
_, decision = ta.propagate(config["ticker"], config["analysis_date"])
print(decision)

# Memorize mistakes and reflect
# ta.reflect_and_remember(1000) # parameter is the position returns
