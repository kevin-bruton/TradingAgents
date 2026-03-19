from tradingagents.position_management import (
    POSITION_MODE_LONG_ONLY,
    format_allowed_decisions_for_mode,
    normalize_position_mode,
)
from tradingagents.position_management.prompt_context import format_position_context


def create_risk_manager(llm, memory):
    def risk_manager_node(state) -> dict:
        company_name = state["company_of_interest"]

        history = state["risk_debate_state"]["history"]
        risk_debate_state = state["risk_debate_state"]
        market_research_report = state["market_report"]
        news_report = state["news_report"]
        fundamentals_report = state["fundamentals_report"]
        sentiment_report = state["sentiment_report"]
        trader_plan = state["investment_plan"]
        current_position = state.get("current_position")
        position_mode = normalize_position_mode(state.get("position_mode", "long_short"))
        position_context = format_position_context(current_position, position_mode)
        position_is_open = bool(current_position and current_position.get("open"))
        position_side = str(current_position.get("side", "long")) if current_position else "long"

        curr_situation = f"{market_research_report}\n\n{sentiment_report}\n\n{news_report}\n\n{fundamentals_report}"
        past_memories = memory.get_memories(curr_situation, n_matches=2)

        past_memory_str = ""
        for i, rec in enumerate(past_memories, 1):
            past_memory_str += rec["recommendation"] + "\n\n"

        position_rules = _build_position_rules(
            position_mode=position_mode,
            position_is_open=position_is_open,
            position_side=position_side,
        )
        allowed_decisions = format_allowed_decisions_for_mode(position_mode)
        allowed_decisions_schema = " | ".join(allowed_decisions.split("/"))

        prompt = f"""As the Risk Management Judge and Debate Facilitator, your goal is to evaluate the debate between three risk analysts—Aggressive, Neutral, and Conservative—and determine the best course of action for the trader. Your decision must result in a clear recommendation using the allowed action set for this run. Strive for clarity and decisiveness.

Guidelines for Decision-Making:
1. **Summarize Key Arguments**: Extract the strongest points from each analyst, focusing on relevance to the context.
2. **Provide Rationale**: Support your recommendation with direct quotes and counterarguments from the debate.
3. **Refine the Trader's Plan**: Start with the trader's original plan, **{trader_plan}**, and adjust it based on the analysts' insights.
4. **Learn from Past Mistakes**: Use lessons from **{past_memory_str}** to address prior misjudgments and improve this decision.
5. **Score Confidence Explicitly**: Include `confidence_pct` (0-100) based on:
   - indicator confluence across market, sentiment, news, and fundamentals reports
   - debate confluence across aggressive/neutral/conservative arguments and rebuttals
   For BUY and SELL_SHORT entries, this score should represent the estimated chance the trade direction is profitable on the next trading day.

Current position context:
{position_context}

Position handling rules:
{position_rules}

Deliverables:
- A clear and actionable recommendation using one allowed decision.
- Detailed reasoning anchored in the debate and past reflections.
- Exactly one authoritative JSON block in fenced ```json``` format using this schema:
```json
{{
  "decision": "{allowed_decisions_schema}",
  "stop_loss": <number or null>,
  "take_profit": <number or null>,
  "confidence_pct": <number from 0 to 100>,
  "rationale": "<debate + memory grounded rationale with confidence justification>"
}}
```

JSON requirements:
- `decision` must be uppercase and one of: {allowed_decisions}.
- `confidence_pct` must be numeric and within [0, 100], no percent sign.
- `rationale` must reference analyst debate, past memory lessons, and explain why the confidence score is justified.
- For close actions, set `stop_loss` and `take_profit` to null.
- The JSON block is the authoritative final output and must be present exactly once.

---

**Analysts Debate History:**  
{history}

---

Focus on actionable insights and continuous improvement. Build on past lessons, critically evaluate all perspectives, and ensure each decision advances better outcomes for {company_name}."""

        response = llm.invoke(prompt)

        new_risk_debate_state = {
            "judge_decision": response.content,
            "history": risk_debate_state["history"],
            "aggressive_history": risk_debate_state["aggressive_history"],
            "conservative_history": risk_debate_state["conservative_history"],
            "neutral_history": risk_debate_state["neutral_history"],
            "latest_speaker": "Judge",
            "current_aggressive_response": risk_debate_state["current_aggressive_response"],
            "current_conservative_response": risk_debate_state["current_conservative_response"],
            "current_neutral_response": risk_debate_state["current_neutral_response"],
            "count": risk_debate_state["count"],
        }

        return {
            "risk_debate_state": new_risk_debate_state,
            "final_trade_decision": response.content,
        }

    return risk_manager_node


def _build_position_rules(
    *,
    position_mode: str,
    position_is_open: bool,
    position_side: str,
) -> str:
    if position_mode == POSITION_MODE_LONG_ONLY:
        if position_is_open:
            return """- A long position is currently open.
- Use SELL to close the long position (set stop_loss and take_profit to null).
- Use MODIFY to adjust stop_loss and/or take_profit while keeping the position open.
- The open position must have numeric stop_loss after MODIFY."""
        return """- No position is currently open.
- Use BUY to open a long position.
- BUY must include numeric stop_loss (take_profit optional).
- SELL and MODIFY are invalid when no long position is open."""

    if not position_is_open:
        return """- No position is currently open.
- Use BUY to open long or SELL_SHORT to open short.
- BUY and SELL_SHORT must include numeric stop_loss (take_profit optional)."""

    if position_side == "long":
        return """- A long position is currently open.
- Use SELL to close long (set stop_loss and take_profit to null).
- Use MODIFY to adjust stop_loss and/or take_profit while staying long.
- Open positions must keep numeric stop_loss."""

    return """- A short position is currently open.
- Use BUY_TO_COVER to close short (set stop_loss and take_profit to null).
- Use MODIFY to adjust stop_loss and/or take_profit while staying short.
- Open positions must keep numeric stop_loss."""
