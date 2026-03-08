import logging
import sys

from prettytable import PrettyTable
from datetime import date
import os
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.position_management import load_current_positions
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

def configure_progress_logger() -> logging.Logger:
    logger = logging.getLogger("backtest.progress")
    logger.setLevel(logging.INFO)
    logger.propagate = False

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.handlers.clear()
    logger.addHandler(handler)
    return logger

class ProgressTracker:
    def __init__(self, progress_logger: logging.Logger) -> None:
        self._logger = progress_logger
        self._started_agents: set[str] = set()

    def reset(self) -> None:
        self._started_agents.clear()

    def __call__(self, event: str, agent_name: str) -> None:
        if event != "start":
            return
        if agent_name in self._started_agents:
            return
        self._started_agents.add(agent_name)
        self._logger.info("Agent started: %s", agent_name)

logging.basicConfig(level=logging.ERROR, format="%(message)s")
progress_logger = configure_progress_logger()
progress_tracker = ProgressTracker(progress_logger)
ta = TradingAgentsGraph(debug=False, config=config, progress_callback=progress_tracker)

trade_date = date.today().isoformat()
positions_path = os.path.join(os.path.dirname(__file__), "current_positions.yaml")
try:
    current_positions = load_current_positions(positions_path)
except (FileNotFoundError, ValueError) as exc:
    raise SystemExit(str(exc)) from exc


def _format_level(level: float | None) -> str:
    return "null" if level is None else f"{level:.2f}"

decisions = {}
# forward propagate
for symbol in current_positions.keys():
    print(f"\nProcessing {symbol}...")
    current_position = current_positions.get(symbol.upper())
    _, decision = ta.propagate(
        symbol.upper(),
        trade_date,
        current_position=current_position,
    )
    decisions[symbol] = decision
    print(
        f"Decision for {symbol} = {decision['decision']} "
        f"(stop_loss={_format_level(decision['stop_loss'])}, "
        f"take_profit={_format_level(decision['take_profit'])}, "
        f"confidence_pct={decision['confidence_pct']:.2f})"
    )

table = PrettyTable()
table.field_names = ["Symbol", "Decision", "Stop Loss", "Take Profit", "Confidence %"]

for symbol, decision in decisions.items():
    table.add_row(
        [
            symbol,
            decision["decision"],
            _format_level(decision["stop_loss"]),
            _format_level(decision["take_profit"]),
            f"{decision['confidence_pct']:.2f}",
        ]
    )

print(f"Today's Trading Decisions ({trade_date}):")
print(table)
# Memorize mistakes and reflect
# ta.reflect_and_remember(1000) # parameter is the position returns
