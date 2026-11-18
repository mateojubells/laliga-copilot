"""Bus de eventos en memoria (asyncio, pub/sub por tema). docs/ARCHITECTURE.md §1.

Un suscriptor lento no frena a los demás: cada uno tiene su cola acotada; si se llena se descarta lo más antiguo
(en directo vale más lo último) y se cuenta en `dropped`.
"""
from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Any, AsyncIterator


class Subscription:
    def __init__(self, bus: "Bus", topics: tuple[str, ...], maxsize: int):
        self._bus, self.topics = bus, topics
        self.queue: asyncio.Queue[tuple[str, Any]] = asyncio.Queue(maxsize=maxsize)
        self.dropped = 0

    def _put(self, topic: str, msg: Any) -> None:
        if self.queue.full():
            self.queue.get_nowait()
            self.dropped += 1
        self.queue.put_nowait((topic, msg))

    async def get(self) -> tuple[str, Any]:
        return await self.queue.get()

    def __aiter__(self) -> AsyncIterator[tuple[str, Any]]:
        return self

    async def __anext__(self) -> tuple[str, Any]:
        return await self.queue.get()

    def close(self) -> None:
        self._bus._unsubscribe(self)


class Bus:
    def __init__(self) -> None:
        self._subs: dict[str, list[Subscription]] = defaultdict(list)
        self.published: dict[str, int] = defaultdict(int)

    def subscribe(self, *topics: str, maxsize: int = 1000) -> Subscription:
        """Temas exactos ("asr.final") o prefijos con comodín ("asr.*", "*")."""
        sub = Subscription(self, topics, maxsize)
        for t in topics:
            self._subs[t].append(sub)
        return sub

    def _unsubscribe(self, sub: Subscription) -> None:
        for t in sub.topics:
            if sub in self._subs[t]:
                self._subs[t].remove(sub)

    def publish(self, topic: str, msg: Any) -> int:
        """Síncrono y no bloqueante (se puede llamar desde cualquier corrutina). Devuelve nº de receptores."""
        self.published[topic] += 1
        seen: list[Subscription] = []
        prefix = topic.split(".")[0] + ".*"
        for key in (topic, prefix, "*"):
            for sub in self._subs.get(key, ()):
                if sub not in seen:
                    sub._put(topic, msg)
                    seen.append(sub)
        return len(seen)
