#!/usr/bin/env python3
"""
Debug script to test the TradingAgentsGraph streaming behavior
"""

import os
from dotenv import load_dotenv
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

# Load environment variables
load_dotenv()

def debug_callback(state):
    """Debug callback to see what state is being passed"""
    print(f"\n🔍 CALLBACK RECEIVED:")
    print(f"   State type: {type(state)}")
    print(f"   State keys: {list(state.keys()) if isinstance(state, dict) else 'Not a dict'}")
    
    if isinstance(state, dict):
        for key, value in state.items():
            if key in ["__end__", "messages"]:
                continue
            print(f"   {key}: {type(value)} - {str(value)[:100]}...")
    print("-" * 50)

def test_streaming():
    """Test the streaming functionality"""
    print("🚀 Testing TradingAgentsGraph streaming...")
    
    # Create a minimal config for testing
    config = DEFAULT_CONFIG.copy()
    config["llm_provider"] = "openai"
    config["quick_think_llm"] = "gpt-3.5-turbo"
    config["deep_think_llm"] = "gpt-4"
    
    try:
        # Initialize the graph
        print("📊 Initializing TradingAgentsGraph...")
        graph = TradingAgentsGraph(config=config)
        
        # Test propagation with callback
        print("🔄 Starting propagation with callback...")
        final_state, signal = graph.propagate(
            company_name="AAPL", 
            trade_date="2024-01-01", 
            on_step_callback=debug_callback
        )
        
        print(f"✅ Propagation completed!")
        print(f"📈 Final signal: {signal}")
        print(f"🎯 Final state keys: {list(final_state.keys())}")
        
    except Exception as e:
        print(f"❌ Error during streaming test: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_streaming()