# Position Management Operational Guide

This guide documents the active position-aware workflow implemented across `run.py`, `main.py`, `TradingAgentsGraph`, and `backtest.py`.

## 1) `current_positions.yaml` input and fail-fast behavior

### Required location for script workflows
- `run.py` and `main.py` load positions from:
  - `<repo_root>\current_positions.yaml`
- Loading happens once at startup via `load_current_positions(...)`.
- If the file is missing or invalid, the script exits immediately with a clear error message.

### Strict validation (no silent fallback)
The loader rejects invalid input with explicit errors:
- file does not exist
- path is not a file
- invalid YAML syntax
- top-level YAML is not a mapping (`symbol -> position`)
- unknown keys in a symbol entry
- missing required keys
- incorrect types
- unsupported `side` values
- duplicate symbols after normalization

Symbols are normalized to uppercase. If your YAML has both `nvda` and `NVDA`, loading fails because they normalize to the same key.

### Schema (`symbol -> position`)
Each symbol maps to:

```yaml
open: <bool>                 # required
stop_loss: <number | null>   # required
take_profit: <number | null> # required
side: "long" | "short"       # optional, defaults to "long"
```

Notes:
- `open` must be a YAML boolean (`true`/`false`).
- `stop_loss` and `take_profit` must be numeric or `null`.
- `side` supports `"long"` and `"short"`.
- If `open: true`, `stop_loss` must be numeric (all open positions require stop protection).
- Omitting a symbol is allowed; that symbol is treated as "no current position data provided."

## 2) Example template

Copy `current_positions.example.yaml` to `current_positions.yaml` and edit values for your symbols.

```yaml
NVDA:
  open: true
  stop_loss: 112.5
  take_profit: 145.0
  side: long

AAPL:
  open: false
  stop_loss: null
  take_profit: null

TSLA:
  open: true
  stop_loss: 298.0
  take_profit: 240.0
  side: short
```

## 3) Structured decision contract

The final risk-manager output must include exactly one fenced `json` block. It is parsed and validated into:

```json
{
  "decision": "BUY | SELL | SELL_SHORT | BUY_TO_COVER | MODIFY",
  "stop_loss": "<number|null>",
  "take_profit": "<number|null>",
  "confidence_pct": "<0..100 number>",
  "rationale": "<non-empty string>"
}
```

Validation highlights:
- `decision` must be uppercase and valid for configured `position_mode`:
  - `long_only`: `BUY`, `SELL`, `MODIFY`
  - `long_short`: `BUY`, `SELL`, `SELL_SHORT`, `BUY_TO_COVER`, `MODIFY`
- `confidence_pct` must be numeric within `[0, 100]`.
- `rationale` must be a non-empty string.
- Action/position coherence is enforced (e.g., cannot `SELL` with no open long, cannot `BUY_TO_COVER` with no open short).

## 4) Trailing-stop guardrail behavior

After structured parsing, a trailing-stop guardrail is applied for open positions:

- Guardrail applies only when:
  - current position is open
  - decision is not a close action (`SELL` / `BUY_TO_COVER`)
- If the proposed stop-loss is looser than the existing stop, it is clamped back to the existing level.
- A `SYSTEM WARNING:` line is appended to `rationale` when clamping occurs.

Guardrail tightening is side-aware:
- long: lower stop can be looser
- short: higher stop can be looser

## 5) Runtime and output surfaces

### `run.py` (multi-symbol script)
- Loads `current_positions.yaml` at startup.
- Passes per-symbol `current_position` into `ta.propagate(...)`.
- Applies structured decisions to next position state and saves output to `current_positions.updated.yaml`.
- Prints and tables these structured fields:
  - `decision`
  - `stop_loss`
  - `take_profit`
  - `confidence_pct`

### `main.py` (single-symbol script)
- Loads `current_positions.yaml` at startup.
- Passes the symbol position into `ta.propagate(...)`.
- Applies the structured decision and saves output to `current_positions.updated.yaml`.
- Prints:
  - `decision`, `stop_loss`, `take_profit`, `confidence_pct`, `rationale`

### CLI (`cli/main.py`)
- Surfaces structured decision fields in final summaries and saved reports.
- Displays and persists:
  - `decision`, `stop_loss`, `take_profit`, `confidence_pct`, `rationale`

## 6) Backtest position lifecycle alignment

`backtest.py` simulates position state day by day and writes:
- `date`
- `decision`
- `stop_loss`
- `take_profit`
- `confidence_pct`
- `position_status`
- `rationale`

`position_status` values include:
- `OPEN`
- `CLOSED`
- `CLOSED_SELL`
- `CLOSED_BUY_TO_COVER`
- `CLOSED_STOP_LOSS`
- `CLOSED_TAKE_PROFIT`

Stop/take-profit range checks use daily historical low/high values; lifecycle notes are appended to `rationale` when a stop-loss or take-profit trigger closes the simulated position.
