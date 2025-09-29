#!/usr/bin/env python3
"""
Test SSL connectivity for TradingAgents components
"""

import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def test_api_connections():
    """Test API connections that TradingAgents will use"""
    
    print("🔍 Testing TradingAgents API Connections")
    print("=" * 50)
    
    # Test 1: Basic HTTP requests with proper SSL
    print("\n1️⃣ Testing HTTP requests with SSL configuration:")
    
    import requests
    
    test_endpoints = [
        ("OpenAI API", "https://api.openai.com/v1/models"),
        ("Google Search", "https://www.google.com/search?q=AAPL"),
        ("OpenRouter API", "https://openrouter.ai/api/v1/models"),
    ]
    
    for name, url in test_endpoints:
        try:
            response = requests.get(url, timeout=10)
            print(f"   ✅ {name}: Status {response.status_code}")
        except Exception as e:
            print(f"   ❌ {name}: {e}")
    
    # Test 2: LangChain LLM initialization
    print("\n2️⃣ Testing LangChain LLM initialization:")
    
    try:
        from langchain_openai import ChatOpenAI
        
        # Test with the SSL configuration
        llm = ChatOpenAI(
            model="gpt-3.5-turbo",
            api_key=os.getenv("OPENAI_API_KEY", "test-key")
        )
        print("   ✅ ChatOpenAI initialization successful")
        
        # Test a simple API call (this might fail due to API key, but SSL should work)
        try:
            # This will test SSL connectivity
            response = llm.invoke("Hello")
            print("   ✅ ChatOpenAI API call successful")
        except Exception as e:
            if "401" in str(e) or "Unauthorized" in str(e):
                print("   ✅ ChatOpenAI SSL working (401 = API key issue, not SSL)")
            else:
                print(f"   ⚠️ ChatOpenAI API call error: {e}")
                
    except Exception as e:
        print(f"   ❌ ChatOpenAI initialization failed: {e}")
    
    # Test 3: TradingAgents configuration
    print("\n3️⃣ Testing TradingAgents SSL configuration:")
    
    try:
        from tradingagents.default_config import DEFAULT_CONFIG
        from tradingagents.dataflows.ssl_utils import get_ssl_config, setup_global_ssl_config
        
        print(f"   📋 SSL cert bundle: {DEFAULT_CONFIG.get('ssl_cert_bundle')}")
        print(f"   📋 SSL verify: {DEFAULT_CONFIG.get('ssl_verify')}")
        
        ssl_config = get_ssl_config(DEFAULT_CONFIG)
        print(f"   📋 SSL config: {ssl_config}")
        
        # Set up global SSL configuration
        setup_global_ssl_config(DEFAULT_CONFIG)
        print("   ✅ Global SSL configuration applied")
        
    except Exception as e:
        print(f"   ❌ TradingAgents SSL configuration failed: {e}")
    
    # Test 4: Google News functionality
    print("\n4️⃣ Testing Google News data retrieval:")
    
    try:
        from tradingagents.dataflows.googlenews_utils import getNewsData
        from tradingagents.dataflows.ssl_utils import get_ssl_config
        from tradingagents.default_config import DEFAULT_CONFIG
        
        ssl_config = get_ssl_config(DEFAULT_CONFIG)
        
        # Test news retrieval with SSL config
        news_results = getNewsData("AAPL", "2024-01-01", "2024-01-02", ssl_config)
        print(f"   ✅ Google News retrieval successful, got {len(news_results)} results")
        
    except Exception as e:
        print(f"   ❌ Google News retrieval failed: {e}")

if __name__ == "__main__":
    test_api_connections()