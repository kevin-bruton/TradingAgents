from typing_extensions import Literal, TypedDict


TradeAction = Literal["BUY", "SELL", "SELL_SHORT", "BUY_TO_COVER", "MODIFY"]


class TradeDecision(TypedDict):
    decision: TradeAction
    stop_loss: float | None
    take_profit: float | None
    confidence_pct: float
    rationale: str
