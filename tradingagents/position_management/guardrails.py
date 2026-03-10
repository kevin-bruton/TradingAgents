from .decision_schema import TradeDecision
from .schema import PositionConfig


def apply_trailing_stop_guardrail(
    decision: TradeDecision,
    current_position: PositionConfig | None,
    current_price: float | None = None,
) -> TradeDecision:
    """Clamp looser stop-loss updates for open long positions."""
    adjusted_decision: TradeDecision = {
        "decision": decision["decision"],
        "stop_loss": decision["stop_loss"],
        "take_profit": decision["take_profit"],
        "confidence_pct": decision["confidence_pct"],
        "rationale": decision["rationale"],
    }

    if not _is_open_long_position(current_position):
        return adjusted_decision

    existing_stop = current_position.get("stop_loss")
    if existing_stop is None:
        return adjusted_decision

    if adjusted_decision["decision"] == "SELL":
        return adjusted_decision

    proposed_stop = adjusted_decision["stop_loss"]
    if proposed_stop is None:
        raise ValueError(
            "Structured decision must include numeric stop_loss for BUY/HOLD when "
            "a long position is open."
        )

    if _is_looser_stop(proposed_stop, existing_stop, current_price):
        adjusted_decision["stop_loss"] = float(existing_stop)
        warning = (
            f"SYSTEM WARNING: Proposed stop_loss {proposed_stop} was looser than "
            f"the existing trailing stop {existing_stop}. stop_loss was clamped "
            "to the existing level."
        )
        adjusted_decision["rationale"] = _append_warning(
            adjusted_decision["rationale"], warning
        )

    return adjusted_decision


def _is_open_long_position(current_position: PositionConfig | None) -> bool:
    if current_position is None:
        return False
    return bool(current_position.get("open")) and current_position.get("side", "long") == "long"


def _is_looser_stop(
    proposed_stop: float,
    existing_stop: float,
    current_price: float | None,
) -> bool:
    if current_price is None:
        return proposed_stop < existing_stop

    if current_price <= 0:
        raise ValueError("current_price must be positive when applying trailing-stop guardrail.")

    proposed_distance = (current_price - proposed_stop) / current_price
    existing_distance = (current_price - existing_stop) / current_price
    return proposed_distance > existing_distance


def _append_warning(rationale: str, warning: str) -> str:
    cleaned_rationale = rationale.strip()
    if not cleaned_rationale:
        return warning
    return f"{cleaned_rationale}\n\n{warning}"
