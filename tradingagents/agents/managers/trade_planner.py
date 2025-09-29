import json

def create_trade_planner_agent(llm, toolkit):
    def trade_planner_node(state) -> dict:
        market_report = state["market_report"]
        investment_plan = state["investment_plan"]

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

        prompt = f'''You are a trade planner. Your role is to determine the stop-loss and take-profit levels for a given investment plan.

Analyze the following market report and investment plan to determine the optimal stop-loss and take-profit levels. You should use the available tools to get the latest market data and calculate technical indicators.

**Market Report:**
{market_report}

**Investment Plan:**
{investment_plan}

Use technical indicators such as Pivots, ATR, support and resistance levels, Donchian Channels, SuperTrend, etc., as well as risk factors to determine the stop-loss and take-profit levels.

Based on your analysis, provide the stop-loss and take-profit levels in a JSON format. For example:
{{
    "stop_loss": 150.00,
    "take_profit": 180.00
}}

The stop-loss level is mandatory. The take-profit level is optional.
Do not provide any other information or explanation.
'''

        response = llm.invoke(prompt)
        
        try:
            levels = json.loads(response.content)
            stop_loss = levels.get("stop_loss")
            take_profit = levels.get("take_profit")
        except (json.JSONDecodeError, AttributeError):
            stop_loss = None
            take_profit = None


        return {
            "stop_loss": stop_loss,
            "take_profit": take_profit,
        }

    return trade_planner_node