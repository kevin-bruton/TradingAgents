"""Common IB Gateway interface built on ib_insync.

All IB-specific logic is encapsulated here so neither broker script
imports ib_insync directly.
"""

from __future__ import annotations

import asyncio
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


class CompletedTrade(TypedDict):
    exec_id: str
    symbol: str
    datetime: str            # ISO-8601 UTC timestamp of the fill
    action: str              # "BOT" (bought) or "SLD" (sold)
    quantity: float
    price: float             # fill price
    commission: float
    realized_pnl: Optional[float]   # None for opening fills; float for closes
    currency: str


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
        # Python 3.10+ no longer auto-creates an event loop; ib_insync needs one.
        try:
            loop = asyncio.get_event_loop()
            if loop.is_closed():
                raise RuntimeError("closed")
        except RuntimeError:
            asyncio.set_event_loop(asyncio.new_event_loop())

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

    def get_completed_trades(self) -> list[CompletedTrade]:
        """Return completed fills received during the current IB session.

        Calls ``reqExecutions()`` with a default filter (today's executions) and
        parses each ``Fill`` into a ``CompletedTrade``.  The ``realized_pnl``
        field is populated only when IB reports a P&L figure, i.e. for fills that
        partially or fully *close* an existing position; it is ``None`` for fills
        that open a new position.
        """
        from ib_insync import ExecutionFilter

        self._ib.reqExecutions(ExecutionFilter())
        self._ib.sleep(2)

        trades: list[CompletedTrade] = []
        for fill in self._ib.fills():
            execution = fill.execution
            comm = fill.commissionReport

            exec_time = execution.time
            dt_str = exec_time.isoformat() if isinstance(exec_time, datetime) else str(exec_time)

            rpnl: Optional[float] = None
            commission = 0.0
            if comm is not None:
                if comm.realizedPNL is not None and not math.isnan(comm.realizedPNL):
                    rpnl = float(comm.realizedPNL)
                if comm.commission is not None and not math.isnan(comm.commission):
                    commission = float(comm.commission)

            trades.append(CompletedTrade(
                exec_id=execution.execId,
                symbol=fill.contract.symbol,
                datetime=dt_str,
                action=execution.side,   # "BOT" or "SLD"
                quantity=float(execution.shares),
                price=float(execution.price),
                commission=commission,
                realized_pnl=rpnl,
                currency=fill.contract.currency,
            ))

        return trades

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
        """Return the last traded price for *symbol*.

        **Primary source — historical daily bars** (reqHistoricalData): requires no
        market-data subscription and is always available via IB Gateway / TWS.
        Returns the most recent daily close, which is accurate enough for position
        sizing (quantity = floor(CAPITAL / price)).

        **Fallback — live/delayed snapshot** (reqMarketDataType 3 then 1): only
        attempted if historical data is unexpectedly unavailable.  Requires either
        a paid live-data subscription or the free "Delayed" bundle to be enabled
        in IB Account Management → Market Data Subscriptions.
        """
        contract = self._qualify_contract(symbol)

        # Primary: historical bars — no subscription required
        try:
            return self._get_price_from_history(contract, symbol)
        except Exception as exc:
            logger.warning(
                "Historical data unavailable for %s (%s); trying market-data snapshot.", symbol, exc
            )

        # Fallback: snapshot (requires subscription or free delayed bundle)
        for data_type, label in ((3, "delayed"), (1, "live")):
            self._ib.reqMarketDataType(data_type)
            ticker = self._ib.reqMktData(contract, "", True, False)
            self._ib.sleep(3)
            self._ib.cancelMktData(contract)

            for candidate in (ticker.last, ticker.close, ticker.bid, ticker.ask):
                if candidate is not None and not math.isnan(candidate) and candidate > 0:
                    self._ib.reqMarketDataType(1)
                    logger.debug("Got %s price for %s: %.4f", label, symbol, candidate)
                    return float(candidate)

        self._ib.reqMarketDataType(1)
        raise ValueError(
            f"Could not retrieve last price for '{symbol}' via historical bars or market-data snapshot. "
            "Verify the symbol is a valid US stock ticker and IB Gateway is connected."
        )

    def _get_price_from_history(self, contract, symbol: str) -> float:
        """Return the most recent daily close via reqHistoricalData.

        This endpoint requires no market-data subscription and works at any time
        of day, including pre-market and after-hours.
        """
        bars = self._ib.reqHistoricalData(
            contract,
            endDateTime="",
            durationStr="5 D",
            barSizeSetting="1 day",
            whatToShow="TRADES",
            useRTH=True,
            formatDate=1,
            keepUpToDate=False,
        )
        if bars:
            price = float(bars[-1].close)
            logger.info("Using historical close price for %s: %.4f", symbol, price)
            return price

        raise ValueError(
            f"Could not retrieve last price for '{symbol}' via live data, "
            "delayed data, or historical bars. "
            "Verify the symbol is a valid US stock ticker and IB Gateway is connected."
        )

    def is_market_open(self, symbol: str) -> bool:
        """Return True if the symbol's primary exchange is in its regular trading session.

        Strategy (first successful answer wins):
        1. Parse ``liquidHours`` from IB contract details + IB-provided timezone.
        2. If liquidHours is empty or unparseable (common on paper-trading TWS),
           fall back to a direct US/Eastern time check covering the standard
           NYSE/NASDAQ session (Mon–Fri 09:30–16:00 ET).
        3. If all else fails, assume **open** (True) — a MKT order submitted when
           the market is closed is held until the next open, whereas a MOO order
           submitted when the market IS open is immediately hard-rejected (error 321).
        """
        contract = self._qualify_contract(symbol)
        details_list = self._ib.reqContractDetails(contract)

        if details_list:
            liquid_hours = details_list[0].liquidHours
            timezone_id = details_list[0].timeZoneId
            if liquid_hours:
                try:
                    result = _is_currently_in_session(liquid_hours, timezone_id)
                    logger.debug("is_market_open(%s) via IB liquidHours → %s", symbol, result)
                    return result
                except ValueError as exc:
                    logger.warning(
                        "liquidHours parse failed for %s (%s); "
                        "falling back to US/Eastern hours check.",
                        symbol, exc,
                    )
            else:
                logger.warning(
                    "liquidHours is empty in contract details for %s; "
                    "falling back to US/Eastern hours check.",
                    symbol,
                )
        else:
            logger.warning(
                "No contract details returned for %s; falling back to US/Eastern hours check.",
                symbol,
            )

        result = _is_us_equity_market_hours()
        logger.debug("is_market_open(%s) via US/Eastern fallback → %s", symbol, result)
        return result

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
        """Place a standalone Market-on-Open order (no bracket children).

        Note: IB does not support attaching bracket children (stop-loss / take-profit
        linked via parentId) to a MOO parent.  Use place_bracket_order instead,
        which uses a MKT parent and fills at or near the open when submitted
        pre-market.
        """
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
        """Place a MKT entry + optional stop-loss + optional take-profit as an OCA group.

        Always uses a MKT parent order.  A MKT/DAY order submitted pre-market is
        held in the IB queue and fills at or near the opening print — the
        ``market_on_open`` parameter is accepted for API compatibility but ignored
        (MOO parent orders cannot carry bracket children in the IB API).

        Child orders are linked via parentId and remain dormant until the parent
        fills, so submitting this before the market opens is safe.
        Returns the parent Trade object.
        """
        contract = self._qualify_contract(symbol)
        reverse_action = "SELL" if action == "BUY" else "BUY"
        has_stop = stop_price is not None
        has_tp = take_profit_price is not None

        # --- parent entry order (always MKT) ---
        parent = MarketOrder(action, quantity)
        parent.transmit = False
        # Explicitly set tif so IB doesn't need to apply an order preset to fill in
        # a missing value.  When tif is left unset, IB may apply the account's order
        # preset and emit error 10349 ("Order TIF was set to DAY based on order
        # preset"), which has been observed to trigger an immediate order cancellation
        # in some account configurations.
        parent.tif = "DAY"

        parent_trade = self._ib.placeOrder(contract, parent)
        parent_id = parent_trade.order.orderId

        # Give IB Gateway time to register the parent before children reference it
        # via parentId.  Without this brief pause, the children can arrive at the
        # gateway before it has finished processing the parent, causing them to be
        # rejected (parentId not found) and leaving the parent orphaned.
        self._ib.sleep(1)

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
            logger.info(
                "BRACKET child STP_%s: orderId=%s parentId=%s qty=%.0f stop=%.4f",
                reverse_action, stop_trade.order.orderId, parent_id, quantity, stop_price,
            )

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
            logger.info(
                "BRACKET child LMT_%s: orderId=%s parentId=%s qty=%.0f lmt=%.4f",
                reverse_action, tp_trade.order.orderId, parent_id, quantity, take_profit_price,
            )

        # If no children, transmit the parent alone
        if not has_stop and not has_tp:
            parent.transmit = True
            parent_trade = self._ib.placeOrder(contract, parent)

        # Allow IB time to process the complete bracket and surface any immediate
        # rejection before the caller checks the order status.
        self._ib.sleep(2)

        entry_type = "MOO" if market_on_open else "MKT"
        self._log_order(f"BRACKET_{entry_type}_{action}", symbol, parent_trade.order)

        status = parent_trade.orderStatus.status
        if status in ("Cancelled", "Inactive"):
            logger.error(
                "Bracket parent order %d for %s was %s shortly after placement. "
                "Check IB order presets for TIF / outside-RTH conflicts.",
                parent_id, symbol, status,
            )

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

    Returns True if the current time is within any listed session window.
    Returns None (falsy) if no segment could be parsed — caller should fall back.
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
    parsed_any = False

    for segment in liquid_hours.split(";"):
        segment = segment.strip()
        if not segment or "CLOSED" in segment:
            continue
        try:
            start_str, end_str = segment.split("-", 1)
            start_dt = _parse_ib_datetime(start_str, tz)
            end_dt = _parse_ib_datetime(end_str, tz)
            parsed_any = True
            if start_dt <= now <= end_dt:
                return True
        except Exception as exc:
            logger.warning(
                "Could not parse trading hours segment '%s': %s — skipping.", segment, exc
            )

    if not parsed_any:
        # No segments parsed successfully; signal to caller to use fallback
        raise ValueError(f"Could not parse any session from liquidHours: {liquid_hours!r}")

    return False


def _is_us_equity_market_hours() -> bool:
    """Return True if the current US/Eastern time is within the standard NYSE/NASDAQ session.

    Used as a fallback when IB contract details are unavailable or unparseable.
    Covers Mon–Fri 09:30–16:00 ET; does **not** account for market holidays.
    """
    from datetime import time as dt_time

    tz = pytz.timezone("US/Eastern")
    now = datetime.now(tz)
    if now.weekday() >= 5:  # Saturday=5, Sunday=6
        return False
    return dt_time(9, 30) <= now.time() <= dt_time(16, 0)


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
