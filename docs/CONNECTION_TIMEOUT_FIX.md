# Connection Timeout Fix for News/Social Tools

## Problem Statement

Connection errors were occurring when calling `_call_llm_api` to retrieve social media and news data. These tools would timeout or fail with connection errors while other LLM API calls worked fine.

## Root Cause Analysis

The issue was that the `_call_llm_api` function (used by news/social tools) did not respect the `http_timeout` and `llm_max_retries` configuration settings that were available in the system.

**Key Issues:**
1. **No Timeout Configuration**: The OpenAI client was created without a timeout parameter, using the SDK's default (which is quite short)
2. **No Retry Logic**: Unlike other analyst agents that use `safe_invoke_llm`, the news/social tools had no retry mechanism for transient connection failures
3. **Missing Max Retries**: The OpenAI SDK's `max_retries` parameter wasn't being used
4. **Gemini Path Not Configured**: The Gemini code path also didn't use timeout settings

News and social media queries often take longer to process than other queries, making them more susceptible to timeout issues.

## Solution Implemented

### 1. Enhanced `llm_client.py`

**File**: `tradingagents/utils/llm_client.py`

Added `timeout` and `max_retries` parameters to `build_openai_compatible_client()`:

```python
def build_openai_compatible_client(
    config: dict, 
    purpose: str = "chat",
    timeout: Optional[int] = None,
    max_retries: Optional[int] = None
) -> Tuple[OpenAI, Optional[str]]:
    # ... existing code ...
    
    # Build client kwargs
    client_kwargs = {
        "base_url": backend_url,
        "api_key": api_key
    }
    
    # Add timeout if specified (helps with long-running queries like news/social)
    if timeout is not None:
        client_kwargs["timeout"] = timeout
    
    # Add max_retries if specified (helps with transient connection issues)
    if max_retries is not None:
        client_kwargs["max_retries"] = max_retries
    
    client = OpenAI(**client_kwargs)
```

### 2. Updated `_call_llm_api` for OpenAI-Compatible Providers

**File**: `tradingagents/dataflows/interface.py`

Modified to pass timeout and max_retries from config:

```python
# Centralized client creation (ensures base_url + correct key usage)
# Pass timeout and max_retries to handle long-running news/social queries
client, _embedding_hint = build_openai_compatible_client(
    config, 
    purpose="chat",
    timeout=config.get("http_timeout"),
    max_retries=config.get("llm_max_retries", 3)
)
```

### 3. Updated `_call_llm_api` for Gemini Provider

Added timeout and max_retries support for Gemini:

```python
# Build Gemini model with timeout support
gemini_kwargs = {
    "model": model,
    "temperature": 1,
    "max_tokens": 4096,
    "google_api_key": api_key
}

# Add timeout if configured (helps with long-running news/social queries)
if config.get("http_timeout"):
    gemini_kwargs["timeout"] = config["http_timeout"]

# Add max_retries if configured
if config.get("llm_max_retries"):
    gemini_kwargs["max_retries"] = config["llm_max_retries"]

gemini_model = ChatGoogleGenerativeAI(**gemini_kwargs)
```

### 4. Added Retry Logic Wrapper

Created `_call_llm_api_with_retry()` function with intelligent retry logic:

```python
def _call_llm_api_with_retry(prompt, config, max_attempts=None):
    """Wrapper around _call_llm_api with retry logic for transient errors.
    
    This is specifically useful for long-running queries like news/social media
    that may experience connection timeouts or temporary network issues.
    """
```

**Features:**
- Exponential backoff with jitter
- Distinguishes between transient (retryable) and permanent (non-retryable) errors
- Retries on: connection errors, timeouts, network errors, 503/504 errors
- Does NOT retry: authentication errors, invalid model, quota/rate limit errors (429, 401, 403)
- Configurable via `llm_max_retries` and `llm_retry_backoff` settings

### 5. Updated News/Social Tool Functions

All three functions now use the retry wrapper:

```python
def get_stock_news_from_llm(ticker, curr_date):
    """Get stock news from LLM with automatic retry for transient errors."""
    config = get_config()
    prompt = f"Can you search Social Media for {ticker}..."
    return _call_llm_api_with_retry(prompt, config)

def get_global_news_from_llm(curr_date):
    """Get global news from LLM with automatic retry for transient errors."""
    # ... uses _call_llm_api_with_retry

def get_fundamentals_from_llm(ticker, curr_date):
    """Get fundamentals from LLM with automatic retry for transient errors."""
    # ... uses _call_llm_api_with_retry
```

## Configuration Options

Users can now configure these settings in their environment or `default_config.py`:

### HTTP_TIMEOUT
Set a longer timeout for API calls (especially useful for news/social queries):

```bash
export HTTP_TIMEOUT=120  # 2 minutes
```

Or in `default_config.py`:
```python
"http_timeout": 120,
```

### LLM_MAX_RETRIES
Configure how many retry attempts to make:

```bash
export LLM_MAX_RETRIES=5  # Default is 3
```

### LLM_RETRY_BACKOFF
Configure the base delay for exponential backoff:

```bash
export LLM_RETRY_BACKOFF=2  # Default is 2 seconds
```

## Benefits

1. **Resilient to Transient Errors**: Automatic retry with exponential backoff handles temporary network issues
2. **Configurable Timeouts**: Users can set appropriate timeouts based on their network conditions
3. **Consistent with SDK Best Practices**: Uses the OpenAI SDK's built-in retry mechanisms
4. **Provider Agnostic**: Works with OpenAI, OpenRouter, Ollama, and Gemini
5. **Better User Experience**: Provides informative retry messages during transient failures
6. **Avoids Wasted Retries**: Doesn't retry permanent errors like authentication failures or rate limits

## Testing Recommendations

1. **Test with slow network**:
   ```bash
   export HTTP_TIMEOUT=180
   export LLM_MAX_RETRIES=5
   # Run your trading analysis
   ```

2. **Test with different providers**:
   - OpenAI: Should respect timeout and max_retries
   - OpenRouter: Should respect timeout and max_retries
   - Gemini: Should respect timeout and max_retries
   - Ollama: Should respect timeout and max_retries

3. **Verify retry behavior**:
   - Temporarily disable network to see retry messages
   - Check that permanent errors (like invalid API key) don't retry

## Related Files Modified

- `tradingagents/utils/llm_client.py`: Added timeout/max_retries parameters
- `tradingagents/dataflows/interface.py`: 
  - Updated `_call_llm_api()` for both OpenAI and Gemini paths
  - Added `_call_llm_api_with_retry()` helper
  - Updated `get_stock_news_from_llm()`
  - Updated `get_global_news_from_llm()`
  - Updated `get_fundamentals_from_llm()`

## Backward Compatibility

All changes are backward compatible:
- Timeout and max_retries are optional parameters
- If not configured, the system uses SDK defaults
- Existing code continues to work without any changes

## Future Improvements

Consider:
1. Adding telemetry/metrics for retry statistics
2. Per-tool timeout configuration (different timeouts for different types of queries)
3. Circuit breaker pattern for repeated failures
4. Caching of successful responses to reduce API calls
