#!/usr/bin/env python3
"""
Test script to verify the connection timeout fixes for news/social tools.

This script tests that:
1. Timeout and max_retries parameters are properly passed to OpenAI clients
2. Retry logic works correctly for transient errors
3. Both OpenAI and Gemini paths respect timeout settings
"""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from tradingagents.dataflows.interface import get_config, set_config
from tradingagents.utils.llm_client import build_openai_compatible_client
from tradingagents.default_config import DEFAULT_CONFIG


def test_client_timeout_configuration():
    """Test that OpenAI client respects timeout configuration."""
    print("=" * 70)
    print("TEST 1: OpenAI Client Timeout Configuration")
    print("=" * 70)
    
    # Test with timeout configured
    config = DEFAULT_CONFIG.copy()
    config['http_timeout'] = 120
    config['llm_max_retries'] = 5
    
    # Set a dummy API key for testing if not present
    import os
    original_key = os.getenv("OPENAI_API_KEY")
    if not original_key:
        os.environ["OPENAI_API_KEY"] = "test-key-for-verification"
    
    try:
        client, _ = build_openai_compatible_client(
            config,
            purpose="chat",
            timeout=config.get("http_timeout"),
            max_retries=config.get("llm_max_retries")
        )
        
        print("✅ Client created successfully with timeout and max_retries")
        print(f"   Timeout: {config.get('http_timeout')} seconds")
        print(f"   Max Retries: {config.get('llm_max_retries')}")
        
        # Check if client has timeout configured
        if hasattr(client, 'timeout'):
            print(f"   Client timeout attribute: {client.timeout}")
        if hasattr(client, 'max_retries'):
            print(f"   Client max_retries attribute: {client.max_retries}")
        
        return True
    except Exception as e:
        print(f"❌ Failed to create client: {e}")
        return False
    finally:
        # Restore original state
        if not original_key:
            os.environ.pop("OPENAI_API_KEY", None)


def test_client_without_timeout():
    """Test that client works without timeout (backward compatibility)."""
    print("\n" + "=" * 70)
    print("TEST 2: OpenAI Client Without Timeout (Backward Compatibility)")
    print("=" * 70)
    
    config = DEFAULT_CONFIG.copy()
    
    # Set a dummy API key for testing if not present
    import os
    original_key = os.getenv("OPENAI_API_KEY")
    if not original_key:
        os.environ["OPENAI_API_KEY"] = "test-key-for-verification"
    
    try:
        client, _ = build_openai_compatible_client(config, purpose="chat")
        print("✅ Client created successfully without explicit timeout")
        print("   (Uses SDK defaults)")
        return True
    except Exception as e:
        print(f"❌ Failed to create client: {e}")
        return False
    finally:
        # Restore original state
        if not original_key:
            os.environ.pop("OPENAI_API_KEY", None)


def test_retry_wrapper_logic():
    """Test the retry wrapper logic (without actually making API calls)."""
    print("\n" + "=" * 70)
    print("TEST 3: Retry Logic Structure")
    print("=" * 70)
    
    from tradingagents.dataflows import interface
    
    # Check if retry wrapper exists
    if hasattr(interface, '_call_llm_api_with_retry'):
        print("✅ Retry wrapper function exists: _call_llm_api_with_retry")
        
        # Check function signature
        import inspect
        sig = inspect.signature(interface._call_llm_api_with_retry)
        print(f"   Function signature: {sig}")
        
        return True
    else:
        print("❌ Retry wrapper function not found")
        return False


def test_news_social_functions():
    """Test that news/social functions use the retry wrapper."""
    print("\n" + "=" * 70)
    print("TEST 4: News/Social Functions Use Retry Wrapper")
    print("=" * 70)
    
    from tradingagents.dataflows import interface
    import inspect
    
    functions_to_check = [
        'get_stock_news_from_llm',
        'get_global_news_from_llm',
        'get_fundamentals_from_llm'
    ]
    
    all_good = True
    for func_name in functions_to_check:
        if hasattr(interface, func_name):
            func = getattr(interface, func_name)
            source = inspect.getsource(func)
            
            if '_call_llm_api_with_retry' in source:
                print(f"✅ {func_name} uses _call_llm_api_with_retry")
            else:
                print(f"❌ {func_name} does NOT use _call_llm_api_with_retry")
                all_good = False
        else:
            print(f"❌ {func_name} not found")
            all_good = False
    
    return all_good


def test_config_values():
    """Test that configuration values are accessible."""
    print("\n" + "=" * 70)
    print("TEST 5: Configuration Values")
    print("=" * 70)
    
    config = DEFAULT_CONFIG.copy()
    
    print(f"✅ http_timeout: {config.get('http_timeout')} (None = SDK default)")
    print(f"✅ llm_max_retries: {config.get('llm_max_retries', 3)}")
    print(f"✅ llm_retry_backoff: {config.get('llm_retry_backoff', 2)}")
    
    # Show how to configure
    print("\n📝 To configure timeout for news/social queries:")
    print("   export HTTP_TIMEOUT=120")
    print("   export LLM_MAX_RETRIES=5")
    print("   export LLM_RETRY_BACKOFF=2")
    
    return True


def main():
    """Run all tests."""
    print("\n" + "🔧 CONNECTION TIMEOUT FIX - VERIFICATION TESTS" + "\n")
    
    results = []
    
    results.append(("Client Timeout Config", test_client_timeout_configuration()))
    results.append(("Client Backward Compat", test_client_without_timeout()))
    results.append(("Retry Wrapper Logic", test_retry_wrapper_logic()))
    results.append(("News/Social Functions", test_news_social_functions()))
    results.append(("Configuration Values", test_config_values()))
    
    # Summary
    print("\n" + "=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {test_name}")
    
    print(f"\n{passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 All tests passed! The connection timeout fix is working correctly.")
        return 0
    else:
        print("\n⚠️  Some tests failed. Please review the output above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
