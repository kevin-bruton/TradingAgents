"""Script 1: Sync current_positions.yaml with live IB portfolio state.

Usage:
    uv run broker/sync_positions.py [--positions-file PATH] [--dry-run] [--verbose]
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

import typer
import yaml
from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table

# Ensure project root is on sys.path when run directly
sys.path.insert(0, str(Path(__file__).parent.parent))

from tradingagents.position_management.loader import (
    load_current_positions,
    save_current_positions,
)
from tradingagents.position_management.schema import PositionConfig, PositionMap

from broker.ib_client import IBClient, IBOpenOrder, PortfolioPosition, create_ib_client_from_env

load_dotenv()

app = typer.Typer(add_completion=False)
console = Console()


@app.command()
def main(
    positions_file: Path = typer.Option(
        Path("current_positions.yaml"),
        "--positions-file",
        help="Path to current_positions.yaml.",
        show_default=True,
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Print planned changes; do not write to disk.",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        help="Show per-symbol reconciliation detail.",
    ),
) -> None:
    """Sync current_positions.yaml with live IB Gateway portfolio state."""
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )

    # ------------------------------------------------------------------
    # 1. Load current tracked positions
    # ------------------------------------------------------------------
    console.print(f"[bold]Loading positions from[/bold] {positions_file}")
    try:
        tracked = load_current_positions(positions_file)
    except (FileNotFoundError, ValueError) as exc:
        console.print(f"[red]Error loading positions file:[/red] {exc}")
        raise typer.Exit(1)

    # ------------------------------------------------------------------
    # 2. Connect to IB Gateway
    # ------------------------------------------------------------------
    ib_client = create_ib_client_from_env(client_id_env_var="IB_CLIENT_ID_SYNC")
    console.print(
        f"Connecting to IB Gateway at {os.getenv('IB_HOST','127.0.0.1')}:"
        f"{os.getenv('IB_PORT','4002')} (client_id={os.getenv('IB_CLIENT_ID_SYNC','1')})…"
    )
    try:
        ib_client.connect()
    except ConnectionError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1)

    try:
        ib_positions = ib_client.get_portfolio_positions()
        all_open_orders = ib_client.get_open_orders()
    finally:
        ib_client.disconnect()

    # ------------------------------------------------------------------
    # 3. Reconcile
    # ------------------------------------------------------------------
    reconciled: PositionMap = {}
    rows: list[dict] = []

    for symbol, current in tracked.items():
        was_open = current["open"]
        was_side = current["side"]
        was_stop = current["stop_loss"]
        was_tp = current["take_profit"]

        ib_pos = ib_positions.get(symbol)
        symbol_orders = [o for o in all_open_orders if o["symbol"] == symbol]

        if ib_pos is not None:
            # Position is open in IB
            new_side = ib_pos["side"]
            new_stop, new_tp = _extract_risk_levels(symbol, symbol_orders, was_stop)
            new_position: PositionConfig = {
                "open": True,
                "side": new_side,
                "stop_loss": new_stop,
                "take_profit": new_tp,
            }

            change = _describe_change(
                was_open, was_side, was_stop, was_tp,
                True, new_side, new_stop, new_tp,
            )
            rows.append(
                {"symbol": symbol, "was": _fmt_state(was_open, was_side, was_stop, was_tp),
                 "now": _fmt_state(True, new_side, new_stop, new_tp), "change": change}
            )
        else:
            # Not in IB portfolio
            if was_open:
                new_position = {
                    "open": False,
                    "side": was_side,
                    "stop_loss": None,
                    "take_profit": None,
                }
                change = "⚠ position closed in IB"
                console.print(
                    f"[yellow]WARNING[/yellow] [{symbol}] was open in YAML but has no position in IB. Marked closed."
                )
            else:
                new_position = current  # no change
                change = "no change"

            rows.append(
                {"symbol": symbol, "was": _fmt_state(was_open, was_side, was_stop, was_tp),
                 "now": _fmt_state(new_position["open"], new_position["side"],
                                   new_position["stop_loss"], new_position["take_profit"]),
                 "change": change}
            )

        reconciled[symbol] = new_position

    # Warn about IB positions not tracked in YAML
    for symbol in ib_positions:
        if symbol not in tracked:
            console.print(
                f"[yellow]WARNING[/yellow] [{symbol}] found in IB portfolio but not in positions file. "
                "Add it manually if you want TradingAgents to track it."
            )

    # ------------------------------------------------------------------
    # 4. Save (unless dry-run)
    # ------------------------------------------------------------------
    if dry_run:
        console.print("\n[bold yellow]DRY RUN — no changes written to disk.[/bold yellow]")
    else:
        try:
            save_current_positions(positions_file, reconciled)
            console.print(f"\n[green]Saved reconciled positions to[/green] {positions_file}")
        except ValueError as exc:
            console.print(f"[red]Error saving positions:[/red] {exc}")
            raise typer.Exit(1)

    # ------------------------------------------------------------------
    # 5. Summary table
    # ------------------------------------------------------------------
    table = Table(title="Position Sync Summary", show_lines=True)
    table.add_column("Symbol", style="bold cyan", no_wrap=True)
    table.add_column("Was")
    table.add_column("Now")
    table.add_column("Change")

    for row in sorted(rows, key=lambda r: r["symbol"]):
        table.add_row(row["symbol"], row["was"], row["now"], row["change"])

    console.print()
    console.print(table)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_risk_levels(
    symbol: str,
    orders: list[IBOpenOrder],
    existing_stop: float | None,
) -> tuple[float | None, float | None]:
    """Extract stop and TP from working orders.

    If no stop order is found for an open position, the *existing_stop* from the
    YAML is preserved (with a warning) because loader.py rejects open positions
    with stop_loss=null.
    """
    # IB uses several order types for stops; match all of them.
    # STPLMT (stop-limit) uses aux_price as the trigger; TRAIL also carries aux_price.
    _STOP_ORDER_TYPES = {"STP", "STPLMT", "TRAIL", "TRAILLMT"}
    stp_orders = [
        o for o in orders
        if o["order_type"] in _STOP_ORDER_TYPES and o["aux_price"] is not None
    ]
    lmt_orders = [o for o in orders if o["order_type"] == "LMT" and o["limit_price"] is not None]

    stop: float | None
    if len(stp_orders) == 0:
        if existing_stop is not None:
            console.print(
                f"[yellow]WARNING[/yellow] [{symbol}] No stop order found at IB. "
                f"Preserving existing stop_loss={existing_stop}. "
                "Consider adding a stop order in IB."
            )
        stop = existing_stop
    elif len(stp_orders) == 1:
        stop = stp_orders[0]["aux_price"]
    else:
        console.print(
            f"[yellow]WARNING[/yellow] [{symbol}] Multiple STP orders found; "
            "using the one with the highest aux_price (most conservative for long; "
            "for short, review manually)."
        )
        stop = max(o["aux_price"] for o in stp_orders)  # type: ignore[type-var]

    tp: float | None
    if len(lmt_orders) == 0:
        tp = None
    elif len(lmt_orders) == 1:
        tp = lmt_orders[0]["limit_price"]
    else:
        console.print(
            f"[yellow]WARNING[/yellow] [{symbol}] Multiple LMT orders found; "
            "using the one with the lowest limit_price."
        )
        tp = min(o["limit_price"] for o in lmt_orders)  # type: ignore[type-var]

    return stop, tp


def _fmt_state(
    is_open: bool, side: str, stop: float | None, tp: float | None
) -> str:
    if not is_open:
        return "closed"
    parts = [f"open {side}"]
    if stop is not None:
        parts.append(f"stop={stop}")
    if tp is not None:
        parts.append(f"tp={tp}")
    return " | ".join(parts)


def _describe_change(
    was_open: bool, was_side: str, was_stop: float | None, was_tp: float | None,
    now_open: bool, now_side: str, now_stop: float | None, now_tp: float | None,
) -> str:
    if was_open != now_open:
        return "⚠ position closed in IB" if was_open else "opened"
    if not now_open:
        return "no change"

    parts = []
    if was_side != now_side:
        parts.append(f"⚠ side {was_side}→{now_side}")
    if was_stop != now_stop:
        parts.append(f"stop {was_stop}→{now_stop}")
    if was_tp != now_tp:
        parts.append(f"tp {was_tp}→{now_tp}")
    if not parts:
        return "no change"
    return ", ".join(parts)


if __name__ == "__main__":
    app()
