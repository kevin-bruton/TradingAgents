from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.position_management import load_current_positions
from pathlib import Path

from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Create a custom config
config = DEFAULT_CONFIG.copy()
config["deep_think_llm"] = "gpt-5-mini"  # Use a different model
config["quick_think_llm"] = "gpt-5-mini"  # Use a different model
config["max_debate_rounds"] = 1  # Increase debate rounds

# Configure data vendors (default uses yfinance, no extra API keys needed)
config["data_vendors"] = {
    "core_stock_apis": "yfinance",           # Options: alpha_vantage, yfinance
    "technical_indicators": "yfinance",      # Options: alpha_vantage, yfinance
    "fundamental_data": "yfinance",          # Options: alpha_vantage, yfinance
    "news_data": "yfinance",                 # Options: alpha_vantage, yfinance
}

# Initialize with custom config
ta = TradingAgentsGraph(debug=True, config=config)


def _format_level(level: float | None) -> str:
    return "null" if level is None else f"{level:.2f}"


symbol = "NVDA"
positions_path = Path(__file__).resolve().parent / "current_positions.yaml"
try:
    current_positions = load_current_positions(positions_path)
except (FileNotFoundError, ValueError) as exc:
    raise SystemExit(str(exc)) from exc
current_position = current_positions.get(symbol)

# forward propagate
_, decision = ta.propagate(symbol, "2024-05-10", current_position=current_position)
print(f"Decision: {decision['decision']}")
print(f"Stop Loss: {_format_level(decision['stop_loss'])}")
print(f"Take Profit: {_format_level(decision['take_profit'])}")
print(f"Confidence %: {decision['confidence_pct']:.2f}")
print(f"Rationale: {decision['rationale']}")

# Memorize mistakes and reflect
# ta.reflect_and_remember(1000) # parameter is the position returns
