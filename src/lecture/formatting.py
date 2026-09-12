"""Dependency-free rich output payloads shared by author primitives.

HTML and a plain Markdown fallback travel in existing v1 text events, so older
viewers can display these outputs without a protocol upgrade.
"""

from __future__ import annotations

import html
import re
import reprlib
from collections.abc import Iterable, Mapping, Sequence
from itertools import islice
from typing import Any

MAX_CELL_CHARACTERS = 2000
MAX_TABLE_COLUMNS = 100
MAX_TABLE_ROWS = 1000


def code_payload(
    source: str,
    language: str = "",
    title: str = "",
    *,
    output_id: str | None = None,
) -> dict[str, Any]:
    if not all(isinstance(v, str) for v in (source, language, title)):
        raise TypeError("code source, language, and title must be strings")
    label = title or (f"Code ({language})" if language else "Code")
    # Choose a fence that cannot be closed by a run of backticks in source.
    longest = max((len(run) for run in re.findall(r"`+", source)), default=0)
    fence = "`" * max(3, longest + 1)
    language = language.strip().replace("\n", " ").replace("\r", " ")
    rendered = html.escape(source)
    output_attribute = ""
    if output_id is not None:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", output_id):
            raise ValueError("invalid code output_id")
        output_attribute = f' data-output-id="{output_id}"'
        rendered = "\n".join(
            f'<span data-code-line="{i}">{html.escape(line)}</span>'
            for i, line in enumerate(source.split("\n"), 1)
        )
    return {
        "format": "code",
        "language": language,
        "title": title,
        "markdown": f"{fence}{language}\n{source}\n{fence}",
        "html": (
            f'<figure class="lecture-code"{output_attribute}>'
            f'<figcaption>{html.escape(label)}</figcaption>'
            f'<pre class="code" tabindex="0" aria-label="{html.escape(label, quote=True)}">'
            f"<code>{rendered}</code></pre></figure>"
        ),
    }


def _cell(value: Any) -> str:
    if value is None:
        return ""
    text = value if isinstance(value, str) else reprlib.repr(value)
    return text if len(text) <= MAX_CELL_CHARACTERS else text[:MAX_CELL_CHARACTERS] + "…"


def table_payload(
    rows: Iterable[Mapping[str, Any]],
    *,
    columns: Sequence[str] | None = None,
    title: str = "Table",
    max_rows: int = 100,
) -> dict[str, Any]:
    """Read at most max_rows + 1 mappings; infer columns only from the preview."""
    if type(max_rows) is not int or not 1 <= max_rows <= MAX_TABLE_ROWS:
        raise ValueError(f"max_rows must be between 1 and {MAX_TABLE_ROWS}")
    if not isinstance(title, str):
        raise TypeError("table title must be a string")
    if isinstance(rows, (str, bytes, Mapping)):
        raise TypeError("table rows must be an iterable of mappings")
    selected = list(islice(rows, max_rows + 1))
    truncated = len(selected) > max_rows
    visible = selected[:max_rows]
    if not all(isinstance(row, Mapping) for row in selected):
        raise TypeError("each table row must be a mapping of column names to values")
    if columns is None:
        names: list[str] = []
        for row in visible:
            for key in row:
                if not isinstance(key, str):
                    raise TypeError("table column names must be strings")
                if key not in names:
                    names.append(key)
                    if len(names) > MAX_TABLE_COLUMNS:
                        raise ValueError(
                            f"table previews support at most {MAX_TABLE_COLUMNS} columns"
                        )
    else:
        if isinstance(columns, (str, bytes)):
            raise TypeError("columns must be a sequence of strings")
        names = list(islice(columns, MAX_TABLE_COLUMNS + 1))
        if not all(isinstance(c, str) for c in names):
            raise TypeError("table column names must be strings")
        if len(names) > MAX_TABLE_COLUMNS or len(names) != len(set(names)):
            raise ValueError(
                f"columns must be unique and contain at most {MAX_TABLE_COLUMNS} names"
            )
    if len(names) * len(visible) > 20_000:
        raise ValueError("table preview exceeds 20,000 cells; reduce columns or max_rows")
    cells = [[_cell(row.get(name)) for name in names] for row in visible]
    count = len(cells)
    caption = title or "Table"
    suffix = f" — first {count} rows (more available)" if truncated else f" — {count} rows"
    header = "".join(f'<th scope="col">{html.escape(name)}</th>' for name in names)
    body = "".join(
        "<tr>" + "".join(f"<td>{html.escape(c)}</td>" for c in row) + "</tr>" for row in cells
    )
    rendered = (
        (
            f'<div class="lecture-table" tabindex="0" role="region" '
            f'aria-label="{html.escape(caption, quote=True)}">'
            f"<table><caption>{html.escape(caption + suffix)}</caption>"
            f"<thead><tr>{header}</tr></thead><tbody>{body}</tbody></table></div>"
        )
        if names
        else f'<p class="muted">{html.escape(caption)}: no columns to display.</p>'
    )
    # A compact plain fallback is useful to non-HTML readers, without duplicating
    # a potentially wide preview in the wire payload.
    return {
        "format": "table",
        "title": caption,
        "columns": names,
        "rows_shown": count,
        "truncated": truncated,
        "markdown": caption + suffix + (": " + ", ".join(names) if names else ""),
        "html": rendered,
    }
