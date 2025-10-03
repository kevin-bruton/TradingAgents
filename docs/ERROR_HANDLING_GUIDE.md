# Enhanced Error Handling Guide

## Overview
The TradingAgents system now includes comprehensive error handling for LLM API issues, providing clear, actionable feedback to users.

## Supported Scenarios

### 1. Invalid Model Configuration
**Error**: When an invalid model name is configured
**Response**: 
- ❌ Clear error message indicating the invalid model
- 📋 List of valid models for the current provider
- 🔧 Specific configuration instructions

### 2. API Quota Exceeded
**Error**: When API usage limits are reached
**Response**:
- ❌ Clear quota exceeded message
- 🔗 Direct links to billing/quota management
- 🔄 Alternative provider suggestions
- 📴 Offline tools recommendation

### 3. Missing API Keys
**Error**: When required environment variables are not set
**Response**:
- ❌ Clear missing API key message
- 🔑 Exact export command to set the key
- 🔗 Links to get API keys

### 4. Connection Issues
**Error**: When network/connectivity problems occur
**Response**:
- ❌ Connection problem identification
- 🌐 Possible causes (network, firewall, service down)
- 🔄 Alternative provider suggestions

## Configuration Options

### Switching Between Providers
```python
# In tradingagents/default_config.py

# For OpenAI
"llm_provider": "openai",
"quick_think_llm": "gpt-4o-mini",
"deep_think_llm": "gpt-4o",

# For Gemini  
"llm_provider": "gemini",
"gemini_quick_think_llm": "gemini-1.5-flash",
"gemini_deep_think_llm": "gemini-1.5-pro",
```

### Using Offline Tools
```python
# Disable online tools to use local data sources
"online_tools": False,
```

## Valid Models

### OpenAI Models
- `gpt-4o`
- `gpt-4o-mini` 
- `gpt-4-turbo`
- `gpt-4`
- `gpt-3.5-turbo`
- `o1-preview`
- `o1-mini`

### Gemini Models
- `gemini-1.5-pro`
- `gemini-1.5-flash`
- `gemini-1.0-pro`
- `gemini-pro`

## Required Environment Variables

### For OpenAI
```bash
export OPENAI_API_KEY=your_openai_key_here
```

### For Gemini
```bash
export GOOGLE_API_KEY=your_google_api_key_here
```

### For OpenRouter
```bash
export OPENROUTER_API_KEY=your_openrouter_api_key_here
```

## Error Handling Flow

1. **Agent Tool Called** → Online LLM function invoked
2. **API Error Occurs** → Comprehensive error handling triggers
3. **User-Friendly Message** → Detailed error with solutions returned
4. **Agent Continues** → Can use offline tools or different approach

## Benefits

- **Clear Problem Identification**: Emoji indicators and specific error types
- **Actionable Solutions**: Multiple alternatives provided for each error
- **Graceful Degradation**: Agents can continue with offline tools
- **User Education**: Links to documentation and setup guides
- **Configuration Guidance**: Exact settings and commands provided