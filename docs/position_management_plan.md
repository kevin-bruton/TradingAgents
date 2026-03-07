# Position Management Implementation Plan

## Problem & Goal
Add position-aware trade recommendations so the system reads current open positions, evaluates stop loss/take profit levels, and returns structured decisions that include those levels when applicable. Ensure trailing stop logic never loosens an existing stop, and update backtesting to evaluate the new outputs.

## Assumptions / Clarifications
- HOLD with no open position means stay out (per user confirmation); no stop loss/take profit required in that case.
- Positions are long-only by default; if shorts are needed, extend schema and trailing-stop logic.
- Stop loss / take profit are absolute price levels (not percentages).

## Approach
1. Position ingestion
   - Define current_positions.yaml schema (symbol -> open flag + stop_loss + optional take_profit).
   - Add PyYAML dependency and a small loader utility with validation and helpful errors.
   - In run.py, read current_positions.yaml once and pass per-symbol position info into propagate.

2. State and propagation updates
   - Extend AgentState with a current_position field (open, stop_loss, take_profit, optional side).
   - Update Propagator.create_initial_state to include current_position.
   - Update TradingAgentsGraph.propagate to accept current_position (optional) and pass it into the initial state.

3. Agent behavior changes (position-aware)
   - Trader: include current position context; if open, propose a to maintain current stop loss or a tightened stop loss (never farther from current price) and optionally adjust take profit; if not open, include stop loss/take profit only for BUY decisions (per clarification).
   - Risk analysts (aggressive/neutral/conservative): critique and refine stop loss/take profit rationale, explicitly consider trailing-stop constraints.
   - Risk manager: produce final decision that includes decision, stop_loss, take_profit (if any) and a brief rationale; remind that reviews happen pre-market each day.
   - Research manager: optionally reference position status to align the investment plan with existing exposure (not required but improves coherence).

4. Stop loss guardrails and output parsing
   - Require structured final decision output (JSON-like block) from the risk manager, e.g. {decision, stop_loss, take_profit, rationale}.
   - Update SignalProcessor to parse the structured block deterministically (no LLM extraction), returning a dict.
   - Enforce trailing-stop rule in code: if position is open, new stop_loss cannot be farther from current price than existing; clamp or reject with a warning in decision rationale.

5. Output plumbing
   - Update ta.propagate to return (final_state, decision_dict) with decision, stop_loss, take_profit.
   - Update run.py/main.py and CLI display/output to include stop loss/take profit fields when present.
   - Log stop loss/take profit into eval_results state logs for traceability.

6. Backtest adaptation
   - Simulate positions across dates: maintain open/closed state and stop loss/take profit from prior decisions; apply daily trailing-stop updates and close when breached using historical prices.
   - Extend backtest outputs to include stop_loss, take_profit, position_status, and any stop adjustments.

## Alternatives & Tradeoffs
- Decision format
  - Structured JSON output (recommended): easy to parse, less brittle.
  - Free-form text + LLM extraction: minimal prompt change, but fragile and harder to validate.
- Stop loss computation source
  - LLM-generated with guardrails (recommended): matches current architecture and reasoning.
  - Deterministic rule (ATR/support levels): more consistent but adds indicator dependencies and less nuanced context.
- Backtest position handling
  - Simulated positions (recommended): fully automated, consistent with decisions; may diverge from real portfolio behavior.
  - External historical positions file: higher fidelity if available, but requires additional data management.
- Missing current_positions.yaml
  - Fail fast with a clear error (recommended): avoids silent assumption errors.
  - Default to all positions closed: easier to run, but risks unintended behavior.

## Todos
1. Add current_positions.yaml schema, loader utility, and PyYAML dependency.
2. Extend AgentState and Propagator; update TradingAgentsGraph.propagate to accept current_position.
3. Update agent prompts to be position-aware and to output stop loss/take profit in structured form.
4. Update SignalProcessor parsing and enforce trailing-stop guardrails.
5. Update run.py/main.py/CLI output to display decision + stop loss/take profit.
6. Adapt backtest.py to simulate position lifecycle and output new fields.
