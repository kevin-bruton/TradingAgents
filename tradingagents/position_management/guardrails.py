from typing import cast

from .actions import CLOSE_DECISIONS
from .decision_schema import TradeDecision
from .schema import PositionConfig, PositionSide


def apply_trailing_stop_guardrail(
    decision: TradeDecision,
    current_position: PositionConfig | None,
    current_price: float | None = None,
) -> TradeDecision:
    """Clamp looser stop-loss updates for open positions."""
    adjusted_decision: TradeDecision = {
        "decision": decision["decision"],
        "stop_loss": decision["stop_loss"],
        "take_profit": decision["take_profit"],
        "confidence_pct": decision["confidence_pct"],
        "rationale": decision["rationale"],
    }

    if not _is_open_position(current_position):
        return adjusted_decision

    side = _normalize_side(current_position)
    existing_stop = current_position.get("stop_loss")

    if adjusted_decision["decision"] in CLOSE_DECISIONS:
        return adjusted_decision

    proposed_stop = adjusted_decision["stop_loss"]
    if proposed_stop is None and existing_stop is None:
        raise ValueError(
            "Structured decision must include numeric stop_loss for open positions."
        )

    if proposed_stop is None and existing_stop is not None:
        adjusted_decision["stop_loss"] = float(existing_stop)
        warning = (
            "SYSTEM WARNING: Proposed stop_loss was null while a position is open. "
            f"stop_loss was preserved at existing level {existing_stop}."
        )
        adjusted_decision["rationale"] = _append_warning(
            adjusted_decision["rationale"], warning
        )
        proposed_stop = adjusted_decision["stop_loss"]

    if existing_stop is None:
        return adjusted_decision

    if _is_looser_stop(proposed_stop, existing_stop, current_price, side):
        adjusted_decision["stop_loss"] = float(existing_stop)
        warning = (
            f"SYSTEM WARNING: Proposed stop_loss {proposed_stop} was looser than "
            f"the existing trailing stop {existing_stop} for the open {side} position. "
            "stop_loss was clamped to the existing level."
        )
        adjusted_decision["rationale"] = _append_warning(
            adjusted_decision["rationale"], warning
        )

    return adjusted_decision


def _is_open_position(current_position: PositionConfig | None) -> bool:
    if current_position is None:
        return False
    return bool(current_position.get("open"))


def _normalize_side(current_position: PositionConfig) -> PositionSide:
    side = str(current_position.get("side", "long")).strip().lower()
    if side not in {"long", "short"}:
        raise ValueError(f"Unsupported position side '{current_position.get('side')}'.")
    return cast(PositionSide, side)


def _is_looser_stop(
    proposed_stop: float,
    existing_stop: float,
    current_price: float | None,
    side: PositionSide,
) -> bool:
    if current_price is None:
        if side == "long":
            return proposed_stop < existing_stop
        return proposed_stop > existing_stop

    if current_price <= 0:
        raise ValueError("current_price must be positive when applying trailing-stop guardrail.")

    if side == "long":
        proposed_distance = (current_price - proposed_stop) / current_price
        existing_distance = (current_price - existing_stop) / current_price
    else:
        proposed_distance = (proposed_stop - current_price) / current_price
        existing_distance = (existing_stop - current_price) / current_price

    return proposed_distance > existing_distance


def _append_warning(rationale: str, warning: str) -> str:
    cleaned_rationale = rationale.strip()
    if not cleaned_rationale:
        return warning
    return f"{cleaned_rationale}\n\n{warning}"
