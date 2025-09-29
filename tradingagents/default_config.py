import os

DEFAULT_CONFIG = {
    "project_dir": os.path.abspath(os.path.join(os.path.dirname(__file__), ".")),
    "results_dir": os.getenv("TRADINGAGENTS_RESULTS_DIR", "./results"),
    "data_dir": "./data",
    "data_cache_dir": os.path.join(
        os.path.abspath(os.path.join(os.path.dirname(__file__), ".")),
        "dataflows/data_cache",
    ),
    # LLM settings
    "llm_provider": "openai",  # "openai"/"gemini"/"openrouter"/"ollama"
    "deep_think_llm": "o4-mini",
    "quick_think_llm": "gpt-4o-mini",
    "backend_url": "https://api.openai.com/v1",
    # Gemini settings (used when llm_provider is "gemini")
    "gemini_deep_think_llm": "gemini-1.5-pro",
    "gemini_quick_think_llm": "gemini-1.5-flash",
    # Memory settings
    "use_local_embeddings": True,  # Use local embeddings instead of API calls
    # Debate and discussion settings
    "max_debate_rounds": 1,
    "max_risk_discuss_rounds": 1,
    "max_recur_limit": 100,
    # Tool settings
    "online_tools": True,
    "user_position": "none",
    "cost_per_trade": 0.0,
    # SSL/TLS Certificate settings - only use if explicitly set
    "ssl_cert_bundle": os.getenv("REQUESTS_CA_BUNDLE") or os.getenv("CURL_CA_BUNDLE"),
    "ssl_verify": os.getenv("SSL_VERIFY", "true").lower() in ("true", "1", "yes"),
    "http_timeout": int(os.getenv("HTTP_TIMEOUT")) if os.getenv("HTTP_TIMEOUT") else None,
    # Proxy settings (if needed)
    "http_proxy": os.getenv("HTTP_PROXY"),
    "https_proxy": os.getenv("HTTPS_PROXY"),
    # LLM resilience settings
    "llm_max_retries": int(os.getenv("LLM_MAX_RETRIES", "3")),
    "llm_retry_backoff": float(os.getenv("LLM_RETRY_BACKOFF", "2")),  # seconds exponential base
    "debug_http": os.getenv("DEBUG_HTTP", "false").lower() in ("1", "true", "yes"),
}
