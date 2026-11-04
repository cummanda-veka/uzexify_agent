from pydantic_ai.exceptions import (
    FallbackExceptionGroup,
    ModelAuthenticationError,
    ModelConnectionError,
    ModelServerError,
)

from uzexify.agent import _describe_error, _is_transient


def test_connection_failures_on_both_models_are_transient():
    group = FallbackExceptionGroup(
        "all models failed",
        [
            ModelConnectionError("a", "Connection error.", in_stream=True),
            ModelServerError("b", "Bad gateway"),
        ],
    )
    assert _is_transient(group)
    assert "in_stream=True" in _describe_error(group)


def test_auth_failure_is_not_retried_even_if_fallback_lost_connection():
    group = FallbackExceptionGroup(
        "all models failed",
        [ModelAuthenticationError("a", "Unauthorized"), ModelConnectionError("b", "Connection error.")],
    )
    assert not _is_transient(group)
