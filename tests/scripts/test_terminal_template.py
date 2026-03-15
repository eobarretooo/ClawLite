from __future__ import annotations


def test_template_returns_string():
    from scripts.terminal_template import build_html
    html = build_html(lines=[])
    assert isinstance(html, str)
    assert "<!DOCTYPE" in html


def test_template_has_traffic_lights():
    from scripts.terminal_template import build_html
    html = build_html(lines=[])
    assert "#ff5f57" in html
    assert "#febc2e" in html
    assert "#28c840" in html


def test_template_renders_lines():
    from scripts.terminal_template import build_html, TermLine
    html = build_html(lines=[
        TermLine(text="hello world", color=None),
        TermLine(text="colored", color="#89b4fa"),
    ])
    assert "hello world" in html
    assert "colored" in html
    assert "#89b4fa" in html


def test_template_dimensions_720():
    from scripts.terminal_template import build_html
    html = build_html(lines=[])
    assert "720" in html


def test_template_partial_prompt_shows_typing():
    from scripts.terminal_template import build_html
    html = build_html(lines=[], partial_prompt="clawlite", show_cursor=True)
    assert "clawlite" in html
    assert "cursor" in html
    html2 = build_html(lines=[], partial_prompt='clawlite run "o que', show_cursor=True)
    assert "o que" in html2
