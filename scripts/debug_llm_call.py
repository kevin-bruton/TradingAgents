"""Standalone diagnostic script to test a single LLM call with resilience.
Run: python debug_llm_call.py --provider openai --model gpt-4o-mini --message "Test message".
It will respect environment variables for keys and SSL the same way the graph does.
"""
import argparse
import os
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.trading_graph import TradingAgentsGraph
from langchain_core.messages import HumanMessage


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--provider', default=DEFAULT_CONFIG['llm_provider'])
    parser.add_argument('--model', default=DEFAULT_CONFIG['quick_think_llm'])
    parser.add_argument('--message', default='Say hello and include a short market summary placeholder.')
    args = parser.parse_args()

    cfg = DEFAULT_CONFIG.copy()
    cfg['llm_provider'] = args.provider
    cfg['quick_think_llm'] = args.model
    cfg['deep_think_llm'] = args.model

    graph = TradingAgentsGraph(config=cfg)
    # Build a minimal state for market analyst
    state = {
        'trade_date': '2025-09-29',
        'company_of_interest': 'AAPL',
        'messages': [HumanMessage(content=args.message)],
    }
    market_node = graph.graph_setup.analyst_nodes.get('market')
    if not market_node:
        print('Market node not found in graph setup.')
        return
    # Directly invoke underlying function if possible
    result_state = market_node(state)
    print('Result keys:', list(result_state.keys()))
    print('Market report snippet:', str(result_state.get('market_report',''))[:500])


if __name__ == '__main__':
    main()
