"""Tests for the VLMAgent Anthropic provider path.

The Anthropic Messages API has a different message format from the
OpenAI-compatible greatrouter we use for the other models:

* ``system`` is a top-level parameter, not a ``"role": "system"`` entry.
* Images use a typed ``image`` block with a ``source`` object that holds
  raw base64 data and a ``media_type`` — *not* a ``data:`` URL.

``_to_anthropic_messages`` is the single conversion point. This test pins
its behavior so the rest of the codebase can keep emitting OpenAI-style
messages everywhere (prompt_builder, chat tools, etc.) without caring
which provider will eventually serve the call.
"""

from __future__ import annotations

import pytest

from quack.agents.vlm_agent import VLMAgent, _is_retryable_error


class TestToAnthropicMessages:
    def test_pulls_system_role_out(self):
        oai = [
            {"role": "system", "content": "You are Alice."},
            {"role": "user", "content": "hi"},
        ]
        system, msgs = VLMAgent._to_anthropic_messages(oai)
        assert system == "You are Alice."
        assert msgs == [{"role": "user", "content": "hi"}]

    def test_joins_multiple_system_messages(self):
        oai = [
            {"role": "system", "content": "Part one."},
            {"role": "system", "content": "Part two."},
            {"role": "user", "content": "hi"},
        ]
        system, msgs = VLMAgent._to_anthropic_messages(oai)
        assert system == "Part one.\n\nPart two."
        assert len(msgs) == 1

    def test_system_list_content_is_concatenated(self):
        oai = [
            {"role": "system", "content": [
                {"type": "text", "text": "sys-a"},
                {"type": "text", "text": "sys-b"},
            ]},
            {"role": "user", "content": "hi"},
        ]
        system, msgs = VLMAgent._to_anthropic_messages(oai)
        assert "sys-a" in system and "sys-b" in system

    def test_string_user_content_passes_through(self):
        oai = [{"role": "user", "content": "hi"}]
        system, msgs = VLMAgent._to_anthropic_messages(oai)
        assert system == ""
        assert msgs == [{"role": "user", "content": "hi"}]

    def test_data_url_image_becomes_base64_block(self):
        b64 = "AAAA"
        oai = [{
            "role": "user",
            "content": [
                {"type": "image_url",
                 "image_url": {"url": f"data:image/png;base64,{b64}"}},
                {"type": "text", "text": "describe it"},
            ],
        }]
        system, msgs = VLMAgent._to_anthropic_messages(oai)
        assert system == ""
        assert msgs == [{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": b64,
                    },
                },
                {"type": "text", "text": "describe it"},
            ],
        }]

    def test_jpeg_media_type_is_preserved(self):
        b64 = "BBBB"
        oai = [{
            "role": "user",
            "content": [
                {"type": "image_url",
                 "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
            ],
        }]
        _, msgs = VLMAgent._to_anthropic_messages(oai)
        block = msgs[0]["content"][0]
        assert block["source"]["media_type"] == "image/jpeg"
        assert block["source"]["data"] == b64

    def test_existing_anthropic_image_blocks_pass_through(self):
        anth_image = {
            "type": "image",
            "source": {"type": "base64", "media_type": "image/png", "data": "CCCC"},
        }
        oai = [{"role": "user", "content": [anth_image, {"type": "text", "text": "x"}]}]
        _, msgs = VLMAgent._to_anthropic_messages(oai)
        assert msgs[0]["content"][0] == anth_image


class TestAnthropicRetryDetection:
    """``_is_retryable_error`` must also classify Anthropic SDK errors."""

    def test_anthropic_rate_limit_is_retryable(self):
        anthropic = pytest.importorskip("anthropic")
        # The constructor signature varies across versions; build a fake
        # error that subclasses RateLimitError to avoid coupling the test
        # to the SDK's internal kwargs.
        class _Fake(anthropic.RateLimitError):
            def __init__(self):  # noqa: D401
                Exception.__init__(self, "rate limited")
        assert _is_retryable_error(_Fake()) is True

    def test_anthropic_internal_server_error_is_retryable(self):
        anthropic = pytest.importorskip("anthropic")

        class _Fake(anthropic.InternalServerError):
            def __init__(self):
                Exception.__init__(self, "boom")
        assert _is_retryable_error(_Fake()) is True
