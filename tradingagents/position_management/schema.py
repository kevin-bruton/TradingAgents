from typing import Dict

from typing_extensions import Literal, TypedDict


class PositionConfig(TypedDict):
    open: bool
    stop_loss: float | None
    take_profit: float | None
    side: Literal["long"]


PositionMap = Dict[str, PositionConfig]
