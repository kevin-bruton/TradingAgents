#!/usr/bin/env python3
"""
SSL Certificate Diagnostic Tool for TradingAgents

This script helps diagnose SSL/TLS certificate issues and provides guidance
on how to configure certificate bundles properly.
"""

import os
import sys
import ssl
import socket
import requests
from urllib.parse import urlparse
from dotenv import load_dotenv
load_dotenv()
from tradingagents.dataflows.ssl_utils import get_certificate_info, get_ssl_config
from tradingagents.default_config import DEFAULT_CONFIG


def test_ssl_connection(hostname, port=443):
    """Test SSL connection to a specific hostname."""
    print(f"\n🔒 Testing SSL connection to {hostname}:{port}")
    
    try:
        # Create SSL context
        context = ssl.create_default_context()
        
        # Connect and get certificate info
        with socket.create_connection((hostname, port), timeout=10) as sock:
            with context.wrap_socket(sock, server_hostname=hostname) as ssock:
                cert = ssock.getpeercert()
                print(f"✅ SSL connection successful")
                print(f"   Subject: {cert.get('subject', 'Unknown')}")
                print(f"   Issuer: {cert.get('issuer', 'Unknown')}")
                print(f"   Version: {cert.get('version', 'Unknown')}")
                return True
                
    except Exception as e:
        print(f"❌ SSL connection failed: {e}")
        return False


def test_requests_connection(url):
    """Test HTTP request with requests library."""
    print(f"\n🌐 Testing HTTP request to {url}")
    
    try:
        response = requests.get(url, timeout=10)
        print(f"✅ HTTP request successful")
        print(f"   Status: {response.status_code}")
        print(f"   SSL Cert: {response.raw.connection.sock.getpeercert().get('subject', 'Unknown') if hasattr(response.raw.connection, 'sock') else 'Unknown'}")
        return True
        
    except requests.exceptions.SSLError as e:
        print(f"❌ SSL Error: {e}")
        return False
    except Exception as e:
        print(f"❌ Request failed: {e}")
        return False


def test_with_custom_cert_bundle(url, cert_bundle_path):
    """Test HTTP request with custom certificate bundle."""
    print(f"\n🔐 Testing with custom cert bundle: {cert_bundle_path}")
    
    if not os.path.exists(cert_bundle_path):
        print(f"❌ Certificate bundle not found: {cert_bundle_path}")
        return False
    
    try:
        response = requests.get(url, verify=cert_bundle_path, timeout=10)
        print(f"✅ Request with custom cert bundle successful")
        print(f"   Status: {response.status_code}")
        return True
        
    except Exception as e:
        print(f"❌ Request with custom cert bundle failed: {e}")
        return False


def main():
    """Main diagnostic function."""
    print("🔍 TradingAgents SSL Certificate Diagnostic Tool")
    print("=" * 50)
    
    # Get certificate information
    print("\n📋 Certificate Bundle Information:")
    cert_info = get_certificate_info()
    for key, value in cert_info.items():
        if isinstance(value, list):
            print(f"   {key}: {', '.join(value) if value else 'None found'}")
        else:
            print(f"   {key}: {value}")
    
    # Test SSL configuration
    print(f"\n⚙️ Current SSL Configuration:")
    ssl_config = get_ssl_config(DEFAULT_CONFIG)
    for key, value in ssl_config.items():
        print(f"   {key}: {value}")
    
    # Test common endpoints
    test_endpoints = [
        ("api.openai.com", 443),
        ("openrouter.ai", 443),
        ("generativelanguage.googleapis.com", 443),
        ("www.google.com", 443)
    ]
    
    print(f"\n🎯 Testing SSL connections:")
    for hostname, port in test_endpoints:
        test_ssl_connection(hostname, port)
    
    # Test HTTP requests
    test_urls = [
        "https://api.openai.com/v1/models",
        "https://www.google.com/search?q=test",
        "https://openrouter.ai/api/v1/models"
    ]
    
    print(f"\n🌍 Testing HTTP requests:")
    for url in test_urls:
        test_requests_connection(url)
    
    # Test with different certificate bundles
    if cert_info.get("certifi_bundle") and cert_info["certifi_bundle"] != "Not available (certifi not installed)":
        print(f"\n🧪 Testing with certifi bundle:")
        test_with_custom_cert_bundle("https://www.google.com", cert_info["certifi_bundle"])
    
    # Provide recommendations
    print(f"\n💡 Recommendations:")
    print("   📋 Certificate Bundle Configuration:")
    print("      • Only set if you need a custom certificate bundle")
    print("      • If not set, system default SSL behavior is used")
    print("      export REQUESTS_CA_BUNDLE=/path/to/your/ca-bundle.crt")
    print("      export CURL_CA_BUNDLE=/path/to/your/ca-bundle.crt")
    
    print("\n   ⚠️  SSL Verification (use with caution):")
    print("      • Only disable for development/testing")
    print("      • If not set, SSL verification is enabled by default")
    print("      export SSL_VERIFY=false")
    
    print("\n   ⏱️  Timeout Configuration:")
    print("      • Only set if default timeout is insufficient")
    print("      export HTTP_TIMEOUT=60")
    
    print("\n   🌐 Proxy Configuration:")
    print("      • Only required if behind corporate firewall")
    print("      export HTTP_PROXY=http://proxy.company.com:8080")
    print("      export HTTPS_PROXY=https://proxy.company.com:8080")
    
    print("\n   📝 Configuration:")
    print("      • Add these to your .env file or export in shell")
    print("      • Leave unset to use system defaults")
    print("      • Only configure what you actually need")


if __name__ == "__main__":
    main()