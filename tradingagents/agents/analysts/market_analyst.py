from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
import time
import json
from tradingagents.agents.utils.agent_utils import get_stock_data, get_indicators
from tradingagents.dataflows.config import get_config


def create_market_analyst(llm):

    def market_analyst_node(state):
        current_date = state["trade_date"]
        ticker = state["company_of_interest"]
        current_price = state.get("current_price", "Unknown")
        market_context = state.get("market_context", {})

        market_data_str = ""
        for indicator, data in market_context.items():
            market_data_str += f"### {indicator}\n{data}\n\n"

        # Escape curly braces for the final system message to avoid LangChain prompt formatting errors
        system_message = (
            f"""You are a market analyst tasked with analyzing financial markets for {ticker}.
The current date is {current_date} and the current stock price is {current_price}.

Below is the pre-retrieved market data and technical indicators for your analysis:

{market_data_str}

Your role is to analyze this data and provide a detailed and nuanced report of the trends you observe.
""".replace("{", "{{").replace("}", "}}")
        )

        system_message += """
The goal is to provide complementary insights from the following categories of indicators:

Moving Averages (50 SMA, 200 SMA, 10 EMA)
MACD Related (MACD, MACD Signal, MACD Histogram)
Momentum Indicators (RSI)
Volatility Indicators (Bollinger Bands, ATR)
Volume-Based Indicators (VWMA)

Briefly explain why specific indicators are suitable for the given market context. Write a very detailed and nuanced report. Do not simply state the trends are mixed; provide fine-grained analysis and insights that may help traders make decisions.
Make sure to append a Markdown table at the end of the report to organize key points."""

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "{system_message}"
                ),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )

        prompt = prompt.partial(system_message=system_message)

        chain = prompt | llm

        result = chain.invoke(state["messages"])

        return {
            "messages": [result],
            "market_report": result.content,
        }

    return market_analyst_node
