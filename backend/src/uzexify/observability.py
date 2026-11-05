"""Langfuse Cloud tracing. No-op when keys are absent."""

import logging
from collections.abc import Generator
from contextlib import contextmanager

from uzexify.settings import get_settings

log = logging.getLogger(__name__)
_enabled = False


def init_tracing() -> bool:
    global _enabled
    s = get_settings()
    if not (s.langfuse_public_key and s.langfuse_secret_key):
        return False
    import os

    os.environ.setdefault("LANGFUSE_PUBLIC_KEY", s.langfuse_public_key)
    os.environ.setdefault("LANGFUSE_SECRET_KEY", s.langfuse_secret_key)
    os.environ.setdefault("LANGFUSE_BASE_URL", s.langfuse_base_url)
    from langfuse import get_client
    from pydantic_ai import Agent

    client = get_client()
    ok = client.auth_check()
    log.info("langfuse auth_check: %s", ok)
    Agent.instrument_all()
    _enabled = True
    return True


@contextmanager
def ask_span(
    session_id: str, channel: str, language: str, model: str, question: str
) -> Generator[str | None]:
    if not _enabled:
        yield None
        return
    from langfuse import get_client, propagate_attributes

    client = get_client()
    with (
        client.start_as_current_observation(as_type="span", name="ask", input=question),
        propagate_attributes(session_id=session_id, tags=[channel, language], metadata={"model": model}),
    ):
        yield client.get_current_trace_id()


def set_ask_output(kind: str, text: str) -> None:
    """Final answer on the `ask` span, so a trace list shows question → answer at a glance."""
    if _enabled:
        from langfuse import get_client

        get_client().update_current_span(output={"kind": kind, "text": text})


def score(trace_id: str, name: str, value: float) -> None:
    if _enabled and trace_id:
        from langfuse import get_client

        get_client().create_score(trace_id=trace_id, name=name, value=value)


def flush() -> None:
    if _enabled:
        from langfuse import get_client

        get_client().flush()
