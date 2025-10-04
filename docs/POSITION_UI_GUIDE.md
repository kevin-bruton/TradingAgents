# Position Configuration UI Guide

## Visual Layout

```
┌─────────────────────────────────────────────────────────────┐
│ Multi-Run Configuration                                     │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│ Company Symbols (CSV):                                     │
│ ┌─────────────────────────────────────────────────────┐   │
│ │ AAPL,MSFT,NVDA                                      │   │
│ └─────────────────────────────────────────────────────┘   │
│                                                             │
│ [Standard configuration fields: LLM Provider, Models, etc.]│
│                                                             │
│ ┌───────────────────────────────────────────────────────┐ │
│ │ Position Configuration                                │ │
│ │ ═══════════════════════════════════════════════════   │ │
│ │ Configure existing positions for each instrument.     │ │
│ │ Leave stop loss and take profit at 0 if not set.     │ │
│ │                                                       │ │
│ │ ┌───────────────────────────────────────────────┐   │ │
│ │ │ AAPL                                          │   │ │
│ │ ├───────────────────────────────────────────────┤   │ │
│ │ │ Position:    │ Stop Loss ($):│Take Profit($):│   │ │
│ │ │ ┌──────────┐ │ ┌──────────┐ │ ┌──────────┐  │   │ │
│ │ │ │ Long  ▼  │ │ │ 180.50   │ │ │ 195.00   │  │   │ │
│ │ │ └──────────┘ │ └──────────┘ │ └──────────┘  │   │ │
│ │ └───────────────────────────────────────────────┘   │ │
│ │                                                       │ │
│ │ ┌───────────────────────────────────────────────┐   │ │
│ │ │ MSFT                                          │   │ │
│ │ ├───────────────────────────────────────────────┤   │ │
│ │ │ Position:    │ Stop Loss ($):│Take Profit($):│   │ │
│ │ │ ┌──────────┐ │ ┌──────────┐ │ ┌──────────┐  │   │ │
│ │ │ │ Short ▼  │ │ │ 425.00   │ │ │ 400.00   │  │   │ │
│ │ │ └──────────┘ │ └──────────┘ │ └──────────┘  │   │ │
│ │ └───────────────────────────────────────────────┘   │ │
│ │                                                       │ │
│ │ ┌───────────────────────────────────────────────┐   │ │
│ │ │ NVDA                                          │   │ │
│ │ ├───────────────────────────────────────────────┤   │ │
│ │ │ Position:    │ Stop Loss ($):│Take Profit($):│   │ │
│ │ │ ┌──────────┐ │ ┌──────────┐ │ ┌──────────┐  │   │ │
│ │ │ │ None  ▼  │ │ │ 0        │ │ │ 0        │  │   │ │
│ │ │ └──────────┘ │ └──────────┘ │ └──────────┘  │   │ │
│ │ └───────────────────────────────────────────────┘   │ │
│ └───────────────────────────────────────────────────┘ │
│                                                             │
│ ┌─────────────────────────────────────────────────────┐   │
│ │         Start Multi-Run                             │   │
│ └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

## Dynamic Behavior

### When User Types Symbols
1. User types: "AAPL"
   - Position card for AAPL appears
   
2. User adds: "AAPL,MSFT"
   - Position cards for AAPL and MSFT appear
   
3. User changes to: "AAPL,MSFT,NVDA,TSLA"
   - Position cards for all 4 symbols appear
   
4. User changes to: "AAPL,TSLA"
   - Only AAPL and TSLA cards remain
   - Previous settings for AAPL and TSLA are preserved

### Data Persistence
```
User Action                → localStorage Update
───────────────────────────────────────────────────────
Set AAPL position to Long → instrument_positions: {
                              "AAPL": {
                                "position": "long",
                                "stop_loss": "0",
                                "take_profit": "0"
                              }
                            }

Set AAPL stop loss to 180 → instrument_positions: {
                              "AAPL": {
                                "position": "long",
                                "stop_loss": "180",
                                "take_profit": "0"
                              }
                            }

Add MSFT position        → instrument_positions: {
                              "AAPL": {...},
                              "MSFT": {
                                "position": "short",
                                "stop_loss": "425",
                                "take_profit": "400"
                              }
                            }
```

## Form Submission Data

### What Gets Sent to Backend
```javascript
FormData {
  company_symbols: "AAPL,MSFT,NVDA",
  llm_provider: "openai",
  quick_think_llm: "gpt-4o-mini",
  deep_think_llm: "o4-mini",
  max_debate_rounds: "1",
  cost_per_trade: "2.0",
  analysis_date: "2025-10-03",
  instrument_positions: `{
    "AAPL": {
      "position": "long",
      "stop_loss": 180.50,
      "take_profit": 195.00
    },
    "MSFT": {
      "position": "short",
      "stop_loss": 425.00,
      "take_profit": 400.00
    },
    "NVDA": {
      "position": "none",
      "stop_loss": 0,
      "take_profit": 0
    }
  }`
}
```

## Backend Processing Flow

```
┌─────────────────┐
│ Form Submission │
└────────┬────────┘
         │
         ▼
┌──────────────────────┐
│ Parse JSON positions │
└────────┬─────────────┘
         │
         ▼
┌─────────────────────────────┐
│ For each instrument symbol: │
├─────────────────────────────┤
│ 1. Extract position config  │
│ 2. Validate values          │
│ 3. Convert 0 → None         │
│ 4. Create config_payload    │
│ 5. Create run               │
│ 6. Start worker thread      │
└────────┬────────────────────┘
         │
         ▼
┌────────────────────────┐
│ AAPL Run               │
│ config: {              │
│   user_position: "long"│
│   initial_stop_loss:   │
│     180.50             │
│   initial_take_profit: │
│     195.00             │
│ }                      │
└────────────────────────┘
         │
         ├──────────────────────────┐
         │                          │
         ▼                          ▼
┌────────────────────────┐  ┌────────────────────────┐
│ MSFT Run               │  │ NVDA Run               │
│ config: {              │  │ config: {              │
│   user_position:"short"│  │   user_position:"none" │
│   initial_stop_loss:   │  │   initial_stop_loss:   │
│     425.00             │  │     None               │
│   initial_take_profit: │  │   initial_take_profit: │
│     400.00             │  │     None               │
│ }                      │  │ }                      │
└────────────────────────┘  └────────────────────────┘
```

## Color Scheme (Dark Theme)

- Background: `#1a1a1a` (dark gray)
- Panel Background: `#242424` (lighter dark gray)
- Card Background: `#2d2d2d` (card gray)
- Border: `#333` (dark border)
- Text Primary: `#e0e0e0` (light gray)
- Text Secondary: `#a0a0a0` (medium gray)
- Accent (headers, focus): `#4CAF50` (green)
- Input Background: `#2a2a2a`

## Responsive Design

### Desktop (> 768px)
```
┌────────────────────────────┐
│ Position | Stop Loss | TP  │
│  Long    |  180.50   |195  │
└────────────────────────────┘
```

### Mobile (≤ 768px)
```
┌────────────┐
│ Position   │
│  Long      │
├────────────┤
│ Stop Loss  │
│  180.50    │
├────────────┤
│ Take Profit│
│  195.00    │
└────────────┘
```

## Key Features

✅ **Dynamic Field Generation**: Position fields appear/disappear as symbols are added/removed
✅ **Independent Configuration**: Each instrument has its own position settings
✅ **Data Persistence**: Settings saved to localStorage and survive page refresh
✅ **Real-time Updates**: Changes are saved immediately as user types/selects
✅ **Validation**: Position status validated, 0 values treated as "not set"
✅ **Dark Theme**: Matches existing UI aesthetic
✅ **Responsive**: Adapts to mobile and desktop screens
✅ **Backward Compatible**: Legacy single-value parameters still supported
