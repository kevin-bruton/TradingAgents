from prettytable import PrettyTable
from datetime import date
import os
from tradingagents.graph.trading_graph import TradingAgentsGraph
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

config = {
    "project_dir": os.path.abspath(os.path.join(os.path.dirname(__file__), ".")),
    "results_dir": os.getenv("TRADINGAGENTS_RESULTS_DIR", "./results"),
    "as_of_date": None,
    "data_cache_dir": os.path.join(
        os.path.abspath(os.path.join(os.path.dirname(__file__), ".")),
        "dataflows/data_cache",
    ),
    # LLM settings
    "llm_provider": "openrouter",
    "deep_think_llm": "qwen/qwen3-vl-235b-a22b-thinking",
    "quick_think_llm": "nvidia/nemotron-3-nano-30b-a3b:free",
    "backend_url": "https://openrouter.ai/api/v1",
    # Provider-specific thinking configuration
    "google_thinking_level": "high",      # "high", "minimal", etc.
    "openai_reasoning_effort": "high",    # "medium", "high", "low"
    # Debate and discussion settings
    "max_debate_rounds": 1,
    "max_risk_discuss_rounds": 1,
    "max_recur_limit": 100,
    # Data vendor configuration
    # Category-level configuration (default for all tools in category)
    "data_vendors": {
        "core_stock_apis": "yfinance",       # Options: alpha_vantage, yfinance
        "technical_indicators": "yfinance",  # Options: alpha_vantage, yfinance
        "fundamental_data": "yfinance",      # Options: alpha_vantage, yfinance
        "news_data": "yfinance",             # Options: alpha_vantage, yfinance
    },
    # Tool-level configuration (takes precedence over category-level)
    "tool_vendors": {
        # Example: "get_stock_data": "alpha_vantage",  # Override category default
    },
}

# Initialize with custom config
ta = TradingAgentsGraph(debug=True, config=config)

symbols = ["AAPL", "MSFT", "GOOGL", "AMZN", "TSLA", "NVDA", "META", "F", "KO", "MCD"]
trade_date = date.today().isoformat()

decisions = {}
# forward propagate
for symbol in symbols:
    _, decision = ta.propagate(symbol.upper(), trade_date)
    decisions[symbol] = decision
    print(f"Decision for {symbol} = {decision}")  # print the decision (decision)

table = PrettyTable()
table.field_names = ["Symbol", "Decision"]

for symbol, decision in decisions.items():
    table.add_row([symbol, decision])

print(f"Today's Trading Decisions ({trade_date}):")
print(table)
# Memorize mistakes and reflect
# ta.reflect_and_remember(1000) # parameter is the position returns
