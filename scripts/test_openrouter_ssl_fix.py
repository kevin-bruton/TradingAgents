#!/usr/bin/env python3
"""Test OpenRouter API connection with SSL certificate configuration"""

import os
from tradingagents.utils.llm_client import build_openai_compatible_client

# Load environment variables from .env
from dotenv import load_dotenv
load_dotenv()

# Test configuration
config = {
    "llm_provider": "openrouter",
    "backend_url": "https://openrouter.ai/api/v1",
    "ssl_cert_bundle": os.getenv("REQUESTS_CA_BUNDLE") or os.getenv("CURL_CA_BUNDLE"),
    "ssl_verify": True
}

print("Testing OpenRouter API connection with SSL certificates...")
print(f"Certificate bundle: {config['ssl_cert_bundle']}")
print(f"Backend URL: {config['backend_url']}")
print(f"API Key set: {bool(os.getenv('OPENROUTER_API_KEY'))}")
print()

try:
    # Build client with timeout and retries
    client, _ = build_openai_compatible_client(
        config, 
        purpose="chat",
        timeout=30,
        max_retries=3
    )
    
    print("✅ Client created successfully")
    print()
    
    # Test simple API call
    print("Making test API call...")
    response = client.chat.completions.create(
        model="meta-llama/llama-3.3-8b-instruct:free",
        messages=[{"role": "user", "content": "Say 'Hello!' if you can hear me."}],
        max_tokens=50
    )
    
    print("✅ API call successful!")
    print(f"Response: {response.choices[0].message.content}")
    print()
    print("🎉 OpenRouter SSL fix is working correctly!")
    
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
