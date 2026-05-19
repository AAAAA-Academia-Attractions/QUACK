"""Tests for VLMAgent free-roam say(...) forwarding."""

from __future__ import annotations

from quack.agents.action_format import combine_action_and_say, extract_say_clause


def test_extract_say_from_combined_response() -> None:
    raw = "move(medbay) | say(I saw a body in storage)"
    assert extract_say_clause(raw) == "say(I saw a body in storage)"


def test_extract_say_case_insensitive_prefix() -> None:
    raw = "move(medbay) | Say(Hello there)"
    assert extract_say_clause(raw) == "say(Hello there)"


def test_extract_say_only_response() -> None:
    assert extract_say_clause("say(hello)") == "say(hello)"


def test_extract_say_none_when_absent() -> None:
    assert extract_say_clause("move(medbay)") is None


def test_combine_action_and_say() -> None:
    raw = "move(medbay) | say(hello)"
    assert combine_action_and_say("move(medbay)", raw) == "move(medbay) | say(hello)"


def test_combine_say_only_uses_wait_action() -> None:
    raw = "say(hello)"
    assert combine_action_and_say("wait()", raw) == "wait() | say(hello)"
