"""Adversarial boundary tests — must stay green before any public release."""

from lecture.sanitize import markdown_to_html, sanitize_html


def test_script_stripped():
    out = sanitize_html("<p>hi</p><script>alert(1)</script>")
    assert "<script" not in out and "hi" in out


def test_event_handlers_stripped():
    out = sanitize_html('<a href="https://example.com" onclick="evil()">x</a>')
    assert "onclick" not in out
    assert 'href="https://example.com"' in out


def test_javascript_url_blocked():
    out = sanitize_html('<a href="javascript:alert(1)">x</a>')
    assert "javascript:" not in out
    assert "x" in out


def test_svg_and_iframe_neutralized():
    out = sanitize_html('<svg onload="evil()"><iframe srcdoc="<script>alert(1)</script>">')
    assert "<svg" not in out and "<iframe" not in out


def test_img_data_text_html_blocked_but_image_data_allowed():
    bad = sanitize_html('<img src="data:text/html,<script>alert(1)</script>">')
    assert "data:text/html" not in bad
    good = sanitize_html('<img src="data:image/png;base64,iVBORw0KGgo=" alt="a">')
    assert "data:image/png" in good


def test_markdown_raw_html_escaped():
    out = markdown_to_html("# T\n<script>alert(1)</script>\n[click](javascript:alert(1))")
    assert "<script" not in out
    assert "javascript:" not in out
    assert "<h1>" in out


def test_markdown_images_require_safe_scheme():
    out = markdown_to_html("![alt](javascript:alert(1))")
    assert "javascript:" not in out


def test_style_attr_and_form_dropped():
    out = sanitize_html('<p style="color:red">a</p><form action="/x"><input></form>')
    assert "style=" not in out and "<form" not in out and "a" in out


def test_img_gets_alt_for_a11y():
    out = sanitize_html('<img src="https://example.com/a.png">')
    assert 'alt=""' in out or "alt=" in out
