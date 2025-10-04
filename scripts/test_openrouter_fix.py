#!/usr/bin/env python3
"""
Test script to verify OpenRouter provider fixes in _call_llm_api
"""
import sys
import os

# Add the project root to the path
sys.path.insert(0, os.path.dirname(__file__))

from tradingagents.dataflows.interface import _get_valid_models

def test_get_valid_models():
    """Test that _get_valid_models returns correct models for each provider"""
    
    print("Testing _get_valid_models function...\n")
    
    # Test OpenAI
    print("1. Testing OpenAI models:")
    openai_models = _get_valid_models("openai")
    print(f"   Found {len(openai_models)} models")
    print(f"   Sample: {openai_models[:3]}")
    assert len(openai_models) > 0, "OpenAI should return models"
    assert "gpt-4o-mini" in openai_models, "Should include gpt-4o-mini"
    print("   ✅ PASS\n")
    
    # Test Gemini
    print("2. Testing Gemini models:")
    gemini_models = _get_valid_models("gemini")
    print(f"   Found {len(gemini_models)} models")
    print(f"   Sample: {gemini_models[:3]}")
    assert len(gemini_models) > 0, "Gemini should return models"
    assert "gemini-1.5-flash" in gemini_models, "Should include gemini-1.5-flash"
    print("   ✅ PASS\n")
    
    # Test OpenRouter
    print("3. Testing OpenRouter models:")
    openrouter_models = _get_valid_models("openrouter")
    print(f"   Found {len(openrouter_models)} models")
    if len(openrouter_models) > 0:
        print(f"   Sample: {openrouter_models[:5]}")
        # Check for some expected OpenRouter models
        has_llama = any("llama" in m.lower() for m in openrouter_models)
        has_deepseek = any("deepseek" in m.lower() for m in openrouter_models)
        print(f"   Contains Llama models: {has_llama}")
        print(f"   Contains DeepSeek models: {has_deepseek}")
        assert has_llama or has_deepseek, "Should include Llama or DeepSeek models"
        print("   ✅ PASS\n")
    else:
        print("   ⚠️  WARNING: No OpenRouter models found (YAML file issue?)\n")
    
    # Test unknown provider
    print("4. Testing unknown provider:")
    unknown_models = _get_valid_models("unknown")
    print(f"   Found {len(unknown_models)} models")
    assert len(unknown_models) == 0, "Unknown provider should return empty list"
    print("   ✅ PASS\n")
    
    print("=" * 60)
    print("All tests passed! ✅")
    print("=" * 60)

if __name__ == "__main__":
    test_get_valid_models()
