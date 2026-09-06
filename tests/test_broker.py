from lecture.broker.service import InProcessBroker


def test_broker_open_trace_subscribe(tmp_path):
    b = InProcessBroker(artifact_root=tmp_path / "artifacts")
    sess = b.open(document="doc1", policy_profile="local-trusted")
    ref = b.put(b"bytes", "application/octet-stream")
    assert b.get(ref) == b"bytes"
    # trace an example into the session
    from pathlib import Path

    ex = Path(__file__).resolve().parents[1] / "examples" / "lecture_01.py"
    ctx = b.start_trace(sess.session_id, str(ex))
    assert len(ctx.log) > 0
    tail = b.subscribe(sess.session_id, after_seq=0)
    assert tail and all(e.seq > 0 for e in tail)
    cp = b.checkpoint(sess.session_id)
    assert cp.event_seq == len(ctx.log)
    b.close(sess.session_id)
    assert sess.session_id not in b._sessions
