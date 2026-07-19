"""Server-Sent Events endpoint — live signal push to the dashboard."""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Request
from sse_starlette.sse import EventSourceResponse

from ..events import bus

router = APIRouter()


@router.get("/events", tags=["events"])
async def events(req: Request):
    """Stream live events: new signals, analysis updates, performance rebuilds."""
    queue = bus.subscribe()

    async def event_generator():
        try:
            while True:
                if await req.is_disconnected():
                    break
                try:
                    payload = await asyncio.wait_for(queue.get(), timeout=15.0)
                    yield {"event": "message", "data": payload}
                except asyncio.TimeoutError:
                    # send a comment-style keepalive
                    yield {"event": "ping", "data": "{}"}
        finally:
            bus.unsubscribe(queue)

    return EventSourceResponse(event_generator())
