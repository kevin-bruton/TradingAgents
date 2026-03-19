# Margin-Aware Recommendation Semantics Plan

## Objective
Replace the current long-only recommendation semantics (`BUY/SELL/HOLD`) with a margin-account aware model and update position ingestion, persistence, prompt contracts, and decision interpretation accordingly.

## Target Recommendation Semantics
- `BUY`: open long
- `SELL`: close long
- `SELL_SHORT`: open short
- `BUY_TO_COVER`: close short
- `MODIFY`: modify/add stop loss and/or take profit

Constraints:
- Every open position must have a stop loss.
- Add config to choose:
  - `long_only`: only `BUY`, `SELL`, `MODIFY`
  - `long_short`: all five actions above.

## Current State Summary (from codebase)
- `TradeDecision` and signal validation are `BUY|SELL|HOLD` only:
  - `tradingagents\position_management\decision_schema.py`
  - `tradingagents\graph\signal_processing.py`
  - `backtest.py`
- Position schema is long-only (`side: "long"`):
  - `tradingagents\position_management\schema.py`
  - `tradingagents\position_management\loader.py`
- Guardrails are long-only trailing-stop checks:
  - `tradingagents\position_management\guardrails.py`
- Prompt contracts and recommendation vocabulary are long-only:
  - `tradingagents\agents\trader\trader.py`
  - `tradingagents\agents\managers\risk_manager.py`
  - `tradingagents\agents\risk_mgmt\*.py`
  - `tradingagents\agents\analysts\*.py` (final proposal hints)
- Current positions are loaded (run/main) but not saved back.
- Backtest lifecycle is long-only with long stop/take semantics.

## Implementation Plan

### 1) Config and shared action contracts
- Add position mode config in `tradingagents\default_config.py`.
- Define shared constants/helpers for allowed actions by mode.
- Ensure mode is available to parser, prompts, and runtime transition logic.

### 2) Position schema + I/O updates
- Extend `PositionConfig` to represent both long and short positions.
- Enforce: `open == true` requires numeric `stop_loss`.
- Update loader validation for new schema.
- Add save helper (paired with loader) for normalized persistence.
- Update `current_positions.example.yaml`.

### 3) Decision schema and parser validation
- Expand `TradeDecision` action enum to include `SELL_SHORT`, `BUY_TO_COVER`, `MODIFY`.
- Update signal parser validation in `signal_processing.py` to:
  - enforce mode-restricted action set
  - enforce position/action coherence
  - enforce mandatory stop-loss for any resulting open position.

### 4) Guardrails (long + short)
- Generalize guardrails to support both open long and open short positions.
- Apply tightening checks for protective stop updates where relevant.
- Keep strict explicit errors for invalid decision payloads.

### 5) Prompt and interpretation changes
- Update trader/risk prompts to use new action vocabulary and rules.
- Update analyst “FINAL TRANSACTION PROPOSAL” hints to match valid actions.
- Add mode-aware guidance (`long_only` vs `long_short`) and side-aware constraints.

### 6) Runtime load/save + decision application
- Update `run.py`, `main.py`, and CLI flow to:
  - load positions under new schema
  - pass mode + position context into graph
  - apply structured decision to next position state
  - persist updated positions to a separate output file (keep `current_positions.yaml` immutable as input).

### 7) Backtest margin semantics
- Extend transitions for short open/close actions and `MODIFY`.
- Add short-side stop/take trigger handling.
- Preserve/extend output status fields consistently.

### 8) Tests + documentation
- Update tests:
  - `tests\test_signal_processing.py`
  - `tests\test_backtest_phase5.py`
- Add/adjust tests for:
  - mode-restricted actions
  - mandatory stop-loss
  - short lifecycle and guardrails
  - `MODIFY` behavior.
- Update README and position-management docs.

## Planned Todos
1. `add-position-mode-config`
2. `extend-position-schema-loader-saver`
3. `expand-decision-schema-and-parser`
4. `generalize-guardrails`
5. `revise-agent-prompts`
6. `wire-runtime-position-persistence`
7. `adapt-backtest-for-margin-actions`
8. `update-tests-and-docs`

## Confirmed Decision
Updated positions should be written to a separate output file; `current_positions.yaml` remains input-only.
