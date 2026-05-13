"""Inter-agent message bus.

Hub-and-spoke model: messages route through the bus so the Boss
can observe, filter, and prioritise all communication.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from enum import Enum


class MessageType(Enum):
    STATUS = "status"
    REQUEST = "request"
    RESPONSE = "response"
    BROADCAST = "broadcast"
    DONE = "done"


@dataclass(frozen=True, slots=True)
class Message:
    sender: str
    recipient: str                  # agent name or "*" for broadcast
    content: str
    msg_type: MessageType
    timestamp: float = field(default_factory=time.time)


class MessageBus:
    """Async message bus with per-agent inboxes."""

    def __init__(self) -> None:
        self._inboxes: dict[str, asyncio.Queue[Message]] = {}
        self._history: list[Message] = []
        self._subscribers: list[asyncio.Queue[Message]] = []

    def register(self, agent_name: str) -> None:
        """Create an inbox for an agent."""
        if agent_name not in self._inboxes:
            self._inboxes[agent_name] = asyncio.Queue()

    async def send(self, message: Message) -> None:
        """Route a message to its recipient(s) and all subscribers."""
        self._history.append(message)

        for sub in self._subscribers:
            await sub.put(message)

        if message.recipient == "*":
            for name, inbox in self._inboxes.items():
                if name != message.sender:
                    await inbox.put(message)
        elif message.recipient in self._inboxes:
            await self._inboxes[message.recipient].put(message)

    async def receive(self, agent_name: str, timeout: float = 0.1) -> Message | None:
        """Non-blocking receive for an agent."""
        inbox = self._inboxes.get(agent_name)
        if inbox is None:
            return None
        try:
            return await asyncio.wait_for(inbox.get(), timeout=timeout)
        except (asyncio.TimeoutError, asyncio.QueueEmpty):
            return None

    def subscribe(self) -> asyncio.Queue[Message]:
        """Subscribe to ALL messages (for Boss / dashboard monitoring)."""
        q: asyncio.Queue[Message] = asyncio.Queue()
        self._subscribers.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue[Message]) -> None:
        self._subscribers.remove(q)

    def history(self, limit: int = 50) -> list[Message]:
        return self._history[-limit:]

    async def stream(self, q: asyncio.Queue[Message]) -> AsyncIterator[Message]:
        """Async iterator over a subscription queue."""
        while True:
            msg = await q.get()
            yield msg
