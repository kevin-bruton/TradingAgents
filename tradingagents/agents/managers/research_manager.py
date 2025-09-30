import time
import json
from tradingagents.agents.utils.safe_llm import safe_invoke_llm


def create_research_manager(llm, memory):
    def research_manager_node(state) -> dict:
        history = state["investment_debate_state"].get("history", "")
        market_research_report = state["market_report"]
        sentiment_report = state["sentiment_report"]
        news_report = state["news_report"]
        fundamentals_report = state["fundamentals_report"]

        investment_debate_state = state["investment_debate_state"]

        curr_situation = f"{market_research_report}\n\n{sentiment_report}\n\n{news_report}\n\n{fundamentals_report}"
        past_memories = memory.get_memories(curr_situation, n_matches=2)

        past_memory_str = ""
        for i, rec in enumerate(past_memories, 1):
            past_memory_str += rec["recommendation"] + "\n\n"

        user_position = state.get("user_position", "none")
        cost_per_trade = state.get("cost_per_trade", 0.0)

        prompt = f"""As the portfolio manager and debate facilitator, your role is to critically evaluate this round of debate and make a definitive decision. Your recommendation will depend on the user's current position on the ticker and the trading cost per operation.

- The user has a current position of '{user_position}' and the cost per trade is {cost_per_trade}.
- If the user has an open long position, your recommendation can be to maintain the long position, close the long position, or close the long position and open a short position.
- If the user has an open short position, your recommendation can be to maintain the short position, close the short position, or close the short position and open a long position.
- If the user has no open position, your recommendation can be to do nothing, open a long position, or open a short position.

Summarize the key points from both sides concisely, focusing on the most compelling evidence or reasoning. Your recommendation must be clear and actionable. Avoid defaulting to a neutral stance simply because both sides have valid points; commit to a stance grounded in the debate's strongest arguments. Take into account that any transaction will incur a cost of {cost_per_trade}, so the potential profit of a transaction must be greater than this cost.

Additionally, develop a detailed investment plan for the trader. This should include:

Your Recommendation: A decisive stance supported by the most convincing arguments, tailored to the user's position of '{user_position}' and the trading cost of {cost_per_trade}.
Rationale: An explanation of why these arguments lead to your conclusion.
Strategic Actions: Concrete steps for implementing the recommendation.
Take into account your past mistakes on similar situations. Use these insights to refine your decision-making and ensure you are learning and improving. Present your analysis conversationally, as if speaking naturally, without special formatting. 

Here are your past reflections on mistakes:
\"{past_memory_str}\"

Here is the debate:
Debate History:
{history}"""
        response = safe_invoke_llm(llm, prompt)

        new_investment_debate_state = {
            "judge_decision": response.content,
            "history": investment_debate_state.get("history", ""),
            "bear_history": investment_debate_state.get("bear_history", ""),
            "bull_history": investment_debate_state.get("bull_history", ""),
            "current_response": response.content,
            "count": investment_debate_state["count"],
        }

        return {
            "investment_debate_state": new_investment_debate_state,
            "investment_plan": response.content,
        }

    return research_manager_node
