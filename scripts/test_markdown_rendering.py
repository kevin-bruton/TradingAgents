"""Test script to understand markdown rendering issues with the 'marked' library."""

# Example markdown content that might have issues with 'marked'
test_markdown = """
### Stock Analysis

The price dropped from ~$250 to ~$200, representing a ~20% decline.

**Key Points:**
- Support level at ~$187
- Resistance around ~$260
- ATR peaked near ~5.0

The 50 SMA (~231) provides dynamic support.

**Percentage Changes:**
- Q1: ~15% gain
- Q2: ~8% decline
- Overall: ~5% increase

Price gap of ~5-8 points suggests volatility.
"""

print("Testing markdown content:")
print(test_markdown)
print("\n" + "="*50)
print("\nIssues with 'marked' library:")
print("- The '~' character is interpreted as strikethrough delimiter")
print("- This causes ~$250 to render as strikethrough instead of approximately $250")
print("- GFM (GitHub Flavored Markdown) uses ~~ for strikethrough, not single ~")
print("- But 'marked' with gfm:true may interpret single ~ as strikethrough")
