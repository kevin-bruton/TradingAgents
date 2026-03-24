"""Script 2: Execute trades from decision_table.yaml on Interactive Brokers.

Usage:
    uv run broker/place_orders.py [--decision-file PATH] [--positions-file PATH]
        [--position-mode long_short|long_only] [--dry-run] [--symbol SYMBOL ...]
        [--min-confidence FLOAT] [--verbose]
"""

from __future__ import annotations

import logging
import os
import sys
from datetime import date
from math import floor
from pathlib import Path
from typing import Optional

import typer
import yaml
from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table

# Ensure project root is on sys.path when run directly
sys.path.insert(0, str(Path(__file__).parent.parent))

from tradingagents.position_management.actions import (
    CLOSE_DECISIONS,
    MODIFY_DECISION,
    OPEN_DECISIONS,
    normalize_position_mode,
    validate_decision_for_position,
)
from tradingagents.position_management.decision_schema import TradeDecision
from tradingagents.position_management.loader import load_current_positions
from tradingagents.position_management.schema import PositionConfig, PositionMap

from broker.ib_client import IBClient, IBOpenOrder, create_ib_client_from_env
from broker.order_mapper import IBOrderRequest, OrderMapper, compute_quantity

load_dotenv()

app = typer.Typer(add_completion=False)
console = Console()

_FILL_TIMEOUT = float(os.getenv("IB_FILL_TIMEOUT", "30"))


def _find_latest_decision_file() -> Optional[Path]:
    """Return the most recently modified decision_table.yaml under reports/."""
    candidates = sorted(
        Path("reports").glob("*/decision_table.yaml"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return candidates[0] if candidates else None


@app.command()
def main(
    decision_file: Optional[Path] = typer.Option(
        None,
        "--decision-file",
        help="Path to decision_table.yaml. Defaults to the most recent reports/<date>/decision_table.yaml.",
    ),
    positions_file: Path = typer.Option(
        Path("current_positions.yaml"),
        "--positions-file",
        help="Path to current_positions.yaml.",
        show_default=True,
    ),
    position_mode: str = typer.Option(
        "long_short",
        "--position-mode",
        help="Position mode: long_short or long_only.",
        show_default=True,
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Map and validate orders; do not submit to IB.",
    ),
    symbol: Optional[list[str]] = typer.Option(
        None,
        "--symbol",
        help="Limit execution to these symbols (repeatable). Default: all.",
    ),
    min_confidence: float = typer.Option(
        0.0,
        "--min-confidence",
        help="Skip decisions below this confidence percentage.",
        show_default=True,
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        help="Show per-symbol order detail.",
    ),
) -> None:
    """Execute trades from decision_table.yaml on Interactive Brokers."""
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )

    capital_per_position = float(os.getenv("CAPITAL_PER_POSITION", "10000"))

    # ------------------------------------------------------------------
    # 1. Resolve decision file
    # ------------------------------------------------------------------
    if decision_file is None:
        decision_file = _find_latest_decision_file()
        if decision_file is None:
            console.print(
                "[red]No decision_table.yaml found under reports/. "
                "Run run.py first or pass --decision-file.[/red]"
            )
            raise typer.Exit(1)
    if not decision_file.exists():
        console.print(f"[red]Decision file not found:[/red] {decision_file}")
        raise typer.Exit(1)

    console.print(f"[bold]Decision file:[/bold] {decision_file}")

    # ------------------------------------------------------------------
    # 2. Load decisions and positions
    # ------------------------------------------------------------------
    with decision_file.open("r", encoding="utf-8") as fh:
        raw_decisions: dict = yaml.safe_load(fh) or {}

    decisions: dict[str, TradeDecision] = {}
    for sym, raw in raw_decisions.items():
        decisions[sym.upper()] = TradeDecision(
            decision=raw["decision"],
            stop_loss=raw.get("stop_loss"),
            take_profit=raw.get("take_profit"),
            confidence_pct=float(raw.get("confidence_pct", 0.0)),
            rationale="",  # rationale is stripped from decision_table.yaml
        )

    try:
        positions: PositionMap = load_current_positions(positions_file)
    except (FileNotFoundError, ValueError) as exc:
        console.print(f"[red]Error loading positions file:[/red] {exc}")
        raise typer.Exit(1)

    # ------------------------------------------------------------------
    # 3. Validate all decisions
    # ------------------------------------------------------------------
    mode = normalize_position_mode(position_mode)
    validation_errors: dict[str, str] = {}
    for sym, dec in decisions.items():
        current_pos = positions.get(sym)
        try:
            validate_decision_for_position(dec, current_pos, mode)
        except ValueError as exc:
            validation_errors[sym] = str(exc)

    if validation_errors:
        for sym, err in validation_errors.items():
            console.print(f"[red]Validation error[/red] [{sym}]: {err}")

    # ------------------------------------------------------------------
    # 4. Apply filters
    # ------------------------------------------------------------------
    allowed_symbols: set[str] = {s.upper() for s in symbol} if symbol else set(decisions.keys())

    filtered: dict[str, TradeDecision] = {}
    skip_reasons: dict[str, str] = {}

    for sym in sorted(decisions.keys()):
        dec = decisions[sym]
        if sym not in allowed_symbols:
            continue
        if sym in validation_errors:
            skip_reasons[sym] = f"validation error: {validation_errors[sym]}"
            continue
        if dec["confidence_pct"] < min_confidence:
            skip_reasons[sym] = f"below min-confidence ({dec['confidence_pct']:.1f} < {min_confidence:.1f})"
            continue
        filtered[sym] = dec

    # ------------------------------------------------------------------
    # 5. Connect to IB Gateway (skip in dry-run if no read data needed)
    # ------------------------------------------------------------------
    ib_client = create_ib_client_from_env(client_id_env_var="IB_CLIENT_ID_ORDERS")
    mapper = OrderMapper(position_mode)

    results: list[dict] = []

    if not filtered:
        console.print("[yellow]No symbols to process after filtering.[/yellow]")
    else:
        console.print(
            f"Connecting to IB Gateway at {os.getenv('IB_HOST','127.0.0.1')}:"
            f"{os.getenv('IB_PORT','4002')} (client_id={os.getenv('IB_CLIENT_ID_ORDERS','2')})…"
        )
        try:
            ib_client.connect()
        except ConnectionError as exc:
            console.print(f"[red]{exc}[/red]")
            raise typer.Exit(1)

        try:
            results = _process_symbols(
                filtered, positions, ib_client, mapper,
                capital_per_position, dry_run, verbose,
            )
        finally:
            ib_client.disconnect()

    # Collect skipped entries
    for sym, reason in skip_reasons.items():
        dec = decisions[sym]
        results.append({
            "symbol": sym,
            "decision": dec["decision"],
            "confidence": dec["confidence_pct"],
            "status": "⏭ skipped",
            "detail": reason,
        })

    # ------------------------------------------------------------------
    # 6. Print summary table
    # ------------------------------------------------------------------
    table = Table(title="Order Execution Summary", show_lines=True)
    table.add_column("Symbol", style="bold cyan", no_wrap=True)
    table.add_column("Decision")
    table.add_column("Confidence", justify="right")
    table.add_column("Status")
    table.add_column("Detail")

    for row in sorted(results, key=lambda r: r["symbol"]):
        table.add_row(
            row["symbol"],
            row["decision"],
            f"{row['confidence']:.1f}%",
            row["status"],
            row["detail"],
        )

    console.print()
    console.print(table)

    # ------------------------------------------------------------------
    # 7. Write results log
    # ------------------------------------------------------------------
    if not dry_run:
        today = date.today().isoformat()
        results_dir = Path("reports") / today
        results_dir.mkdir(parents=True, exist_ok=True)
        results_path = results_dir / "order_results.yaml"
        with results_path.open("w", encoding="utf-8") as fh:
            yaml.safe_dump(
                {r["symbol"]: {k: v for k, v in r.items() if k != "symbol"} for r in results},
                fh,
                default_flow_style=False,
                sort_keys=True,
            )
        console.print(f"\n[green]Results log written to[/green] {results_path}")


# ---------------------------------------------------------------------------
# Core execution loop
# ---------------------------------------------------------------------------

def _process_symbols(
    decisions: dict[str, TradeDecision],
    positions: PositionMap,
    ib_client: IBClient,
    mapper: OrderMapper,
    capital_per_position: float,
    dry_run: bool,
    verbose: bool,
) -> list[dict]:
    results = []

    ib_portfolio = ib_client.get_portfolio_positions()

    for sym in sorted(decisions.keys()):
        dec = decisions[sym]
        current_pos = positions.get(sym)
        action = dec["decision"]

        if verbose:
            console.print(f"\n[bold]Processing[/bold] {sym}: {action} ({dec['confidence_pct']:.1f}%)")

        try:
            result = _execute_symbol(
                sym, dec, current_pos, ib_portfolio, ib_client, mapper,
                capital_per_position, dry_run,
            )
        except Exception as exc:
            console.print(f"[red]ERROR[/red] [{sym}]: {exc}")
            result = {
                "symbol": sym,
                "decision": action,
                "confidence": dec["confidence_pct"],
                "status": "❌ error",
                "detail": str(exc),
            }

        results.append(result)

    return results


def _execute_symbol(
    symbol: str,
    dec: TradeDecision,
    current_pos: Optional[PositionConfig],
    ib_portfolio: dict,
    ib_client: IBClient,
    mapper: OrderMapper,
    capital_per_position: float,
    dry_run: bool,
) -> dict:
    action = dec["decision"]
    open_orders = ib_client.get_open_orders_for_symbol(symbol)
    market_open = ib_client.is_market_open(symbol)

    # For opening decisions: compute quantity
    quantity: Optional[int] = None
    last_price: Optional[float] = None
    if action in OPEN_DECISIONS:
        last_price = ib_client.get_last_price(symbol)
        quantity = compute_quantity(capital_per_position, last_price)
        console.print(
            f"  [{symbol}] last_price={last_price:.4f}, "
            f"capital={capital_per_position:.0f}, qty={quantity}"
        )

    # Build order requests
    order_requests = mapper.map(
        symbol, dec, current_pos, open_orders,
        market_open=market_open,
        quantity=quantity,
    )

    entry_type = "market open" if market_open else "market closed"
    detail_parts: list[str] = []

    if dry_run:
        for req in order_requests:
            detail_parts.append(_describe_request(req, action))
        return {
            "symbol": symbol,
            "decision": action,
            "confidence": dec["confidence_pct"],
            "status": "🔎 dry-run",
            "detail": "; ".join(detail_parts) if detail_parts else "no orders",
        }

    # --- execute ---
    for req in order_requests:
        # Cancel stale risk orders first
        for oid in req.get("cancel_order_ids", []):
            try:
                ib_client.cancel_order(oid)
            except Exception as exc:
                console.print(f"  [yellow]WARNING[/yellow] [{symbol}] cancel order {oid}: {exc}")

        # Modify existing order
        if req["modify_order_id"] is not None:
            _apply_modify(req, ib_client)
            detail_parts.append(_describe_request(req, action))
            continue

        # Resolve quantity for close/modify-create requests
        resolved_qty = req["quantity"]
        if resolved_qty is None:
            ib_pos = ib_portfolio.get(symbol)
            if ib_pos is None:
                raise ValueError(
                    f"[{symbol}] Decision is {action} but no open position found in IB. "
                    "Run sync_positions.py first."
                )
            resolved_qty = ib_pos["quantity"]

            # Adjust close-side action for shorts (MODIFY create-new case)
            if req["order_type"] in ("STP", "LMT") and req["modify_order_id"] is None:
                side = ib_pos["side"]
                req = dict(req)  # type: ignore[assignment]
                req["action"] = "BUY" if side == "short" else "SELL"

        # Execute the order
        trade = _place_request(req, symbol, resolved_qty, ib_client)

        if req["order_type"] in ("MKT",) and not req.get("is_bracket"):
            filled = ib_client._wait_for_fill(trade, _FILL_TIMEOUT)
            status_str = "✅ filled" if filled else "⏳ pending"
            fill_info = (
                f"Filled {resolved_qty:.0f} @ {trade.orderStatus.avgFillPrice:.2f}"
                if filled and trade.orderStatus.avgFillPrice
                else "pending fill"
            )
            detail_parts.append(f"{fill_info} ({entry_type})")
        elif req["order_type"] in ("MOO",) or (req.get("is_bracket") and not market_open):
            detail_parts.append(f"MOO {resolved_qty:.0f} shares @ open ({entry_type})")
            status_str = "🕐 queued"
        elif req.get("is_bracket") and market_open:
            filled = ib_client._wait_for_fill(trade, _FILL_TIMEOUT)
            status_str = "✅ filled" if filled else "⏳ pending"
            fill_info = (
                f"Filled {resolved_qty:.0f} @ {trade.orderStatus.avgFillPrice:.2f}"
                if filled and trade.orderStatus.avgFillPrice
                else "pending fill"
            )
            detail_parts.append(f"{fill_info} ({entry_type})")
        else:
            status_str = "✅ done"
            detail_parts.append(_describe_request(req, action))

    if not detail_parts:
        status_str = "✅ done"
        detail_parts = ["no changes needed"]

    return {
        "symbol": symbol,
        "decision": action,
        "confidence": dec["confidence_pct"],
        "status": status_str if "status_str" in dir() else "✅ done",
        "detail": "; ".join(detail_parts),
    }


# ---------------------------------------------------------------------------
# Order dispatch helpers
# ---------------------------------------------------------------------------

def _apply_modify(req: IBOrderRequest, ib_client: IBClient) -> None:
    """Apply a modify request to an existing stop or TP order."""
    order_id = req["modify_order_id"]
    if req["order_type"] == "STP" and req["stop_price"] is not None:
        ib_client.modify_stop_order(order_id, req["stop_price"])
    elif req["order_type"] == "LMT" and req["take_profit_price"] is not None:
        ib_client.modify_take_profit_order(order_id, req["take_profit_price"])
    else:
        raise ValueError(
            f"Modify request has no price to update (order_id={order_id}, type={req['order_type']})."
        )


def _place_request(req: IBOrderRequest, symbol: str, quantity: float, ib_client: IBClient):
    """Dispatch a non-modify IBOrderRequest to the appropriate IBClient method."""
    action = req["action"]
    order_type = req["order_type"]

    if req.get("is_bracket"):
        return ib_client.place_bracket_order(
            symbol, action, quantity,
            req["stop_price"], req["take_profit_price"],
            market_on_open=req["market_on_open"],
        )

    if order_type == "MKT":
        return ib_client.place_market_order(symbol, action, quantity)

    if order_type == "MOO":
        return ib_client.place_market_on_open_order(symbol, action, quantity)

    if order_type == "STP" and req["stop_price"] is not None:
        return ib_client.place_stop_order(symbol, action, quantity, req["stop_price"])

    if order_type == "LMT" and req["take_profit_price"] is not None:
        return ib_client.place_take_profit_order(symbol, action, quantity, req["take_profit_price"])

    raise ValueError(f"Cannot dispatch unrecognised request: order_type={order_type}, req={req}")


def _describe_request(req: IBOrderRequest, decision: str) -> str:
    """Build a human-readable summary of a single IBOrderRequest."""
    if req["modify_order_id"] is not None:
        if req["order_type"] == "STP":
            return f"stop → {req['stop_price']}"
        if req["order_type"] == "LMT":
            return f"tp → {req['take_profit_price']}"

    if req.get("is_bracket"):
        entry = "MOO" if req["market_on_open"] else "MKT"
        qty = req["quantity"]
        parts = [f"{entry} {qty:.0f}" if qty else entry]
        if req["stop_price"]:
            parts.append(f"stop={req['stop_price']}")
        if req["take_profit_price"]:
            parts.append(f"tp={req['take_profit_price']}")
        return " ".join(parts)

    entry = "MOO" if req["order_type"] == "MOO" else req["order_type"]
    qty = req["quantity"]
    return f"{entry} {qty:.0f}" if qty else entry


if __name__ == "__main__":
    app()
