"""Markdown → sanitized HTML.

The old edtrace path ran `marked(...)` straight into `dangerouslySetInnerHTML`
with no visible sanitization. Here raw HTML in author markdown is escaped, the
markdown subset generates only allowlisted tags, and `sanitize_html` enforces
an allowlist + URL-scheme policy as defense-in-depth for every HTML string
that reaches the viewer (including plugin-provided HTML).
"""

from __future__ import annotations

import html
import re
from html.parser import HTMLParser
from urllib.parse import urlparse

ALLOWED_TAGS = frozenset(
    {
        "h1",
        "h2",
        "h3",
        "h4",
        "p",
        "strong",
        "em",
        "code",
        "pre",
        "ul",
        "ol",
        "li",
        "blockquote",
        "a",
        "img",
        "br",
        "hr",
    }
)
ALLOWED_ATTRS: dict[str, frozenset[str]] = {
    "a": frozenset({"href", "title"}),
    "img": frozenset({"src", "alt", "title"}),
}
ALLOWED_SCHEMES = frozenset({"http", "https"})
ALLOWED_IMG_SCHEMES = frozenset({"http", "https", "data", "blob"})


def _safe_url(url: str, *, for_img: bool = False) -> str | None:
    url = url.strip()
    if not url:
        return None
    # Block event-handler / script vectors even before scheme parsing.
    lowered = url.lower()
    if lowered.startswith(("javascript:", "vbscript:", "data:text/html")):
        return None
    if url.startswith("#"):
        return url
    parsed = urlparse(url)
    allowed = ALLOWED_IMG_SCHEMES if for_img else ALLOWED_SCHEMES
    if parsed.scheme and parsed.scheme.lower() not in allowed:
        return None
    if for_img and parsed.scheme.lower() == "data":
        # Only allow image data: URLs, never data:text/html.
        if not lowered.startswith("data:image/"):
            return None
    return url


class _Sanitizer(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._out: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in (
            "script",
            "style",
            "iframe",
            "object",
            "embed",
            "form",
            "input",
            "button",
            "link",
            "meta",
            "base",
            "svg",
            "math",
        ):
            self._out.append(f"&lt;{html.escape(tag)}&gt;")
            return
        if tag not in ALLOWED_TAGS:
            return
        allowed = ALLOWED_ATTRS.get(tag, frozenset())
        clean: list[str] = []
        for name, value in attrs:
            name = name.lower()
            if name.startswith("on") or name in ("style", "srcdoc", "hrefset"):
                continue
            if name not in allowed:
                continue
            if value is None:
                continue
            if name in ("href", "src"):
                safe = _safe_url(value, for_img=(tag == "img"))
                if safe is None:
                    continue
                value = safe
            clean.append(f'{name}="{html.escape(value, quote=True)}"')
        attr_str = (" " + " ".join(clean)) if clean else ""
        if tag in ("img", "br", "hr"):
            # img always carries alt for accessibility diagnostics
            if tag == "img" and not any(a.startswith("alt=") for a in clean):
                attr_str += ' alt=""'
            self._out.append(f"<{tag}{attr_str}>")
        else:
            self._out.append(f"<{tag}{attr_str}>")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in ALLOWED_TAGS and tag not in ("img", "br", "hr"):
            self._out.append(f"</{tag}>")

    def handle_data(self, data: str) -> None:
        self._out.append(html.escape(data))

    def handle_entityref(self, name: str) -> None:
        self._out.append(f"&{name};")

    def handle_charref(self, name: str) -> None:
        self._out.append(f"&#{name};")

    def result(self) -> str:
        return "".join(self._out)


def sanitize_html(dirty: str) -> str:
    """Allowlist-sanitize an HTML string. Never raises on hostile input."""
    parser = _Sanitizer()
    try:
        parser.feed(dirty)
        parser.close()
    except Exception:
        # Parser failures must not leak raw input into the DOM.
        return html.escape(dirty)
    return parser.result()


# -- minimal markdown subset (headings, bold, italic, code, links, images, lists)
_HEADING = re.compile(r"^(#{1,4})\s+(.*)$")
_FENCE = re.compile(r"^```(\w*)\s*$")
_INLINE_CODE = re.compile(r"`([^`\n]+)`")
_BOLD = re.compile(r"\*\*([^*]+)\*\*")
_ITALIC = re.compile(r"(?<!\*)\*([^*]+)\*(?!\*)")
_IMAGE = re.compile(r"!\[([^\]]*)\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
_LINK = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")
_LIST_ITEM = re.compile(r"^\s*[-*]\s+(.*)$")


def _inline(md: str) -> str:
    # Escape first so raw HTML can never pass through; then re-introduce
    # allowlisted constructs.
    esc = html.escape(md)
    # inline code (escaped content inside <code>)
    esc = _INLINE_CODE.sub(lambda m: f"<code>{m.group(1)}</code>", esc)
    # images
    esc = _IMAGE.sub(
        lambda m: (
            f'<img src="{html.escape(m.group(2), quote=True)}" '
            f'alt="{html.escape(m.group(1), quote=True)}">'
            if _safe_url(html.unescape(m.group(2)), for_img=True)
            else html.escape(m.group(1))
        ),
        esc,
    )
    # links
    esc = _LINK.sub(
        lambda m: (
            f'<a href="{html.escape(m.group(2), quote=True)}">{m.group(1)}</a>'
            if _safe_url(html.unescape(m.group(2)))
            else m.group(1)
        ),
        esc,
    )
    esc = _BOLD.sub(r"<strong>\1</strong>", esc)
    esc = _ITALIC.sub(r"<em>\1</em>", esc)
    return esc


def markdown_to_html(md: str) -> str:
    """Render a small markdown subset to *already-sanitized* HTML."""
    lines = md.split("\n")
    out: list[str] = []
    in_code = False
    code_buf: list[str] = []
    list_buf: list[str] = []

    def flush_list() -> None:
        if list_buf:
            out.append("<ul>" + "".join(f"<li>{_inline(i)}</li>" for i in list_buf) + "</ul>")
            list_buf.clear()

    for line in lines:
        fence = _FENCE.match(line)
        if fence:
            if in_code:
                out.append(
                    "<pre><code>" + "\n".join(html.escape(c) for c in code_buf) + "</code></pre>"
                )
                code_buf.clear()
                in_code = False
            else:
                flush_list()
                in_code = True
            continue
        if in_code:
            code_buf.append(line)
            continue
        m = _HEADING.match(line)
        if m:
            flush_list()
            level = len(m.group(1))
            out.append(f"<h{level}>{_inline(m.group(2).strip())}</h{level}>")
            continue
        lm = _LIST_ITEM.match(line)
        if lm:
            list_buf.append(lm.group(1).strip())
            continue
        if line.strip().startswith(">"):
            flush_list()
            out.append(f"<blockquote><p>{_inline(line.strip()[1:].strip())}</p></blockquote>")
            continue
        if not line.strip():
            flush_list()
            continue
        flush_list()
        out.append(f"<p>{_inline(line.strip())}</p>")
    if in_code:  # unclosed fence: still escape safely
        out.append("<pre><code>" + "\n".join(html.escape(c) for c in code_buf) + "</code></pre>")
    flush_list()
    raw = "\n".join(out)
    # Defense in depth: even our own generator output passes the sanitizer so a
    # future markdown extension cannot silently widen the DOM surface.
    return sanitize_html(raw)
