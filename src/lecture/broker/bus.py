"""In-process fan-out for session event streams (single writer, many readers).

Execution stays a single-writer ordered log (EventLog); this bus only
distributes already-sequenced event dicts to WS subscribers and joins.
"""

from __future__ import annotations

import queue
import threading
from typing import Any


class EventBus:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._subs: dict[str, list[queue.Queue]] = {}

    def subscribe(self, session_id: str) -> queue.Queue:
        q: queue.Queue = queue.Queue()
        with self._lock:
            self._subs.setdefault(session_id, []).append(q)
        return q

    def unsubscribe(self, session_id: str, q: queue.Queue) -> None:
        with self._lock:
            subs = self._subs.get(session_id, [])
            if q in subs:
                subs.remove(q)
            if not subs:
                self._subs.pop(session_id, None)

    def publish(self, session_id: str, event: dict[str, Any]) -> None:
        with self._lock:
            subs = list(self._subs.get(session_id, []))
        for q in subs:
            try:
                q.put_nowait(event)
            except queue.Full:
                pass

    def subscriber_count(self, session_id: str) -> int:
        with self._lock:
            return len(self._subs.get(session_id, []))
