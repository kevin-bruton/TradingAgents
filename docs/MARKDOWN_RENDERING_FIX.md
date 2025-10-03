# Markdown Rendering Fix: Tilde (~) Strikethrough Issue

## Problem

The "marked" JavaScript library was incorrectly interpreting single tilde (`~`) characters as strikethrough delimiters, which conflicted with the common usage of `~` to indicate approximate values in trading reports (e.g., `~$250`, `~20%`).

### Root Cause

When `marked.parse()` is configured with `{ gfm: true }`, it enables GitHub Flavored Markdown (GFM) extensions. However, the implementation was incorrectly treating single tildes as strikethrough markers, when the proper GFM standard requires **double tildes** (`~~text~~`) for strikethrough.

### Impact

- Reports showing prices like "~$250" were being rendered with strikethrough styling
- Approximate percentages like "~20%" appeared crossed out
- Technical indicators like "~5.0" were misinterpreted
- This made the reports confusing and harder to read

## Solution

The fix involves two complementary approaches:

### 1. Frontend JavaScript Fix (webapp/static/js/content.js)

Updated the `renderContentForItem()` function to include a custom extension that overrides the default strikethrough behavior:

```javascript
export function renderContentForItem(itemId, raw) {
  if (!raw) return '';
  const isReport = /_report$/.test(itemId);
  const isMessages = /_messages$/.test(itemId);
  if (isReport || isMessages || isLikelyMarkdown(raw)) {
    try { 
      return window.marked.parse(raw, { 
        breaks: true, 
        gfm: true,
        // Custom extension to only recognize ~~ as strikethrough
        extensions: [{
          name: 'del',
          level: 'inline',
          start(src) { return src.match(/~~/)?.index; },
          tokenizer(src) {
            const match = src.match(/^~~(?=\S)([\s\S]*?\S)~~/);
            if (match) {
              return {
                type: 'del',
                raw: match[0],
                text: match[1]
              };
            }
          },
          renderer(token) {
            return `<del>${this.parser.parseInline(token.text)}</del>`;
          }
        }]
      }); 
    } catch { return raw; }
  }
  return raw;
}
```

**How it works:**
- The custom extension explicitly defines strikethrough to require double tildes (`~~`)
- Single tildes are now treated as literal characters
- This aligns with proper GFM specification

### 2. Agent Prompt Updates

Added markdown formatting guidelines to all agent system prompts to instruct LLMs to avoid problematic patterns:

**Files updated:**
- `tradingagents/agents/analysts/market_analyst.py`
- `tradingagents/agents/analysts/fundamentals_analyst.py`
- `tradingagents/agents/analysts/news_analyst.py`
- `tradingagents/agents/analysts/social_media_analyst.py`
- `tradingagents/agents/trader/trader.py`
- `tradingagents/agents/managers/research_manager.py`
- `tradingagents/agents/managers/risk_manager.py`
- `tradingagents/agents/risk_mgmt/aggresive_debator.py`
- `tradingagents/agents/risk_mgmt/conservative_debator.py`
- `tradingagents/agents/risk_mgmt/neutral_debator.py`
- `tradingagents/agents/researchers/bull_researcher.py`
- `tradingagents/agents/researchers/bear_researcher.py`

**Guidelines added:**
```
IMPORTANT MARKDOWN FORMATTING GUIDELINES:
- Use 'approximately', 'around', or 'about' instead of the tilde symbol (~) when describing approximate values
- For example, write 'approximately $250' or 'around $250' instead of '~$250'
- If you need to use strikethrough, use double tildes (~~text~~) not single tilde
- This ensures proper markdown rendering in the web interface
```

**Benefits of this approach:**
- Prevents the issue at the source by guiding LLM output
- Makes reports more readable even in plain text
- Reduces ambiguity in generated content
- Future-proofs against rendering engine changes

## Testing

A test HTML file (`test_markdown_fix.html`) has been created to demonstrate:
1. The problem with default marked configuration
2. The solution with the custom extension
3. Various test cases including:
   - Approximate values: `~$250`, `~20%`
   - Proper strikethrough: `~~text~~`
   - Mixed usage scenarios
   - File paths: `~/Documents`

To test:
```bash
# Open the test file in a browser
open test_markdown_fix.html
```

## Verification

After deploying these changes:

1. **For existing reports**: The frontend fix will immediately correct rendering of any reports containing tildes
2. **For new reports**: Both the frontend fix AND the prompt guidelines will ensure proper formatting
3. **Backwards compatibility**: Properly formatted strikethrough (`~~text~~`) continues to work as expected

## Additional Notes

- The fix is defensive: if the custom extension fails, the original text is returned
- No breaking changes to existing functionality
- The solution follows proper GFM specification
- Both CLI and web app rendering are now consistent

## Files Modified

**Frontend:**
- `webapp/static/js/content.js` - Updated renderContentForItem() with custom extension

**Agent Prompts (12 files):**
- All analyst agents (market, fundamentals, news, social)
- Trader agent
- Manager agents (research, risk)
- Debator agents (aggressive, conservative, neutral)
- Researcher agents (bull, bear)

**Testing/Documentation:**
- `test_markdown_fix.html` - Visual test/demonstration
- `test_markdown_rendering.py` - Python documentation of the issue
- `MARKDOWN_RENDERING_FIX.md` - This summary document
