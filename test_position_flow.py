import pytest
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

@pytest.mark.skip(reason="Integration style test requires API keys and network access")
def test_initial_state_includes_position():
    cfg = DEFAULT_CONFIG.copy()
    cfg["llm_provider"] = "openai"  # or mock provider if available
    cfg["quick_think_llm"] = cfg.get("quick_think_llm", "gpt-4o-mini")
    cfg["deep_think_llm"] = cfg.get("deep_think_llm", "gpt-4o")

    graph = TradingAgentsGraph(config=cfg)
    # We won't actually run LLM calls; just inspect initial state creation
    init_state = graph.propagator.create_initial_state(
        "AAPL", "2025-09-30", user_position="long", cost_per_trade=2.0, initial_stop_loss=150.0, initial_take_profit=175.0
    )
    assert init_state["user_position"] == "long"
    assert init_state["current_position_stop_loss"] == 150.0
    assert init_state["current_position_take_profit"] == 175.0
