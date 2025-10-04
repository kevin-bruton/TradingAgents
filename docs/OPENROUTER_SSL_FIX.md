# OpenRouter SSL Connection Fix - Summary

## Problem
Connection errors when calling `_call_llm_api` to retrieve social and news data using OpenRouter API through corporate Netskope proxy:
```
❌ OpenRouter API connection failed
Unable to connect to OpenRouter API at https://openrouter.ai/api/v1
Raw error: Connection error.
```

## Root Cause
The OpenAI Python SDK uses `httpx` for HTTP requests, which doesn't automatically recognize the `REQUESTS_CA_BUNDLE` or `CURL_CA_BUNDLE` environment variables that contain the Netskope SSL certificate bundle path. Without explicit SSL configuration, `httpx` couldn't validate the SSL certificates presented by the Netskope proxy.

## Solution
Modified `tradingagents/utils/llm_client.py` to:
1. Detect custom SSL certificate bundles from config or environment variables
2. Create an `httpx.Client` with custom SSL context using the certificate bundle
3. Pass the configured `httpx` client to the OpenAI SDK

### Code Changes

**File:** `tradingagents/utils/llm_client.py`

Added imports:
```python
import ssl
import httpx
```

Enhanced `build_openai_compatible_client()` function:
```python
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

# Add max_retries if specified
if max_retries is not None:
    client_kwargs["max_retries"] = max_retries

client = OpenAI(**client_kwargs)
```

## Compatibility

✅ **Works WITH Netskope proxy** (custom certificates)
- Detects `REQUESTS_CA_BUNDLE` or `CURL_CA_BUNDLE` from environment
- Creates custom SSL context with certificate bundle
- SSL verification succeeds through corporate proxy

✅ **Works WITHOUT Netskope proxy** (normal environment)
- When no custom certificate is specified, uses system defaults
- Falls back gracefully when certificate file doesn't exist
- OpenAI SDK uses standard SSL behavior

✅ **Backward Compatible**
- No changes needed to calling code
- Works with existing timeout and retry configurations
- Respects `ssl_verify` flag for disabling verification (if needed)

## Testing

### Test 1: Basic OpenRouter Connection
```bash
uv run test_openrouter_ssl_fix.py
```
**Result:** ✅ SUCCESS - API call completed successfully

### Test 2: News Tool Integration
```bash
uv run test_news_tools_connection.py
```
**Result:** ✅ SUCCESS - News tool can connect to OpenRouter

### Test 3: SSL Compatibility
```bash
uv run test_ssl_compatibility.py
```
**Result:** ✅ SUCCESS - All scenarios work correctly:
- With custom SSL certificates (Netskope)
- Without custom certificates (system default)
- Missing certificate file (graceful fallback)
- SSL verification disabled (explicit override)

## Configuration

The SSL certificate configuration is loaded from:

1. **Config dictionary:** `config["ssl_cert_bundle"]`
2. **Environment variable:** `REQUESTS_CA_BUNDLE`
3. **Environment variable:** `CURL_CA_BUNDLE`

Current `.env` file has:
```bash
REQUESTS_CA_BUNDLE=/Users/kevin.bruton/netskope-certificates/combined-cert-bundle.pem
CURL_CA_BUNDLE=/Users/kevin.bruton/netskope-certificates/combined-cert-bundle.pem
```

## Impact

This fix resolves connection errors for:
- ✅ `get_stock_news_from_llm()` - News retrieval tool
- ✅ `get_global_news_from_llm()` - Global news tool
- ✅ `get_fundamentals_from_llm()` - Fundamentals tool
- ✅ Any other tool using `_call_llm_api()` with OpenRouter

## Files Modified

1. `tradingagents/utils/llm_client.py` - Added SSL certificate support for httpx client

## Test Files Created

1. `test_openrouter_ssl_fix.py` - Basic connection test
2. `test_news_tools_connection.py` - News tool integration test
3. `test_ssl_compatibility.py` - Multi-scenario compatibility test

## Notes

- The fix is transparent to users - works in both Netskope and non-Netskope environments
- No code changes required in other parts of the codebase
- Existing timeout and retry configurations continue to work
- SSL certificate validation ensures secure connections through corporate proxies

## Date
October 3, 2025
