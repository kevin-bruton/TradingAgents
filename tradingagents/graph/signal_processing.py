import json
import re
from typing import Any

from tradingagents.position_management.decision_schema import TradeDecision

JSON_BLOCK_PATTERN = re.compile(
    r"```json\s*(.*?)\s*```",
    flags=re.IGNORECASE | re.DOTALL,
)
REQUIRED_DECISION_KEYS = {
    "decision",
    "stop_loss",
    "take_profit",
    "confidence_pct",
    "rationale",
}
VALID_DECISIONS = {"BUY", "SELL", "HOLD"}


class SignalProcessor:
    """Processes final trade outputs into deterministic structured decisions."""

    def __init__(self, quick_thinking_llm: Any = None):
        # Kept for backward compatibility with existing graph construction.
        self.quick_thinking_llm = quick_thinking_llm

    def process_signal(self, full_signal: str) -> TradeDecision:
        """Extract and validate exactly one structured decision JSON block."""
        decision_data = _extract_json_block(full_signal)
        return _validate_decision_payload(decision_data)


def _extract_json_block(full_signal: str) -> dict[str, Any]:
    if not isinstance(full_signal, str) or not full_signal.strip():
        raise ValueError(
            "Final trade decision output is empty; expected one fenced ```json``` block."
        )
    # Remove all content before the first '{' and after the last '}' to handle cases where the model omits fences but includes a JSON-like structure.
    full_signal = re.sub(r".*?\{", "{", full_signal, flags=re.DOTALL)
    full_signal = re.sub(r"\}.*", "}", full_signal, flags=re.DOTALL)
    full_signal = f"""```json
{full_signal}
```"""
    json_blocks = JSON_BLOCK_PATTERN.findall(full_signal)
    if not json_blocks:
        raise ValueError(
            "No fenced ```json``` block found in final trade decision output."
        )
    if len(json_blocks) > 1:
        raise ValueError(
            f"Expected exactly one fenced ```json``` block, found {len(json_blocks)}."
        )

    block = json_blocks[0].strip()
    try:
        parsed = json.loads(block)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON decision block: {exc.msg}") from exc

    if not isinstance(parsed, dict):
        raise ValueError("Structured decision JSON block must contain an object.")

    return parsed


def _validate_decision_payload(payload: dict[str, Any]) -> TradeDecision:
    missing_keys = sorted(REQUIRED_DECISION_KEYS.difference(payload.keys()))
    if missing_keys:
        missing = ", ".join(missing_keys)
        raise ValueError(f"Structured decision JSON is missing required keys: {missing}.")

    decision_raw = payload["decision"]
    if not isinstance(decision_raw, str):
        raise ValueError("Structured decision field 'decision' must be a string.")
    decision = decision_raw.strip().upper()
    if decision not in VALID_DECISIONS:
        raise ValueError(
            f"Structured decision field 'decision' must be one of {sorted(VALID_DECISIONS)}."
        )

    stop_loss = _parse_optional_number(payload["stop_loss"], "stop_loss")
    take_profit = _parse_optional_number(payload["take_profit"], "take_profit")
    confidence_pct = _parse_number(payload["confidence_pct"], "confidence_pct")
    if confidence_pct < 0 or confidence_pct > 100:
        raise ValueError(
            "Structured decision field 'confidence_pct' must be within [0, 100]."
        )

    rationale_raw = payload["rationale"]
    if not isinstance(rationale_raw, str):
        raise ValueError("Structured decision field 'rationale' must be a string.")
    rationale = rationale_raw.strip()
    if not rationale:
        raise ValueError("Structured decision field 'rationale' cannot be empty.")

    return {
        "decision": decision,
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "confidence_pct": confidence_pct,
        "rationale": rationale,
    }


def _parse_optional_number(value: Any, field_name: str) -> float | None:
    if value is None:
        return None
    return _parse_number(value, field_name)


def _parse_number(value: Any, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(
            f"Structured decision field '{field_name}' must be numeric or null."
            if field_name in {"stop_loss", "take_profit"}
            else f"Structured decision field '{field_name}' must be numeric."
        )
    return float(value)
