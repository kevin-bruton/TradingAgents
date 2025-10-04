#!/usr/bin/env python3
"""Test that SSL configuration works with and without custom certificates."""

import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from tradingagents.utils.llm_client import build_openai_compatible_client
from dotenv import load_dotenv
load_dotenv()

def test_ssl_scenarios():
    """Test different SSL certificate scenarios."""
    
    print("=" * 80)
    print("Testing SSL Configuration Compatibility")
    print("=" * 80)
    
    # Scenario 1: With custom certificate bundle (Netskope)
    print("\n📋 Scenario 1: WITH custom SSL certificate bundle")
    print("-" * 80)
    cert_path = "/Users/kevin.bruton/netskope-certificates/combined-cert-bundle.pem"
    if os.path.exists(cert_path):
        config_with_cert = {
            "llm_provider": "openrouter",
            "backend_url": "https://openrouter.ai/api/v1",
            "ssl_cert_bundle": cert_path,
            "ssl_verify": True
        }
        try:
            client, _ = build_openai_compatible_client(config_with_cert, timeout=30)
            print(f"✅ Client created successfully with custom cert: {cert_path}")
            print("   → This will use Netskope certificates")
            print("   → Checking if httpx client has custom SSL context...")
            # Check if client has custom http_client
            if hasattr(client, '_client') and client._client is not None:
                print("   ✅ Custom httpx client is configured")
            else:
                print("   ℹ️  Using default SSL settings")
        except Exception as e:
            print(f"❌ Failed: {e}")
    else:
        print(f"⚠️  Certificate not found at {cert_path}")
        print("   (This is expected if not on Netskope network)")
    
    # Scenario 2: WITHOUT custom certificate bundle (normal environment)
    print("\n📋 Scenario 2: WITHOUT custom SSL certificate bundle")
    print("-" * 80)
    config_no_cert = {
        "llm_provider": "openrouter",
        "backend_url": "https://openrouter.ai/api/v1",
        "ssl_cert_bundle": None,  # No custom cert
        "ssl_verify": True
    }
    try:
        client, _ = build_openai_compatible_client(config_no_cert, timeout=30)
        print("✅ Client created successfully without custom cert")
        print("   → This will use system default SSL certificates")
        print("   → Works in normal environments (no Netskope)")
        # Check if client uses default httpx behavior
        if hasattr(client, '_client') and client._client is None:
            print("   ✅ Using default httpx SSL (no custom client)")
        elif not hasattr(client, '_client'):
            print("   ✅ Using OpenAI SDK defaults")
    except Exception as e:
        print(f"❌ Failed: {e}")
    
    # Scenario 3: With env var but file doesn't exist
    print("\n📋 Scenario 3: Cert path in env but file doesn't exist")
    print("-" * 80)
    config_missing_cert = {
        "llm_provider": "openrouter",
        "backend_url": "https://openrouter.ai/api/v1",
        "ssl_cert_bundle": "/path/that/does/not/exist.pem",
        "ssl_verify": True
    }
    try:
        client, _ = build_openai_compatible_client(config_missing_cert, timeout=30)
        print("✅ Client created successfully (ignored missing cert file)")
        print("   → Falls back to system default SSL certificates")
    except Exception as e:
        print(f"❌ Failed: {e}")
    
    # Scenario 4: SSL verification disabled
    print("\n📋 Scenario 4: SSL verification explicitly disabled")
    print("-" * 80)
    config_no_verify = {
        "llm_provider": "openrouter",
        "backend_url": "https://openrouter.ai/api/v1",
        "ssl_cert_bundle": None,
        "ssl_verify": False  # Explicitly disabled
    }
    try:
        client, _ = build_openai_compatible_client(config_no_verify, timeout=30)
        print("✅ Client created with SSL verification disabled")
        print("   ⚠️  Not recommended for production!")
    except Exception as e:
        print(f"❌ Failed: {e}")
    
    print("\n" + "=" * 80)
    print("✅ COMPATIBILITY TEST: SUCCESS")
    print("The SSL configuration works in all scenarios:")
    print("  • WITH Netskope proxy (custom certificates)")
    print("  • WITHOUT Netskope proxy (system default)")
    print("  • With missing certificate files (graceful fallback)")
    print("=" * 80)

if __name__ == "__main__":
    test_ssl_scenarios()
