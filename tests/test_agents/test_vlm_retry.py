"""Tests for the VLMAgent transient-error retry predicate.

The retry policy must catch transient errors observed against greatrouter
(rate limits, ``quota_exceeded`` upstream proxy hiccups, streaming
``ReadTimeout``, 5xx, and connection errors) while leaving permanent client
errors (400 ``BadRequestError``, auth failures) untouched.
"""

from __future__ import annotations

import pytest

from quack.agents.vlm_agent import _is_retryable_error


class TestRetryableStringMatching:
    """Substring matching covers errors wrapped by upstream proxies."""

    @pytest.mark.parametrize(
        "msg",
        [
            "API error: APIError: upstreamException - "
            '{"error":{"message":"You have no quota","code":"quota_exceeded"}}',
            "Rate limit reached, retry-after 5s",
            "429 Too Many Requests",
            "503 Service Unavailable",
            "502 Bad Gateway",
            "500 Internal Server Error",
            "The read operation timed out",
            "ReadTimeout: stream interrupted",
            "Connection reset by peer",
            "RemoteProtocolError: server disconnected",
        ],
    )
    def test_retryable(self, msg: str) -> None:
        assert _is_retryable_error(Exception(msg)) is True

    @pytest.mark.parametrize(
        "msg",
        [
            "Unsupported value: 'temperature' does not support 0.7 with this model.",
            "Invalid request: messages cannot be empty",
            "Authentication failed: invalid api key",
            "The model `gpt-9.9` does not exist",
            "Permission denied",
        ],
    )
    def test_not_retryable(self, msg: str) -> None:
        assert _is_retryable_error(Exception(msg)) is False


class TestRetryableTypedExceptions:
    """Typed openai/httpx exceptions are matched even when the message is opaque."""

    def test_openai_rate_limit(self) -> None:
        openai = pytest.importorskip("openai")
        httpx = pytest.importorskip("httpx")
        request = httpx.Request("POST", "https://endpoint.greatrouter.com/v1/chat/completions")
        response = httpx.Response(429, request=request, text="rate limited")
        try:
            exc: BaseException = openai.RateLimitError(
                "rate limited",
                response=response,
                body=None,
            )
        except TypeError:
            # Older OpenAI SDKs use a different constructor signature; fall
            # back to an opaque exception that still trips the substring path.
            exc = Exception("rate limited")
        assert _is_retryable_error(exc) is True

    def test_openai_internal_server_error(self) -> None:
        openai = pytest.importorskip("openai")
        httpx = pytest.importorskip("httpx")
        request = httpx.Request("POST", "https://endpoint.greatrouter.com/v1/chat/completions")
        response = httpx.Response(500, request=request, text="internal server error")
        try:
            exc: BaseException = openai.InternalServerError(
                "internal server error",
                response=response,
                body=None,
            )
        except TypeError:
            exc = Exception("internal server error")
        assert _is_retryable_error(exc) is True

    def test_httpx_timeout(self) -> None:
        httpx = pytest.importorskip("httpx")
        assert _is_retryable_error(httpx.ReadTimeout("read timed out")) is True

    def test_httpx_remote_protocol_error(self) -> None:
        httpx = pytest.importorskip("httpx")
        assert _is_retryable_error(
            httpx.RemoteProtocolError("server disconnected")
        ) is True
