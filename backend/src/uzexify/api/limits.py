"""Load protection for the agent endpoints: a per-client rate limit and a cap on concurrent agent runs.

One agent run holds a model call and a database connection for up to a minute, so a burst of
questions must queue for a slot instead of piling up into timeouts for everyone.
"""

import asyncio
import time
from collections import deque
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager


class RateLimiter:
    """Sliding window: at most `limit` events per `window` seconds per key."""

    def __init__(self, limit: int, window: float = 60.0, clock=time.monotonic) -> None:
        self.limit, self.window, self.clock = limit, window, clock
        self._hits: dict[str, deque[float]] = {}

    def allow(self, key: str) -> bool:
        now = self.clock()
        hits = self._hits.setdefault(key, deque())
        while hits and now - hits[0] >= self.window:
            hits.popleft()
        if len(hits) >= self.limit:
            return False
        hits.append(now)
        if len(self._hits) > 10_000:  # bound memory under many distinct clients
            for k in [k for k, v in self._hits.items() if not v or now - v[-1] >= self.window]:
                del self._hits[k]
        return True


class Busy(Exception):
    """No agent slot became free within the queue wait."""


class AgentGate:
    """At most `slots` agent runs at once; others wait up to `wait` seconds for a slot."""

    def __init__(self, slots: int, wait: float) -> None:
        self._sem = asyncio.Semaphore(slots)
        self.wait = wait

    @property
    def free(self) -> bool:
        return not self._sem.locked()

    @asynccontextmanager
    async def slot(self) -> AsyncGenerator[None]:
        try:
            await asyncio.wait_for(self._sem.acquire(), self.wait)
        except TimeoutError as e:
            raise Busy from e
        try:
            yield
        finally:
            self._sem.release()


def client_key(forwarded_for: str | None, peer: str | None, session_id: str | None, channel: str) -> str:
    """Rate-limit key. Public traffic always passes Caddy, which sets X-Forwarded-For: it is limited
    by the original client IP whatever X-Client or session_id it sends. Only requests that reach the
    API directly on the internal network (the bot) are keyed by Telegram chat, since all bot traffic
    shares one IP."""
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    if channel == "telegram" and session_id and session_id.count(":") >= 2:
        return "tg:" + session_id.split(":")[1]
    return peer or "unknown"
