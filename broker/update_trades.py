"""Script: Retrieve completed trades from IB and save them to CSV files.

One CSV is written per instrument (``trades_{SYMBOL}.csv``) plus a combined
file (``trades_all.csv``), all placed under *trades-dir*.  Re-running the
script is safe: trades already present in a CSV (matched by ``exec_id``) are
never duplicated.

Usage:
    uv run broker/update_trades.py [--trades-dir PATH] [--dry-run] [--verbose]
"""

from __future__ import annotations

import csv
import logging
import math
import os
import sys
from pathlib import Path

import typer
from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table

# Ensure project root is on sys.path when run directly
sys.path.insert(0, str(Path(__file__).parent.parent))

from broker.ib_client import CompletedTrade, create_ib_client_from_env

load_dotenv()

app = typer.Typer(add_completion=False)
console = Console()

_TRADE_CSV_FIELDS = [
    "exec_id",
    "symbol",
    "datetime",
    "action",
    "quantity",
    "price",
    "commission",
    "realized_pnl",
    "currency",
]


@app.command()
def main(
    trades_dir: Path = typer.Option(
        Path("trades"),
        "--trades-dir",
        help="Directory in which to write per-symbol and combined trades CSVs.",
        show_default=True,
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Fetch and display trades without writing any files.",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        help="Enable debug logging.",
    ),
) -> None:
    """Retrieve completed trades from IB Gateway and append new ones to CSV files."""
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )

    # ------------------------------------------------------------------
    # 1. Connect to IB Gateway and fetch completed trades
    # ------------------------------------------------------------------
    ib_client = create_ib_client_from_env(client_id_env_var="IB_CLIENT_ID_TRADES")
    console.print(
        f"Connecting to IB Gateway at {os.getenv('IB_HOST', '127.0.0.1')}:"
        f"{os.getenv('IB_PORT', '4002')} "
        f"(client_id={os.getenv('IB_CLIENT_ID_TRADES', '2')})…"
    )
    try:
        ib_client.connect()
    except ConnectionError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1)

    try:
        trades = ib_client.get_completed_trades()
    finally:
        ib_client.disconnect()

    console.print(f"Retrieved [bold]{len(trades)}[/bold] trade execution(s) from IB.")

    if not trades:
        console.print("[dim]Nothing to save.[/dim]")
        return

    # ------------------------------------------------------------------
    # 2. Save to CSV (unless dry-run)
    # ------------------------------------------------------------------
    if dry_run:
        console.print(
            f"\n[bold yellow]DRY RUN — {len(trades)} trade(s) retrieved but not written.[/bold yellow]"
        )
    else:
        new_counts = _save_completed_trades(trades, trades_dir, console)
        total_new = sum(new_counts.values())
        if total_new:
            console.print(
                f"\n[green]Saved {total_new} new trade execution(s) to[/green] {trades_dir}"
            )
        else:
            console.print(
                f"\n[dim]No new trades to record "
                f"({len(trades)} execution(s) already present in CSV).[/dim]"
            )

    # ------------------------------------------------------------------
    # 3. Summary table
    # ------------------------------------------------------------------
    table = Table(title="Completed Trades", show_lines=True)
    table.add_column("Symbol", style="bold cyan", no_wrap=True)
    table.add_column("Datetime")
    table.add_column("Action")
    table.add_column("Qty", justify="right")
    table.add_column("Price", justify="right")
    table.add_column("Commission", justify="right")
    table.add_column("Realized P&L", justify="right")
    table.add_column("Currency")

    for t in sorted(trades, key=lambda x: (x["symbol"], x["datetime"])):
        rpnl = t["realized_pnl"]
        rpnl_str = f"{rpnl:+.2f}" if rpnl is not None else ""
        rpnl_style = (
            "[green]" if rpnl is not None and rpnl > 0
            else "[red]" if rpnl is not None and rpnl < 0
            else ""
        )
        table.add_row(
            t["symbol"],
            t["datetime"],
            t["action"],
            str(t["quantity"]),
            f"{t['price']:.4f}",
            f"{t['commission']:.2f}",
            f"{rpnl_style}{rpnl_str}",
            t["currency"],
        )

    console.print()
    console.print(table)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _save_completed_trades(
    trades: list[CompletedTrade],
    trades_dir: Path,
    cons: Console,
) -> dict[str, int]:
    """Persist *trades* to per-symbol CSVs and a combined CSV under *trades_dir*.

    Existing files are read first to collect known ``exec_id`` values; only
    genuinely new trades are appended, making the function idempotent.

    Returns a mapping of filename → number of new rows written.
    """
    trades_dir.mkdir(parents=True, exist_ok=True)

    by_symbol: dict[str, list[CompletedTrade]] = {}
    for trade in trades:
        by_symbol.setdefault(trade["symbol"], []).append(trade)

    new_counts: dict[str, int] = {}

    for symbol, symbol_trades in by_symbol.items():
        csv_path = trades_dir / f"trades_{symbol}.csv"
        n = _append_new_trades(csv_path, symbol_trades, cons)
        if n:
            new_counts[csv_path.name] = n

    all_csv_path = trades_dir / "trades_all.csv"
    n_all = _append_new_trades(all_csv_path, trades, cons)
    if n_all:
        new_counts[all_csv_path.name] = n_all

    return new_counts


def _append_new_trades(
    csv_path: Path,
    trades: list[CompletedTrade],
    cons: Console,
) -> int:
    """Append trades whose ``exec_id`` is not already present in *csv_path*.

    Creates the file with a header row when it does not yet exist.
    Returns the number of rows written.
    """
    existing_exec_ids: set[str] = set()
    if csv_path.exists():
        try:
            with csv_path.open(newline="", encoding="utf-8") as fh:
                for row in csv.DictReader(fh):
                    if "exec_id" in row:
                        existing_exec_ids.add(row["exec_id"])
        except Exception as exc:
            cons.print(
                f"[yellow]WARNING[/yellow] Could not read {csv_path}: {exc}. "
                "File will be overwritten."
            )
            existing_exec_ids = set()

    new_trades = [t for t in trades if t["exec_id"] not in existing_exec_ids]
    if not new_trades:
        return 0

    write_header = not csv_path.exists() or csv_path.stat().st_size == 0
    with csv_path.open("a", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=_TRADE_CSV_FIELDS)
        if write_header:
            writer.writeheader()
        for trade in new_trades:
            writer.writerow({
                "exec_id": trade["exec_id"],
                "symbol": trade["symbol"],
                "datetime": trade["datetime"],
                "action": trade["action"],
                "quantity": trade["quantity"],
                "price": trade["price"],
                "commission": trade["commission"],
                "realized_pnl": "" if trade["realized_pnl"] is None else trade["realized_pnl"],
                "currency": trade["currency"],
            })

    return len(new_trades)


if __name__ == "__main__":
    app()
