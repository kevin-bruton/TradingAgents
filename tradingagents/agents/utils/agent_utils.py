from langchain_core.messages import HumanMessage, RemoveMessage

# Import tools from separate utility files
from tradingagents.agents.utils.core_stock_tools import (
    get_stock_data
)
from tradingagents.agents.utils.technical_indicators_tools import (
    get_indicators
)
from tradingagents.agents.utils.fundamental_data_tools import (
    get_fundamentals,
    get_balance_sheet,
    get_cashflow,
    get_income_statement
)
from tradingagents.agents.utils.news_data_tools import (
    get_news,
    get_insider_transactions,
    get_global_news
)
import pandas as pd
import io
from datetime import datetime, timedelta

def get_market_context(ticker: str, trade_date: str) -> dict:
    """Fetch all necessary market data for the given ticker and date."""

    # Get current price from stock data first (and to potentially satisfy dependency for indicators)
    current_price = "Unknown"
    try:
        # We want data for exactly trade_date.
        # Note: the dataflow interface will handle vendor-specific end-date clamping/exclusivity
        # based on as_of_date. We specify trade_date + 1 here to request the full day.
        request_end = (datetime.strptime(trade_date, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")

        stock_data_csv = get_stock_data.invoke({
            "symbol": ticker,
            "start_date": trade_date,
            "end_date": request_end
        })

        # Use pandas to find the last row's close price
        # Skip comment lines
        lines = [line for line in stock_data_csv.split('\n') if not line.startswith('#')]
        df = pd.read_csv(io.StringIO('\n'.join(lines)))
        if not df.empty:
            current_price = df.iloc[-1]['Close']
    except Exception:
        pass

    indicators = [
        "close_50_sma", "close_200_sma", "close_10_ema",
        "macd", "macds", "macdh", "rsi",
        "boll", "boll_ub", "boll_lb", "atr", "vwma"
    ]

    market_data = {}
    for indicator in indicators:
        try:
            market_data[indicator] = get_indicators.invoke({
                "symbol": ticker,
                "indicator": indicator,
                "curr_date": trade_date,
                "look_back_days": 30
            })
        except Exception:
            market_data[indicator] = "Data unavailable"

    return {
        "market_data": market_data,
        "current_price": current_price
    }

def create_msg_delete():
    def delete_messages(state):
        """Clear messages and add placeholder for Anthropic compatibility"""
        messages = state["messages"]

        # Remove all messages
        removal_operations = [RemoveMessage(id=m.id) for m in messages]

        # Add a minimal placeholder message
        placeholder = HumanMessage(content="Continue")

        return {"messages": removal_operations + [placeholder]}

    return delete_messages


        