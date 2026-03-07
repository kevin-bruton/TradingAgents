# Position Management Improvements

A plan for the following improvements must be prepared and saved as a markdown file:
- When "uv run run.py" is executed, it must read from a file "current_positions.yaml" file, for each symbol, whether there is currently a position open, and if so, also obtain the stop loss level, and the take profit level (if there is one)
- The agents must be modified to consider, in their evaluation, whether a current position is open or not. If there is a position already open, they must determine whether the stop loss must be modified. If it is to be modified, it should never be modified further away from the current price, only closer, if at all. If a position is not open, then if the agents recommend to "BUY" or "HOLD", then this recommendation should always be accompanied by a stop loss level and optionally, a take profit level. The final decision must always include with a "BUY" or "HOLD" recommendation, the stop loss level and optionally, a take profit level.
- In the plan, it must be investigated carefully, as an expert professional stock market trader, which agents must be the ones to consider the current position status, and how, and also how each agent is to handle the stop loss and take profit levels.
- The general criteria for establishing a stop loss level should be to determine a level where it is clear that the recommendation to BUY or HOLD would then be incorrect and to avoid further losses past this level. The stop loss level may be modified for open positions to work as a trailing stop.
- When evaluating possible recommendations, the agents must be aware that the recommendations, and the open positions are revised before the open of each trading day.
- When producing the output of ta.propagate, now, not only should the main decision be extracted and returned, but also the determined stop loss level and the determined take profit level, if it was included.
- It must also be investigated how to adapt "backtest.py" so that the new functionality can be evaluated on historical data.

With all these requirements, develop an position management implementation plan, with the recommended changes to the current project. Present pros and cons for alternatives where the best option is not obvious.
