# Broker Integration — Interactive Brokers

This folder contains two standalone scripts that connect TradingAgents to a live
Interactive Brokers account via **IB Gateway** (or TWS).

```
broker/
├── ib_client.py        # IB Gateway wrapper (ib_insync)
├── order_mapper.py     # TradeDecision → IBOrderRequest translator
├── sync_positions.py   # Script 1: sync current_positions.yaml ← IB portfolio
├── place_orders.py     # Script 2: execute orders from decision_table.yaml
└── __init__.py
```

---

## Prerequisites

### 1. IB Gateway or TWS

- Download and install [IB Gateway](https://www.interactivebrokers.com/en/trading/ibgateway.php)
  (recommended) or Trader Workstation (TWS).
- Log in and enable **API connections**:
  - IB Gateway: **Configuration → Settings → API → Enable ActiveX and Socket Clients**
  - TWS: **File → Global Configuration → API → Settings → Enable ActiveX and Socket Clients**
- Note the socket port in use (default: `4002` for IB Gateway live, `7497` for TWS paper).

### 2. Python dependency

`ib_insync` is already listed in `requirements.txt` / `pyproject.toml` and installed via:

```bash
uv sync
```

### 3. Environment variables

Copy `.env.example` to `.env` (project root) and set the IB-specific variables:

```dotenv
# Interactive Brokers Gateway
IB_HOST=127.0.0.1
IB_PORT=4002             # 4002 = Gateway live | 7497 = TWS paper | 4001 = Gateway paper
IB_CLIENT_ID_SYNC=1      # client ID used by sync_positions.py
IB_CLIENT_ID_ORDERS=2    # client ID used by place_orders.py
IB_TIMEOUT=20            # seconds to wait for connection

# Position sizing (USD allocated per symbol when opening a new position)
CAPITAL_PER_POSITION=10000
```

> **Client IDs must be unique.** If you run both scripts simultaneously, they need
> different client IDs (`IB_CLIENT_ID_SYNC` ≠ `IB_CLIENT_ID_ORDERS`).

---

## Recommended Workflow

```
1. sync_positions.py        ← pull live IB state → current_positions.yaml
2. run.py                   ← generate decision_table.yaml (reads positions)
3. [human review]           ← inspect decision_table.yaml, adjust if needed
4. place_orders.py --dry-run ← review planned orders before submitting
5. place_orders.py          ← execute approved orders
```

**`sync_positions.py` must run before `run.py`** so the AI agents receive accurate
current position state. Running them in the wrong order risks decisions based on
stale data (e.g., recommending SELL on a position already closed in IB).

---

## Script 1 — `sync_positions.py`

Pulls the live IB portfolio and reconciles `current_positions.yaml` in-place.

### Usage

```bash
uv run broker/sync_positions.py [OPTIONS]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--positions-file PATH` | `current_positions.yaml` | Path to the positions file |
| `--dry-run` | off | Print planned changes; do not write to disk |
| `--verbose` | off | Show debug-level IB connection detail |

### Examples

```bash
# Standard sync (updates current_positions.yaml in place)
uv run broker/sync_positions.py

# Preview what would change without writing anything
uv run broker/sync_positions.py --dry-run

# Use a non-default positions file
uv run broker/sync_positions.py --positions-file my_positions.yaml
```

### What it does

1. Loads `current_positions.yaml` (tracked positions).
2. Connects to IB Gateway and fetches portfolio positions and open orders.
3. For each tracked symbol:
   - **Found in IB**: marks `open=true`, updates `side`, reads `stop_loss` from
     the working STP order and `take_profit` from the working LMT order.
   - **Not in IB (was open)**: marks `open=false`, nullifies risk levels, logs a warning.
   - **Not in IB (was closed)**: no change.
4. Warns about IB positions not tracked in the YAML (user must add them manually).
5. Saves the reconciled state back to `current_positions.yaml`.
6. Prints a Rich summary table.

### Reconciliation rules

| Scenario | Handling |
|----------|----------|
| Symbol open in IB, tracked | Update `side`, `stop_loss`, `take_profit` from IB |
| Symbol open in IB, **not tracked** | ⚠ Warn and skip — add manually if needed |
| Symbol **not** in IB, was open | Mark `open=false`, clear risk levels, ⚠ warn |
| Symbol not in IB, was closed | No change |
| Side mismatch (YAML long, IB short) | Update side, ⚠ warn |
| No stop order found at IB (position open) | Preserve existing `stop_loss`, ⚠ warn |
| Multiple STP orders for same symbol | Use highest `aux_price`, ⚠ warn |
| Multiple LMT orders for same symbol | Use lowest `limit_price`, ⚠ warn |

### Sample output

```
Symbol │ Was                    │ Now                    │ Change
───────┼────────────────────────┼────────────────────────┼───────────────────────────
CAT    │ open long | stop=655   │ open long | stop=648.5 │ stop 655→648.5
JPM    │ closed                 │ closed                 │ no change
LLY    │ open long | stop=890   │ open long | stop=890   │ no change
NVDA   │ open short | stop=196  │ closed                 │ ⚠ position closed in IB
WMT    │ open short | stop=124  │ open short | stop=124  │ no change
```

---

## Script 2 — `place_orders.py`

Reads `decision_table.yaml` and submits the corresponding orders to IB.

### Usage

```bash
uv run broker/place_orders.py [OPTIONS]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--decision-file PATH` | latest `reports/*/decision_table.yaml` | Decision table to execute |
| `--positions-file PATH` | `current_positions.yaml` | Current positions file |
| `--position-mode TEXT` | `long_short` | `long_short` or `long_only` |
| `--dry-run` | off | Map and validate; do not submit any orders |
| `--symbol TEXT` | all | Limit to specific symbols (repeatable) |
| `--min-confidence FLOAT` | `0.0` | Skip decisions below this confidence % |
| `--verbose` | off | Show per-symbol price/quantity detail |

### Examples

```bash
# Preview all planned orders (safe — no orders submitted)
uv run broker/place_orders.py --dry-run

# Execute with a minimum confidence threshold
uv run broker/place_orders.py --min-confidence 65

# Execute only specific symbols
uv run broker/place_orders.py --symbol NVDA --symbol TSLA

# Execute from a specific decision file
uv run broker/place_orders.py --decision-file reports/2026-03-24/decision_table.yaml

# Full run: min confidence + symbol filter + verbose
uv run broker/place_orders.py --min-confidence 70 --symbol CAT --symbol LLY --verbose
```

### What it does

1. Loads the decision table and current positions.
2. Validates every decision against the current position state and `--position-mode`.
3. Applies `--symbol` and `--min-confidence` filters.
4. Connects to IB Gateway.
5. For each symbol (alphabetical order):
   - Fetches working orders and checks whether the market is currently open.
   - For **opening** decisions (BUY / SELL_SHORT): fetches last price and computes
     `quantity = floor(CAPITAL_PER_POSITION / last_price)`.
   - Calls `OrderMapper.map()` to build `IBOrderRequest` objects.
   - Executes cancellations, then the order(s).
   - If market **open**: places a MKT entry, waits up to `IB_FILL_TIMEOUT` seconds
     for a fill confirmation.
   - If market **closed**: places a MOO (Market-on-Open) entry that executes at the
     next regular-session open.
6. Prints a Rich execution summary.
7. Writes `reports/<date>/order_results.yaml`.

### Decision → order type mapping

| Decision | Position state | Entry order | Risk orders |
|----------|---------------|-------------|-------------|
| `BUY` | closed | MKT (open) or MOO (closed) | Bracket: STP + LMT (GTC, OCA) |
| `SELL` | open long | MKT (open) or MOO (closed) | Cancel existing STP/LMT first |
| `SELL_SHORT` | closed | MKT (open) or MOO (closed) | Bracket: STP + LMT (GTC, OCA) |
| `BUY_TO_COVER` | open short | MKT (open) or MOO (closed) | Cancel existing STP/LMT first |
| `MODIFY` | open | — | Modify existing STP/LMT in-place; create if missing |

### Position sizing

```
quantity = floor(CAPITAL_PER_POSITION / last_price)
```

`CAPITAL_PER_POSITION` is read from the environment (default: `10000` USD). If the
computed quantity is less than 1, the symbol is skipped with an error.

`last_price` is obtained via IB historical daily bars (no market-data subscription
required). If a live or free delayed-data subscription is available it is used
instead for slightly better intraday accuracy, but historical close is sufficient
for position sizing in practice.

### Sample output

```
Symbol │ Decision     │ Confidence │ Status       │ Detail
───────┼──────────────┼────────────┼──────────────┼──────────────────────────────
CAT    │ SELL         │ 75.5%      │ ✅ filled     │ Filled 32 @ 312.40 (market open)
JPM    │ BUY_TO_COVER │ 82.3%      │ ✅ filled     │ Filled 50 @ 198.75 (market open)
NVDA   │ MODIFY       │ 70.0%      │ ✅ done       │ stop → 188
TSLA   │ SELL_SHORT   │ 64.0%      │ 🕐 queued     │ MOO 25 shares @ open (market closed)
WMT    │ BUY          │ 55.0%      │ ⏭ skipped    │ below min-confidence (55.0 < 60.0)
```

---

## Error handling

| Scenario | Behaviour |
|----------|-----------|
| IB Gateway not running | `ConnectionError` with clear message; exit code 1 |
| Symbol not found in IB contract database | Log warning; skip symbol |
| Decision invalid for current position state | Log error; skip symbol |
| `CAPITAL_PER_POSITION / last_price < 1` | Log error ("insufficient capital"); skip symbol |
| Market closed — opening/closing order | Use MOO entry; note in results |
| Order rejected by IB | Log rejection reason; mark as failed |
| Fill timeout (market open) | Mark as `⏳ pending`; do not assume fill |
| `open=true` but no IB position found | Warn; skip — run `sync_positions.py` first |
| Duplicate client ID | `ConnectionError` with hint to check `IB_CLIENT_ID_*` env vars |
| `--dry-run` | No orders submitted; all IB calls are read-only |

---

## Environment variable reference

| Variable | Default | Description |
|----------|---------|-------------|
| `IB_HOST` | `127.0.0.1` | IB Gateway / TWS host |
| `IB_PORT` | `4002` | Port (`4002` = Gateway live, `4001` = Gateway paper, `7497` = TWS paper) |
| `IB_CLIENT_ID_SYNC` | `1` | Client ID for `sync_positions.py` |
| `IB_CLIENT_ID_ORDERS` | `2` | Client ID for `place_orders.py` |
| `IB_TIMEOUT` | `20` | Seconds to wait for IB connection |
| `IB_FILL_TIMEOUT` | `30` | Seconds to wait for a market-order fill confirmation |
| `CAPITAL_PER_POSITION` | `10000` | USD capital allocated per symbol when opening a position |

---

## Out of scope (this iteration)

- Partial fills and fill reconciliation
- Real-time P&L monitoring
- Automatic retries on transient order rejections
- Options, futures, or forex contracts
- Per-symbol `CAPITAL_PER_POSITION` overrides
- TWS API (IB Gateway only)
