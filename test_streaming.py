#!/usr/bin/env python3
"""
Test script to verify LangGraph streaming behavior
"""
import os
import sys
from datetime import date
from dotenv import load_dotenv

# Add the project root to the path
sys.path.insert(0, '/Users/kevin.bruton/repo2/TradingAgents')

# Load environment variables
load_dotenv()

def test_callback(state):
    """Test callback to understand state structure"""
    print(f"\n🔍 CALLBACK RECEIVED:")
    print(f"   Type: {type(state)}")
    print(f"   Keys: {list(state.keys()) if isinstance(state, dict) else 'Not a dict'}")
    if isinstance(state, dict):
        for key, value in state.items():
            if key not in ["__end__", "messages"]:
                print(f"   {key}: {type(value)} - {'Has content' if value else 'Empty'}")

def main():
    """Test the TradingAgentsGraph streaming"""
    try:
        from tradingagents.graph.trading_graph import TradingAgentsGraph
        from tradingagents.default_config import DEFAULT_CONFIG
        
        print("🚀 Testing TradingAgentsGraph streaming...")
        
        # Create a minimal config for testing
        config = DEFAULT_CONFIG.copy()
        config["llm_provider"] = "openai"
        config["quick_think_llm"] = "gpt-3.5-turbo"
        config["deep_think_llm"] = "gpt-4"
        
        # Create graph with debug mode
        graph = TradingAgentsGraph(config=config, debug=True)
        
        print("📊 Starting propagation with callback...")
        
        # Test with a simple company
        final_state, signal = graph.propagate(
            company_name="AAPL",
            trade_date=str(date.today()),
            on_step_callback=test_callback
        )
        
        print(f"\n✅ Propagation completed!")
        print(f"   Final signal: {signal}")
        
    except Exception as e:
        import traceback
        print(f"❌ Error: {e}")
        print(traceback.format_exc())

if __name__ == "__main__":
    main()