"""Maps TradeDecision dicts (from decision_table.yaml) + PositionConfig into
concrete IBOrderRequest parameter objects consumed by IBClient.
"""

from __future__ import annotations

import logging
from math import floor
from typing import Optional

from typing_extensions import Literal, TypedDict

from tradingagents.position_management.actions import (
    CLOSE_DECISIONS,
    MODIFY_DECISION,
    OPEN_DECISIONS,
    normalize_position_mode,
)
from tradingagents.position_management.decision_schema import TradeDecision
from tradingagents.position_management.schema import PositionConfig

from .ib_client import IBClient, IBOpenOrder

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public data contract
# ---------------------------------------------------------------------------

class IBOrderRequest(TypedDict):
    symbol: str
    action: Literal["BUY", "SELL"]
    quantity: Optional[float]       # None = use existing position size (close/modify)
    order_type: str                 # "MKT", "MOO", "STP", "LMT"
    stop_price: Optional[float]
    take_profit_price: Optional[float]
    is_bracket: bool
    market_on_open: bool            # True → MOO entry; False → MKT entry
    modify_order_id: Optional[int]  # set for MODIFY requests only
    cancel_order_ids: list[int]     # orders to cancel before placing new ones


# ---------------------------------------------------------------------------
# OrderMapper
# ---------------------------------------------------------------------------

class OrderMapper:
    """Translates a TradeDecision + position context into IBOrderRequest objects."""

    def __init__(self, position_mode: str) -> None:
        self._position_mode = normalize_position_mode(position_mode)

    def map(
        self,
        symbol: str,
        decision: TradeDecision,
        current_position: Optional[PositionConfig],
        open_orders: list[IBOpenOrder],
        *,
        market_open: bool,
        quantity: Optional[float] = None,
    ) -> list[IBOrderRequest]:
        """Return one or more IBOrderRequest objects for the given decision.

        Parameters
        ----------
        symbol:
            Ticker symbol (uppercase).
        decision:
            The TradeDecision dict (from decision_table.yaml).
        current_position:
            Current PositionConfig from current_positions.yaml, or None if unctracked.
        open_orders:
            Working IB orders for this symbol (from IBClient.get_open_orders_for_symbol).
        market_open:
            Whether the primary exchange is currently in its regular session.
        quantity:
            Pre-computed share quantity for opening orders (BUY / SELL_SHORT).
            Must be provided and >= 1 for opening decisions; ignored for others.
        """
        action = decision["decision"]
        stop_loss = decision["stop_loss"]
        take_profit = decision["take_profit"]

        if action in OPEN_DECISIONS:
            return self._map_open(
                symbol, action, quantity, stop_loss, take_profit, open_orders, market_open
            )
        if action in CLOSE_DECISIONS:
            return self._map_close(symbol, action, open_orders, market_open)
        if action == MODIFY_DECISION:
            return self._map_modify(symbol, stop_loss, take_profit, open_orders)

        raise ValueError(f"Unsupported decision action '{action}'.")

    # ------------------------------------------------------------------
    # Private mapping helpers
    # ------------------------------------------------------------------

    def _map_open(
        self,
        symbol: str,
        action: str,
        quantity: Optional[float],
        stop_loss: Optional[float],
        take_profit: Optional[float],
        open_orders: list[IBOpenOrder],
        market_open: bool,
    ) -> list[IBOrderRequest]:
        """BUY / SELL_SHORT → bracket entry + cancel any stale risk orders.

        Always uses MKT order type regardless of market hours.  A MKT/DAY order
        submitted pre-market is held in the IB queue and fills at or near the
        opening print — functionally the same as MOO.  MOO order type is
        intentionally avoided here because IB does not support bracket children
        (stop-loss / take-profit linked via parentId) on a MOO parent order.
        """
        if quantity is None or quantity < 1:
            raise ValueError(
                f"Cannot open position for '{symbol}': quantity must be >= 1 "
                f"(got {quantity}). Check CAPITAL_PER_POSITION and last price."
            )

        # IB action: BUY → "BUY"; SELL_SHORT → "SELL"
        ib_action: Literal["BUY", "SELL"] = "BUY" if action == "BUY" else "SELL"

        cancel_ids = _collect_risk_order_ids(open_orders)

        return [
            IBOrderRequest(
                symbol=symbol,
                action=ib_action,
                quantity=float(quantity),
                order_type="MKT",
                stop_price=stop_loss,
                take_profit_price=take_profit,
                is_bracket=True,
                market_on_open=False,
                modify_order_id=None,
                cancel_order_ids=cancel_ids,
            )
        ]

    def _map_close(
        self,
        symbol: str,
        action: str,
        open_orders: list[IBOpenOrder],
        market_open: bool,
    ) -> list[IBOrderRequest]:
        """SELL / BUY_TO_COVER → cancel risk orders then close with a MKT order.

        Always uses MKT.  A pre-market MKT/DAY order is held and fills at the
        open; during-market it fills immediately.
        """
        # IB action: SELL → "SELL"; BUY_TO_COVER → "BUY"
        ib_action: Literal["BUY", "SELL"] = "SELL" if action == "SELL" else "BUY"

        cancel_ids = _collect_risk_order_ids(open_orders)

        return [
            IBOrderRequest(
                symbol=symbol,
                action=ib_action,
                quantity=None,   # place_orders.py resolves from IB portfolio
                order_type="MKT",
                stop_price=None,
                take_profit_price=None,
                is_bracket=False,
                market_on_open=False,
                modify_order_id=None,
                cancel_order_ids=cancel_ids,
            )
        ]

    def _map_modify(
        self,
        symbol: str,
        stop_loss: Optional[float],
        take_profit: Optional[float],
        open_orders: list[IBOpenOrder],
    ) -> list[IBOrderRequest]:
        """MODIFY → cancel existing STP/LMT orders and recreate with updated levels.

        Uses cancel-then-create rather than in-place modification so that the
        operation succeeds even when the existing order belongs to a previous API
        session.  The old order is cancelled first (via cancel_order_ids) and a
        fresh standalone GTC order is placed at the new price level.

        If no existing order is found the new order is created without a
        preceding cancellation (place_orders.py resolves action/quantity from the
        live IB portfolio in that case).
        """
        requests: list[IBOrderRequest] = []

        existing_stop = next(
            (o for o in open_orders if o["order_type"] == "STP"), None
        )
        existing_tp = next(
            (o for o in open_orders if o["order_type"] == "LMT"), None
        )

        # --- stop-loss ---
        if stop_loss is not None:
            if existing_stop is not None:
                # Cancel old stop and place a fresh GTC stop at the new level.
                requests.append(
                    IBOrderRequest(
                        symbol=symbol,
                        action=existing_stop["action"],
                        quantity=existing_stop["quantity"],
                        order_type="STP",
                        stop_price=stop_loss,
                        take_profit_price=None,
                        is_bracket=False,
                        market_on_open=False,
                        modify_order_id=None,
                        cancel_order_ids=[existing_stop["order_id"]],
                    )
                )
            else:
                logger.warning(
                    "MODIFY for %s: no existing STP order found; will create a new standalone GTC stop.",
                    symbol,
                )
                requests.append(
                    IBOrderRequest(
                        symbol=symbol,
                        action="SELL",      # default; place_orders.py adjusts for shorts
                        quantity=None,      # place_orders.py fills from IB portfolio
                        order_type="STP",
                        stop_price=stop_loss,
                        take_profit_price=None,
                        is_bracket=False,
                        market_on_open=False,
                        modify_order_id=None,
                        cancel_order_ids=[],
                    )
                )

        # --- take-profit ---
        if take_profit is not None:
            if existing_tp is not None:
                # Cancel old limit and place a fresh GTC limit at the new level.
                requests.append(
                    IBOrderRequest(
                        symbol=symbol,
                        action=existing_tp["action"],
                        quantity=existing_tp["quantity"],
                        order_type="LMT",
                        stop_price=None,
                        take_profit_price=take_profit,
                        is_bracket=False,
                        market_on_open=False,
                        modify_order_id=None,
                        cancel_order_ids=[existing_tp["order_id"]],
                    )
                )
            else:
                logger.warning(
                    "MODIFY for %s: no existing LMT order found; will create a new standalone GTC limit.",
                    symbol,
                )
                requests.append(
                    IBOrderRequest(
                        symbol=symbol,
                        action="SELL",      # default; place_orders.py adjusts for shorts
                        quantity=None,
                        order_type="LMT",
                        stop_price=None,
                        take_profit_price=take_profit,
                        is_bracket=False,
                        market_on_open=False,
                        modify_order_id=None,
                        cancel_order_ids=[],
                    )
                )

        return requests


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _collect_risk_order_ids(open_orders: list[IBOpenOrder]) -> list[int]:
    """Return order IDs for all STP and LMT orders (risk-management orders)."""
    return [
        o["order_id"]
        for o in open_orders
        if o["order_type"] in ("STP", "LMT")
    ]


def compute_quantity(capital_per_position: float, last_price: float) -> int:
    """Return floor(capital_per_position / last_price).

    Raises ValueError if the computed quantity is less than 1.
    """
    if last_price <= 0:
        raise ValueError(f"last_price must be positive (got {last_price}).")
    qty = floor(capital_per_position / last_price)
    if qty < 1:
        raise ValueError(
            f"Insufficient capital for ≥1 share: "
            f"CAPITAL_PER_POSITION={capital_per_position:.2f}, "
            f"last_price={last_price:.2f}."
        )
    return qty
