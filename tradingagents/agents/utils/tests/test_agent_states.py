from tradingagents.agents.utils.agent_states import AgentState, InvestDebateState, RiskDebateState

def test_agent_state_typed_fields_presence():
    required = [
        'user_position','cost_per_trade','company_of_interest','trade_date','sender',
        'market_report','sentiment_report','news_report','fundamentals_report',
        'investment_debate_state','investment_plan','trader_investment_plan',
        'risk_debate_state','final_trade_decision','stop_loss','take_profit'
    ]
    anns = getattr(AgentState, '__annotations__', {})
    missing = [k for k in required if k not in anns]
    assert not missing, f"Missing annotations: {missing}"

def test_invest_debate_state_keys():
    expected = {'bull_history','bear_history','history','current_response','judge_decision','count'}
    anns = InvestDebateState.__annotations__
    assert expected.issubset(anns)

def test_risk_debate_state_keys():
    expected = {'risky_history','safe_history','neutral_history','history','latest_speaker',
                'current_risky_response','current_safe_response','current_neutral_response',
                'judge_decision','count'}
    anns = RiskDebateState.__annotations__
    assert expected.issubset(anns)
