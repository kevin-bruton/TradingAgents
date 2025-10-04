#!/usr/bin/env python3
"""Test news/social tools with OpenRouter connection."""

import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

from tradingagents.dataflows.interface import _call_llm_api
from tradingagents.default_config import DEFAULT_CONFIG
from datetime import datetime, timedelta

def test_news_tool():
    """Test the news tool that was failing before."""
    
    print("=" * 80)
    print("Testing News Tool with OpenRouter")
    print("=" * 80)
    
    # Configure for OpenRouter
    test_config = DEFAULT_CONFIG.copy()
    test_config["llm_provider"] = "openrouter"
    test_config["backend_url"] = "https://openrouter.ai/api/v1"
    test_config["quick_think_llm"] = "meta-llama/llama-3.3-8b-instruct:free"
    
    # Add SSL certificate configuration
    cert_bundle = os.getenv("REQUESTS_CA_BUNDLE") or os.getenv("CURL_CA_BUNDLE")
    if cert_bundle:
        test_config["ssl_cert_bundle"] = cert_bundle
    
    print(f"\n📊 Configuration:")
    print(f"   Provider: {test_config['llm_provider']}")
    print(f"   Backend URL: {test_config['backend_url']}")
    print(f"   Model: {test_config['quick_think_llm']}")
    print(f"   SSL Cert: {cert_bundle}")
    
    # Test the underlying _call_llm_api function that was failing
    print(f"\n🔍 Testing _call_llm_api with news-like prompt:")
    try:
        # Use recent date for testing
        test_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        
        prompt = f"Can you search Social Media for AAPL from 7 days before {test_date} to {test_date}? Make sure you only get the data posted during that period."
        
        result = _call_llm_api(
            prompt=prompt,
            config=test_config
        )
        
        if result:
            print(f"   ✅ News tool successful!")
            print(f"   Result length: {len(str(result))} characters")
            # Show first 500 chars
            result_str = str(result)
            preview = result_str[:500] + "..." if len(result_str) > 500 else result_str
            print(f"   Preview: {preview}")
            return True
        else:
            print(f"   ⚠️  No results returned (but no error)")
            return True  # Still counts as success if no exception
            
    except Exception as e:
        print(f"   ❌ News tool failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_news_tool()
    print("\n" + "=" * 80)
    if success:
        print("✅ NEWS TOOL TEST: SUCCESS")
        print("The news/social tools can now connect to OpenRouter!")
    else:
        print("❌ NEWS TOOL TEST: FAILED")
        print("There are still issues with the news tools.")
    print("=" * 80)
    
    sys.exit(0 if success else 1)
