"""Central loader for providers_models.yaml.

Provides helper functions to access provider metadata and model lists
from a single source of truth used by both CLI and WebApp.
"""
from __future__ import annotations
import os
import threading
from pathlib import Path
from typing import Dict, List, Any, Optional
import yaml
import re

__all__ = [
    "ConfigError",
    "load_config",
    "get_providers",
    "get_provider_info",
    "get_provider_base_url",
    "get_models",
    "validate_model",
]

CONFIG_FILENAME = "providers_models.yaml"
_config_cache: Dict[str, Any] | None = None
_config_mtime: float | None = None
_lock = threading.Lock()

class ConfigError(RuntimeError):
    pass

def _interpolate_env(value: str) -> str:
    """Render simple Jinja-like {{ VAR | default('x') }} placeholders in base_url.
    Only supports pattern {{ VAR }} or {{ VAR | default('value') }}.
    """
    pattern = re.compile(r"\{\{\s*([A-Z0-9_]+)(?:\s*\|\s*default\('([^']*)'\))?\s*\}\}")
    def repl(match):
        var = match.group(1)
        default = match.group(2)
        return os.getenv(var, default if default is not None else "")
    return pattern.sub(repl, value)

def _load_from_disk() -> Dict[str, Any]:
    path = Path(CONFIG_FILENAME)
    if not path.exists():
        raise ConfigError(f"Configuration file '{CONFIG_FILENAME}' not found at project root.")
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    if "providers" not in data or not isinstance(data["providers"], dict):
        raise ConfigError("Invalid configuration: missing top-level 'providers' mapping")
    # Interpolate environment variables in base_url fields
    for key, info in data["providers"].items():
        base_url = info.get("base_url")
        if isinstance(base_url, str):
            info["base_url"] = _interpolate_env(base_url)
    return data

def load_config(force: bool = False) -> Dict[str, Any]:
    global _config_cache, _config_mtime
    path = Path(CONFIG_FILENAME)
    with _lock:
        mtime = path.stat().st_mtime if path.exists() else None
        if force or _config_cache is None or (mtime and _config_mtime and mtime > _config_mtime):
            _config_cache = _load_from_disk()
            _config_mtime = mtime
    return _config_cache  # type: ignore

def get_providers() -> List[Dict[str, Any]]:
    cfg = load_config()
    out = []
    for key, info in cfg["providers"].items():
        out.append({
            "key": key,
            "display_name": info.get("display_name", key.title()),
            "base_url": info.get("base_url"),
            "models": info.get("models", {}),
        })
    return out

def get_provider_info(provider_key: str) -> Dict[str, Any]:
    cfg = load_config()
    info = cfg["providers"].get(provider_key)
    if not info:
        raise ConfigError(f"Unknown provider '{provider_key}'")
    return info

def get_provider_base_url(provider_key: str) -> str:
    return get_provider_info(provider_key).get("base_url")

def get_models(provider_key: str, tier: str) -> List[Dict[str, str]]:
    info = get_provider_info(provider_key)
    models = info.get("models", {})
    tier_list = models.get(tier, [])
    # Normalize each to {id, name}
    normalized = []
    for m in tier_list:
        if isinstance(m, dict) and "id" in m:
            normalized.append({"id": m["id"], "name": m.get("name", m["id"])})
        elif isinstance(m, str):
            normalized.append({"id": m, "name": m})
    return normalized

def validate_model(provider_key: str, model_id: str) -> bool:
    info = get_provider_info(provider_key)
    models = info.get("models", {})
    for tier_list in models.values():
        for m in tier_list:
            if (isinstance(m, dict) and m.get("id") == model_id) or (isinstance(m, str) and m == model_id):
                return True
    return False
