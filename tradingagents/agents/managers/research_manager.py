import time
import json

from tradingagents.position_management import (
    POSITION_MODE_LONG_ONLY,
    normalize_position_mode,
)
from tradingagents.position_management.prompt_context import format_position_context


def create_research_manager(llm, memory):
    def research_manager_node(state) -> dict:
        history = state["investment_debate_state"].get("history", "")
        market_research_report = state["market_report"]
        sentiment_report = state["sentiment_report"]
        news_report = state["news_report"]
        fundamentals_report = state["fundamentals_report"]
        current_price = state.get("current_price", "Unknown")
        current_position = state.get("current_position")
        position_mode = normalize_position_mode(state.get("position_mode", "long_short"))
        position_context = format_position_context(current_position, position_mode)
        position_is_open = bool(current_position and current_position.get("open"))

        investment_debate_state = state["investment_debate_state"]

        curr_situation = f"{market_research_report}\n\n{sentiment_report}\n\n{news_report}\n\n{fundamentals_report}\n\nCurrent Price: {current_price}"
        past_memories = memory.get_memories(curr_situation, n_matches=2)

        past_memory_str = ""
        for i, rec in enumerate(past_memories, 1):
            past_memory_str += rec["recommendation"] + "\n\n"

        if position_mode == POSITION_MODE_LONG_ONLY and position_is_open:
            exposure_guidance = (
                "A position is already open. Explicitly account for existing exposure by stating whether to maintain, "
                "modify, or exit using SELL/MODIFY semantics, and ensure your plan is coherent with existing stop_loss/take_profit context."
            )
        elif position_mode == POSITION_MODE_LONG_ONLY:
            exposure_guidance = (
                "No position is currently open. Focus on whether to initiate long exposure (BUY) with a stop_loss; "
                "do not suggest short-selling actions in long_only mode."
            )
        elif position_is_open:
            exposure_guidance = (
                "A position is already open. Explicitly account for existing side exposure and whether to modify or close "
                "it with the correct action semantics."
            )
        else:
            exposure_guidance = (
                "No position is currently open. Focus on entry-readiness for either long (BUY) or short (SELL_SHORT) setups "
                "and avoid language that assumes active exposure."
            )

        prompt = f"""As the portfolio manager and debate facilitator, your role is to critically evaluate this round of debate and make a definitive directional plan aligned to position-mode constraints.

Summarize the key points from both sides concisely, focusing on the most compelling evidence or reasoning. Your recommendation must be clear and actionable using the currently allowed decision semantics. Avoid indecisive fallback language; commit to a stance grounded in the debate's strongest arguments.

Additionally, develop a detailed investment plan for the trader. This should include:

Your Recommendation: A decisive stance supported by the most convincing arguments.
Rationale: An explanation of why these arguments lead to your conclusion.
Strategic Actions: Concrete steps for implementing the recommendation.
Take into account your past mistakes on similar situations. Use these insights to refine your decision-making and ensure you are learning and improving. Present your analysis conversationally, as if speaking naturally, without special formatting. 

Here are your past reflections on mistakes:
\"{past_memory_str}\"

Current Price: {current_price}

Current position context:
{position_context}

Exposure coherence requirement:
{exposure_guidance}

Here is the debate:
Debate History:
{history}"""
        response = llm.invoke(prompt)

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
