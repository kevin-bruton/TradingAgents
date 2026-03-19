# Copilot instructions

## Build and test
- Install dependencies: `uv sync`
- Run the CLI (interactive): `uv run -m cli.main` or `tradingagents`

## Architecture (high level)
- `TradingAgentsGraph` (tradingagents/graph/trading_graph.py) orchestrates a LangGraph StateGraph of analyst, researcher, trader, and risk nodes. `GraphSetup` wires the nodes and edges, `ConditionalLogic` drives loop/stop decisions, `Propagator` initializes state, and `Reflector`/`SignalProcessor` post-process outputs.
- Agent implementations live under `tradingagents/agents/*` and are constructed via `create_*` factories exported from `tradingagents/agents/__init__.py`.
- Data tools are abstracted in `tradingagents/agents/utils/*` and routed through `tradingagents/dataflows/interface.py` to vendor backends (`y_finance.py`, `alpha_vantage.py`) using the active config.
- LLM provider wiring is centralized in `tradingagents/llm_clients/*` with `factory.create_llm_client`, which maps provider names to the correct client class.

## Key conventions
- Start from `DEFAULT_CONFIG.copy()` and pass the config into `TradingAgentsGraph`; the graph calls `dataflows.config.set_config` so tool routing reads the same config.
- Data vendor selection uses `data_vendors` (category defaults) and `tool_vendors` (per-tool overrides); values can be comma-separated to enable fallback order. Alpha Vantage rate limits trigger automatic vendor fallback.
- Agent state fields must match `AgentState`/`InvestDebateState`/`RiskDebateState` in `agents/utils/agent_states.py` because LangGraph state wiring depends on those keys.
- `.env` is loaded via `dotenv` in CLI/scripts; keep API keys in `.env` (see `.env.example`).

## Position management and recommendation semantics
- Recommendation semantics are mode-aware via `config["position_mode"]`:
  - `long_only`: `BUY` (open long), `SELL` (close long), `MODIFY` (update stop/take on open long)
  - `long_short`: `BUY`, `SELL`, `SELL_SHORT` (open short), `BUY_TO_COVER` (close short), `MODIFY`
- Open positions must always have numeric `stop_loss`; this is enforced in loader, signal validation, and guardrails.
- Position schema lives in `tradingagents/position_management/schema.py` and loader/saver logic is in `tradingagents/position_management/loader.py`.
- Use `apply_decision_to_position` and related helpers in `tradingagents/position_management/actions.py` for decision-to-position transitions instead of re-implementing action logic.
- `run.py` and `main.py` load from `current_positions.yaml` and persist updated state to `current_positions.updated.yaml` (input file remains immutable).
