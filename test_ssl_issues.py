#!/usr/bin/env python3
"""
Test TradingAgents SSL connections specifically
"""

import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.absolute()
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
load_dotenv()

from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.dataflows.ssl_utils import get_ssl_config, setup_global_ssl_config, get_certificate_info
from tradingagents.graph.trading_graph import TradingAgentsGraph
import requests

def test_certificate_issues():
    """Test SSL certificate issues that might occur in TradingAgents"""
    
    print("🔍 Testing TradingAgents SSL Certificate Issues")
    print("=" * 55)
    
    # Show environment variables
    print("\n📋 Environment Variables:")
    ssl_vars = ["REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE", "SSL_VERIFY", "HTTP_TIMEOUT", 
                "HTTP_PROXY", "HTTPS_PROXY", "OPENAI_API_KEY", "FINNHUB_API_KEY"]
    for var in ssl_vars:
        value = os.getenv(var)
        if value:
            if "API_KEY" in var:
                print(f"   {var}: {'*' * min(8, len(value))}...")
            else:
                print(f"   {var}: {value}")
        else:
            print(f"   {var}: Not set")
    
    # Show certificate info
    print("\n📋 Certificate Bundle Information:")
    cert_info = get_certificate_info()
    for key, value in cert_info.items():
        if isinstance(value, list):
            print(f"   {key}: {', '.join(value) if value else 'None found'}")
        else:
            print(f"   {key}: {value}")
    
    # Test SSL config
    print("\n⚙️ Current SSL Configuration:")
    config = DEFAULT_CONFIG.copy()
    ssl_config = get_ssl_config(config)
    print(f"   SSL Config: {ssl_config}")
    
    # Set up global SSL config
    print("\n🔧 Setting up global SSL configuration...")
    setup_global_ssl_config(config)
    
    # Test basic HTTPS connections
    test_urls = [
        "https://api.openai.com/",
        "https://www.google.com/",
        "https://openrouter.ai/",
        "https://finnhub.io/"
    ]
    
    print(f"\n🌐 Testing HTTPS connections:")
    for url in test_urls:
        try:
            print(f"   Testing {url}...")
            response = requests.get(url, timeout=10)
            print(f"   ✅ {url}: Status {response.status_code}")
        except requests.exceptions.SSLError as e:
            print(f"   ❌ SSL Error for {url}: {e}")
        except Exception as e:
            print(f"   ❌ Connection error for {url}: {e}")
    
    # Test TradingAgentsGraph initialization
    print(f"\n🤖 Testing TradingAgentsGraph initialization:")
    try:
        # Create minimal config
        test_config = DEFAULT_CONFIG.copy()
        test_config["llm_provider"] = "openai"
        test_config["quick_think_llm"] = "gpt-3.5-turbo"
        test_config["deep_think_llm"] = "gpt-4"
        
        print("   Creating TradingAgentsGraph...")
        graph = TradingAgentsGraph(config=test_config)
        print("   ✅ TradingAgentsGraph created successfully")
        
        # Test if we can make a simple LLM call
        print("   Testing LLM connection...")
        try:
            # This won't actually make an API call but will test the LLM initialization
            llm = graph.quick_thinking_llm
            print(f"   ✅ LLM initialized: {llm}")
        except Exception as e:
            print(f"   ❌ LLM initialization error: {e}")
            
    except Exception as e:
        print(f"   ❌ TradingAgentsGraph initialization error: {e}")
        import traceback
        traceback.print_exc()
    
    # Recommendations based on findings
    print(f"\n💡 Troubleshooting Recommendations:")
    
    # Check if we're on macOS and suggest system certificates
    if sys.platform == "darwin":
        macos_cert = "/etc/ssl/cert.pem"
        if os.path.exists(macos_cert):
            print(f"   📱 macOS detected - try: export REQUESTS_CA_BUNDLE={macos_cert}")
        else:
            print(f"   📱 macOS detected but {macos_cert} not found")
    
    # Check for certifi
    try:
        import certifi
        print(f"   🔐 Certifi available - try: export REQUESTS_CA_BUNDLE={certifi.where()}")
    except ImportError:
        print(f"   ❌ Certifi not installed - try: pip install certifi")
    
    # Corporate environment suggestions
    print(f"   🏢 If behind corporate firewall:")
    print(f"      • Contact IT for corporate certificate bundle")
    print(f"      • Check if HTTP_PROXY/HTTPS_PROXY needed")
    print(f"      • Ask about custom CA certificates")
    
    # Temporary workaround (not recommended for production)
    print(f"   🚨 Temporary workaround (development only):")
    print(f"      export SSL_VERIFY=false")
    print(f"      ⚠️  This disables SSL verification - use with caution!")

if __name__ == "__main__":
    test_certificate_issues()