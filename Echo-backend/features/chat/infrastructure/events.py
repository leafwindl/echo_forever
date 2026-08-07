from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass


@dataclass(frozen=True)
class ChatEvent:
    event: str
    data: dict[str, object]


class ChatEventBroker:
    def __init__(self, queue_size: int = 100):
        self.queue_size = queue_size
        self._subscribers: dict[str, set[asyncio.Queue[ChatEvent]]] = {}
        self._lock = asyncio.Lock()

    async def publish(self, user_id: str, event: ChatEvent) -> None:
        async with self._lock:
            queues = tuple(self._subscribers.get(user_id, ()))
        for queue in queues:
            if queue.full():
                with suppress(asyncio.QueueEmpty):
                    queue.get_nowait()
            queue.put_nowait(event)

    @asynccontextmanager
    async def subscribe(self, user_id: str) -> AsyncIterator[asyncio.Queue[ChatEvent]]:
        queue: asyncio.Queue[ChatEvent] = asyncio.Queue(maxsize=self.queue_size)
        async with self._lock:
            self._subscribers.setdefault(user_id, set()).add(queue)
        try:
            yield queue
        finally:
            async with self._lock:
                subscribers = self._subscribers.get(user_id)
                if subscribers is not None:
                    subscribers.discard(queue)
                    if not subscribers:
                        self._subscribers.pop(user_id, None)


_broker = ChatEventBroker()


def get_chat_event_broker() -> ChatEventBroker:
    return _broker
