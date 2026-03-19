from typing import Dict

from typing_extensions import Literal, TypedDict


PositionSide = Literal["long", "short"]


class PositionConfig(TypedDict):
    open: bool
    stop_loss: float | None
    take_profit: float | None
    side: PositionSide


PositionMap = Dict[str, PositionConfig]
