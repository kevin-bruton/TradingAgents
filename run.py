import questionary
from questionary import Choice, Style as QStyle
from rich import box
from rich.align import Align
from rich.panel import Panel
from rich.rule import Rule
from rich.text import Text
from broker.place_orders import place_orders
from broker.plot_equity import plot_equity
from broker.sync_positions import sync_positions
from broker.update_trades import update_trades
from console import console
from evaluation import evaluate_positions


MENU_STYLE = QStyle([
    ("qmark",       "fg:#22d3ee bold"),
    ("question",    "fg:#f8fafc bold"),
    ("answer",      "fg:#22d3ee bold"),
    ("pointer",     "fg:#22d3ee bold"),
    ("highlighted", "fg:#22d3ee bold"),
    ("selected",    "fg:#64748b"),
    ("instruction", "fg:#475569"),
    ("text",        "fg:#e2e8f0"),
    ("disabled",    "fg:#334155 italic"),
])

_QUIT = object()

CHOICES = [
    Choice("⚡  Update current positions",                          value=sync_positions),
    Choice("📊  Get trade recommendations",                        value=evaluate_positions),
    Choice("🚀  Place orders according to recommendations",          value=place_orders),
    Choice("🔄  Update trades",                                     value=update_trades),
    Choice("📈  Plot equity curve of live trades",                     value=plot_equity),
    Choice("✗   Quit",                                          value=_QUIT),
]


def print_header():
    title = Text(justify="center")
    title.append("\n")
    title.append("TRADING AGENTS", style="bold bright_cyan")
    title.append("\n\n")
    title.append("AI Agents Trading on Interactive Brokers", style="italic dim white")
    title.append("\n")

    console.print()
    console.print(
        Panel(
            Align.center(title),
            box=box.DOUBLE_EDGE,
            border_style="cyan",
            padding=(0, 8),
        )
    )
    console.print()


def main():
    print_header()
    while True:
        console.print(Rule(style="dim cyan"))
        console.print()
        response = questionary.select(
            "What would you like to do?",
            choices=CHOICES,
            style=MENU_STYLE,
        ).ask()
        console.print()

        if response is _QUIT:
            console.print(Rule("[dim cyan]goodbye[/dim cyan]", style="dim cyan"))
            console.print()
            break

        response()


if __name__ == "__main__":
    main()
