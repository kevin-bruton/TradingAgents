from datetime import datetime
import logging
import sys
from pathlib import Path

from prettytable import PrettyTable
from datetime import date
import os

import yaml
from cli.main import save_report_to_disk
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.position_management import (
    apply_decision_to_position,
    load_current_positions,
    normalize_position_mode,
    save_current_positions,
    validate_position_for_mode,
)
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
    # Position recommendation mode: "long_only" or "long_short"
    "position_mode": "long_short",
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
reports_root = Path(config["project_dir"]) / "reports" / trade_date
reports_root.mkdir(parents=True, exist_ok=True)

positions_path = os.path.join(os.path.dirname(__file__), "current_positions.yaml")
try:
    current_positions = load_current_positions(positions_path)
except (FileNotFoundError, ValueError) as exc:
    raise SystemExit(str(exc)) from exc
position_mode = normalize_position_mode(config.get("position_mode", "long_short"))
for symbol, current_position in current_positions.items():
    try:
        validate_position_for_mode(current_position, position_mode)
    except ValueError as exc:
        raise SystemExit(f"Invalid current position for '{symbol}': {exc}") from exc


def _format_level(level: float | None) -> str:
    return "null" if level is None else f"{level:.2f}"


def _build_parse_error_decision(error_message: str) -> dict[str, str | float | None]:
    return {
        "decision": "PARSE_ERROR",
        "stop_loss": None,
        "take_profit": None,
        "confidence_pct": 0.0,
        "rationale": error_message,
    }


def _is_structured_decision_parse_error(error: ValueError) -> bool:
    message = str(error).lower()
    markers = ("json", "structured decision", "final trade decision output")
    return any(marker in message for marker in markers)


decisions = {}
updated_positions = {}
# forward propagate
for symbol in current_positions.keys():
    symbol_key = symbol.upper()
    print(f"\nStarted processing {symbol_key} at {datetime.now().strftime('%H:%M:%S')}...")
    progress_tracker.reset()
    current_position = current_positions[symbol]
    previous_state = ta.curr_state
    report_structured_decision = None

    try:
        final_state, decision = ta.propagate(
            symbol_key,
            trade_date,
            current_position=current_position,
        )
        report_structured_decision = decision
    except ValueError as exc:
        if not _is_structured_decision_parse_error(exc):
            raise
        final_state = ta.curr_state
        has_new_state = final_state is not None and final_state is not previous_state
        has_final_report = bool(has_new_state and final_state.get("final_trade_decision"))
        if not has_final_report:
            raise

        print(
            f"Warning: structured decision parsing failed for {symbol_key}; "
            "saving raw reports for inspection."
        )
        print(f"Parse error: {exc}")
        decision = _build_parse_error_decision(str(exc))

    decisions[symbol_key] = decision
    if decision["decision"] == "PARSE_ERROR":
        updated_positions[symbol_key] = current_position
    else:
        updated_positions[symbol_key] = apply_decision_to_position(
            current_position,
            decision,
            position_mode=position_mode,
        )
    symbol_report_dir = reports_root / symbol_key
    save_report_to_disk(
        final_state,
        symbol_key,
        symbol_report_dir,
        structured_decision=report_structured_decision,
    )
    print(f"Saved reports to {symbol_report_dir}")
    print(
        f"Decision for {symbol_key} = {decision['decision']} "
        f"(stop_loss={_format_level(decision['stop_loss'])}, "
        f"take_profit={_format_level(decision['take_profit'])}, "
        f"confidence_pct={decision['confidence_pct']:.2f})"
    )

table = PrettyTable()
table.field_names = ["Symbol", "Decision", "Stop Loss", "Take Profit", "Confidence %"]
summary = {}
for symbol, decision in decisions.items():
    row = [
            symbol,
            decision["decision"],
            _format_level(decision["stop_loss"]),
            _format_level(decision["take_profit"]),
            f"{decision['confidence_pct']:.2f}",
        ]
    table.add_row(row)

table.sortby = "Symbol"

for symbol in sorted(decisions.keys()):
    summary[symbol] = {k: v for k, v in decisions[symbol].items() if k != "rationale"}

print(f"\nToday's Trading Decisions ({trade_date}):")
print(table)
with open(reports_root / "decision_table.yaml", "w") as f:
    yaml.dump(summary, f, indent=4, default_flow_style=False)

positions_output_path = Path(config["project_dir"]) / "current_positions.updated.yaml"
save_current_positions(positions_output_path, updated_positions)
print(f"Saved updated positions to {positions_output_path}")
# Memorize mistakes and reflect
# ta.reflect_and_remember(1000) # parameter is the position returns
