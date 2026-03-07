from pathlib import Path
from typing import Any, Literal

import yaml

from .schema import PositionConfig, PositionMap


def load_current_positions(path: str | Path) -> PositionMap:
    """Load and validate current position data from YAML."""
    positions_path = Path(path)
    if not positions_path.exists():
        raise FileNotFoundError(f"Current positions file not found: {positions_path}")
    if not positions_path.is_file():
        raise ValueError(f"Current positions path must be a file: {positions_path}")

    with positions_path.open("r", encoding="utf-8") as positions_file:
        try:
            raw_positions = yaml.safe_load(positions_file)
        except yaml.YAMLError as exc:
            raise ValueError(
                f"Invalid YAML in current positions file '{positions_path}': {exc}"
            ) from exc

    if raw_positions is None:
        return {}
    if not isinstance(raw_positions, dict):
        raise ValueError(
            "Current positions file must contain a top-level mapping of symbol to position."
        )

    normalized_positions: PositionMap = {}
    for raw_symbol, raw_position in raw_positions.items():
        if not isinstance(raw_symbol, str):
            raise ValueError(
                f"Position symbol keys must be strings. Found key {raw_symbol!r}."
            )

        symbol = raw_symbol.strip().upper()
        if not symbol:
            raise ValueError("Position symbol keys cannot be empty.")
        if symbol in normalized_positions:
            raise ValueError(f"Duplicate symbol after normalization: '{symbol}'.")

        normalized_positions[symbol] = _normalize_position(symbol, raw_position)

    return normalized_positions


def _normalize_position(symbol: str, raw_position: Any) -> PositionConfig:
    if not isinstance(raw_position, dict):
        raise ValueError(f"Position entry for '{symbol}' must be a mapping.")

    allowed_keys = {"open", "stop_loss", "take_profit", "side"}
    unknown_keys = [key for key in raw_position.keys() if key not in allowed_keys]
    if unknown_keys:
        formatted_unknown = ", ".join(repr(key) for key in unknown_keys)
        raise ValueError(
            f"Position entry for '{symbol}' contains unknown fields: {formatted_unknown}"
        )

    open_position = _require_bool(symbol, raw_position, "open")
    stop_loss = _require_price_or_none(symbol, raw_position, "stop_loss")
    take_profit = _require_price_or_none(symbol, raw_position, "take_profit")
    side = _normalize_side(symbol, raw_position.get("side", "long"))

    return {
        "open": open_position,
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "side": side,
    }


def _require_bool(symbol: str, raw_position: dict[str, Any], field_name: str) -> bool:
    if field_name not in raw_position:
        raise ValueError(f"Position entry for '{symbol}' is missing '{field_name}'.")

    value = raw_position[field_name]
    if not isinstance(value, bool):
        raise ValueError(
            f"Position field '{field_name}' for '{symbol}' must be a boolean."
        )
    return value


def _require_price_or_none(
    symbol: str, raw_position: dict[str, Any], field_name: str
) -> float | None:
    if field_name not in raw_position:
        raise ValueError(f"Position entry for '{symbol}' is missing '{field_name}'.")

    value = raw_position[field_name]
    if value is None:
        return None

    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(
            f"Position field '{field_name}' for '{symbol}' must be a number or null."
        )
    return float(value)


def _normalize_side(symbol: str, side_value: Any) -> Literal["long"]:
    if not isinstance(side_value, str):
        raise ValueError(f"Position field 'side' for '{symbol}' must be a string.")

    normalized_side = side_value.strip().lower()
    if normalized_side != "long":
        raise ValueError(
            f"Position field 'side' for '{symbol}' must be 'long'. Found '{side_value}'."
        )
    return "long"
