from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
import time
import json
from tradingagents.agents.utils.safe_llm import safe_invoke_llm, LLMRetryConfig


def create_market_analyst(llm, toolkit):

    def market_analyst_node(state):
        current_date = state["trade_date"]
        ticker = state["company_of_interest"]
        company_name = state["company_of_interest"]

        if toolkit.config["online_tools"]:
            tools = [
                toolkit.get_YFin_data_online,
                toolkit.get_stockstats_indicators_report_online,
            ]
        else:
            tools = [
                toolkit.get_YFin_data,
                toolkit.get_stockstats_indicators_report,
            ]

        system_message = (
            """
You are a trading assistant tasked with analyzing financial markets. Your role is to select the **most relevant indicators** for a given market condition or trading strategy from the following list. The goal is to choose the indicators that provide complementary insights without redundancy. Categories and each category's indicators are:

Moving Averages:
- close_50_sma: 50 SMA: A medium-term trend indicator. Usage: Identify trend direction and serve as dynamic support/resistance. Tips: It lags price; combine with faster indicators for timely signals.
- close_200_sma: 200 SMA: A long-term trend benchmark. Usage: Confirm overall market trend and identify golden/death cross setups. Tips: It reacts slowly; best for strategic trend confirmation rather than frequent trading entries.
- close_10_ema: 10 EMA: A responsive short-term average. Usage: Capture quick shifts in momentum and potential entry points. Tips: Prone to noise in choppy markets; use alongside longer averages for filtering false signals.

MACD Related:
- macd: MACD: Computes momentum via differences of EMAs. Usage: Look for crossovers and divergence as signals of trend changes. Tips: Confirm with other indicators in low-volatility or sideways markets.
- macds: MACD Signal: An EMA smoothing of the MACD line. Usage: Use crossovers with the MACD line to trigger trades. Tips: Should be part of a broader strategy to avoid false positives.
- macdh: MACD Histogram: Shows the gap between the MACD line and its signal. Usage: Visualize momentum strength and spot divergence early. Tips: Can be volatile; complement with additional filters in fast-moving markets.

Momentum Indicators:
- rsi: RSI: Measures momentum to flag overbought/oversold conditions. Usage: Apply 70/30 thresholds and watch for divergence to signal reversals. Tips: In strong trends, RSI may remain extreme; always cross-check with trend analysis.

Volatility Indicators:
- boll: Bollinger Middle: A 20 SMA serving as the basis for Bollinger Bands. Usage: Acts as a dynamic benchmark for price movement. Tips: Combine with the upper and lower bands to effectively spot breakouts or reversals.
- boll_ub: Bollinger Upper Band: Typically 2 standard deviations above the middle line. Usage: Signals potential overbought conditions and breakout zones. Tips: Confirm signals with other tools; prices may ride the band in strong trends.
- boll_lb: Bollinger Lower Band: Typically 2 standard deviations below the middle line. Usage: Indicates potential oversold conditions. Tips: Use additional analysis to avoid false reversal signals.
- atr: ATR: Averages true range to measure volatility. Usage: Set stop-loss levels and adjust position sizes based on current market volatility. Tips: It's a reactive measure, so use it as part of a broader risk management strategy.

Volume-Based Indicators:
- vwma: VWMA: A moving average weighted by volume. Usage: Confirm trends by integrating price action with volume data. Tips: Watch for skewed results from volume spikes; use in combination with other volume analyses.

Support and Resistance Indicators:
- supertrend_lower: Lower Band of the SuperTrend. Usage: Identify trend direction and serve as dynamic support/resistance. Tips: It lags price; combine with faster indicators for timely signals.
- supertrend_upper: Upper Band of the SuperTrend. Usage: Identify trend direction and serve as dynamic support/resistance. Tips: It lags price; combine with faster indicators for timely signals.
- Pivot Points: Pivot Points: Key points used to identify potential entry points. Usage: Identify potential entry points for long/short positions. Tips: Watch for confirmation with other indicators.
- Donchian Chanells: Donchian Channels: A range of high and low prices over a specified period. Usage: Identify potential entry points for long/short positions. Tips: Watch for confirmation with other indicators.

Bullish and Bearish Candlestick Patterns:
- bullish_candlestick: Bullish Candlestick Pattern: A bullish candlestick pattern. Usage: Identify potential entry points for long positions. Tips: Watch for confirmation with other indicators.
- bearish_candlestick: Bearish Candlestick Pattern: A bearish candlestick pattern. Usage: Identify potential entry points for short positions. Tips: Watch for confirmation with other indicators.

- Select indicators that provide diverse and complementary information. Avoid redundancy (e.g., do not select both rsi and stochrsi). Also briefly explain why they are suitable for the given market context. When you tool call, please use the exact name of the indicators provided above as they are defined parameters, otherwise your call will fail. Please make sure to call get_YFin_data first to retrieve the CSV that is needed to generate indicators. Write a very detailed and nuanced report of the trends you observe. Do not simply state the trends are mixed, provide detailed and finegrained analysis and insights that may help traders make decisions."""
            + """ Make sure to append a Markdown table at the end of the report to organize key points in the report, organized and easy to read."""
            + """ 
IMPORTANT MARKDOWN FORMATTING GUIDELINES:
- Use 'approximately', 'around', or 'about' instead of the tilde symbol (~) when describing approximate values
- For example, write 'approximately $250' or 'around $250' instead of '~$250'
- If you need to use strikethrough, use double tildes (~~text~~) not single tilde
- This ensures proper markdown rendering in the web interface"""
        )

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are a helpful AI assistant, collaborating with other assistants."
                    " Use the provided tools to progress towards answering the question."
                    " If you are unable to fully answer, that's OK; another assistant with different tools"
                    " will help where you left off. Execute what you can to make progress."
                    " If you or any other assistant has the FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** or deliverable,"
                    " prefix your response with FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** so the team knows to stop."
                    " You have access to the following tools: {tool_names}.\n{system_message}"
                    "For your reference, the current date is {current_date}. The company we want to look at is {ticker}",
                ),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )

        prompt = prompt.partial(system_message=system_message)
        prompt = prompt.partial(tool_names=", ".join([tool.name for tool in tools]))
        prompt = prompt.partial(current_date=current_date)
        prompt = prompt.partial(ticker=ticker)

        chain = prompt | llm.bind_tools(tools)

        # Resilient invocation using unified safe_invoke_llm
        try:
            retry_cfg = LLMRetryConfig(
                max_attempts=toolkit.config.get("llm_max_retries", 4),
                base_delay=toolkit.config.get("llm_retry_backoff", 0.75),
            )
            result = safe_invoke_llm(chain, state["messages"], retry_cfg)
        except Exception as e:  # noqa: BLE001
            class DummyResult:  # graceful degraded response
                def __init__(self, content):
                    self.content = content
                    self.tool_calls = []
            result = DummyResult(f"Market analyst failed after retries. Error: {e}")

        report = ""

        if getattr(result, 'tool_calls', []) == []:
            report = getattr(result, 'content', '')
       
        # Coerce result into a LangChain-compatible AI message structure if it's a fallback DummyResult.
        msg = result
        try:
            from langchain_core.messages import AIMessage
            if not isinstance(result, AIMessage):
                # Construct an AIMessage with minimal fields
                msg = AIMessage(content=getattr(result, 'content', str(result)))
        except Exception:
            # Fallback: create plain dict that downstream code can stringify
            msg = {"type": "ai", "content": getattr(result, 'content', str(result))}

        return {
            "messages": [msg],
            "market_report": report,
        }

    return market_analyst_node
