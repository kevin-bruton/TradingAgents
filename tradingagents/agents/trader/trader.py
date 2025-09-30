import functools
import time
import json
from tradingagents.agents.utils.safe_llm import safe_invoke_llm


def create_trader(llm, memory):
    def trader_node(state, name):
        company_name = state["company_of_interest"]
        investment_plan = state["investment_plan"]
        market_research_report = state["market_report"]
        sentiment_report = state["sentiment_report"]
        news_report = state["news_report"]
        fundamentals_report = state["fundamentals_report"]

        curr_situation = f"{market_research_report}\n\n{sentiment_report}\n\n{news_report}\n\n{fundamentals_report}"
        past_memories = memory.get_memories(curr_situation, n_matches=2)

        past_memory_str = ""
        if past_memories:
            for i, rec in enumerate(past_memories, 1):
                past_memory_str += rec["recommendation"] + "\n\n"
        else:
            past_memory_str = "No past memories found."

        user_position = state.get("user_position", "none")
        cost_per_trade = state.get("cost_per_trade", 0.0)

        stop_loss = state.get("stop_loss")
        take_profit = state.get("take_profit")

        context = {
            "role": "user",
            "content": f"Based on a comprehensive analysis by a team of analysts, here is an investment plan tailored for {company_name}. This plan incorporates insights from current technical market trends, macroeconomic indicators, and social media sentiment. Use this plan as a foundation for evaluating your next trading decision.\n\nProposed Investment Plan: {investment_plan}\n\nThe Trade Planner has proposed a stop-loss of **{stop_loss}** and a take-profit of **{take_profit}**. You must consider these levels in your final recommendation.\n\nLeverage these insights to make an informed and strategic decision.",
        }

        messages = [
            {
                "role": "system",
                "content": f"""You are a trading agent analyzing market data to make investment decisions. Your recommendation will depend on the user's current position on the ticker and the trading cost per operation.

- The user has a current position of '{user_position}' and the cost per trade is {cost_per_trade}.
- If the user has an open long position, your recommendation can be to maintain the long position, close the long position, or close the long position and open a short position.
- If the user has an open short position, your recommendation can be to maintain the short position, close the short position, or close the short position and open a long position.
- If the user has no open position, your recommendation can be to do nothing, open a long position, or open a short position.

Based on your analysis, provide a specific recommendation. End with a firm decision and always conclude your response with 'FINAL TRANSACTION PROPOSAL: **YOUR_RECOMMENDATION**' to confirm your recommendation. Take into account that any transaction will incur a cost of {cost_per_trade}, so the potential profit of a transaction must be greater than this cost. Do not forget to utilize lessons from past decisions to learn from your mistakes. Here is some reflections from similar situations you traded in and the lessons learned: {past_memory_str}
Your output should always be in markdown format.""",
            },
            context,
        ]
        result = safe_invoke_llm(llm, messages)

        return {
            "messages": [result],
            "trader_investment_plan": result.content,
            "sender": name,
        }

    return functools.partial(trader_node, name="Trader")
