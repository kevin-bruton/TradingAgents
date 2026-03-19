from .actions import (
    POSITION_MODE_LONG_ONLY,
    format_allowed_decisions_for_mode,
    normalize_position_mode,
)
from .schema import PositionConfig


def _format_level(value: float | None) -> str:
    return "null" if value is None else str(value)


def format_position_context(
    current_position: PositionConfig | None,
    position_mode: str = POSITION_MODE_LONG_ONLY,
) -> str:
    """Format current-position data for agent prompts."""
    normalized_mode = normalize_position_mode(position_mode)
    allowed_decisions = format_allowed_decisions_for_mode(normalized_mode)

    if current_position is None:
        return (
            "Current position data was not provided.\n"
            "- Treat this as no open position.\n"
            f"- Allowed decisions for this run: {allowed_decisions}.\n"
            "- Do not invent existing stop_loss or take_profit levels."
        )

    is_open = current_position.get("open", False)
    side = current_position.get("side", "long")
    stop_loss = _format_level(current_position.get("stop_loss"))
    take_profit = _format_level(current_position.get("take_profit"))

    return (
        "Current position context:\n"
        f"- Position open: {'yes' if is_open else 'no'}\n"
        f"- Side: {side}\n"
        f"- Existing stop_loss: {stop_loss}\n"
        f"- Existing take_profit: {take_profit}\n"
        f"- Position mode: {normalized_mode}\n"
        f"- Allowed decisions for this run: {allowed_decisions}\n"
        "- Position is reviewed before each market open."
    )
