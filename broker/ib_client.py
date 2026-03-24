"""Common IB Gateway interface built on ib_insync.

All IB-specific logic is encapsulated here so neither broker script
imports ib_insync directly.
"""

from __future__ import annotations

import logging
import math
import os
import time
from datetime import datetime
from typing import Optional

import pytz
from ib_insync import IB, LimitOrder, MarketOrder, Order, Stock, StopOrder
from typing_extensions import Literal, TypedDict

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public data contracts
# ---------------------------------------------------------------------------

class PortfolioPosition(TypedDict):
    symbol: str
    side: Literal["long", "short"]
    quantity: float          # positive
    avg_cost: float
    market_price: float
    unrealized_pnl: float


class IBOpenOrder(TypedDict):
    order_id: int
    symbol: str
    order_type: str          # "STP", "LMT", "MKT", "MOO", etc.
    action: str              # "BUY", "SELL"
    quantity: float
    aux_price: Optional[float]   # stop price
    limit_price: Optional[float]
    status: str              # "PreSubmitted", "Submitted", etc.


# ---------------------------------------------------------------------------
# IBClient
# ---------------------------------------------------------------------------

class IBClient:
    """Thin wrapper around ib_insync.IB providing typed portfolio and order methods."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 4002,
        client_id: int = 1,
        timeout: float = 20.0,
    ) -> None:
        self._host = host
        self._port = port
        self._client_id = client_id
        self._timeout = timeout
        self._ib = IB()

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    def connect(self) -> None:
        """Connect to IB Gateway / TWS."""
        try:
            self._ib.connect(
                self._host,
                self._port,
                clientId=self._client_id,
                timeout=self._timeout,
                readonly=False,
            )
        except ConnectionRefusedError as exc:
            raise ConnectionError(
                f"Could not connect to IB Gateway at {self._host}:{self._port}. "
                "Ensure IB Gateway or TWS is running and API connections are enabled. "
                f"Check IB_CLIENT_ID env var if you see a duplicate client-ID error."
            ) from exc
        except Exception as exc:
            raise ConnectionError(
                f"IB connection failed ({self._host}:{self._port}): {exc}"
            ) from exc

    def disconnect(self) -> None:
        """Disconnect from IB Gateway / TWS."""
        if self._ib.isConnected():
            self._ib.disconnect()

    # ------------------------------------------------------------------
    # Portfolio / account methods
    # ------------------------------------------------------------------

    def get_portfolio_positions(self) -> dict[str, PortfolioPosition]:
        """Return all open IB positions keyed by symbol."""
        result: dict[str, PortfolioPosition] = {}
        for item in self._ib.portfolio():
            symbol = item.contract.symbol
            qty = item.position
            if qty == 0:
                continue
            result[symbol] = PortfolioPosition(
                symbol=symbol,
                side="long" if qty > 0 else "short",
                quantity=abs(qty),
                avg_cost=item.averageCost,
                market_price=item.marketPrice,
                unrealized_pnl=item.unrealizedPNL,
            )
        return result

    def get_open_orders(self) -> list[IBOpenOrder]:
        """Return all working orders across all symbols and all client sessions.

        Uses reqAllOpenOrders() so that stop/TP orders placed manually in TWS
        (client_id=0) or from a different API session are included, not just
        orders placed by the current client ID.
        """
        self._ib.reqAllOpenOrders()
        self._ib.sleep(2)
        return [self._trade_to_open_order(trade) for trade in self._ib.openTrades()]

    def get_open_orders_for_symbol(self, symbol: str) -> list[IBOpenOrder]:
        """Return working orders for a single symbol."""
        return [o for o in self.get_open_orders() if o["symbol"] == symbol]

    def get_stop_and_take_profit_for_symbol(
        self, symbol: str
    ) -> tuple[Optional[float], Optional[float]]:
        """Extract (stop_price, take_profit_price) from working STP/LMT orders.

        Recognises all IB stop-order variants (STP, STPLMT, TRAIL, TRAILLMT) so
        that orders placed manually in TWS are detected correctly.
        When multiple orders of the same type are found, the most conservative
        (closest to current market price) is used and a warning is logged.
        Returns (None, None) if no relevant orders found.
        """
        _STOP_TYPES = {"STP", "STPLMT", "TRAIL", "TRAILLMT"}
        orders = self.get_open_orders_for_symbol(symbol)
        stop_prices = [
            o["aux_price"]
            for o in orders
            if o["order_type"] in _STOP_TYPES and o["aux_price"] is not None
        ]
        tp_prices = [
            o["limit_price"]
            for o in orders
            if o["order_type"] == "LMT" and o["limit_price"] is not None
        ]

        stop_price: Optional[float] = None
        tp_price: Optional[float] = None

        if len(stop_prices) == 1:
            stop_price = stop_prices[0]
        elif len(stop_prices) > 1:
            logger.warning(
                "Multiple STP orders found for %s; using most conservative (closest to current price).",
                symbol,
            )
            try:
                last = self.get_last_price(symbol)
                stop_price = min(stop_prices, key=lambda p: abs(p - last))
            except Exception:
                stop_price = stop_prices[0]

        if len(tp_prices) == 1:
            tp_price = tp_prices[0]
        elif len(tp_prices) > 1:
            logger.warning(
                "Multiple LMT orders found for %s; using most conservative (closest to current price).",
                symbol,
            )
            try:
                last = self.get_last_price(symbol)
                tp_price = min(tp_prices, key=lambda p: abs(p - last))
            except Exception:
                tp_price = tp_prices[0]

        return (stop_price, tp_price)

    def get_last_price(self, symbol: str) -> float:
        """Return the last traded price for *symbol* via a market-data snapshot."""
        contract = self._qualify_contract(symbol)
        ticker = self._ib.reqMktData(contract, "", True, False)
        self._ib.sleep(2)
        self._ib.cancelMktData(contract)

        for candidate in (ticker.last, ticker.close, ticker.bid, ticker.ask):
            if candidate is not None and not math.isnan(candidate) and candidate > 0:
                return float(candidate)

        raise ValueError(f"Could not retrieve last price for '{symbol}'.")

    def is_market_open(self, symbol: str) -> bool:
        """Return True if the symbol's primary exchange is in its regular trading session."""
        contract = self._qualify_contract(symbol)
        details_list = self._ib.reqContractDetails(contract)
        if not details_list:
            logger.warning("No contract details returned for %s; assuming market closed.", symbol)
            return False
        details = details_list[0]
        return _is_currently_in_session(details.liquidHours, details.timeZoneId)

    # ------------------------------------------------------------------
    # Order placement methods
    # ------------------------------------------------------------------

    def place_market_order(self, symbol: str, action: str, quantity: float):
        """Place a market order. Only call when the market is open."""
        contract = self._qualify_contract(symbol)
        order = MarketOrder(action, quantity)
        trade = self._ib.placeOrder(contract, order)
        self._log_order(f"MKT_{action}", symbol, order)
        return trade

    def place_market_on_open_order(self, symbol: str, action: str, quantity: float):
        """Place a Market-on-Open order that executes at the next regular-session open."""
        contract = self._qualify_contract(symbol)
        order = Order(action=action, orderType="MOO", totalQuantity=quantity)
        trade = self._ib.placeOrder(contract, order)
        self._log_order(f"MOO_{action}", symbol, order)
        return trade

    def place_stop_order(
        self, symbol: str, action: str, quantity: float, stop_price: float
    ):
        """Place a GTC stop-loss order."""
        contract = self._qualify_contract(symbol)
        order = StopOrder(action, quantity, stop_price, tif="GTC")
        trade = self._ib.placeOrder(contract, order)
        self._log_order(f"STP_{action}", symbol, order)
        return trade

    def place_take_profit_order(
        self, symbol: str, action: str, quantity: float, limit_price: float
    ):
        """Place a GTC take-profit limit order."""
        contract = self._qualify_contract(symbol)
        order = LimitOrder(action, quantity, limit_price, tif="GTC")
        trade = self._ib.placeOrder(contract, order)
        self._log_order(f"LMT_{action}", symbol, order)
        return trade

    def place_bracket_order(
        self,
        symbol: str,
        action: str,
        quantity: float,
        stop_price: Optional[float],
        take_profit_price: Optional[float],
        market_on_open: bool = False,
    ):
        """Place entry (MKT or MOO) + optional stop + optional take-profit as an OCA group.

        Child orders are linked to the parent via parentId and remain dormant
        until the parent fills, so this is safe to submit before market open.
        Returns the parent Trade object.
        """
        contract = self._qualify_contract(symbol)
        reverse_action = "SELL" if action == "BUY" else "BUY"
        has_stop = stop_price is not None
        has_tp = take_profit_price is not None

        # --- parent entry order ---
        if market_on_open:
            parent = Order(action=action, orderType="MOO", totalQuantity=quantity)
        else:
            parent = MarketOrder(action, quantity)
        parent.transmit = False

        parent_trade = self._ib.placeOrder(contract, parent)
        parent_id = parent_trade.order.orderId

        oca_group = f"OCA_{symbol}_{parent_id}" if (has_stop and has_tp) else ""

        # --- stop-loss child ---
        stop_trade = None
        if has_stop:
            stop_order = StopOrder(reverse_action, quantity, stop_price, tif="GTC")
            stop_order.parentId = parent_id
            stop_order.transmit = not has_tp  # transmit only if it is the last child
            if oca_group:
                stop_order.ocaGroup = oca_group
                stop_order.ocaType = 1
            stop_trade = self._ib.placeOrder(contract, stop_order)

        # --- take-profit child ---
        tp_trade = None
        if has_tp:
            tp_order = LimitOrder(reverse_action, quantity, take_profit_price, tif="GTC")
            tp_order.parentId = parent_id
            tp_order.transmit = True  # last order → triggers full transmission
            if oca_group:
                tp_order.ocaGroup = oca_group
                tp_order.ocaType = 1
            tp_trade = self._ib.placeOrder(contract, tp_order)

        # If no children, transmit the parent alone
        if not has_stop and not has_tp:
            parent.transmit = True
            parent_trade = self._ib.placeOrder(contract, parent)

        entry_type = "MOO" if market_on_open else "MKT"
        self._log_order(f"BRACKET_{entry_type}_{action}", symbol, parent_trade.order)
        return parent_trade

    def modify_stop_order(self, order_id: int, new_stop_price: float) -> None:
        """Update the aux (stop) price on an existing stop order."""
        trade = self._find_open_trade(order_id)
        trade.order.auxPrice = new_stop_price
        self._ib.placeOrder(trade.contract, trade.order)
        self._ib.sleep(1)
        logger.info("Modified stop order %d → stop_price=%.4f", order_id, new_stop_price)

    def modify_take_profit_order(self, order_id: int, new_limit_price: float) -> None:
        """Update the limit price on an existing take-profit order."""
        trade = self._find_open_trade(order_id)
        trade.order.lmtPrice = new_limit_price
        self._ib.placeOrder(trade.contract, trade.order)
        self._ib.sleep(1)
        logger.info("Modified TP order %d → limit_price=%.4f", order_id, new_limit_price)

    def cancel_order(self, order_id: int) -> None:
        """Cancel a working order by its order ID."""
        trade = self._find_open_trade(order_id)
        self._ib.cancelOrder(trade.order)
        self._ib.sleep(1)
        logger.info("Cancelled order %d", order_id)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _qualify_contract(self, symbol: str) -> Stock:
        """Resolve a STK contract on SMART exchange, USD currency."""
        contract = Stock(symbol, "SMART", "USD")
        qualified = self._ib.qualifyContracts(contract)
        if not qualified:
            raise ValueError(
                f"Could not qualify IB contract for symbol '{symbol}'. "
                "Verify the symbol is a valid US stock ticker."
            )
        return qualified[0]

    def _wait_for_fill(self, trade, timeout: float) -> bool:
        """Block until *trade* is done (filled/cancelled) or *timeout* seconds elapse.

        Returns True if the trade completed within the timeout.
        """
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self._ib.sleep(1)
            if trade.isDone():
                return True
        return False

    def _log_order(self, action: str, symbol: str, order) -> None:
        """Emit a structured log entry for every placed order."""
        logger.info(
            "ORDER | action=%s symbol=%s orderId=%s orderType=%s qty=%s auxPrice=%s lmtPrice=%s",
            action,
            symbol,
            getattr(order, "orderId", "?"),
            getattr(order, "orderType", "?"),
            getattr(order, "totalQuantity", "?"),
            getattr(order, "auxPrice", None),
            getattr(order, "lmtPrice", None),
        )

    def _find_open_trade(self, order_id: int):
        """Return the Trade object for *order_id*; raise ValueError if not found."""
        for trade in self._ib.openTrades():
            if trade.order.orderId == order_id:
                return trade
        raise ValueError(
            f"No open trade found with orderId {order_id}. "
            "The order may have already been filled or cancelled."
        )

    def _trade_to_open_order(self, trade) -> IBOpenOrder:
        order = trade.order
        aux_price = getattr(order, "auxPrice", None)
        lmt_price = getattr(order, "lmtPrice", None)
        return IBOpenOrder(
            order_id=order.orderId,
            symbol=trade.contract.symbol,
            order_type=order.orderType,
            action=order.action,
            quantity=float(order.totalQuantity),
            aux_price=float(aux_price) if aux_price not in (None, 0, 0.0) else None,
            limit_price=float(lmt_price) if lmt_price not in (None, 0, 0.0) else None,
            status=trade.orderStatus.status,
        )


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

def _is_currently_in_session(liquid_hours: str, timezone_id: str) -> bool:
    """Parse IB liquidHours string and check whether *now* falls inside a session.

    IB format example:
        "20231204:0930-20231204:1600;20231205:CLOSED;20231206:0930-20231206:1600"
    """
    if not liquid_hours:
        return False

    try:
        tz = pytz.timezone(timezone_id)
    except Exception:
        logger.warning(
            "Unknown IB timezone '%s'; falling back to US/Eastern.", timezone_id
        )
        tz = pytz.timezone("US/Eastern")

    now = datetime.now(tz)

    for segment in liquid_hours.split(";"):
        segment = segment.strip()
        if not segment or "CLOSED" in segment:
            continue
        try:
            start_str, end_str = segment.split("-", 1)
            start_dt = _parse_ib_datetime(start_str, tz)
            end_dt = _parse_ib_datetime(end_str, tz)
            if start_dt <= now <= end_dt:
                return True
        except Exception as exc:
            logger.debug("Could not parse trading hours segment '%s': %s", segment, exc)

    return False


def _parse_ib_datetime(dt_str: str, tz: pytz.BaseTzInfo) -> datetime:
    """Parse an IB datetime token like '20231204:0930' into a timezone-aware datetime."""
    date_part, time_part = dt_str.strip().split(":")
    return tz.localize(datetime.strptime(f"{date_part} {time_part}", "%Y%m%d %H%M"))


# ---------------------------------------------------------------------------
# Environment-variable constructor shortcut
# ---------------------------------------------------------------------------

def create_ib_client_from_env(
    client_id_env_var: str = "IB_CLIENT_ID",
) -> "IBClient":
    """Build an IBClient from environment variables with sensible defaults."""
    return IBClient(
        host=os.getenv("IB_HOST", "127.0.0.1"),
        port=int(os.getenv("IB_PORT", "4002")),
        client_id=int(os.getenv(client_id_env_var, "1")),
        timeout=float(os.getenv("IB_TIMEOUT", "20")),
    )
