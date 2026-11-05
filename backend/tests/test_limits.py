import asyncio

import pytest

from uzexify.api.limits import AgentGate, Busy, RateLimiter, client_key


def test_rate_limit_window_per_key():
    now = [0.0]
    limiter = RateLimiter(2, window=60, clock=lambda: now[0])
    assert limiter.allow("a") and limiter.allow("a")
    assert not limiter.allow("a")
    assert limiter.allow("b")  # other clients are unaffected
    now[0] = 61
    assert limiter.allow("a")  # the window slides


def test_gate_turns_away_after_wait():
    async def scenario():
        gate = AgentGate(1, wait=0.05)
        async with gate.slot():
            assert not gate.free
            with pytest.raises(Busy):
                async with gate.slot():
                    pass
        async with gate.slot():  # released after use
            pass

    asyncio.run(scenario())


def test_client_key():
    assert client_key("203.0.113.5, 10.0.0.2", "10.0.0.2", None, "web") == "203.0.113.5"
    # Bot traffic shares one IP; each chat is its own client.
    assert client_key(None, "172.18.0.3", "tg:42:abc", "telegram") == "tg:42"
    assert client_key(None, "172.18.0.3", "tg:42:def", "telegram") == "tg:42"
