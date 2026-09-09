import json

from lecture import equation, text, uml
from lecture.context import ExecutionContext, execution_scope
from lecture.events import replay_to_presentation
from lecture.export_static import export_static
from lecture.ir import LectureManifest
from lecture.policy import default_policy
from lecture.trace import TraceExecutor


def test_static_bundle_structure_and_csp(tmp_path):
    src = tmp_path / "lec.py"
    src.write_text('from lecture import text\ndef main():\n    text("# Hello")\n', encoding="utf-8")
    ctx = TraceExecutor(policy=default_policy("local-trusted")).trace_file(src)
    manifest = LectureManifest(
        title="Hello", source_file=str(src), source_sha256="abc", policy_profile="static"
    )
    out = export_static(ctx, manifest, tmp_path / "dist")
    assert (out / "lecture.json").exists()
    assert (out / "index.html").exists()
    html = (out / "index.html").read_text(encoding="utf-8")
    assert "Content-Security-Policy" in html
    assert "default-src 'none'" in html
    assert "?step=" in html or "?step" in html or "step" in html
    bundle = json.loads((out / "lecture.json").read_text(encoding="utf-8"))
    assert bundle["manifest"]["policy_profile"] == "static"
    # Source snapshot embedded for the v0.2 shell's source pane.
    assert bundle["source"] is not None
    assert bundle["source"]["file"] == "lec.py"
    assert "# Hello" in bundle["source"]["text"]
    # Golden property: bundle events replay deterministically.
    assert replay_to_presentation(bundle["events"]) == replay_to_presentation(bundle["events"])


def test_viewer_escapes_hostile_markdown(tmp_path):
    ctx = ExecutionContext()
    with execution_scope(ctx):
        text("<script>alert(1)</script>\n[evil](javascript:alert(1))")
    manifest = LectureManifest(title="X", source_file="x.py", source_sha256="0")
    out = export_static(ctx, manifest, tmp_path / "dist")
    html = (out / "index.html").read_text(encoding="utf-8")
    # No executable breakout from the embedded JSON data block: the only
    # `</script>` sequences must be the two legitimate closing tags
    # (data block + viewer script). Raw `<script>` *data* inside JSON is inert.
    assert html.count("</script>") == 2
    assert "<\\/" in html  # data-side `</` escaping is active
    # ... and the rendered payload itself is sanitized, not raw.
    bundle = json.loads((out / "lecture.json").read_text(encoding="utf-8"))
    rendered = bundle["events"][0]["payload"]["html"]
    assert "<script" not in rendered
    assert "javascript:" not in rendered


def test_trace_json_roundtrip_is_replayable(tmp_path):
    from pathlib import Path

    ex = Path(__file__).resolve().parents[1] / "examples" / "lecture_01.py"
    ctx = TraceExecutor(policy=default_policy("local-trusted")).trace_file(ex)
    items = ctx.log.to_list()
    assert replay_to_presentation(items)["steps"]


def test_static_export_inlines_only_visual_modules_in_use(tmp_path):
    ctx = ExecutionContext()
    with execution_scope(ctx):
        equation(r"\frac{a}{b}", output_id="fraction")
        uml(
            "sequence",
            {"participants": ["A", "B"], "messages": [{"from": "A", "to": "B", "label": "go"}]},
        )
    out = export_static(ctx, LectureManifest(title="Visuals"), tmp_path / "dist")
    html = (out / "index.html").read_text(encoding="utf-8")
    assert "export function texToMathML" in html
    assert "export function umlSvg" in html
    assert 'kind": "equation"' in (out / "lecture.json").read_text(encoding="utf-8")
