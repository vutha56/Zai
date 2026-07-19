"""In-process event bus for Server-Sent Events (live signal push to the dashboard).

Multiple dashboard tabs subscribe; the scan job publishes new signals.
"""
from __future__ import annotations

import asyncio
import json
import logging
from collections import deque
from typing import Deque

log = logging.getLogger(__name__)


class EventBus:
    def __init__(self, history: int = 20) -> None:
        self._subscribers: set[asyncio.Queue] = set()
        self._recent: Deque[str] = deque(maxlen=history)

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=64)
        self._subscribers.add(q)
        # replay recent events so a freshly opened tab isn't blank
        for evt in self._recent:
            try:
                q.put_nowait(evt)
            except asyncio.QueueFull:
                break
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subscribers.discard(q)

    def publish(self, event: dict) -> None:
        """Thread-safe publish: called from the scheduler (sync thread)."""
        text = json.dumps(event, default=str)
        self._recent.append(text)
        for q in list(self._subscribers):
            try:
                q.put_nowait(text)
            except asyncio.QueueFull:
                # drop if a subscriber is slow
                pass
        log.debug("EventBus publish: %s -> %d subs", event.get("type"), len(self._subscribers))


bus = EventBus()
