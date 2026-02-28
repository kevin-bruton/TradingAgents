# Copilot instructions

## Build and test
- Install dependencies: `pip install -r requirements.txt`
- Run the CLI (interactive): `python -m cli.main` or `tradingagents`
- Single test/smoke run: `python test.py`

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
