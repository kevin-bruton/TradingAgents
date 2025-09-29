#!/usr/bin/env python3
"""
Test SSL configuration behavior
"""

import os
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.dataflows.ssl_utils import get_ssl_config, setup_global_ssl_config

def test_ssl_config():
    """Test SSL configuration with different environment variable settings"""
    
    print("🧪 Testing SSL Configuration Behavior")
    print("=" * 50)
    
    # Test 1: No environment variables set
    print("\n1️⃣  Test: No SSL environment variables set")
    os.environ.pop("REQUESTS_CA_BUNDLE", None)
    os.environ.pop("CURL_CA_BUNDLE", None)
    os.environ.pop("SSL_VERIFY", None)
    os.environ.pop("HTTP_TIMEOUT", None)
    
    from tradingagents.default_config import DEFAULT_CONFIG
    config = DEFAULT_CONFIG.copy()
    ssl_config = get_ssl_config(config)
    print(f"   SSL Config: {ssl_config}")
    print(f"   Expected: Empty or minimal config (default behavior)")
    
    # Test 2: Custom certificate bundle set
    print("\n2️⃣  Test: Custom certificate bundle set")
    os.environ["REQUESTS_CA_BUNDLE"] = "/custom/path/ca-bundle.crt"
    
    # Re-import to get updated config
    from importlib import reload
    import tradingagents.default_config
    reload(tradingagents.default_config)
    from tradingagents.default_config import DEFAULT_CONFIG
    
    config = DEFAULT_CONFIG.copy()
    ssl_config = get_ssl_config(config)
    print(f"   Config ssl_cert_bundle: {config.get('ssl_cert_bundle')}")
    print(f"   SSL Config: {ssl_config}")
    print(f"   Expected: cert_bundle and verify set to custom path")
    
    # Test 3: SSL verification disabled
    print("\n3️⃣  Test: SSL verification disabled")
    os.environ.pop("REQUESTS_CA_BUNDLE", None)
    os.environ["SSL_VERIFY"] = "false"
    
    reload(tradingagents.default_config)
    from tradingagents.default_config import DEFAULT_CONFIG
    
    config = DEFAULT_CONFIG.copy()
    ssl_config = get_ssl_config(config)
    print(f"   Config ssl_verify: {config.get('ssl_verify')}")
    print(f"   SSL Config: {ssl_config}")
    print(f"   Expected: verify set to False")
    
    # Test 4: Timeout and proxy settings
    print("\n4️⃣  Test: Timeout and proxy settings")
    os.environ["HTTP_TIMEOUT"] = "60"
    os.environ["HTTP_PROXY"] = "http://proxy.example.com:8080"
    os.environ["HTTPS_PROXY"] = "https://proxy.example.com:8080"
    
    reload(tradingagents.default_config)
    from tradingagents.default_config import DEFAULT_CONFIG
    
    config = DEFAULT_CONFIG.copy()
    ssl_config = get_ssl_config(config)
    print(f"   Config timeout: {config.get('http_timeout')}")
    print(f"   Config proxies: HTTP={config.get('http_proxy')}, HTTPS={config.get('https_proxy')}")
    print(f"   SSL Config: {ssl_config}")
    print(f"   Expected: timeout and proxies in ssl_config")
    
    # Test 5: Empty environment variables (should not be used)
    print("\n5️⃣  Test: Empty environment variables")
    os.environ["REQUESTS_CA_BUNDLE"] = ""
    os.environ["HTTP_TIMEOUT"] = ""
    
    reload(tradingagents.default_config)
    from tradingagents.default_config import DEFAULT_CONFIG
    
    config = DEFAULT_CONFIG.copy()
    ssl_config = get_ssl_config(config)
    print(f"   Config ssl_cert_bundle: '{config.get('ssl_cert_bundle')}'")
    print(f"   Config http_timeout: {config.get('http_timeout')}")
    print(f"   SSL Config: {ssl_config}")
    print(f"   Expected: Empty values should not be used")
    
    # Clean up
    for var in ["REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE", "SSL_VERIFY", "HTTP_TIMEOUT", "HTTP_PROXY", "HTTPS_PROXY"]:
        os.environ.pop(var, None)
    
    print("\n✅ SSL configuration tests completed")

if __name__ == "__main__":
    test_ssl_config()