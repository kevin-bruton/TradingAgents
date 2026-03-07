import functools
import time
import json

from tradingagents.position_management.prompt_context import format_position_context


def create_trader(llm, memory):
    def trader_node(state, name):
        company_name = state["company_of_interest"]
        investment_plan = state["investment_plan"]
        market_research_report = state["market_report"]
        sentiment_report = state["sentiment_report"]
        news_report = state["news_report"]
        fundamentals_report = state["fundamentals_report"]
        current_position = state.get("current_position")
        position_context = format_position_context(current_position)
        position_is_open = bool(current_position and current_position.get("open"))

        curr_situation = f"{market_research_report}\n\n{sentiment_report}\n\n{news_report}\n\n{fundamentals_report}"
        past_memories = memory.get_memories(curr_situation, n_matches=2)

        past_memory_str = ""
        if past_memories:
            for i, rec in enumerate(past_memories, 1):
                past_memory_str += rec["recommendation"] + "\n\n"
        else:
            past_memory_str = "No past memories found."

        if position_is_open:
            position_guidance = """- There is currently an open long position.
- If you recommend HOLD or BUY, include a numeric stop_loss and optionally a take_profit.
- If you recommend SELL to close the position, set stop_loss and take_profit to null.
- Any updated stop_loss for an open position must maintain or tighten the existing stop; do not loosen it."""
        else:
            position_guidance = """- There is no open position right now.
- Include stop_loss (required) and take_profit (optional) only when recommending BUY.
- If recommending HOLD or SELL when no position is open, set stop_loss and take_profit to null."""

        context = {
            "role": "user",
            "content": f"Based on a comprehensive analysis by a team of analysts, here is an investment plan tailored for {company_name}. This plan incorporates insights from current technical market trends, macroeconomic indicators, and social media sentiment. Use this plan as a foundation for evaluating your next trading decision.\n\nProposed Investment Plan: {investment_plan}\n\n{position_context}\n\nPosition-aware requirements:\n{position_guidance}\n\nLeverage these insights to make an informed and strategic decision.",
        }

        messages = [
            {
                "role": "system",
                "content": f"""You are a trading agent analyzing market data to make investment decisions. Based on your analysis, provide a specific recommendation to buy, sell, or hold. Do not forget to utilize lessons from past decisions to learn from your mistakes. Here is some reflections from similar situations you traded in and the lessons learned: {past_memory_str}

Output requirements (mandatory):
1. Provide concise reasoning.
2. Include the line: FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL**
3. End with exactly one fenced JSON block using this schema:
```json
{{
  "decision": "BUY | SELL | HOLD",
  "stop_loss": <number or null>,
  "take_profit": <number or null>,
  "confidence_pct": <number from 0 to 100>,
  "rationale": "<brief rationale>"
}}
```

JSON rules:
- `decision` must be uppercase BUY, SELL, or HOLD.
- `confidence_pct` must be numeric in [0, 100] with no percent sign.
- `rationale` must explain key evidence and risk/reward reasoning.
- Always obey the position-aware requirements supplied by the user context.
- Do not output more than one JSON block.""",
            },
            context,
        ]

        result = llm.invoke(messages)

        return {
            "messages": [result],
            "trader_investment_plan": result.content,
            "sender": name,
        }

    return functools.partial(trader_node, name="Trader")
