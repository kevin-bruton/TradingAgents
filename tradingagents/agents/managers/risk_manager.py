import time
import json

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
        position_context = format_position_context(current_position)
        position_is_open = bool(current_position and current_position.get("open"))

        curr_situation = f"{market_research_report}\n\n{sentiment_report}\n\n{news_report}\n\n{fundamentals_report}"
        past_memories = memory.get_memories(curr_situation, n_matches=2)

        past_memory_str = ""
        for i, rec in enumerate(past_memories, 1):
            past_memory_str += rec["recommendation"] + "\n\n"

        if position_is_open:
            position_rules = """- A long position is currently open. For BUY/HOLD, include a numeric stop_loss and optional take_profit.
- If closing with SELL, use null for stop_loss and take_profit.
- For an open long, any revised stop_loss must maintain or tighten protection versus the existing stop; do not loosen it."""
        else:
            position_rules = """- No position is currently open.
- If decision is BUY, stop_loss is required and take_profit is optional.
- If decision is HOLD or SELL while no position is open, stop_loss and take_profit must be null."""

        prompt = f"""As the Risk Management Judge and Debate Facilitator, your goal is to evaluate the debate between three risk analysts—Aggressive, Neutral, and Conservative—and determine the best course of action for the trader. Your decision must result in a clear recommendation: Buy, Sell, or Hold. Choose Hold only if strongly justified by specific arguments, not as a fallback when all sides seem valid. Strive for clarity and decisiveness.

Guidelines for Decision-Making:
1. **Summarize Key Arguments**: Extract the strongest points from each analyst, focusing on relevance to the context.
2. **Provide Rationale**: Support your recommendation with direct quotes and counterarguments from the debate.
3. **Refine the Trader's Plan**: Start with the trader's original plan, **{trader_plan}**, and adjust it based on the analysts' insights.
4. **Learn from Past Mistakes**: Use lessons from **{past_memory_str}** to address prior misjudgments and improve the decision you are making now to make sure you don't make a wrong BUY/SELL/HOLD call that loses money.
5. **Score Confidence Explicitly**: Include `confidence_pct` (0-100) based on:
   - indicator confluence across market, sentiment, news, and fundamentals reports
   - debate confluence across aggressive/neutral/conservative arguments and rebuttals
   For long-entry BUY decisions, this score should represent the estimated chance that price moves up enough to be profitable on the next trading day.

Current position context:
{position_context}

Position handling rules:
{position_rules}

Deliverables:
- A clear and actionable recommendation: Buy, Sell, or Hold.
- Detailed reasoning anchored in the debate and past reflections.
- Exactly one authoritative JSON block in fenced ```json``` format using this schema:
```json
{{
  "decision": "BUY | SELL | HOLD",
  "stop_loss": <number or null>,
  "take_profit": <number or null>,
  "confidence_pct": <number from 0 to 100>,
  "rationale": "<debate + memory grounded rationale with confidence justification>"
}}
```

JSON requirements:
- `decision` must be uppercase BUY, SELL, or HOLD.
- `confidence_pct` must be numeric and within [0, 100], no percent sign.
- `rationale` must reference analyst debate, past memory lessons, and explain why the confidence score is justified.
- The JSON block is the authoritative final output and must be present exactly once.

---

**Analysts Debate History:**  
{history}

---

Focus on actionable insights and continuous improvement. Build on past lessons, critically evaluate all perspectives, and ensure each decision advances better outcomes."""

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
