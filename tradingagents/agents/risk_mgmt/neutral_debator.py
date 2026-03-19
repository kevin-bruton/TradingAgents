import time
import json

from tradingagents.position_management import (
    POSITION_MODE_LONG_ONLY,
    normalize_position_mode,
)
from tradingagents.position_management.prompt_context import format_position_context


def create_neutral_debator(llm):
    def neutral_node(state) -> dict:
        risk_debate_state = state["risk_debate_state"]
        history = risk_debate_state.get("history", "")
        neutral_history = risk_debate_state.get("neutral_history", "")

        current_aggressive_response = risk_debate_state.get("current_aggressive_response", "")
        current_conservative_response = risk_debate_state.get("current_conservative_response", "")

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
                stop_guidance = """- Evaluate whether SELL vs MODIFY is appropriate for the open long position.
- For MODIFY, ensure stop_loss remains numeric and risk protection is not loosened."""
            else:
                stop_guidance = """- With no open long position, only BUY is coherent.
- BUY must include numeric stop_loss."""
        elif not position_is_open:
            stop_guidance = """- With no open exposure, only BUY or SELL_SHORT should be proposed.
- Entry actions must include numeric stop_loss."""
        elif position_side == "long":
            stop_guidance = """- With an open long position, only SELL or MODIFY is coherent.
- For MODIFY, ensure stop_loss remains numeric and does not loosen."""
        else:
            stop_guidance = """- With an open short position, only BUY_TO_COVER or MODIFY is coherent.
- For MODIFY, ensure stop_loss remains numeric and does not loosen."""

        prompt = f"""As the Neutral Risk Analyst, your role is to provide a balanced perspective, weighing both the potential benefits and risks of the trader's decision or plan. You prioritize a well-rounded approach, evaluating the upsides and downsides while factoring in broader market trends, potential economic shifts, and diversification strategies.

Current position context:
{position_context}

Here is the trader's decision:

{trader_decision}

Your task is to challenge both the Aggressive and Conservative Analysts, pointing out where each perspective may be overly optimistic or overly cautious. You must explicitly assess stop-loss and take-profit quality, including whether the levels are balanced and executable. Use insights from the following data sources to support a moderate, sustainable strategy to adjust the trader's decision:

Current Price: {current_price}
Market Research Report: {market_research_report}
Social Media Sentiment Report: {sentiment_report}
Latest World Affairs Report: {news_report}
Company Fundamentals Report: {fundamentals_report}
Here is the current conversation history: {history} Here is the last response from the aggressive analyst: {current_aggressive_response} Here is the last response from the conservative analyst: {current_conservative_response}. If there are no responses from the other viewpoints, do not hallucinate and just present your point.

Position handling requirements:
{stop_guidance}

Engage actively by analyzing both sides critically, addressing weaknesses in the aggressive and conservative arguments to advocate for a more balanced approach. Challenge each of their points to illustrate why a moderate risk strategy might offer the best of both worlds, providing growth potential while safeguarding against extreme volatility. Focus on debating rather than simply presenting data, aiming to show that a balanced view can lead to the most reliable outcomes. Output conversationally as if you are speaking without any special formatting."""

        response = llm.invoke(prompt)

        argument = f"Neutral Analyst: {response.content}"

        new_risk_debate_state = {
            "history": history + "\n" + argument,
            "aggressive_history": risk_debate_state.get("aggressive_history", ""),
            "conservative_history": risk_debate_state.get("conservative_history", ""),
            "neutral_history": neutral_history + "\n" + argument,
            "latest_speaker": "Neutral",
            "current_aggressive_response": risk_debate_state.get(
                "current_aggressive_response", ""
            ),
            "current_conservative_response": risk_debate_state.get("current_conservative_response", ""),
            "current_neutral_response": argument,
            "count": risk_debate_state["count"] + 1,
        }

        return {"risk_debate_state": new_risk_debate_state}

    return neutral_node
