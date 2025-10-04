"""Centralized factory for OpenAI-compatible (OpenAI/OpenRouter/Ollama) clients.

This helper reduces duplication when creating an OpenAI SDK `OpenAI` client.
It selects the correct API key env var and enforces base_url usage for
non-OpenAI providers. Falls back cleanly with actionable error messages.

Usage:
    from tradingagents.utils.llm_client import build_openai_compatible_client
    client, embedding_model_name = build_openai_compatible_client(config, purpose="embeddings")

Returned:
    (client, embedding_model_name)

The embedding model name is provided for contexts (like memory) that need
an embedding model hint tied to provider differences.
"""
from __future__ import annotations
import os
import ssl
from typing import Tuple, Optional

try:
    from openai import OpenAI  # type: ignore
    import httpx  # type: ignore
except ImportError as e:  # pragma: no cover
    raise ImportError("openai or httpx package not installed. Install with: pip install openai httpx") from e

# Default model hints per purpose (can be extended later)
DEFAULT_EMBEDDING_MODEL = {
    "openai": "text-embedding-3-small",
    "openrouter": "text-embedding-3-small",  # maps to OpenAI-compatible route
    "ollama": "nomic-embed-text",
}


def _detect_provider(config: dict) -> str:
    provider = (config.get("llm_provider") or "openai").lower()
    # Infer from URL if ambiguous
    backend = config.get("backend_url", "").lower()
    if "openrouter.ai" in backend:
        return "openrouter"
    if "localhost:11434" in backend or "ollama" in provider:
        return "ollama"
    if provider in {"openai", "openrouter", "ollama"}:
        return provider
    return "openai"


def _get_api_key(provider: str) -> Optional[str]:
    if provider == "openrouter":
        return os.getenv("OPENROUTER_API_KEY")
    if provider == "openai":
        return os.getenv("OPENAI_API_KEY")
    # Ollama local server normally does not require key
    return None


def build_openai_compatible_client(
    config: dict, 
    purpose: str = "chat",
    timeout: Optional[int] = None,
    max_retries: Optional[int] = None
) -> Tuple[OpenAI, Optional[str]]:
    """Build and return an OpenAI-compatible client + optional model hint.

    purpose: one of {"chat", "embeddings"} to select default model hint.
    timeout: optional timeout in seconds for API calls.
    max_retries: optional number of retries for failed API calls.
    """
    provider = _detect_provider(config)
    backend_url = config.get("backend_url") or (
        "http://localhost:11434/v1" if provider == "ollama" else "https://api.openai.com/v1"
    )

    api_key = _get_api_key(provider)
    if provider == "openrouter" and not api_key:
        raise ValueError(
            "❌ OPENROUTER_API_KEY not set. Export it with:\n"
            "export OPENROUTER_API_KEY=your_key_here"
        )
    if provider == "openai" and not api_key:
        raise ValueError(
            "❌ OPENAI_API_KEY not set. Export it with:\n"
            "export OPENAI_API_KEY=your_key_here"
        )

    # Configure SSL/TLS for httpx (used by OpenAI SDK)
    httpx_kwargs = {}
    
    # Check for custom certificate bundle
    cert_bundle = config.get("ssl_cert_bundle") or os.getenv("REQUESTS_CA_BUNDLE") or os.getenv("CURL_CA_BUNDLE")
    if cert_bundle and os.path.exists(cert_bundle):
        # Create SSL context with custom certificate bundle
        ssl_context = ssl.create_default_context(cafile=cert_bundle)
        httpx_kwargs["verify"] = ssl_context
    elif not config.get("ssl_verify", True):
        # Disable SSL verification if explicitly set to false
        httpx_kwargs["verify"] = False
    
    # Add timeout if specified
    if timeout is not None:
        httpx_kwargs["timeout"] = timeout
    
    # Create httpx client with SSL configuration
    http_client = httpx.Client(**httpx_kwargs) if httpx_kwargs else None

    # Build OpenAI client kwargs
    client_kwargs = {
        "base_url": backend_url,
        "api_key": api_key
    }
    
    # Add http_client if we configured SSL/timeout
    if http_client is not None:
        client_kwargs["http_client"] = http_client
    
    # Add max_retries if specified (helps with transient connection issues)
    if max_retries is not None:
        client_kwargs["max_retries"] = max_retries
    
    client = OpenAI(**client_kwargs)

    embedding_model = None
    if purpose == "embeddings":
        embedding_model = DEFAULT_EMBEDDING_MODEL.get(provider)

    return client, embedding_model

__all__ = ["build_openai_compatible_client"]
