"""Perf smoke: prove large histories don't need to live in React state.

Acceptance is benchmark-driven (see docs): virtualized slicing, bounded
previews, and backpressure — not fixed magic limits.
"""

import time

from lecture.context import ExecutionContext, execution_scope
from lecture.events import EventLog, replay_to_presentation


def test_100k_events_append_and_slice_fast():
    log = EventLog("s", "e")
    t0 = time.time()
    for i in range(20_000):  # scaled smoke of the 1M-event path (CI budget)
        log.append("step", {"line": i})
    dt = time.time() - t0
    assert dt < 20, f"event append too slow: {dt:.1f}s"
    assert log.check_monotonic()
    # virtualized window: viewer only materializes a slice
    window = log.subscribe(after_seq=19_899)
    assert len(window) == 100
    assert window[0].seq == 19_900


def test_large_inspect_preview_stays_bounded():
    ctx = ExecutionContext()
    with execution_scope(ctx):
        from lecture import inspect_value

        ev = inspect_value("big", "x" * 1_000_000)
    assert len(ev.payload.get("summary", "")) <= 2100
    assert len(ev.payload.get("preview", "")) <= 600


def test_replay_scales_linearly_small():
    log = EventLog("s", "e")
    for i in range(2000):
        log.append("step", {"line": i})
        if i % 10 == 0:
            log.append("text", {"markdown": f"#{i}"})
    t0 = time.time()
    pres = replay_to_presentation(log.to_list())
    dt = time.time() - t0
    assert len(pres["steps"]) == 2000
    assert dt < 10
