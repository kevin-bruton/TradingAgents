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

        # Escape curly braces for the market data to avoid LangChain prompt formatting errors
        market_data_str = market_data_str.replace("{", "{{").replace("}", "}}")

        system_message = (
            """You are a helpful AI assistant, collaborating with other assistants. Use the provided tools to progress towards answering the question. If you are unable to fully answer, that's OK; another assistant with different tools will help where you left off. Execute what you can to make progress. If you or any other assistant has the FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** or deliverable, prefix your response with FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** so the team knows to stop.

You are a market analyst tasked with analyzing financial markets for {ticker}.
The current date is {current_date} and the current stock price is {current_price}.

Below is the pre-retrieved market data and technical indicators for your analysis:

""" + market_data_str + """

Your role is to analyze this data and provide a detailed and nuanced report of the trends you observe.
The goal is to provide complementary insights from the following categories of indicators:

Moving Averages (50 SMA, 200 SMA, 10 EMA)
MACD Related (MACD, MACD Signal, MACD Histogram)
Momentum Indicators (RSI)
Volatility Indicators (Bollinger Bands, ATR)
Volume-Based Indicators (VWMA)

Briefly explain why specific indicators are suitable for the given market context. Write a very detailed and nuanced report. Do not simply state the trends are mixed; provide fine-grained analysis and insights that may help traders make decisions.
Make sure to append a Markdown table at the end of the report to organize key points."""
        )

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "{system_message}"
                    "\n\nFor your reference, the current date is {current_date}. The company we want to look at is {ticker}. The current price is {current_price}.",
                ),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )

        prompt = prompt.partial(system_message=system_message)
        prompt = prompt.partial(current_date=current_date)
        prompt = prompt.partial(ticker=ticker)
        prompt = prompt.partial(current_price=current_price)

        chain = prompt | llm

        result = chain.invoke(state["messages"])

        return {
            "messages": [result],
            "market_report": result.content,
        }

    return market_analyst_node
