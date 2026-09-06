import pytest

from lecture.artifacts import ArtifactStore


def test_put_get_roundtrip(tmp_path):
    store = ArtifactStore(tmp_path)
    ref = store.put(b"hello", "text/plain", source_url="https://example.com", license="CC-BY-4.0")
    assert ref.startswith("sha256:")
    assert store.get(ref) == b"hello"
    meta = store.meta(ref)
    assert meta is not None and meta.license == "CC-BY-4.0"
    assert store.exists(ref)


def test_put_is_content_addressed(tmp_path):
    store = ArtifactStore(tmp_path)
    assert store.put(b"same") == store.put(b"same")


def test_traversal_ref_rejected(tmp_path):
    store = ArtifactStore(tmp_path)
    with pytest.raises(ValueError):
        store.get("../../etc/passwd")
    with pytest.raises((KeyError, ValueError)):
        store.get("sha256:" + "0" * 64)


def test_index_persists(tmp_path):
    store = ArtifactStore(tmp_path)
    ref = store.put(b"data", "application/octet-stream")
    store2 = ArtifactStore(tmp_path)
    assert store2.exists(ref)
    assert ref in store2.list_refs()
