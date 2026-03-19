import time
import json

from tradingagents.position_management import (
    POSITION_MODE_LONG_ONLY,
    normalize_position_mode,
)
from tradingagents.position_management.prompt_context import format_position_context


def create_aggressive_debator(llm):
    def aggressive_node(state) -> dict:
        risk_debate_state = state["risk_debate_state"]
        history = risk_debate_state.get("history", "")
        aggressive_history = risk_debate_state.get("aggressive_history", "")

        current_conservative_response = risk_debate_state.get("current_conservative_response", "")
        current_neutral_response = risk_debate_state.get("current_neutral_response", "")

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

        trader_decision = state["trader_investment_plan"]

        if position_mode == POSITION_MODE_LONG_ONLY:
            if position_is_open:
                stop_guidance = """- Evaluate whether SELL vs MODIFY is chosen coherently for an open long position.
- For MODIFY, verify stop_loss remains numeric and does not loosen downside protection."""
            else:
                stop_guidance = """- With no open long position, only BUY is valid.
- BUY must include numeric stop_loss; reject invalid close/modify actions."""
        elif not position_is_open:
            stop_guidance = """- With no open position, only BUY or SELL_SHORT should be proposed.
- Entry actions must include numeric stop_loss; reject close/modify actions without exposure."""
        elif position_side == "long":
            stop_guidance = """- For an open long position, only SELL or MODIFY is coherent.
- For MODIFY, verify stop_loss stays numeric and does not loosen protection."""
        else:
            stop_guidance = """- For an open short position, only BUY_TO_COVER or MODIFY is coherent.
- For MODIFY, verify stop_loss stays numeric and does not loosen protection."""

        prompt = f"""As the Aggressive Risk Analyst, your role is to actively champion high-reward, high-risk opportunities, emphasizing bold strategies and competitive advantages. When evaluating the trader's decision or plan, focus intently on the potential upside, growth potential, and innovative benefits—even when these come with elevated risk. Use the provided market data and sentiment analysis to strengthen your arguments and challenge the opposing views. Specifically, respond directly to each point made by the conservative and neutral analysts, countering with data-driven rebuttals and persuasive reasoning. Highlight where their caution might miss critical opportunities or where their assumptions may be overly conservative.

Current position context:
{position_context}

Here is the trader's decision:

{trader_decision}

Your task is to create a compelling case for the trader's decision by questioning and critiquing the conservative and neutral stances to demonstrate why your high-reward perspective offers the best path forward. You must explicitly evaluate stop-loss and take-profit quality (placement, reward-to-risk, and practical execution) while debating. Incorporate insights from the following sources into your arguments:

Current Price: {current_price}
Market Research Report: {market_research_report}
Social Media Sentiment Report: {sentiment_report}
Latest World Affairs Report: {news_report}
Company Fundamentals Report: {fundamentals_report}
Here is the current conversation history: {history} Here are the last arguments from the conservative analyst: {current_conservative_response} Here are the last arguments from the neutral analyst: {current_neutral_response}. If there are no responses from the other viewpoints, do not hallucinate and just present your point.

Position handling requirements:
{stop_guidance}

Engage actively by addressing any specific concerns raised, refuting the weaknesses in their logic, and asserting the benefits of risk-taking to outpace market norms. Maintain a focus on debating and persuading, not just presenting data. Challenge each counterpoint to underscore why a high-risk approach is optimal. Output conversationally as if you are speaking without any special formatting."""

        response = llm.invoke(prompt)

        argument = f"Aggressive Analyst: {response.content}"

        new_risk_debate_state = {
            "history": history + "\n" + argument,
            "aggressive_history": aggressive_history + "\n" + argument,
            "conservative_history": risk_debate_state.get("conservative_history", ""),
            "neutral_history": risk_debate_state.get("neutral_history", ""),
            "latest_speaker": "Aggressive",
            "current_aggressive_response": argument,
            "current_conservative_response": risk_debate_state.get("current_conservative_response", ""),
            "current_neutral_response": risk_debate_state.get(
                "current_neutral_response", ""
            ),
            "count": risk_debate_state["count"] + 1,
        }

        return {"risk_debate_state": new_risk_debate_state}

    return aggressive_node
