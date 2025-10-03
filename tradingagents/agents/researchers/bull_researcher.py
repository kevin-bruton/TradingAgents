from langchain_core.messages import AIMessage
import time
import json
from tradingagents.agents.utils.safe_llm import safe_invoke_llm


def create_bull_researcher(llm, memory):
    def bull_node(state) -> dict:
        investment_debate_state = state["investment_debate_state"]
        history = investment_debate_state.get("history", "")
        bull_history = investment_debate_state.get("bull_history", "")

        current_response = investment_debate_state.get("current_response", "")
        market_research_report = state["market_report"]
        sentiment_report = state["sentiment_report"]
        news_report = state["news_report"]
        fundamentals_report = state["fundamentals_report"]

        curr_situation = f"{market_research_report}\n\n{sentiment_report}\n\n{news_report}\n\n{fundamentals_report}"
        past_memories = memory.get_memories(curr_situation, n_matches=2)

        past_memory_str = ""
        for i, rec in enumerate(past_memories, 1):
            past_memory_str += rec["recommendation"] + "\n\n"

        user_position = state.get("user_position", "none")
        cost_per_trade = state.get("cost_per_trade", 0.0)

        prompt = f"""You are a Bull Analyst advocating for investing in the stock. Your recommendation will depend on the user's current position on the ticker and the trading cost per operation.

- The user has a current position of '{user_position}' and the cost per trade is {cost_per_trade}.
- If the user has an open long position, your recommendation can be to maintain the long position, close the long position, or close the long position and open a short position.
- If the user has an open short position, your recommendation can be to maintain the short position, close the short position, or close the short position and open a long position.
- If the user has no open position, your recommendation can be to do nothing, open a long position, or open a short position.

Your task is to build a strong, evidence-based case emphasizing growth potential, competitive advantages, and positive market indicators. Leverage the provided research and data to address concerns and counter bearish arguments effectively. Take into account that any transaction will incur a cost of {cost_per_trade}, so the potential profit of a transaction must be greater than this cost.

Key points to focus on:
- Growth Potential: Highlight the company's market opportunities, revenue projections, and scalability.
- Competitive Advantages: Emphasize factors like unique products, strong branding, or dominant market positioning.
- Positive Indicators: Use financial health, industry trends, and recent positive news as evidence.
- Bear Counterpoints: Critically analyze the bear argument with specific data and sound reasoning, addressing concerns thoroughly and showing why the bull perspective holds stronger merit.
- Engagement: Present your argument in a conversational style, engaging directly with the bear analyst's points and debating effectively rather than just listing data.

Resources available:
Market research report: {market_research_report}
Social media sentiment report: {sentiment_report}
Latest world affairs news: {news_report}
Company fundamentals report: {fundamentals_report}
Conversation history of the debate: {history}
Last bear argument: {current_response}
Reflections from similar situations and lessons learned: {past_memory_str}
Use this information to deliver a compelling bull argument, refute the bear's concerns, and engage in a dynamic debate that demonstrates the strengths of the bull position. You must also address reflections and learn from lessons and mistakes you made in the past.

IMPORTANT MARKDOWN FORMATTING GUIDELINES:
- Use 'approximately', 'around', or 'about' instead of the tilde symbol (~) when describing approximate values
- For example, write 'approximately $250' or 'around $250' instead of '~$250'
- If you need to use strikethrough, use double tildes (~~text~~) not single tilde
- This ensures proper markdown rendering in the web interface
"""
        response = safe_invoke_llm(llm, prompt)

        argument = f"Bull Analyst: {response.content}"

        new_investment_debate_state = {
            "history": history + "\n" + argument,
            "bull_history": bull_history + "\n" + argument,
            "bear_history": investment_debate_state.get("bear_history", ""),
            "current_response": argument,
            "count": investment_debate_state["count"] + 1,
        }

        return {"investment_debate_state": new_investment_debate_state}

    return bull_node
