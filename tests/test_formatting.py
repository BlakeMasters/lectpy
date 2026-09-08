import inspect
from html.parser import HTMLParser
from itertools import count

import pytest

from lecture import code, table
from lecture.context import execution_scope
from lecture.events import validate_event
from lecture.formatting import code_payload, table_payload


class Tags(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.starts = []
        self.text = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        self.starts.append((tag, dict(attrs)))

    def handle_data(self, data):
        self.text.append(data)


def test_code_is_literal_accessible_and_has_safe_fence():
    payload = code_payload('print("<script>")\n# ``` in source', "python", 'A "sample"')
    parsed = Tags(payload["html"])
    assert all(tag != "script" for tag, _ in parsed.starts)
    assert ("pre", {"class": "code", "tabindex": "0", "aria-label": 'A "sample"'}) in parsed.starts
    assert 'print("<script>")\n# ``` in source' in parsed.text
    assert payload["markdown"].startswith("````python\n")


def test_table_reads_only_requested_preview_and_one_lookahead():
    consumed = []

    def rows():
        for i in count():
            consumed.append(i)
            yield {"n": i, "square": i * i}

    payload = table_payload(rows(), max_rows=5)
    assert consumed == list(range(6))
    assert payload["rows_shown"] == 5
    assert payload["truncated"] is True
    assert payload["columns"] == ["n", "square"]
    assert "more available" in payload["html"]


def test_table_preserves_column_order_handles_missing_cells_and_escapes():
    payload = table_payload(
        [
            {"z": '<img src="x">', "a": None},
            {"z": "two", "b": 3},
        ],
        columns=["b", "z", "a"],
        title="<Results>",
    )
    parsed = Tags(payload["html"])
    assert sum(tag == "th" for tag, _ in parsed.starts) == 3
    assert all(attrs["scope"] == "col" for tag, attrs in parsed.starts if tag == "th")
    assert all(tag != "img" for tag, _ in parsed.starts)
    assert (
        "div",
        {"class": "lecture-table", "tabindex": "0", "role": "region", "aria-label": "<Results>"},
    ) in parsed.starts
    assert payload["columns"] == ["b", "z", "a"]
    assert payload["truncated"] is False
    assert '<img src="x">' in parsed.text


def test_table_infers_union_of_preview_columns():
    assert table_payload([{"a": 1}, {"b": 2}])["columns"] == ["a", "b"]


def test_empty_table_and_long_values_have_useful_previews():
    assert "no columns" in table_payload([])["html"]
    payload = table_payload([{"x": "a" * 100_000}])
    assert "…" in payload["html"]
    assert len(payload["html"]) < 3000
    empty = Tags(table_payload([], columns=["x"])["html"])
    assert ("th", {"scope": "col"}) in empty.starts


@pytest.mark.parametrize(
    "rows, kwargs, error",
    [
        ([{}], {"max_rows": 0}, ValueError),
        ([{}], {"max_rows": True}, ValueError),
        ([{}], {"max_rows": 1001}, ValueError),
        ([1], {}, TypeError),
        ({"a": 1}, {}, TypeError),
        ([{1: 2}], {}, TypeError),
        ([{}], {"columns": "abc"}, TypeError),
        ([{}], {"columns": ["a", "a"]}, ValueError),
        ([{}], {"columns": [1]}, TypeError),
        ([{str(i): i for i in range(101)}], {}, ValueError),
    ],
)
def test_invalid_tables_report_author_errors(rows, kwargs, error):
    with pytest.raises(error):
        table_payload(rows, **kwargs)


def test_new_primitives_preserve_v1_events_and_source_links():
    with execution_scope() as ctx:
        line = inspect.currentframe().f_lineno + 1
        first = code("x = 1", language="python")
        second = table([{"x": 1}])
    assert [e.kind for e in ctx.log.subscribe()] == ["text", "text"]
    assert first.source_location.line == line
    assert second.source_location.line == line + 1
    assert validate_event(first.to_dict()) == []
    assert validate_event(second.to_dict()) == []
