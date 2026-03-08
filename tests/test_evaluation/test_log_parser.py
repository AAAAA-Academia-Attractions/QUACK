"""Tests for log_parser module."""

from __future__ import annotations

import json
import tempfile

import pytest

from quack.evaluation.log_parser import (
    filter_events,
    get_game_config,
    get_initial_state,
    get_player_name_map,
    get_player_role_map,
    parse_log,
)


class TestParseLog:
    def test_parse_valid_log(self, minimal_log_file: str) -> None:
        events = parse_log(minimal_log_file)
        assert len(events) > 0
        assert events[0]["event_type"] == "game_started"

    def test_parse_nonexistent_file(self) -> None:
        with pytest.raises(FileNotFoundError):
            parse_log("/nonexistent/path.jsonl")

    def test_parse_empty_file(self, tmp_path) -> None:
        empty_file = tmp_path / "empty.jsonl"
        empty_file.write_text("")
        with pytest.raises(ValueError, match="No valid events"):
            parse_log(str(empty_file))

    def test_parse_skips_malformed_lines(self, tmp_path) -> None:
        log_file = tmp_path / "test.jsonl"
        lines = [
            json.dumps({"event_type": "game_started", "tick": 0, "data": {}, "timestamp": 1.0}),
            "not valid json {{{",
            json.dumps({"event_type": "game_over", "tick": 10, "data": {}, "timestamp": 2.0}),
        ]
        log_file.write_text("\n".join(lines))
        events = parse_log(str(log_file))
        assert len(events) == 2


class TestHelperFunctions:
    def test_get_initial_state(self, minimal_game_events) -> None:
        initial = get_initial_state(minimal_game_events)
        assert "player_0" in initial
        assert initial["player_0"]["name"] == "Alice"
        assert initial["player_0"]["team"] == "goose"

    def test_get_game_config(self, minimal_game_events) -> None:
        config = get_game_config(minimal_game_events)
        assert config["num_players"] == 6
        assert config["num_ducks"] == 1

    def test_get_player_name_map(self, minimal_game_events) -> None:
        name_map = get_player_name_map(minimal_game_events)
        assert name_map["player_0"] == "Alice"
        assert name_map["player_5"] == "Frank"

    def test_get_player_role_map(self, minimal_game_events) -> None:
        role_map = get_player_role_map(minimal_game_events)
        assert role_map["player_5"] == "duck"
        assert role_map["player_0"] == "goose"

    def test_filter_events_by_type(self, minimal_game_events) -> None:
        kills = filter_events(minimal_game_events, event_type="player_killed")
        assert len(kills) == 1
        assert kills[0]["data"]["killer_id"] == "player_5"

    def test_filter_events_by_tick_range(self, minimal_game_events) -> None:
        early = filter_events(minimal_game_events, tick_range=(0, 3))
        assert all(e["tick"] <= 3 for e in early)
