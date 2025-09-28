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
}
