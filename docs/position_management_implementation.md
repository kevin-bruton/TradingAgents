# Position Management Detailed Implementation Plan

## Problem Statement
Implement position-aware decisioning so TradingAgents can ingest open positions, produce structured decisions with stop loss/take profit, enforce trailing-stop guardrails, and propagate those outputs through run flows and backtesting.

## Selected Options (from Alternatives & Tradeoffs)
1. Decision format: **Structured JSON output** from risk manager (`{decision, stop_loss, take_profit, rationale}`)
2. Stop-loss computation: **LLM-generated recommendations with code guardrails**
3. Backtest handling: **Simulated position lifecycle** across dates
4. Missing `current_positions.yaml`: **Fail fast with explicit error**

## Scope Boundaries
- In scope: long-position workflow, position ingestion, state plumbing, prompt updates, structured parsing, guardrails, CLI/run/backtest output updates, docs
- Out of scope (defer): short-selling support, external historical position import, advanced stop engines (ATR/support-resistance)

## Phase 1 - Position Ingestion and State Plumbing

### Tasks
1. Add `pyyaml` dependency in `pyproject.toml` and `requirements.txt`
2. Add new loader utility (e.g., `tradingagents/position_management/loader.py`):
   - Load YAML once
   - Validate schema and types
   - Normalize symbols (uppercase)
   - Return position map keyed by symbol
3. Define schema for each symbol:
   - `open: bool`
   - `stop_loss: float | null`
   - `take_profit: float | null`
   - optional `side: "long"` (default long)
4. Extend `AgentState` (`tradingagents/agents/utils/agent_states.py`) with `current_position`
5. Update `Propagator.create_initial_state` to accept and inject `current_position`
6. Update `TradingAgentsGraph.propagate(company_name, trade_date, current_position=None)` and pass through to propagator

### Dependencies
- None (foundation phase)

### Validation
- Import checks for new loader
- Backward compatibility check: existing `propagate(symbol, date)` still works

## Phase 2 - Prompt and Node Behavior Updates

### Tasks
1. Update trader prompt (`tradingagents/agents/trader/trader.py`):
   - If position open: include current stop/take-profit context
   - If position closed: include stop/take-profit only when recommending BUY
   - Require trader output to include a JSON block with decision fields
2. Update risk analysts (`tradingagents/agents/risk_mgmt/*.py`):
   - Explicitly critique stop-loss/take-profit quality
   - Evaluate trailing-stop compliance when position is open
3. Update risk manager (`tradingagents/agents/managers/risk_manager.py`):
   - Produce final structured JSON block (authoritative output)
   - Include rationale referencing analyst debate + past memory
4. Optional coherence update in research manager (`tradingagents/agents/managers/research_manager.py`) to mention existing exposure when open

### Dependencies
- Phase 1 complete

### Validation
- Prompt snapshots/manual dry-runs confirm JSON block instructions exist in trader and risk manager

## Phase 3 - Structured Parsing and Guardrails

### Tasks
1. Replace decision-only extraction in `tradingagents/graph/signal_processing.py` with deterministic structured parsing:
   - Extract JSON block
   - Parse and validate required keys
   - Return typed decision dict
2. Add trailing-stop guardrail utility:
   - For open long positions, new `stop_loss` cannot be looser than current stop relative to current price
   - If violation, clamp to existing stop and append a system warning in rationale
3. Wire guardrails into `TradingAgentsGraph.propagate` after risk manager output parsing
4. Keep strict error handling:
   - Invalid structured output should raise explicit parse/validation error (no silent success fallback)

### Dependencies
- Phase 2 complete

### Validation
- Unit-style checks for parser and guardrail edge cases

## Phase 4 - Runtime and Output Plumbing

### Tasks
1. Update `run.py`:
   - Load `current_positions.yaml` at startup
   - Pass per-symbol `current_position` into `propagate`
   - Display decision + stop_loss + take_profit when present
2. Update `main.py` similarly for single-symbol flow
3. Update `cli/main.py`:
   - Surface structured decision details in final summary/report output
   - Include stop/take-profit fields in saved report sections where appropriate
4. Update state logging in `tradingagents/graph/trading_graph.py` to include `current_position` and parsed decision dict

### Dependencies
- Phase 3 complete

### Validation
- Manual run confirms visible structured outputs and log persistence

## Phase 5 - Backtest Adaptation

### Tasks
1. Update `backtest.py` to maintain simulated position state per symbol/date
2. Apply decision transitions:
   - BUY opens or maintains position
   - SELL closes position
   - HOLD preserves current state
3. Apply stop/take-profit checks against historical price range to trigger closes
4. Extend CSV outputs with at least:
   - `date`, `decision`, `stop_loss`, `take_profit`, `position_status`, `rationale`

### Dependencies
- Phases 1-4 complete

### Validation
- Backtest output schema verification and lifecycle sanity checks across date range

## Phase 6 - Documentation and Operational Readiness

### Tasks
1. Add/refresh docs for `current_positions.yaml` schema and fail-fast behavior
2. Document trailing-stop guardrail behavior and clamping rationale
3. Add example position file template (or documented sample snippet)
4. Ensure README/run instructions include position-aware workflow

### Dependencies
- Phases 1-5 complete

### Validation
- Docs align with actual runtime arguments/output fields

## Cross-Cutting Risks and Mitigations
- Invalid YAML or missing fields -> strict validation with actionable errors
- LLM emits malformed JSON -> explicit parser error with clear remediation guidance
- Guardrail ambiguity around price source -> document and standardize source (latest close/intraday feed used by run mode)
- Behavior drift across run/main/cli/backtest -> centralize parser + guardrail logic and reuse everywhere

## Execution Order Summary
1. Dependencies + loader + state/propagate signatures
2. Prompt changes (trader, risk analysts, risk manager)
3. Structured parser + guardrail enforcement
4. run/main/CLI/logging plumbing
5. backtest simulation updates
6. docs finalization
