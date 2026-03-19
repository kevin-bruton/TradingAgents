import functools

from tradingagents.position_management import (
    POSITION_MODE_LONG_ONLY,
    format_allowed_decisions_for_mode,
    normalize_position_mode,
)
from tradingagents.position_management.prompt_context import format_position_context


def create_trader(llm, memory):
    def trader_node(state, name):
        company_name = state["company_of_interest"]
        investment_plan = state["investment_plan"]
        market_research_report = state["market_report"]
        sentiment_report = state["sentiment_report"]
        news_report = state["news_report"]
        fundamentals_report = state["fundamentals_report"]
        current_price = state.get("current_price", "Unknown")
        current_position = state.get("current_position")
        position_mode = normalize_position_mode(state.get("position_mode", "long_short"))
        position_context = format_position_context(current_position, position_mode)
        position_is_open = bool(current_position and current_position.get("open"))
        position_side = str(current_position.get("side", "long")) if current_position else "long"

        curr_situation = f"{market_research_report}\n\n{sentiment_report}\n\n{news_report}\n\n{fundamentals_report}\n\nCurrent Price: {current_price}"
        past_memories = memory.get_memories(curr_situation, n_matches=2)

        past_memory_str = ""
        if past_memories:
            for i, rec in enumerate(past_memories, 1):
                past_memory_str += rec["recommendation"] + "\n\n"
        else:
            past_memory_str = "No past memories found."

        position_guidance = _build_position_guidance(
            position_mode=position_mode,
            position_is_open=position_is_open,
            position_side=position_side,
        )
        allowed_decisions = format_allowed_decisions_for_mode(position_mode)
        allowed_decisions_schema = " | ".join(allowed_decisions.split("/"))

        context = {
            "role": "user",
            "content": f"Based on a comprehensive analysis by a team of analysts, here is an investment plan tailored for {company_name}. This plan incorporates insights from current technical market trends, macroeconomic indicators, and social media sentiment. Use this plan as a foundation for evaluating your next trading decision.\n\nProposed Investment Plan: {investment_plan}\n\nCurrent Price: {current_price}\n\n{position_context}\n\nPosition-aware requirements:\n{position_guidance}\n\nLeverage these insights to make an informed and strategic decision.",
        }

        messages = [
            {
                "role": "system",
                "content": f"""You are a trading agent analyzing market data to make investment decisions. Based on your analysis, provide a specific recommendation aligned to margin-aware execution semantics. Do not forget to utilize lessons from past decisions to learn from your mistakes. Here is some reflections from similar situations you traded in and the lessons learned: {past_memory_str}

Output requirements (mandatory):
1. Provide concise reasoning.
2. Include the line: FINAL TRANSACTION PROPOSAL: **{allowed_decisions}**
3. End with exactly one fenced JSON block using this schema:
```json
{{
  "decision": "{allowed_decisions_schema}",
  "stop_loss": <number or null>,
  "take_profit": <number or null>,
  "confidence_pct": <number from 0 to 100>,
  "rationale": "<brief rationale>"
}}
```

JSON rules:
- `decision` must be uppercase and one of: {allowed_decisions}.
- `confidence_pct` must be numeric in [0, 100] with no percent sign.
- `rationale` must explain key evidence and risk/reward reasoning.
- Always obey the position-aware requirements supplied by the user context.
- For close actions, set `stop_loss` and `take_profit` to null.
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


def _build_position_guidance(
    *,
    position_mode: str,
    position_is_open: bool,
    position_side: str,
) -> str:
    if position_mode == POSITION_MODE_LONG_ONLY:
        if position_is_open:
            return """- There is currently an open long position.
- Valid decisions are SELL (close long) or MODIFY (adjust stop_loss and/or take_profit).
- SELL must set stop_loss and take_profit to null.
- MODIFY must leave the position with a numeric stop_loss."""
        return """- There is no open position right now.
- Valid decision is BUY (open long).
- BUY must include numeric stop_loss and may include take_profit.
- SELL and MODIFY are invalid when no long position is open."""

    if not position_is_open:
        return """- There is no open position right now.
- Valid decisions are BUY (open long) or SELL_SHORT (open short).
- BUY and SELL_SHORT must include numeric stop_loss and may include take_profit."""

    if position_side == "long":
        return """- There is currently an open long position.
- Valid decisions are SELL (close long) or MODIFY (adjust stop_loss and/or take_profit).
- SELL must set stop_loss and take_profit to null.
- MODIFY must keep or set a numeric stop_loss."""

    return """- There is currently an open short position.
- Valid decisions are BUY_TO_COVER (close short) or MODIFY (adjust stop_loss and/or take_profit).
- BUY_TO_COVER must set stop_loss and take_profit to null.
- MODIFY must keep or set a numeric stop_loss."""
