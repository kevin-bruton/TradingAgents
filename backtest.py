import argparse
import ast
import contextlib
import csv
import io
import json
import logging
import os
import sys
from datetime import date, datetime, timedelta
from typing import Any, Mapping, Set

import pandas as pd
from dotenv import load_dotenv
from pandas.tseries.holiday import (
    AbstractHolidayCalendar,
    GoodFriday,
    Holiday,
    USLaborDay,
    USMartinLutherKingJr,
    USMemorialDay,
    USPresidentsDay,
    USThanksgivingDay,
    nearest_workday,
)

from tradingagents.position_management import PositionConfig, TradeDecision

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


CSV_FIELDNAMES = [
    "date",
    "decision",
    "stop_loss",
    "take_profit",
    "confidence_pct",
    "position_status",
    "rationale",
]

VALID_DECISIONS = {"BUY", "SELL", "HOLD"}

POSITION_STATUS_OPEN = "OPEN"
POSITION_STATUS_CLOSED = "CLOSED"
POSITION_STATUS_CLOSED_SELL = "CLOSED_SELL"
POSITION_STATUS_CLOSED_STOP_LOSS = "CLOSED_STOP_LOSS"
POSITION_STATUS_CLOSED_TAKE_PROFIT = "CLOSED_TAKE_PROFIT"

CLOSED_POSITION_STATUSES = {
    POSITION_STATUS_CLOSED,
    POSITION_STATUS_CLOSED_SELL,
    POSITION_STATUS_CLOSED_STOP_LOSS,
    POSITION_STATUS_CLOSED_TAKE_PROFIT,
}


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
    expected_header = ",".join(CSV_FIELDNAMES)

    if not needs_header:
        with open(output_path, "r", encoding="utf-8", newline="") as existing_file:
            existing_header = existing_file.readline().strip()
        if existing_header != expected_header:
            raise SystemExit(
                "Output CSV has incompatible header. "
                f"Expected '{expected_header}', found '{existing_header}'."
            )

    csv_file = open(output_path, "a", newline="", encoding="utf-8")
    writer = csv.DictWriter(csv_file, fieldnames=CSV_FIELDNAMES)
    if needs_header:
        writer.writeheader()
        csv_file.flush()
    return writer, csv_file


def _closed_position() -> PositionConfig:
    return {"open": False, "stop_loss": None, "take_profit": None, "side": "long"}


def _clone_position(position: PositionConfig | None) -> PositionConfig:
    if not position:
        return _closed_position()
    return {
        "open": bool(position.get("open")),
        "stop_loss": position.get("stop_loss"),
        "take_profit": position.get("take_profit"),
        "side": "long",
    }


def _is_empty_value(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and not value.strip():
        return True
    if isinstance(value, Mapping):
        return False
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False
    return False


def _coerce_optional_float(value: Any, field_name: str) -> float | None:
    if _is_empty_value(value):
        return None
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be numeric or empty.")
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be numeric or empty.") from exc


def _coerce_required_float(value: Any, field_name: str) -> float:
    parsed = _coerce_optional_float(value, field_name)
    if parsed is None:
        raise ValueError(f"{field_name} must be numeric.")
    return parsed


def _normalize_decision_label(raw_decision: str) -> str:
    decision = raw_decision.strip().upper()
    if decision not in VALID_DECISIONS:
        raise ValueError(f"Decision must be one of {sorted(VALID_DECISIONS)}.")
    return decision


def _parse_decision_payload(raw_decision: Any) -> Mapping[str, Any] | None:
    if isinstance(raw_decision, Mapping):
        return raw_decision
    if not isinstance(raw_decision, str):
        return None

    candidate = raw_decision.strip()
    if not candidate.startswith("{") or not candidate.endswith("}"):
        return None

    try:
        parsed = ast.literal_eval(candidate)
    except (SyntaxError, ValueError):
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError as exc:
            raise ValueError("Decision payload literal could not be parsed.") from exc
    if not isinstance(parsed, dict):
        raise ValueError("Decision payload literal must parse into a mapping.")
    return parsed


def _extract_decision_label(raw_decision: Any) -> str:
    payload = _parse_decision_payload(raw_decision)
    if payload is not None:
        if "decision" not in payload:
            raise ValueError("Decision payload is missing 'decision'.")
        payload_decision = payload["decision"]
        if not isinstance(payload_decision, str):
            raise ValueError("Decision payload field 'decision' must be a string.")
        return _normalize_decision_label(payload_decision)

    if not isinstance(raw_decision, str):
        raise ValueError("Decision value must be a string.")
    return _normalize_decision_label(raw_decision)


def _read_optional_level(
    history_row: Mapping[str, Any],
    field_name: str,
    decision_payload: Mapping[str, Any] | None,
) -> float | None:
    row_value = history_row.get(field_name)
    if not _is_empty_value(row_value):
        return _coerce_optional_float(row_value, field_name)

    if decision_payload is None:
        return None
    if field_name not in decision_payload:
        return None
    return _coerce_optional_float(decision_payload[field_name], field_name)


def normalize_live_decision(raw_decision: Any) -> TradeDecision:
    payload = _parse_decision_payload(raw_decision)
    if payload is None:
        if not isinstance(raw_decision, Mapping):
            raise ValueError("Live decision must be a mapping.")
        payload = raw_decision

    if "decision" not in payload:
        raise ValueError("Live decision payload is missing 'decision'.")
    decision_raw = payload["decision"]
    if not isinstance(decision_raw, str):
        raise ValueError("Live decision field 'decision' must be a string.")
    decision = _normalize_decision_label(decision_raw)

    stop_loss = _coerce_optional_float(payload.get("stop_loss"), "stop_loss")
    take_profit = _coerce_optional_float(payload.get("take_profit"), "take_profit")
    confidence_pct = _coerce_required_float(payload.get("confidence_pct"), "confidence_pct")
    if confidence_pct < 0 or confidence_pct > 100:
        raise ValueError("confidence_pct must be within [0, 100].")

    rationale_raw = payload.get("rationale")
    if not isinstance(rationale_raw, str) or not rationale_raw.strip():
        raise ValueError("rationale must be a non-empty string.")

    return {
        "decision": decision,
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "confidence_pct": confidence_pct,
        "rationale": rationale_raw.strip(),
    }


def apply_decision_transition(
    current_position: PositionConfig,
    decision: TradeDecision,
) -> PositionConfig:
    decision_label = decision["decision"]
    if decision_label == "SELL":
        return _closed_position()

    if decision_label == "BUY":
        return {
            "open": True,
            "stop_loss": (
                decision["stop_loss"]
                if decision["stop_loss"] is not None
                else current_position.get("stop_loss")
            ),
            "take_profit": (
                decision["take_profit"]
                if decision["take_profit"] is not None
                else current_position.get("take_profit")
            ),
            "side": "long",
        }

    return _clone_position(current_position)


def apply_price_range_exits(
    current_position: PositionConfig,
    *,
    day_low: float,
    day_high: float,
) -> tuple[PositionConfig, str | None]:
    if day_low > day_high:
        raise ValueError(
            f"day_low ({day_low}) cannot be higher than day_high ({day_high})."
        )

    if not current_position.get("open"):
        return _clone_position(current_position), None

    stop_loss = current_position.get("stop_loss")
    if stop_loss is not None and day_low <= stop_loss:
        return _closed_position(), "STOP_LOSS_HIT"

    take_profit = current_position.get("take_profit")
    if take_profit is not None and day_high >= take_profit:
        return _closed_position(), "TAKE_PROFIT_HIT"

    return _clone_position(current_position), None


def simulate_position_day(
    current_position: PositionConfig,
    decision: TradeDecision,
    *,
    day_low: float,
    day_high: float,
) -> tuple[PositionConfig, str, str | None]:
    transitioned_position = apply_decision_transition(current_position, decision)
    if not transitioned_position.get("open"):
        if decision["decision"] == "SELL":
            return transitioned_position, POSITION_STATUS_CLOSED_SELL, None
        return transitioned_position, POSITION_STATUS_CLOSED, None

    final_position, trigger_reason = apply_price_range_exits(
        transitioned_position,
        day_low=day_low,
        day_high=day_high,
    )
    if trigger_reason == "STOP_LOSS_HIT":
        note = (
            "SYSTEM NOTE: Stop-loss was triggered by historical range check "
            f"(low={day_low:.2f}, high={day_high:.2f}); position closed."
        )
        return final_position, POSITION_STATUS_CLOSED_STOP_LOSS, note
    if trigger_reason == "TAKE_PROFIT_HIT":
        note = (
            "SYSTEM NOTE: Take-profit was triggered by historical range check "
            f"(low={day_low:.2f}, high={day_high:.2f}); position closed."
        )
        return final_position, POSITION_STATUS_CLOSED_TAKE_PROFIT, note

    return final_position, POSITION_STATUS_OPEN, None


def advance_position_from_history_row(
    current_position: PositionConfig,
    history_row: Mapping[str, Any],
) -> PositionConfig:
    decision_payload = _parse_decision_payload(history_row.get("decision"))
    decision_source = (
        decision_payload.get("decision")
        if decision_payload is not None and "decision" in decision_payload
        else history_row.get("decision")
    )
    decision_label = _extract_decision_label(decision_source)
    stop_loss = _read_optional_level(history_row, "stop_loss", decision_payload)
    take_profit = _read_optional_level(history_row, "take_profit", decision_payload)

    raw_status = history_row.get("position_status")
    if not _is_empty_value(raw_status):
        if not isinstance(raw_status, str):
            raise ValueError("position_status must be a string when present.")
        status = raw_status.strip().upper()
        if status == POSITION_STATUS_OPEN:
            return {
                "open": True,
                "stop_loss": stop_loss,
                "take_profit": take_profit,
                "side": "long",
            }
        if status in CLOSED_POSITION_STATUSES:
            return _closed_position()
        raise ValueError(f"Unsupported position_status value '{raw_status}'.")

    if decision_label == "BUY":
        return {
            "open": True,
            "stop_loss": (
                stop_loss
                if stop_loss is not None
                else current_position.get("stop_loss")
            ),
            "take_profit": (
                take_profit
                if take_profit is not None
                else current_position.get("take_profit")
            ),
            "side": "long",
        }
    if decision_label == "SELL":
        return _closed_position()
    return _clone_position(current_position)


def build_backtest_row(
    *,
    trade_date: date,
    decision: TradeDecision,
    position_status: str,
    lifecycle_note: str | None = None,
) -> dict[str, Any]:
    rationale = decision["rationale"]
    if lifecycle_note:
        rationale = f"{rationale}\n\n{lifecycle_note}" if rationale else lifecycle_note

    return {
        "date": trade_date.isoformat(),
        "decision": decision["decision"],
        "stop_loss": decision["stop_loss"],
        "take_profit": decision["take_profit"],
        "confidence_pct": decision["confidence_pct"],
        "position_status": position_status,
        "rationale": rationale,
    }


def _format_level(level: float | None) -> str:
    return "null" if level is None else f"{level:.2f}"


def load_backtest_history(backtest_file: str) -> pd.DataFrame:
    if not os.path.exists(backtest_file) or os.path.getsize(backtest_file) == 0:
        empty = pd.DataFrame(columns=CSV_FIELDNAMES)
        empty["date"] = pd.to_datetime(empty["date"])
        return empty

    history_df = pd.read_csv(backtest_file)
    history_df = history_df.rename(
        columns={
            "Date": "date",
            "Decision": "decision",
            "Stop_Loss": "stop_loss",
            "Take_Profit": "take_profit",
            "Confidence_Pct": "confidence_pct",
            "Position_Status": "position_status",
            "Rationale": "rationale",
        }
    )

    required_columns = {"date", "decision"}
    if not required_columns.issubset(history_df.columns):
        raise SystemExit(
            f"backtest_file must contain columns {sorted(required_columns)}: {backtest_file}"
        )

    for field_name in CSV_FIELDNAMES:
        if field_name not in history_df.columns:
            history_df[field_name] = None

    history_df = history_df[CSV_FIELDNAMES]
    history_df["date"] = pd.to_datetime(history_df["date"], errors="raise")
    return (
        history_df.sort_values(by="date")
        .drop_duplicates(subset=["date"], keep="last")
        .reset_index(drop=True)
    )


def load_daily_price_ranges(
    symbol: str,
    start_date: date,
    end_date: date,
) -> dict[date, tuple[float, float]]:
    import yfinance as yf

    download_end = end_date + timedelta(days=1)
    price_df = yf.download(
        symbol,
        start=start_date.isoformat(),
        end=download_end.isoformat(),
        progress=False,
        auto_adjust=False,
        multi_level_index=False,
    )

    if price_df.empty:
        raise SystemExit(
            f"No historical price data available for '{symbol}' between "
            f"{start_date.isoformat()} and {end_date.isoformat()}."
        )

    if isinstance(price_df.columns, pd.MultiIndex):
        price_df.columns = [column[0] for column in price_df.columns]

    if "Low" not in price_df.columns or "High" not in price_df.columns:
        raise SystemExit("Historical price data must include both 'Low' and 'High' columns.")

    if price_df.index.tz is not None:
        price_df.index = price_df.index.tz_localize(None)

    price_ranges: dict[date, tuple[float, float]] = {}
    for index_value, price_row in price_df.iterrows():
        trade_day = pd.Timestamp(index_value).date()
        day_low = _coerce_optional_float(price_row["Low"], "Low")
        day_high = _coerce_optional_float(price_row["High"], "High")
        if day_low is None or day_high is None:
            continue
        price_ranges[trade_day] = (day_low, day_high)

    return price_ranges


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
    daily_price_ranges = load_daily_price_ranges(
        args.ticker.upper(),
        args.start_date,
        args.end_date,
    )

    from tradingagents.graph.trading_graph import TradingAgentsGraph

    ta = TradingAgentsGraph(debug=args.debug, config=config, progress_callback=progress_tracker)
    
    symbol = args.ticker.upper()
    backtest_folder = "backtests"
    os.makedirs(backtest_folder, exist_ok=True)
    backtest_file = os.path.join(backtest_folder, f"{symbol}.csv")
    backtest_df = load_backtest_history(backtest_file)
    backtest_rows_by_date: dict[date, dict[str, Any]] = {
        pd.Timestamp(row["date"]).date(): row for row in backtest_df.to_dict("records")
    }
    simulated_position: PositionConfig = _closed_position()

    try:
        current_date = args.start_date
        while current_date <= args.end_date:
            iso_date = current_date.isoformat()
            existing_row = backtest_rows_by_date.get(current_date)
            if existing_row is not None:
                progress_logger.info("\nSkipping %s (already processed)", iso_date)
                try:
                    simulated_position = advance_position_from_history_row(
                        simulated_position,
                        existing_row,
                    )
                except ValueError as exc:
                    raise SystemExit(
                        f"Invalid backtest history row for {iso_date}: {exc}"
                    ) from exc
                current_date += timedelta(days=1)
                continue
            if is_weekend(current_date):
                progress_logger.info("\nSkipping %s (weekend)", iso_date)
            elif current_date in holidays:
                progress_logger.info("\nSkipping %s (US market holiday)", iso_date)
            else:
                if current_date not in daily_price_ranges:
                    raise SystemExit(
                        f"Missing historical price range for {symbol} on {iso_date}."
                    )
                day_low, day_high = daily_price_ranges[current_date]

                progress_logger.info(f"\nStarting to process {iso_date} at {datetime.now().strftime('%H:%M:%S')}...")
                progress_tracker.reset()
                with contextlib.redirect_stdout(io.StringIO()):
                    _, raw_decision = ta.propagate(
                        symbol,
                        iso_date,
                        current_position=simulated_position,
                    )

                try:
                    decision = normalize_live_decision(raw_decision)
                except ValueError as exc:
                    raise SystemExit(
                        f"Invalid structured decision for {symbol} on {iso_date}: {exc}"
                    ) from exc

                simulated_position, position_status, lifecycle_note = simulate_position_day(
                    simulated_position,
                    decision,
                    day_low=day_low,
                    day_high=day_high,
                )

                output_row = build_backtest_row(
                    trade_date=current_date,
                    decision=decision,
                    position_status=position_status,
                    lifecycle_note=lifecycle_note,
                )

                writer.writerow(output_row)
                csv_file.flush()

                backtest_row = dict(output_row)
                backtest_row["date"] = pd.Timestamp(current_date)
                backtest_rows_by_date[current_date] = backtest_row
                backtest_df = (
                    pd.DataFrame(backtest_rows_by_date.values())
                    .sort_values(by="date")
                    .reset_index(drop=True)
                )
                backtest_df.to_csv(backtest_file, index=False, date_format="%Y-%m-%d")

                print(
                    f"{iso_date}: Decision={decision['decision']} "
                    f"(status={position_status}, "
                    f"stop_loss={_format_level(decision['stop_loss'])}, "
                    f"take_profit={_format_level(decision['take_profit'])}, "
                    f"confidence_pct={decision['confidence_pct']:.2f})"
                )
            current_date += timedelta(days=1)
    finally:
        csv_file.close()


if __name__ == "__main__":
    main()
