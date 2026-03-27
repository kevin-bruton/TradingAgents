"""Plot a cumulative P&L equity curve from trade CSV files.

Reads the per-symbol CSV (``trades_{SYMBOL}.csv``) when ``--symbol`` is
supplied, or the combined ``trades_all.csv`` otherwise.  Only fills that
carry a realized P&L (i.e. closing fills) contribute to the curve.

Usage:
    uv run broker/plot_equity.py                      # all trades
    uv run broker/plot_equity.py --symbol NVDA        # single symbol
    uv run broker/plot_equity.py --trades-dir path/to/trades --symbol TSLA
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import pandas as pd
import plotly.graph_objects as go
import typer
from rich.console import Console

# Ensure project root is on sys.path when run directly
sys.path.insert(0, str(Path(__file__).parent.parent))

app = typer.Typer(add_completion=False)
console = Console()


@app.command()
def main(
    symbol: Optional[str] = typer.Option(
        None,
        "--symbol",
        help="Ticker symbol to plot (e.g. NVDA). Omit to plot all trades.",
        metavar="SYMBOL",
    ),
    trades_dir: Path = typer.Option(
        Path("trades"),
        "--trades-dir",
        help="Directory containing the trades CSV files.",
        show_default=True,
    ),
) -> None:
    """Render a cumulative P&L equity curve from the trades CSV files."""

    # ------------------------------------------------------------------
    # 1. Locate and load CSV
    # ------------------------------------------------------------------
    if symbol:
        symbol = symbol.upper()
        csv_path = trades_dir / f"trades_{symbol}.csv"
        title = f"Equity Curve — {symbol}"
    else:
        csv_path = trades_dir / "trades_all.csv"
        title = "Equity Curve — All Trades"

    if not csv_path.exists():
        console.print(f"[red]Trades file not found:[/red] {csv_path}")
        raise typer.Exit(1)

    try:
        df = pd.read_csv(csv_path, parse_dates=["datetime"])
    except Exception as exc:
        console.print(f"[red]Could not read {csv_path}:[/red] {exc}")
        raise typer.Exit(1)

    # ------------------------------------------------------------------
    # 2. Filter to closing fills (rows with a realized P&L)
    # ------------------------------------------------------------------
    df = df[df["realized_pnl"].notna() & (df["realized_pnl"] != "")]
    if df.empty:
        console.print(
            "[yellow]No closing fills with a realized P&L found in[/yellow] "
            f"{csv_path}\n"
            "Run [bold]update_trades.py[/bold] after closing a position to populate the data."
        )
        raise typer.Exit(0)

    df["realized_pnl"] = pd.to_numeric(df["realized_pnl"], errors="coerce")
    df = df.dropna(subset=["realized_pnl"])
    df = df.sort_values("datetime").reset_index(drop=True)
    df["cumulative_pnl"] = df["realized_pnl"].cumsum()

    console.print(
        f"Plotting [bold]{len(df)}[/bold] closing fill(s) from [bold]{csv_path}[/bold]"
    )

    # ------------------------------------------------------------------
    # 3. Build Plotly figure
    # ------------------------------------------------------------------
    final_pnl = df["cumulative_pnl"].iloc[-1]
    line_color = "#26a69a" if final_pnl >= 0 else "#ef5350"
    fill_color = "rgba(38,166,154,0.2)" if final_pnl >= 0 else "rgba(239,83,80,0.2)"

    hover_text = [
        f"<b>{row['symbol']}</b><br>"
        f"Date: {row['datetime'].strftime('%Y-%m-%d %H:%M') if hasattr(row['datetime'], 'strftime') else row['datetime']}<br>"
        f"Action: {row['action']}<br>"
        f"Qty: {row['quantity']}<br>"
        f"Price: {row['price']:.4f}<br>"
        f"Trade P&L: {row['realized_pnl']:+.2f}<br>"
        f"<b>Cumulative P&L: {row['cumulative_pnl']:+.2f}</b>"
        for _, row in df.iterrows()
    ]

    fig = go.Figure()

    # Area fill to zero
    fig.add_trace(go.Scatter(
        x=df["datetime"],
        y=df["cumulative_pnl"],
        mode="lines+markers",
        line=dict(color=line_color, width=2),
        fill="tozeroy",
        fillcolor=fill_color,
        marker=dict(size=6, color=line_color),
        hovertemplate="%{customdata}<extra></extra>",
        customdata=hover_text,
        name="Cumulative P&L",
    ))

    # Zero baseline
    fig.add_hline(y=0, line=dict(color="#555555", width=1, dash="dash"))

    fig.update_layout(
        template="plotly_dark",
        title=dict(text=title, font=dict(size=18)),
        xaxis=dict(
            title="Date",
            showgrid=True,
            gridcolor="#1e2530",
            tickangle=-30,
        ),
        yaxis=dict(
            title="Cumulative P&L",
            showgrid=True,
            gridcolor="#1e2530",
            tickformat="+,.2f",
            zeroline=False,
        ),
        hovermode="x unified",
        plot_bgcolor="#0e1117",
        paper_bgcolor="#0e1117",
        margin=dict(l=60, r=40, t=70, b=60),
        annotations=[
            dict(
                x=df["datetime"].iloc[-1],
                y=final_pnl,
                text=f"  Final: {final_pnl:+,.2f}",
                showarrow=False,
                font=dict(color=line_color, size=12),
                xanchor="left",
            )
        ],
    )

    fig.show()


if __name__ == "__main__":
    app()
