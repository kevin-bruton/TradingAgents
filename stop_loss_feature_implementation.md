
# Stop-Loss Feature Implementation Plan

This document outlines the plan for implementing a stop-loss feature in the TradingAgents project.

## 1. Overview

The goal is to enhance the trading agents' capabilities by requiring a stop-loss price level for every trade recommendation. This will improve risk management and provide more concrete trading plans. An optional take-profit level can also be included.

## 2. Recommended Architecture: New Trade Planner Agent

After investigating the existing architecture, the recommended approach is to introduce a new, dedicated **Trade Planner Agent**. This approach is favored over modifying existing agents for the following reasons:

*   **Modularity and Separation of Concerns:** It keeps the responsibilities of each agent clear. The new agent will specialize in technical analysis, while other agents, like the `risk_manager`, can focus on their core competencies.
*   **Expertise:** A dedicated agent can be specifically prompted and potentially fine-tuned to become an expert in technical analysis, leading to more accurate stop-loss and take-profit levels.
*   **Scalability:** It will be easier to add more sophisticated technical analysis logic in the future without complicating the existing agents.

The new workflow will be as follows:

1.  **Analyst Team:** Gathers and analyzes data (no changes).
2.  **Researcher Team:** Debates the findings and creates an investment plan (no changes).
3.  **Trade Planner Agent (New):** Receives the market data and investment plan, and calculates the stop-loss and (optionally) take-profit levels.
4.  **Risk Management Team:** Assesses the risk of the proposed trade, now also considering the stop-loss level.
5.  **Trader Agent:** Makes the final trading decision, incorporating the stop-loss and take-profit levels into the final transaction proposal.

## 3. Implementation Details

### 3.1. Create the Trade Planner Agent

*   **File:** `tradingagents/agents/managers/trade_planner.py`
*   **Function:** `create_trade_planner_agent`
*   **Logic:**
    *   The agent will take the `market_report` and `investment_plan` from the state as input.
    *   It will use a detailed prompt that instructs the LLM to act as a trade planner.
    *   The prompt will guide the LLM to determine stop-loss and take-profit levels based on technical indicators such as:
        *   Support and resistance levels
        *   Moving averages
        *   Fibonacci retracement levels
        *   Volume analysis
    *   The prompt will specify the desired output format, which should be a JSON object with `stop_loss` and `take_profit` keys.

### 3.2. Update the Graph

*   **File:** `tradingagents/graph/trading_graph.py`
*   **Changes:**
    *   Instantiate the new `trade_planner_agent`.
    *   Add a new node for the agent in the `LangGraph` setup.
    *   The new node will be placed after the `research_manager` and before the `risk_manager`.

### 3.3. Update Existing Agents

*   **`risk_manager.py`:**
    *   The prompt for the `risk_manager` will be updated to include the `stop_loss` level in its context. This will allow the risk manager to provide a more comprehensive risk assessment.
*   **`trader.py`:**
    *   The prompt for the `trader` agent will be updated to include the `stop_loss` and `take_profit` levels.
    *   The final output of the trader agent, the "FINAL TRANSACTION PROPOSAL", must include the stop-loss level.

### 3.4. Update Agent State

*   **File:** `tradingagents/agents/utils/agent_states.py`
*   **Changes:**
    *   Add `stop_loss: float` and `take_profit: float` fields to the `AgentState` dataclass. This will allow the new price levels to be passed between agents in the graph.

## 4. Next Steps

The next step is to implement the changes described in this document. This will involve creating the new agent, updating the graph, and modifying the existing agents and state.
