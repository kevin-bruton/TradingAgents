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
from typing import Tuple, Optional

try:
    from openai import OpenAI  # type: ignore
except ImportError as e:  # pragma: no cover
    raise ImportError("openai package not installed. Install with: pip install openai") from e

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


def build_openai_compatible_client(config: dict, purpose: str = "chat") -> Tuple[OpenAI, Optional[str]]:
    """Build and return an OpenAI-compatible client + optional model hint.

    purpose: one of {"chat", "embeddings"} to select default model hint.
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

    # For Ollama we omit api_key (local server)
    client = OpenAI(base_url=backend_url, api_key=api_key)

    embedding_model = None
    if purpose == "embeddings":
        embedding_model = DEFAULT_EMBEDDING_MODEL.get(provider)

    return client, embedding_model

__all__ = ["build_openai_compatible_client"]
