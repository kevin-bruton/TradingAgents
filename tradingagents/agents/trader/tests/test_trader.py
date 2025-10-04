import types
from tradingagents.agents.trader.trader import create_trader

class DummyLLM:
    def __init__(self, content="FINAL TRANSACTION PROPOSAL: **HOLD**"):
        self._content = content
        self.invocations = []
    def invoke(self, messages):
        self.invocations.append(messages)
        return types.SimpleNamespace(content=self._content)

class DummyMemory:
    def get_memories(self, situation, n_matches=2):
        return [
            {"recommendation": "Lesson: respect stop losses"},
            {"recommendation": "Lesson: avoid overtrading"},
        ]

def test_create_trader_includes_final_transaction_marker():
    llm = DummyLLM()
    memory = DummyMemory()
    trader = create_trader(llm, memory)
    state = {
        'company_of_interest': 'AAPL',
        'investment_plan': 'Enter on pullback to 180',
        'market_report': 'Market trending up',
        'sentiment_report': 'Positive social sentiment',
        'news_report': 'No major news',
        'fundamentals_report': 'Solid earnings',
        'user_position': 'none',
        'cost_per_trade': 1.25,
        'stop_loss': 170,
        'take_profit': 195,
    }
    result = trader(state)
    assert 'trader_investment_plan' in result
    assert 'FINAL TRANSACTION PROPOSAL' in result['trader_investment_plan']
    assert llm.invocations
    assert any('Lesson:' in str(m) for batch in llm.invocations for m in batch)
