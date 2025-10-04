#!/usr/bin/env python3
"""
Certificate Bundle Combiner for TradingAgents

This script combines your corporate certificate bundle (Netskope) with
the certifi certificate bundle to ensure all certificates are available.
"""

import os
import shutil
from pathlib import Path

def combine_certificate_bundles():
    """Combine corporate and certifi certificate bundles"""
    
    print("🔗 Certificate Bundle Combiner")
    print("=" * 40)
    
    # Paths
    corporate_bundle = "/Users/kevin.bruton/netskope-certificates/netskope-cert-bundle.pem"
    
    try:
        import certifi
        certifi_bundle = certifi.where()
    except ImportError:
        print("❌ certifi package not found. Please install it: pip install certifi")
        return False
    
    combined_bundle = "/Users/kevin.bruton/netskope-certificates/combined-cert-bundle.pem"
    
    print(f"📋 Corporate bundle: {corporate_bundle}")
    print(f"📋 Certifi bundle: {certifi_bundle}")
    print(f"📋 Combined bundle: {combined_bundle}")
    
    # Check if corporate bundle exists
    if not os.path.exists(corporate_bundle):
        print(f"❌ Corporate certificate bundle not found: {corporate_bundle}")
        return False
    
    # Create combined bundle
    try:
        with open(combined_bundle, 'w') as combined_file:
            # Write corporate certificates first
            print("📝 Adding corporate certificates...")
            with open(corporate_bundle, 'r') as corp_file:
                combined_file.write(corp_file.read())
            
            # Add separator
            combined_file.write("\n# Certifi certificates below\n")
            
            # Write certifi certificates
            print("📝 Adding certifi certificates...")
            with open(certifi_bundle, 'r') as certifi_file:
                certifi_content = certifi_file.read()
                combined_file.write(certifi_content)
        
        print(f"✅ Combined certificate bundle created: {combined_bundle}")
        
        # Set permissions
        os.chmod(combined_bundle, 0o644)
        
        # Show usage instructions
        print("\n💡 Usage Instructions:")
        print(f"   Add this to your .env file:")
        print(f"   REQUESTS_CA_BUNDLE={combined_bundle}")
        print(f"   CURL_CA_BUNDLE={combined_bundle}")
        
        print("\n   Or export in your shell:")
        print(f"   export REQUESTS_CA_BUNDLE={combined_bundle}")
        print(f"   export CURL_CA_BUNDLE={combined_bundle}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error creating combined bundle: {e}")
        return False

def test_combined_bundle():
    """Test the combined certificate bundle"""
    combined_bundle = "/Users/kevin.bruton/netskope-certificates/combined-cert-bundle.pem"
    
    if not os.path.exists(combined_bundle):
        print("❌ Combined bundle not found. Run combine_certificate_bundles() first.")
        return False
    
    print(f"\n🧪 Testing combined certificate bundle: {combined_bundle}")
    
    import requests
    test_urls = [
        "https://www.google.com",
        "https://api.openai.com/v1/models",
        "https://openrouter.ai/api/v1/models"
    ]
    
    for url in test_urls:
        try:
            response = requests.get(url, verify=combined_bundle, timeout=10)
            print(f"✅ {url} - Status: {response.status_code}")
        except Exception as e:
            print(f"❌ {url} - Error: {e}")
    
    return True

if __name__ == "__main__":
    if combine_certificate_bundles():
        test_combined_bundle()