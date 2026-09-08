import json
from pathlib import Path

import pytest

from lecture import asset, component, image, link, video
from lecture.artifacts import ArtifactStore
from lecture.context import ExecutionContext, execution_scope
from lecture.export_static import export_static
from lecture.ir import LectureManifest

SVG = b'<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"/>'


def test_capture_source_relative_files_and_bytes(tmp_path, monkeypatch):
    source = tmp_path / "author"
    source.mkdir()
    (source / "figure.svg").write_bytes(SVG)
    ctx = ExecutionContext(source_file=str(source / "main.py"))
    monkeypatch.chdir(tmp_path)
    with execution_scope(ctx):
        first = image("figure.svg", "Diagram")
        second = image(SVG, mime="image/svg+xml")
        third = image(Path("figure.svg"))
    assert first.payload["src"] == second.payload["src"] == third.payload["src"]
    assert first.artifact_refs == second.artifact_refs
    assert ctx.artifacts.get(first.artifact_refs[0]) == SVG
    assert len(ctx.artifacts.list_refs()) == 1
    assert ctx.artifacts.meta(first.artifact_refs[0]).mime == "image/svg+xml"


def test_url_compatibility_and_invalid_inputs(tmp_path):
    ctx = ExecutionContext(source_file=str(tmp_path / "main.py"))
    with execution_scope(ctx):
        for url in ["https://example.com/x.png", "data:image/png;base64,eA==", "blob:abc"]:
            assert image(url).payload["src"] == url
            assert video(url).artifact_refs == []
        assert ctx.artifacts is None  # URLs are not downloaded or cached.
        with pytest.raises(ValueError, match="mime"):
            asset(b"x")
        with pytest.raises(FileNotFoundError, match="missing.png"):
            image("missing.png")
        with pytest.raises(ValueError, match="invalid artifact"):
            image("artifact:bad")


def test_export_resource_closure_and_no_log_mutation(tmp_path):
    store = ArtifactStore(tmp_path / "store")
    store.put(b"unreferenced")
    ctx = ExecutionContext(artifacts=store)
    with execution_scope(ctx):
        uri = asset(SVG, mime="image/svg+xml")
        ev = image(uri, "Chart")
        component("custom", {"nested": [{"src": uri}]})
        link(uri, "Download")
        video(b"video", "Clip", mime="video/mp4")
    before = json.dumps(ctx.log.to_list())
    out = export_static(
        ctx,
        LectureManifest(title="Media", source_file="", source_sha256=""),
        tmp_path / "relocated" / "nested",
    )
    assert json.dumps(ctx.log.to_list()) == before
    bundle = json.loads((out / "lecture.json").read_text())
    assert len(bundle["resources"]) == 2
    path = bundle["resources"][ev.artifact_refs[0]]["path"]
    assert path.endswith(".svg") and (out / path).read_bytes() == SVG
    assert bundle["events"][1]["payload"]["props"]["nested"][0]["src"] == path
    assert bundle["events"][2]["payload"]["href"] == path
    assert "img-src 'self'" in (out / "index.html").read_text(encoding="utf-8")


def test_export_legacy_and_missing_artifact(tmp_path):
    ctx = ExecutionContext(artifacts=ArtifactStore(tmp_path / "store"))
    ref = ctx.artifacts.put(SVG, "image/svg+xml")
    ctx.emit("image", {"src": "/v1/artifacts/" + ref[7:]}, artifact_refs=[ref])
    manifest = LectureManifest(title="Legacy", source_file="", source_sha256="")
    out = export_static(ctx, manifest, tmp_path / "out")
    bundle = json.loads((out / "lecture.json").read_text())
    assert bundle["events"][0]["payload"]["src"].endswith(".svg")
    ctx.emit("image", {"src": "artifact:sha256:" + "0" * 64})
    with pytest.raises(KeyError, match="unknown artifact"):
        export_static(ctx, manifest, tmp_path / "missing")


def test_file_capture_and_export_do_not_use_eager_bytes_api(tmp_path, monkeypatch):
    source = tmp_path / "file.mp4"
    source.write_bytes(b"x" * (2 * 1024 * 1024 + 1))
    store = ArtifactStore(tmp_path / "store")

    def eager_forbidden(*args, **kwargs):
        raise AssertionError("must stream file assets")

    monkeypatch.setattr(Path, "read_bytes", eager_forbidden)
    monkeypatch.setattr(store, "get", eager_forbidden)
    ref = store.put_file(source, "video/mp4")
    store.copy_to(ref, tmp_path / "copy.mp4")
    assert (tmp_path / "copy.mp4").stat().st_size == source.stat().st_size
    assert store.put(b"metadata", "text/plain", license="CC0") == store.put(b"metadata")
    assert store.meta(store.hash_bytes(b"metadata")).mime == "text/plain"
    assert store.meta(store.hash_bytes(b"metadata")).license == "CC0"
