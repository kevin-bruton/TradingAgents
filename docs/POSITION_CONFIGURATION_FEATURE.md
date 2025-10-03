# Position Configuration Feature

## Overview
This feature allows users to specify existing positions, stop loss levels, and take profit levels for each instrument in the multi-run configuration. Each instrument can have independent position settings.

## Changes Made

### 1. Frontend Changes

#### HTML (`webapp/templates/index.html`)
- Added a **Position Configuration** section to the multi-run form
- Created a container (`#position-instruments-list`) for dynamically generated per-instrument position fields
- Position fields are generated dynamically based on the company symbols entered

#### JavaScript (`webapp/static/js/config.js`)
- Added `updatePositionFields()` function to dynamically generate position configuration fields for each instrument
- Added `saveInstrumentPosition()` function to persist position settings in localStorage
- Added `getAllInstrumentPositions()` function to collect all position settings when submitting the form
- Enhanced `initializeConfigFields()` to initialize position fields and listen for symbol changes
- Modified form submission to include per-instrument position data as JSON

#### CSS (`webapp/static/styles.css`)
- Added styles for `.position-instrument-fieldset` to create visually distinct cards for each instrument
- Added `.position-instrument-header` styling with accent color for instrument names
- Added `.position-fields-grid` with 3-column grid layout for position, stop loss, and take profit fields
- Added responsive styling that switches to single-column layout on smaller screens
- Styled input and select fields within position configuration to match the dark theme

### 2. Backend Changes

#### FastAPI Endpoint (`webapp/main.py`)
- Modified `/start-multi` endpoint to accept `instrument_positions` parameter (JSON string)
- Added parsing logic to extract per-instrument position configurations
- Updated to create separate config payloads for each instrument with its specific position settings
- Maintained backward compatibility with legacy single-value parameters
- Position validation ensures:
  - Valid position values: "none", "long", or "short"
  - Stop loss and take profit are ignored when position is "none"
  - Stop loss and take profit values of 0 are converted to `None` (no level set)
  - Non-positive values are treated as "not set"

## User Interface

### Position Configuration Fields (Per Instrument)
Each instrument specified in the "Company Symbols" field gets its own position configuration card with:

1. **Position Status** (dropdown):
   - None (default)
   - Long
   - Short

2. **Stop Loss** (number input):
   - Default: 0 (indicates no stop loss set)
   - Accepts decimal values
   - Only relevant when position is Long or Short

3. **Take Profit** (number input):
   - Default: 0 (indicates no take profit set)
   - Accepts decimal values
   - Only relevant when position is Long or Short

### Data Persistence
- All position configurations are saved to localStorage
- Settings persist across browser sessions
- Automatically restored when revisiting the page
- Updated dynamically as users modify instrument symbols

## Data Flow

1. User enters company symbols (e.g., "AAPL,MSFT,NVDA")
2. JavaScript dynamically generates position fields for each symbol
3. User configures position settings for each instrument
4. Settings are saved to localStorage on change
5. On form submission, all position data is collected and sent as JSON
6. Backend parses JSON and creates per-instrument configurations
7. Each instrument's trading process receives its specific position settings
8. Trading graph uses position settings to inform agent decision-making

## Example Configuration

### For AAPL:
- Position: Long
- Stop Loss: $180.50
- Take Profit: $195.00

### For MSFT:
- Position: Short
- Stop Loss: $425.00
- Take Profit: $400.00

### For NVDA:
- Position: None
- Stop Loss: 0 (ignored)
- Take Profit: 0 (ignored)

## Technical Details

### JSON Format
```json
{
  "AAPL": {
    "position": "long",
    "stop_loss": "180.50",
    "take_profit": "195.00"
  },
  "MSFT": {
    "position": "short",
    "stop_loss": "425.00",
    "take_profit": "400.00"
  },
  "NVDA": {
    "position": "none",
    "stop_loss": "0",
    "take_profit": "0"
  }
}
```

### Backend Processing
- Parses JSON string from form data
- Extracts configuration for each symbol
- Validates position status
- Converts numeric values (0 becomes None)
- Creates individual config payloads per instrument
- Passes to trading graph's propagate method

## Backward Compatibility
- Single-run endpoint (`/start`) still uses simple form parameters
- Legacy parameters (`position_status`, `current_stop_loss`, `current_take_profit`) still work if per-instrument config not provided
- Existing functionality remains unchanged for single-instrument analysis

## Testing Recommendations

1. **Basic Functionality**
   - Enter multiple symbols and verify position fields appear
   - Change symbols and verify fields update dynamically
   - Set different positions for different instruments

2. **Data Persistence**
   - Set position configurations
   - Refresh the page
   - Verify all settings are restored

3. **Validation**
   - Set position to "none" and verify stop loss/take profit are ignored
   - Enter zero values and verify they're treated as "not set"
   - Test with negative values (should be rejected or treated as 0)

4. **Multi-Run Execution**
   - Start a multi-run with different position settings per instrument
   - Verify each instrument's analysis reflects its specific position
   - Check that stop loss/take profit recommendations consider existing levels

## Future Enhancements

- Add visual indicators showing which instruments have positions configured
- Add validation warnings (e.g., stop loss above current price for long position)
- Add preset templates (e.g., "All Long", "All Short", "Clear All")
- Add bulk edit functionality for multiple instruments
- Display current market prices next to position fields for context
