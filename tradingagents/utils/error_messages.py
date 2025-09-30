"""Centralized error message builders for LLM & embedding flows.

All functions return plain strings so they can be:
- Raised directly in exceptions
- Logged to message_tool.log
- Reused across memory, interface, and graph modules
"""
from __future__ import annotations
from typing import Iterable

# Generic helpers -----------------------------------------------------------

def _format_list(items: Iterable[str], prefix: str = "  • ") -> str:
    return "\n".join(f"{prefix}{i}" for i in items)

# API Key Errors ------------------------------------------------------------

def missing_api_key(provider: str, export_var: str, extra: str = "") -> str:
    hint = f"export {export_var}=your_{provider.lower()}_key_here"
    return (
        f"❌ {export_var} not set.\n"
        f"Please set your {provider} API key:\n{hint}\n" + (extra if extra else "")
    )

# Connection / Network Errors ----------------------------------------------

def connection_failed(provider: str, backend_url: str) -> str:
    return (
        f"❌ {provider} API connection failed\n"
        f"Unable to connect to {provider} API at {backend_url}\n"
        f"This could be due to:\n" + _format_list([
            "Network connectivity issues",
            "Invalid backend URL",
            "Firewall blocking the connection",
            f"{provider} service temporarily unavailable",
        ]) +
        "\n\nAlternatives:\n" + _format_list([
            "Switch to Gemini: 'llm_provider': 'gemini' in default_config.py",
            "Use offline tools: 'online_tools': False in default_config.py",
        ]) +
        "\nPlease use alternative offline tools or fix the configuration."
    )

# Quota / Rate Limit Errors -------------------------------------------------

def quota_exceeded(provider: str, model: str) -> str:
    return (
        f"❌ {provider} API quota/rate limit exceeded\n"
        f"You have hit usage limits for model '{model}'.\n"
        f"Options:\n" + _format_list([
            "Check billing/usage dashboard",
            "Wait for quota to reset",
            "Switch provider in default_config.py",
            "Use offline tools by setting 'online_tools': False",
        ])
    )

# Authentication Errors -----------------------------------------------------

def authentication_failed(provider: str) -> str:
    return (
        f"❌ {provider} API authentication failed\n"
        f"Your API key appears to be invalid or expired.\n"
        f"Please verify the environment variable and regenerate the key if needed."
    )

# Invalid Model -------------------------------------------------------------

def invalid_model(provider: str, model: str, valid_models: Iterable[str]) -> str:
    listed = _format_list(valid_models)
    return (
        f"❌ Invalid {provider} model: '{model}'\n"
        f"Valid models include:\n{listed}\n"
        f"Update your configuration in default_config.py."
    )

# Generic Provider Error ----------------------------------------------------

def provider_error(provider: str, model: str, error: str, sample_models: Iterable[str]) -> str:
    return (
        f"❌ {provider} API error with model '{model}'\n"
        f"Error: {error}\n"
        f"Valid models (sample): {', '.join(sample_models)}\n"
        f"Consider switching provider or using offline tools."
    )

__all__ = [
    "missing_api_key",
    "connection_failed",
    "quota_exceeded",
    "authentication_failed",
    "invalid_model",
    "provider_error",
]
