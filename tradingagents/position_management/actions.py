from typing import Any, cast

from typing_extensions import Literal

from .decision_schema import TradeDecision
from .schema import PositionConfig, PositionSide

PositionMode = Literal["long_only", "long_short"]

POSITION_MODE_LONG_ONLY: PositionMode = "long_only"
POSITION_MODE_LONG_SHORT: PositionMode = "long_short"

LONG_ONLY_DECISIONS = frozenset({"BUY", "SELL", "MODIFY"})
LONG_SHORT_DECISIONS = frozenset({"BUY", "SELL", "SELL_SHORT", "BUY_TO_COVER", "MODIFY"})
ALL_DECISIONS = frozenset(set(LONG_ONLY_DECISIONS).union(LONG_SHORT_DECISIONS))

OPEN_DECISIONS = frozenset({"BUY", "SELL_SHORT"})
CLOSE_DECISIONS = frozenset({"SELL", "BUY_TO_COVER"})
MODIFY_DECISION = "MODIFY"

_DECISION_ORDER = ("BUY", "SELL", "SELL_SHORT", "BUY_TO_COVER", "MODIFY")


def normalize_position_mode(mode: Any) -> PositionMode:
    if not isinstance(mode, str):
        raise ValueError(
            "position_mode must be a string: 'long_only' or 'long_short'."
        )
    normalized_mode = mode.strip().lower()
    if normalized_mode not in {POSITION_MODE_LONG_ONLY, POSITION_MODE_LONG_SHORT}:
        raise ValueError(
            "position_mode must be either 'long_only' or 'long_short'. "
            f"Found '{mode}'."
        )
    return cast(PositionMode, normalized_mode)


def allowed_decisions_for_mode(position_mode: PositionMode | str) -> set[str]:
    normalized_mode = normalize_position_mode(position_mode)
    if normalized_mode == POSITION_MODE_LONG_ONLY:
        return set(LONG_ONLY_DECISIONS)
    return set(LONG_SHORT_DECISIONS)


def format_allowed_decisions_for_mode(position_mode: PositionMode | str) -> str:
    allowed = allowed_decisions_for_mode(position_mode)
    ordered = [decision for decision in _DECISION_ORDER if decision in allowed]
    return "/".join(ordered)


def closed_position(side: PositionSide = "long") -> PositionConfig:
    return {"open": False, "stop_loss": None, "take_profit": None, "side": side}


def clone_position(position: PositionConfig | None) -> PositionConfig:
    if position is None:
        return closed_position()
    return {
        "open": bool(position.get("open")),
        "stop_loss": position.get("stop_loss"),
        "take_profit": position.get("take_profit"),
        "side": cast(PositionSide, position.get("side", "long")),
    }


def validate_position_for_mode(
    current_position: PositionConfig | None,
    position_mode: PositionMode | str,
) -> None:
    normalized_mode = normalize_position_mode(position_mode)
    position = clone_position(current_position)
    if not position["open"]:
        return

    if position["stop_loss"] is None:
        raise ValueError("Open positions must include a numeric stop_loss.")

    if normalized_mode == POSITION_MODE_LONG_ONLY and position["side"] != "long":
        raise ValueError(
            "Open short positions are not allowed when position_mode is 'long_only'."
        )


def validate_decision_for_position(
    decision: TradeDecision,
    current_position: PositionConfig | None,
    position_mode: PositionMode | str,
) -> None:
    normalized_mode = normalize_position_mode(position_mode)
    allowed_decisions = allowed_decisions_for_mode(normalized_mode)
    decision_label = decision["decision"]
    stop_loss = decision["stop_loss"]
    take_profit = decision["take_profit"]

    if decision_label not in allowed_decisions:
        raise ValueError(
            f"Decision '{decision_label}' is not allowed for position_mode "
            f"'{normalized_mode}'. Allowed decisions: {sorted(allowed_decisions)}."
        )

    position = clone_position(current_position)
    validate_position_for_mode(position, normalized_mode)

    if not position["open"]:
        if decision_label in CLOSE_DECISIONS:
            raise ValueError(
                f"Decision '{decision_label}' requires an open position, but no position is open."
            )
        if decision_label == MODIFY_DECISION:
            raise ValueError("Decision 'MODIFY' requires an open position.")
        _require_stop_for_opening(decision_label, stop_loss)
        return

    side = position["side"]
    if side == "long":
        if decision_label == "SELL":
            _require_null_risk_levels_for_close(decision_label, stop_loss, take_profit)
            return
        if decision_label == MODIFY_DECISION:
            _require_stop_after_modify(stop_loss, position["stop_loss"])
            return
        raise ValueError(
            f"Decision '{decision_label}' is invalid while a long position is open. "
            "Use SELL to close or MODIFY to adjust risk levels."
        )

    if side == "short":
        if decision_label == "BUY_TO_COVER":
            _require_null_risk_levels_for_close(decision_label, stop_loss, take_profit)
            return
        if decision_label == MODIFY_DECISION:
            _require_stop_after_modify(stop_loss, position["stop_loss"])
            return
        raise ValueError(
            f"Decision '{decision_label}' is invalid while a short position is open. "
            "Use BUY_TO_COVER to close or MODIFY to adjust risk levels."
        )

    raise ValueError(f"Unsupported position side '{side}'.")


def apply_decision_to_position(
    current_position: PositionConfig | None,
    decision: TradeDecision,
    *,
    position_mode: PositionMode | str,
) -> PositionConfig:
    validate_decision_for_position(decision, current_position, position_mode)
    position = clone_position(current_position)
    decision_label = decision["decision"]

    if decision_label == "BUY":
        return {
            "open": True,
            "stop_loss": float(decision["stop_loss"]),
            "take_profit": decision["take_profit"],
            "side": "long",
        }
    if decision_label == "SELL_SHORT":
        return {
            "open": True,
            "stop_loss": float(decision["stop_loss"]),
            "take_profit": decision["take_profit"],
            "side": "short",
        }
    if decision_label == "SELL":
        return closed_position("long")
    if decision_label == "BUY_TO_COVER":
        return closed_position("short")
    if decision_label == MODIFY_DECISION:
        if not position["open"]:
            raise ValueError("Decision 'MODIFY' requires an open position.")
        updated_stop = (
            decision["stop_loss"]
            if decision["stop_loss"] is not None
            else position["stop_loss"]
        )
        if updated_stop is None:
            raise ValueError(
                "Decision 'MODIFY' must leave the open position with a numeric stop_loss."
            )
        return {
            "open": True,
            "stop_loss": float(updated_stop),
            "take_profit": (
                decision["take_profit"]
                if decision["take_profit"] is not None
                else position["take_profit"]
            ),
            "side": position["side"],
        }

    raise ValueError(f"Unsupported decision '{decision_label}'.")


def _require_stop_for_opening(decision_label: str, stop_loss: float | None) -> None:
    if decision_label in OPEN_DECISIONS and stop_loss is None:
        raise ValueError(
            f"Decision '{decision_label}' must include a numeric stop_loss because it opens a position."
        )


def _require_stop_after_modify(
    proposed_stop: float | None,
    existing_stop: float | None,
) -> None:
    if proposed_stop is None and existing_stop is None:
        raise ValueError(
            "Decision 'MODIFY' must provide stop_loss when the current position has no stop_loss."
        )


def _require_null_risk_levels_for_close(
    decision_label: str,
    stop_loss: float | None,
    take_profit: float | None,
) -> None:
    if stop_loss is not None or take_profit is not None:
        raise ValueError(
            f"Decision '{decision_label}' must set stop_loss and take_profit to null when closing a position."
        )
