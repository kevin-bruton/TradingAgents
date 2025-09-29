from webapp.main import render_markdown

def test_markdown_basic_headers():
    md_text = "# Title\n\nSome **bold** text and a table:\n\n| Col1 | Col2 |\n| ---- | ---- |\n| A | B |\n"
    html = render_markdown(md_text)
    assert '<h1>' in html and 'Title' in html
    assert '<strong>' in html and 'bold' in html
    assert '<table>' in html

def test_markdown_code_block():
    md_text = "```python\nprint('hi')\n```"
    html = render_markdown(md_text)
    # Sanitized but should keep code element
    assert 'print' in html and '<code' in html
