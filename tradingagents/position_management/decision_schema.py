from typing_extensions import Literal, TypedDict


class TradeDecision(TypedDict):
    decision: Literal["BUY", "SELL", "HOLD"]
    stop_loss: float | None
    take_profit: float | None
    confidence_pct: float
    rationale: str
