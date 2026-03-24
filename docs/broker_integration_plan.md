# Broker Integration Plan: Interactive Brokers Connectivity

## Problem Statement

TradingAgents is a recommendation engine that outputs trade decisions (BUY, SELL, SELL_SHORT, BUY_TO_COVER, MODIFY) and position state to YAML files. It currently has no connection to any live brokerage. Two execution gaps must be closed:

1. **Position sync**: `current_positions.yaml` is maintained manually. It must be kept in sync with actual IB portfolio state before each analysis run.
2. **Order execution**: `decision_table.yaml` (produced by `run.py`) contains trading decisions that must be translated into real IB orders (or modifications to existing orders).

Both scripts will share a common Interactive Brokers gateway client built on **ib_insync**.

---

## Proposed Folder Structure

```
broker/
├── __init__.py              # Public re-exports
├── ib_client.py             # Common IB Gateway interface (ib_insync wrapper)
├── order_mapper.py          # Maps TradeDecision → IB order parameters
├── sync_positions.py        # Script 1: sync current_positions.yaml ← IB portfolio
└── place_orders.py          # Script 2: execute orders from decision_table.yaml
```

All scripts live at the **project root level** under `broker/`, parallel to `tradingagents/`. They are invoked directly:

```bash
uv run broker/sync_positions.py [options]
uv run broker/place_orders.py   [options]
```

---

## Data Contracts

### current_positions.yaml (read + written by sync_positions.py)

```yaml
SYMBOL:
  open: bool          # true if a position is currently held
  side: str           # "long" | "short"
  stop_loss: float | null   # required numeric when open=true
  take_profit: float | null
```

### decision_table.yaml (read-only by place_orders.py)

```yaml
SYMBOL:
  decision: str         # BUY | SELL | SELL_SHORT | BUY_TO_COVER | MODIFY
  stop_loss: float | null
  take_profit: float | null
  confidence_pct: float
```

> Note: `rationale` is present in the internal `TradeDecision` object but is **explicitly excluded** from `decision_table.yaml` by `run.py` (line 206: `{k: v ... if k != "rationale"}`). The broker scripts therefore never see this field.

---

## Component 1 — `broker/ib_client.py` (Common IB Gateway Interface)

This module provides the single point of contact with IB Gateway. All IB-specific logic is encapsulated here so neither script imports `ib_insync` directly.

### Class: `IBClient`

```python
class IBClient:
    def __init__(self, host: str, port: int, client_id: int, timeout: float): ...
    def connect(self) -> None: ...
    def disconnect(self) -> None: ...
```

#### Portfolio / Account Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `get_portfolio_positions()` | `dict[str, PortfolioPosition]` | All open IB positions keyed by symbol |
| `get_open_orders()` | `list[IBOpenOrder]` | All working orders (stops, limits) |
| `get_open_orders_for_symbol(symbol)` | `list[IBOpenOrder]` | Working orders for one symbol |
| `get_stop_and_take_profit_for_symbol(symbol)` | `tuple[float\|None, float\|None]` | Extracts `(stop_price, take_profit_price)` from working STP/LMT orders for the symbol; returns `(None, None)` if no relevant orders found |
| `get_last_price(symbol)` | `float` | Last traded price for the symbol (from IB market data snapshot) |
| `is_market_open(symbol)` | `bool` | Returns `True` if the primary exchange for the symbol is currently in its regular trading session |

#### Order Placement Methods

| Method | Description |
|--------|-------------|
| `place_market_order(symbol, action, quantity)` | `"BUY"` or `"SELL"` market order (use only when market is open) |
| `place_market_on_open_order(symbol, action, quantity)` | MOO order that executes at next regular-session open (use when market is closed) |
| `place_stop_order(symbol, action, quantity, stop_price)` | Attached stop-loss (GTC) |
| `place_take_profit_order(symbol, action, quantity, limit_price)` | Attached take-profit limit (GTC) |
| `place_bracket_order(symbol, action, quantity, stop_price, take_profit_price, market_on_open)` | Entry (MKT or MOO) + stop + take-profit as OCA group; child orders activate only after parent fills |
| `modify_stop_order(order_id, new_stop_price)` | Updates aux price on existing stop order |
| `modify_take_profit_order(order_id, new_limit_price)` | Updates limit price on existing order |
| `cancel_order(order_id)` | Cancels a working order |

#### Internal Helpers

| Method | Description |
|--------|-------------|
| `_qualify_contract(symbol)` | Resolves STK contract on SMART exchange, USD currency |
| `_wait_for_fill(trade, timeout)` | Blocks until order fills or timeout |
| `_log_order(action, symbol, order)` | Structured logging of every placed order |

#### NamedTuples / TypedDicts

```python
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
    order_type: str          # "STP", "LMT", "MKT", etc.
    action: str              # "BUY", "SELL"
    quantity: float
    aux_price: float | None  # stop price
    limit_price: float | None
    status: str              # "PreSubmitted", "Submitted", etc.
```

#### Configuration (via environment variables or constructor kwargs)

| Variable | Default | Description |
|----------|---------|-------------|
| `IB_HOST` | `127.0.0.1` | IB Gateway / TWS host |
| `IB_PORT` | `4002` | 4001 = TWS live, 4002 = Gateway live, 7497/7496 = paper |
| `IB_CLIENT_ID` | `1` | Unique client ID (sync script uses 1, orders script uses 2) |
| `IB_TIMEOUT` | `20` | Seconds to wait for connection |

---

## Component 2 — `broker/order_mapper.py`

Maps a `TradeDecision` dict (from `decision_table.yaml`) plus the current `PositionConfig` (from `current_positions.yaml`) into concrete `IBOrderRequest` parameter objects consumed by `IBClient`.

### Class: `OrderMapper`

```python
class OrderMapper:
    def __init__(self, position_mode: str): ...
    def map(
        self,
        symbol: str,
        decision: TradeDecision,
        current_position: PositionConfig,
        open_orders: list[IBOpenOrder],
    ) -> list[IBOrderRequest]: ...
```

### Decision → IB Action Mapping

| Decision | Current State | Entry Order | Stop / TP |
|----------|--------------|-------------|-----------|
| `BUY` | closed | MKT (market open) or MOO (market closed) | Bracket: STP + LMT (GTC), linked via `parentId` |
| `SELL` | open long | MKT (market open) or MOO (market closed) | Cancel existing STP/LMT first |
| `SELL_SHORT` | closed | MKT (market open) or MOO (market closed) | Bracket: STP + LMT (GTC), linked via `parentId` |
| `BUY_TO_COVER` | open short | MKT (market open) or MOO (market closed) | Cancel existing STP/LMT first |
| `MODIFY` | open | — | Modify existing STP/LMT orders in place; no entry order |

**Market-hours rule**: `place_orders.py` calls `IBClient.is_market_open(symbol)` once per symbol. If the market is closed, all entry orders use MOO so they execute at the next regular-session open at the prevailing market price.

### IBOrderRequest (TypedDict)

```python
class IBOrderRequest(TypedDict):
    symbol: str
    action: Literal["BUY", "SELL"]
    quantity: float | None          # None means "use existing position size" (for MODIFY/close)
    order_type: str                 # "MKT", "MOO", "STP", "LMT"
    stop_price: float | None
    take_profit_price: float | None
    is_bracket: bool
    market_on_open: bool            # True → use MOO entry; False → use MKT entry
    modify_order_id: int | None     # set for MODIFY only
    cancel_order_ids: list[int]     # orders to cancel before placing new ones
```

### Position Sizing

When opening a new position (BUY or SELL_SHORT), the number of shares is calculated as:

```
quantity = floor(CAPITAL_PER_POSITION / last_price)
```

`last_price` is fetched via `IBClient.get_last_price(symbol)` immediately before order construction. `CAPITAL_PER_POSITION` is read from the environment (see [Configuration](#configuration--environment-variables)).

This means `OrderMapper.map()` receives a `capital_per_position` argument and calls `IBClient.get_last_price()` internally, or the caller pre-computes the quantity and passes it in. The final `IBOrderRequest.quantity` is always a concrete integer for opening orders; `None` is reserved for close/modify orders where IB already knows the full position size.

---

## Component 3 — `broker/sync_positions.py` (Script 1)

**Purpose**: Pull live IB portfolio state and reconcile `current_positions.yaml`.

### Invocation

```bash
uv run broker/sync_positions.py [--positions-file PATH] [--dry-run] [--verbose]
```

| Flag | Default | Description |
|------|---------|-------------|
| `--positions-file` | `current_positions.yaml` | Path to the positions file |
| `--dry-run` | false | Print planned changes; do not write file |
| `--verbose` | false | Show per-symbol reconciliation detail |

### Algorithm

```
1. Load current_positions.yaml  → tracked_positions: PositionMap
2. Connect to IB Gateway        → ib_positions: dict[symbol, PortfolioPosition]
3.                              → ib_open_orders: list[IBOpenOrder]
4. For each symbol in tracked_positions:
   a. If symbol found in ib_positions:
      - set open = true
      - set side = ib_positions[symbol].side
      - extract stop_loss from the symbol's working STP order (aux_price), or null if none found
      - extract take_profit from the symbol's working LMT order (limit_price), or null if none found
   b. If symbol NOT found in ib_positions (but was open):
      - set open = false
      - set side to existing value (preserved for history)
      - set stop_loss = null, take_profit = null
5. Warn about symbols in ib_positions not tracked in current_positions.yaml
6. Save reconciled map back to current_positions.yaml (in-place, not .updated.yaml)
7. Print summary table (rich)
```

### Reconciliation Rules

- **New IB position, not tracked**: Warn and skip (user must add to YAML manually).
- **Tracked open, not in IB**: Mark closed (`open=false`, nullify risk levels).
- **Tracked closed, not in IB**: No change.
- **Side mismatch (tracked long, IB short)**: Update side, log a warning.
- **Stop-loss**: Updated from the symbol's working STP order at IB (`aux_price`). Set to `null` if no stop order is found (log a warning, as open positions should always carry a stop).
- **Take-profit**: Updated from the symbol's working LMT order at IB (`limit_price`). Set to `null` if no take-profit order is found (acceptable; take-profit is optional).
- **Multiple stop or TP orders**: If more than one STP or LMT order is found for the same symbol, use the most conservative value (closest to current price) and log a warning.

### Output

- Updated `current_positions.yaml` (in-place).
- Rich console summary table:

```
Symbol │ Was            │ Now            │ Change
───────┼────────────────┼────────────────┼────────────────────────────────
CAT    │ open long      │ open long      │ stop 655.00→648.50
JPM    │ closed         │ closed         │ no change
LLY    │ open long      │ open long      │ no change (stop 890, tp 1030)
NVDA   │ open short     │ closed         │ ⚠ position closed in IB
WMT    │ open short     │ open short     │ ⚠ no stop order found at IB
```

---

## Component 4 — `broker/place_orders.py` (Script 2)

**Purpose**: Read `decision_table.yaml` and execute trades on IB accordingly.

### Invocation

```bash
uv run broker/place_orders.py \
    [--decision-file PATH] \
    [--positions-file PATH] \
    [--position-mode long_short|long_only] \
    [--dry-run] \
    [--symbol SYMBOL ...] \
    [--min-confidence FLOAT] \
    [--verbose]
```

| Flag | Default | Description |
|------|---------|-------------|
| `--decision-file` | `reports/<latest>/decision_table.yaml` | Path to decision table |
| `--positions-file` | `current_positions.yaml` | Path to current positions |
| `--position-mode` | `long_short` | Governs which decisions are valid |
| `--dry-run` | false | Map and validate orders; do not submit |
| `--symbol` | all | Limit execution to listed symbols |
| `--min-confidence` | `0.0` | Skip decisions below this confidence % |
| `--verbose` | false | Per-symbol order detail |

### Algorithm

```
1. Load decision_table.yaml    → decisions: dict[symbol, TradeDecision]
2. Load current_positions.yaml → positions: PositionMap
3. Validate each decision against current position and position_mode
   (reuse validate_decision_for_position from position_management/actions.py)
4. Apply --symbol and --min-confidence filters
5. Connect to IB Gateway
6. For each symbol (in deterministic sorted order):
   a. Fetch open orders from IB for this symbol
   b. Determine market state: market_open = IBClient.is_market_open(symbol)
   c. For opening decisions (BUY / SELL_SHORT):
      - Fetch last_price = IBClient.get_last_price(symbol)
      - Compute quantity = floor(CAPITAL_PER_POSITION / last_price)
      - Log: symbol, last_price, quantity, capital_per_position
   d. Call OrderMapper.map(symbol, decision, position, open_orders,
                           market_open=market_open, quantity=quantity)
   e. If --dry-run: print planned orders; continue
   f. Execute cancel_order_ids (if any)
   g. Execute the order request(s) via IBClient
   h. If market open: wait for fill / partial fill up to configurable timeout
      If market closed: confirm order acceptance (MOO queued); no fill wait
   i. Record result (filled, queued, rejected, timeout)
7. Print execution summary table (rich)
8. Write results log to reports/<date>/order_results.yaml
```

### Order Execution Detail by Decision Type

#### BUY / SELL_SHORT (open new position)
1. Cancel any stale stop/TP orders for the symbol.
2. Compute `quantity = floor(CAPITAL_PER_POSITION / last_price)`. Abort if quantity < 1.
3. **If market is open**: place a **MKT order** for the entry; wait for fill.  
   **If market is closed**: place a **MOO (Market-on-Open) order**; it will execute at the next regular-session open.
4. Attach bracket child orders (linked via `parentId`, submitted together with the parent):
   - A **stop-loss** order (STP, GTC) if `stop_loss` is set.
   - A **take-profit** order (LMT, GTC) if `take_profit` is set.
   - If both are set, the two child orders form an **OCA (One-Cancels-All)** group.
   - Child orders are submitted alongside the parent in a single `placeOrder` sequence; they remain dormant until the parent fills, so it is safe to submit them before market open.

#### SELL / BUY_TO_COVER (close position)
1. Cancel all open stop/TP orders for the symbol.
2. **If market is open**: place a **MKT order** for the full position quantity (fetched from IB).  
   **If market is closed**: place a **MOO order** for the full position quantity.

#### MODIFY (adjust risk levels on open position)
1. Locate existing stop and/or TP orders via `get_open_orders_for_symbol()`.
2. If stop order found and `stop_loss` changed: call `modify_stop_order()`.
3. If TP order found and `take_profit` changed: call `modify_take_profit_order()`.
4. If a stop/TP order is expected but not found: create it (using `place_stop_order` / `place_take_profit_order`).

### Output

- Rich execution summary:

```
Symbol │ Decision       │ Confidence │ Status      │ Detail
───────┼────────────────┼────────────┼─────────────┼────────────────────────────────────
CAT    │ SELL           │ 75.5%      │ ✅ filled    │ Sold 32 @ 312.40 (market open)
JPM    │ BUY_TO_COVER   │ 82.3%      │ ✅ filled    │ Covered 50 @ 198.75 (market open)
NVDA   │ MODIFY         │ 70.0%      │ ✅ done      │ Stop updated 196→188
TSLA   │ SELL_SHORT     │ 64.0%      │ 🕐 queued    │ MOO 25 shares @ open (market closed)
WMT    │ BUY            │ 55.0%      │ ⏭ skipped    │ Below min-confidence (55 < 60)
```

- `reports/<date>/order_results.yaml` log file.

---

## Error Handling and Safety

| Scenario | Handling |
|----------|----------|
| IB Gateway not running | `ConnectionError` with clear message; exit code 1 |
| Symbol not found in IB contract database | Log warning; skip symbol |
| Decision invalid for current position state | Log error (from `validate_decision_for_position`); skip symbol |
| `CAPITAL_PER_POSITION / last_price < 1` | Log error ("insufficient capital for ≥1 share"); skip symbol |
| Market closed — opening/closing order | Use MOO entry; log that order is queued for next open |
| Order rejected by IB | Log rejection reason; mark as failed in results |
| Fill timeout (market open) | Log timeout; mark as pending; do not assume fill |
| `open=true` but no position found in IB | Warn; skip (requires manual sync first) |
| Duplicate client ID conflict | Raise with hint to check `IB_CLIENT_ID` env var |
| `--dry-run` | No orders are ever submitted; all IB calls are read-only |

---

## Dependency

Add to `requirements.txt` / `pyproject.toml`:

```
ib_insync>=0.9.86
```

`ib_insync` wraps the TWS API with asyncio and provides a synchronous convenience layer that avoids callback hell.

---

## Configuration & Environment Variables

All IB connectivity settings are read from environment variables (`.env` file, loaded via `python-dotenv`) with sensible defaults:

```dotenv
# Interactive Brokers Gateway
IB_HOST=127.0.0.1
IB_PORT=4002         # 4002 = Gateway live, 7497 = TWS paper
IB_CLIENT_ID_SYNC=1
IB_CLIENT_ID_ORDERS=2
IB_TIMEOUT=20

# Position sizing
CAPITAL_PER_POSITION=10000   # USD capital allocated per symbol when opening a position
                              # quantity = floor(CAPITAL_PER_POSITION / last_price)
```

---

## Integration with Existing Codebase

| Existing Module | Usage in Broker Scripts |
|-----------------|------------------------|
| `tradingagents/position_management/schema.py` | `PositionConfig`, `PositionMap` types |
| `tradingagents/position_management/loader.py` | `load_current_positions()`, `save_current_positions()` |
| `tradingagents/position_management/actions.py` | `validate_decision_for_position()`, `apply_decision_to_position()` |
| `tradingagents/position_management/decision_schema.py` | `TradeDecision` type |
| `tradingagents/position_management/guardrails.py` | `apply_trailing_stop_guardrail()` before MODIFY |

The broker scripts are deliberately **not part of the `tradingagents` package**. They are standalone scripts that import from it. This keeps the AI analysis engine free of execution-layer concerns.

---

## Recommended Workflow

```
1. sync_positions.py        → pull live IB state into current_positions.yaml
2. run.py                   → generate decision_table.yaml using up-to-date positions
3. [human review]           → inspect decision_table.yaml, adjust if needed
4. place_orders.py --dry-run → review planned orders
5. place_orders.py          → execute approved orders
```

`sync_positions.py` must run **before** `run.py` so the AI agents receive accurate current position state (open/closed, side) when forming their recommendations. Running them in the wrong order risks generating decisions based on stale data (e.g., recommending SELL on a position that was already closed).

---

## Out of Scope (for this iteration)

- Partial fills and fill reconciliation
- Real-time P&L monitoring
- Order status polling / fill notifications (beyond basic timeout wait)
- Support for options, futures, or forex contracts
- TWS API (only IB Gateway is targeted)
- Automatic re-tries on transient order rejections
- Per-symbol `CAPITAL_PER_POSITION` overrides (single global value only)
