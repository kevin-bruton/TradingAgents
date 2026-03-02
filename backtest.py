import argparse
import contextlib
import csv
import io
import logging
import os
import sys
from datetime import datetime, date, timedelta
from typing import Set

import pandas as pd
from pandas.tseries.holiday import (
    AbstractHolidayCalendar,
    Holiday,
    GoodFriday,
    USMartinLutherKingJr,
    USPresidentsDay,
    USMemorialDay,
    USLaborDay,
    USThanksgivingDay,
    nearest_workday,
)
from dotenv import load_dotenv

from tradingagents.graph.trading_graph import TradingAgentsGraph

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


class NYSEHolidayCalendar(AbstractHolidayCalendar):
    rules = [
        Holiday("NewYearsDay", month=1, day=1, observance=nearest_workday),
        USMartinLutherKingJr,
        USPresidentsDay,
        GoodFriday,
        USMemorialDay,
        Holiday(
            "JuneteenthNationalIndependenceDay",
            month=6,
            day=19,
            observance=nearest_workday,
        ),
        Holiday("IndependenceDay", month=7, day=4, observance=nearest_workday),
        USLaborDay,
        USThanksgivingDay,
        Holiday("ChristmasDay", month=12, day=25, observance=nearest_workday),
    ]


def parse_date(value: str) -> date:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"Invalid date '{value}'. Use YYYY-MM-DD."
        ) from exc


def get_us_market_holidays(start_date: date, end_date: date) -> Set[date]:
    calendar = NYSEHolidayCalendar()
    holidays = calendar.holidays(start=start_date, end=end_date)
    return {d.date() for d in pd.to_datetime(holidays)}


def is_weekend(trade_date: date) -> bool:
    return trade_date.weekday() >= 5


def resolve_output_path(
    output_path: str | None, ticker: str, start_date: date, end_date: date, results_dir: str
) -> str:
    if output_path:
        return output_path
    filename = f"backtest_{ticker}_{start_date.isoformat()}_{end_date.isoformat()}.csv"
    return os.path.join(results_dir, filename)


def ensure_csv_writer(output_path: str) -> tuple[csv.DictWriter, "io.TextIOWrapper"]:
    output_dir = os.path.dirname(output_path)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    file_exists = os.path.exists(output_path)
    needs_header = not file_exists or os.path.getsize(output_path) == 0

    csv_file = open(output_path, "a", newline="", encoding="utf-8")
    writer = csv.DictWriter(csv_file, fieldnames=["date", "decision"])
    if needs_header:
        writer.writeheader()
        csv_file.flush()
    return writer, csv_file


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


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run a TradingAgents backtest over a date range."
    )
    parser.add_argument("ticker", help="Ticker/company symbol (e.g., NVDA)")
    parser.add_argument("start_date", type=parse_date, help="Start date YYYY-MM-DD")
    parser.add_argument("end_date", type=parse_date, help="End date YYYY-MM-DD")
    parser.add_argument(
        "--output",
        "-o",
        help="Output CSV path (default: results/backtest_<ticker>_<start>_<end>.csv)",
    )
    parser.add_argument(
        "--debug", action="store_true", help="Enable debug mode for TradingAgentsGraph"
    )
    args = parser.parse_args()

    if args.start_date > args.end_date:
        raise SystemExit("start_date must be on or before end_date.")

    logging.basicConfig(level=logging.ERROR, format="%(message)s")
    progress_logger = configure_progress_logger()
    progress_tracker = ProgressTracker(progress_logger)

    load_dotenv()

    output_path = resolve_output_path(
        args.output, args.ticker.upper(), args.start_date, args.end_date, config["results_dir"]
    )

    holidays = get_us_market_holidays(args.start_date, args.end_date)
    writer, csv_file = ensure_csv_writer(output_path)

    ta = TradingAgentsGraph(
        debug=args.debug, config=config, progress_callback=progress_tracker
    )
    
    symbol = args.ticker.upper()
    backtest_folder = "backtests"
    os.makedirs(backtest_folder, exist_ok=True)
    backtest_file = os.path.join(backtest_folder, f"{symbol}.csv")
    if os.path.exists(backtest_file) and os.path.getsize(backtest_file) > 0:
        backtest_df = pd.read_csv(backtest_file)
        required_columns = {"Date", "Decision"}
        if not required_columns.issubset(backtest_df.columns):
            raise SystemExit(
                f"backtest_file must contain columns {sorted(required_columns)}: {backtest_file}"
            )
        backtest_df["Date"] = pd.to_datetime(backtest_df["Date"])
        backtest_df = backtest_df.sort_values(by="Date").reset_index(drop=True)
    else:
        backtest_df = pd.DataFrame(columns=["Date", "Decision"])
        backtest_df["Date"] = pd.to_datetime(backtest_df["Date"])

    try:
        current_date = args.start_date
        while current_date <= args.end_date:
            iso_date = current_date.isoformat()
            decision_date = pd.Timestamp(current_date)
            if backtest_df["Date"].eq(decision_date).any():
                progress_logger.info("\nSkipping %s (already processed)", iso_date)
                current_date += timedelta(days=1)
                continue
            if is_weekend(current_date):
                progress_logger.info("\nSkipping %s (weekend)", iso_date)
            elif current_date in holidays:
                progress_logger.info("\nSkipping %s (US market holiday)", iso_date)
            else:
                progress_logger.info(f"\nStarting to process {iso_date} at {datetime.now().strftime('%H:%M:%S')}...")
                progress_tracker.reset()
                with contextlib.redirect_stdout(io.StringIO()):
                    _, decision = ta.propagate(symbol, iso_date)
                writer.writerow({"date": iso_date, "decision": decision})
                csv_file.flush()
                if not backtest_df["Date"].eq(decision_date).any():
                    new_row = {"Date": decision_date, "Decision": decision}
                    backtest_df = pd.concat(
                        [backtest_df, pd.DataFrame([new_row])], ignore_index=True
                    )
                    backtest_df = backtest_df.sort_values(by="Date").reset_index(drop=True)
                    backtest_df.to_csv(
                        backtest_file, index=False, date_format="%Y-%m-%d"
                    )
                print(f"{iso_date}: Decision = {decision}")
            current_date += timedelta(days=1)
    finally:
        csv_file.close()


if __name__ == "__main__":
    main()
