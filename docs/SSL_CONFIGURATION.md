# SSL Certificate Bundle Configuration for TradingAgents

## Overview

This implementation provides flexible SSL/TLS certificate configuration for TradingAgents while maintaining backward compatibility. The system only applies custom SSL settings when explicitly configured via environment variables.

## Key Features

### 1. Environment Variable Based Configuration
- `REQUESTS_CA_BUNDLE` or `CURL_CA_BUNDLE`: Path to custom certificate bundle
- `SSL_VERIFY`: Enable/disable SSL verification (true/false)
- `HTTP_TIMEOUT`: Custom timeout for HTTP requests (seconds)
- `HTTP_PROXY`: HTTP proxy server
- `HTTPS_PROXY`: HTTPS proxy server

### 2. Default Behavior Preservation
- **If no environment variables are set**: Uses system default SSL behavior
- **Only applies custom settings when explicitly configured**
- **Empty or undefined variables are ignored**

### 3. Comprehensive Coverage
- **LangChain LLM clients**: Custom SSL configuration for OpenAI, OpenRouter, etc.
- **HTTP requests**: Custom configuration for Google News, Reddit APIs
- **Global SSL setup**: Sets environment variables for libraries that respect them

## Usage Examples

### Basic Usage (No Custom SSL)
```bash
# No SSL environment variables set
# Uses system default SSL behavior
python webapp/main.py
```

### Custom Certificate Bundle
```bash
# Use custom corporate certificate bundle
export REQUESTS_CA_BUNDLE=/path/to/corporate-ca-bundle.crt
python webapp/main.py
```

### Development/Testing (Disable SSL Verification)
```bash
# Disable SSL verification (NOT recommended for production)
export SSL_VERIFY=false
python webapp/main.py
```

### Behind Corporate Proxy
```bash
# Configure proxy settings
export HTTP_PROXY=http://proxy.company.com:8080
export HTTPS_PROXY=https://proxy.company.com:8080
export REQUESTS_CA_BUNDLE=/etc/ssl/corporate-ca-bundle.crt
python webapp/main.py
```

## Files Modified

### Core Configuration
- `tradingagents/default_config.py`: Added SSL configuration parameters
- `tradingagents/dataflows/ssl_utils.py`: SSL utility functions (NEW)

### Integration Points
- `tradingagents/graph/trading_graph.py`: LLM client SSL configuration
- `tradingagents/dataflows/googlenews_utils.py`: HTTP requests SSL configuration
- `tradingagents/dataflows/interface.py`: Integration with SSL configuration

### Documentation and Tools
- `.env.example`: Updated with SSL configuration examples
- `diagnose_ssl.py`: SSL diagnostic tool (NEW)
- `test_ssl_config.py`: SSL configuration test suite (NEW)

## Testing

Run the diagnostic tool to check your SSL configuration:
```bash
python diagnose_ssl.py
```

Run the test suite to verify SSL configuration behavior:
```bash
python test_ssl_config.py
```

## Troubleshooting

### Common SSL Errors and Solutions

1. **Certificate verification failed**
   - Set `REQUESTS_CA_BUNDLE` to correct certificate bundle path
   - Check if your organization uses custom CA certificates

2. **SSL: WRONG_VERSION_NUMBER**
   - Usually indicates proxy configuration issues
   - Set appropriate `HTTP_PROXY` and `HTTPS_PROXY` variables

3. **Connection timeout**
   - Increase `HTTP_TIMEOUT` value
   - Check network connectivity and proxy settings

4. **Name or service not known**
   - Check DNS settings
   - Verify proxy configuration

### Getting Help

1. Run `python diagnose_ssl.py` for comprehensive SSL diagnostics
2. Check your organization's IT documentation for certificate bundles
3. Contact your IT department for corporate proxy and certificate information

## Security Considerations

- **Never disable SSL verification in production**
- **Use custom certificate bundles for corporate environments**
- **Keep certificate bundles updated**
- **Secure proxy credentials if using authenticated proxies**