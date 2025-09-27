# Gemini Code Assistant Workspace Configuration

This document provides a comprehensive guide for the Gemini Code Assistant to effectively understand and contribute to the `TradingAgents` project.

## Project Overview

`TradingAgents` is a multi-agent LLM framework for financial trading that simulates a real-world trading firm. It leverages a team of specialized LLM-powered agents, including analysts, researchers, and a trader, to collaboratively analyze market conditions and make informed trading decisions. The framework is built on `LangGraph`, which enables a modular and flexible agent-based architecture.

The core of the project is the `TradingAgentsGraph`, which orchestrates the interactions between the different agents. The agents are organized into teams:

*   **Analyst Team:** Gathers and analyzes different types of data (e.g., fundamentals, news, social media).
*   **Researcher Team:** Debates the findings of the analyst team to form an investment plan.
*   **Trader Agent:** Makes the final trading decision based on the input from the other teams.
*   **Risk Management Team:** Assesses the risk of the proposed trade.

## Getting Started

### Installation

1.  Clone the repository:
    ```bash
    git clone https://github.com/TauricResearch/TradingAgents.git
    cd TradingAgents
    ```
2.  Create and activate a virtual environment:
    ```bash
    conda create -n tradingagents python=3.13
    conda activate tradingagents
    ```
3.  Install the required dependencies:
    ```bash
    pip install -r requirements.txt
    ```

### API Keys

The project requires the following API keys to be set as environment variables:

*   **FinnHub:** For financial data.
    ```bash
    export FINNHUB_API_KEY=$YOUR_FINNHUB_API_KEY
    ```
*   **OpenAI:** For the LLM agents.
    ```bash
    export OPENAI_API_KEY=$YOUR_OPENAI_API_KEY
    ```
*   **OpenRouter (optional):** If you want to use OpenRouter as your LLM provider.
    ```bash
    export OPENROUTER_API_KEY=$YOUR_OPENROUTER_API_KEY
    ```

## Project Structure

```
C:\Users\kevin\repo\TradingAgents\
├───.gitignore
├───.python-version
├───ERROR_HANDLING_GUIDE.md
├───LICENSE
├───main.py
├───openrouter_status.py
├───pyproject.toml
├───README.md
├───requirements.txt
├───setup.py
├───uv.lock
├───.git\...
├───.venv\
│   ├───include\...
│   ├───Lib\...
│   ├───Scripts\...
│   └───share\...
├───assets\
│   ├───analyst.png
│   ├───researcher.png
│   ├───risk.png
│   ├───schema.png
│   ├───TauricResearch.png
│   ├───trader.png
│   ├───wechat.png
│   └───cli\
│       ├───cli_init.png
│       ├───cli_news.png
│       ├───cli_technical.png
│       └───cli_transaction.png
├───cli\
│   ├───__init__.py
│   ├───main.py
│   ├───models.py
│   ├───utils.py
│   ├───__pycache__\
│   └───static\
│       └───welcome.txt
├───results\
│   ├───AAPL\...
│   └───TSLA\...
└───tradingagents\
    ├───default_config.py
    ├───__pycache__\
    ├───agents\
    │   ├───__init__.py
    │   ├───__pycache__\
    │   ├───analysts\
    │   │   ├───fundamentals_analyst.py
    │   │   ├───market_analyst.py
    │   │   ├───news_analyst.py
    │   │   ├───social_media_analyst.py
    │   │   └───__pycache__\
    │   ├───managers\
    │   │   ├───research_manager.py
    │   │   ├───risk_manager.py
    │   │   └───__pycache__\
    │   ├───researchers\
    │   │   ├───bear_researcher.py
    │   │   ├───bull_researcher.py
    │   │   └───__pycache__\
    │   ├───risk_mgmt\
    │   │   ├───aggresive_debator.py
    │   │   ├───conservative_debator.py
    │   │   ├───neutral_debator.py
    │   │   └───__pycache__\
    │   ├───trader\
    │   │   ├───trader.py
    │   │   └───__pycache__\
    │   └───utils\
    │       ├───agent_states.py
    │       ├───agent_utils.py
    │       ├───memory.py
    │       └───__pycache__\
    ├───dataflows\
    │   ├───__init__.py
    │   ├───config.py
    │   ├───finnhub_utils.py
    │   ├───googlenews_utils.py
    │   ├───interface.py
    │   ├───reddit_utils.py
    │   ├───stockstats_utils.py
    │   ├───utils.py
    │   ├───yfin_utils.py
    │   ├───__pycache__\
    │   └───data_cache\
    └───graph\
        ├───__init__.py
        ├───conditional_logic.py
        ├───propagation.py
        ├───reflection.py
        ├───setup.py
        ├───signal_processing.py
        ├───trading_graph.py
        └───__pycache__\
```

*   **`main.py`**: A simple script demonstrating how to use the `TradingAgentsGraph` as a Python package.
*   **`cli/main.py`**: The main entry point for the command-line interface.
*   **`tradingagents/`**: The core Python package.
    *   **`agents/`**: Contains the implementation of the different agents.
    *   **`dataflows/`**: Handles data acquisition from various APIs.
    *   **`graph/`**: Defines the `LangGraph` graph and the overall orchestration of the agents.
    *   **`default_config.py`**: The default configuration for the project.
*   **`requirements.txt`**: A list of the Python dependencies.
*   **`pyproject.toml`**: Project metadata and dependencies.
*   **`README.md`**: The main README file for the project.

## Core Concepts

### TradingAgentsGraph

The `TradingAgentsGraph` class in `tradingagents/graph/trading_graph.py` is the central orchestrator of the framework. It initializes the LLMs, tools, and agents, and then constructs a `LangGraph` graph to define the workflow. The `propagate` method executes the graph for a given company and date.

### Agents

Agents are defined in the `tradingagents/agents/` directory. Each agent is a "node" in the `LangGraph` graph. The agents are created by functions that take the LLM and other necessary components as input. These functions return a node function that processes the current state of the graph and returns an updated state.

### Dataflows

The `tradingagents/dataflows/` directory contains the logic for fetching data from various financial data APIs, such as Finnhub, Yahoo Finance, and Reddit. The `Toolkit` class in `tradingagents/agents/__init__.py` provides a unified interface for the agents to access these data sources.

## Development Guidelines

### Adding a New Agent

1.  Create a new Python file in the appropriate subdirectory of `tradingagents/agents/`.
2.  Define a `create_<agent_name>_agent` function that takes the LLM and any other necessary components as input.
3.  Inside this function, define a node function that takes the current state of the graph as input.
4.  Prepare a prompt for the LLM and invoke it.
5.  Return an updated state dictionary.
6.  Add the new agent to the `TradingAgentsGraph` in `tradingagents/graph/trading_graph.py`.

### Adding a New Tool

1.  Add a new function to the appropriate file in `tradingagents/dataflows/`.
2.  Add the new function to the `Toolkit` class in `tradingagents/agents/__init__.py`.
3.  Add the new tool to the appropriate `ToolNode` in the `_create_tool_nodes` method of the `TradingAgentsGraph` class.

### Running Tests

This project does not currently have a dedicated test suite. When adding new features, it is recommended to add unit tests to ensure the correctness of the code.

## Key Commands

*   **Run the CLI:**
    ```bash
    python -m cli.main
    ```
*   **Run the package example:**
    ```bash
    python main.py
    ```
