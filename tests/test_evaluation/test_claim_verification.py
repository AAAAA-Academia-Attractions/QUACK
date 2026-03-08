"""Tests for Tier 3 claim verification logic (without LLM calls)."""

from __future__ import annotations

import pytest

from quack.evaluation.game_reconstructor import GameReconstructor, GameTimeline, PlayerTickState
from quack.evaluation.tier3_statement_verification import (
    normalize_room_name,
    verify_activity_claim,
    verify_location_claim,
    verify_sighting_claim,
)
from quack.map.game_map import GameMap

from .conftest import build_minimal_game_events, make_event


class TestRoomNormalization:
    def test_exact_match(self) -> None:
        assert normalize_room_name("cafeteria") == "cafeteria"
        assert normalize_room_name("medbay") == "medbay"

    def test_alias(self) -> None:
        assert normalize_room_name("med bay") == "medbay"
        assert normalize_room_name("nav") == "navigation"
        assert normalize_room_name("elec") == "electrical"
        assert normalize_room_name("o2") == "oxygen"

    def test_case_insensitive(self) -> None:
        assert normalize_room_name("CAFETERIA") == "cafeteria"
        assert normalize_room_name("MedBay") == "medbay"

    def test_with_spaces(self) -> None:
        assert normalize_room_name("upper engine") == "upper_engine"
        assert normalize_room_name("lower engine") == "lower_engine"

    def test_unknown_room(self) -> None:
        assert normalize_room_name("nonexistent") is None


class TestVerifyLocationClaim:
    def _make_timeline(self) -> tuple[GameTimeline, dict[str, str]]:
        """Create a simple timeline where Alice is in medbay for ticks 0-5."""
        tl = GameTimeline()
        tl.max_tick = 10
        tl.player_names = {"player_0": "Alice"}
        tl.player_teams = {"player_0": "goose"}
        tl.player_timelines = {
            "player_0": [
                PlayerTickState(tick=t, room="medbay" if t <= 5 else "electrical")
                for t in range(11)
            ]
        }
        name_to_id = {"Alice": "player_0"}
        return tl, name_to_id

    def test_true_location(self) -> None:
        tl, n2i = self._make_timeline()
        claim = {"type": "location", "subject": "Alice", "room": "medbay", "temporal": "this round"}
        result = verify_location_claim(claim, tl, n2i, 0, 5)
        assert result == "true"

    def test_false_location(self) -> None:
        tl, n2i = self._make_timeline()
        claim = {"type": "location", "subject": "Alice", "room": "weapons", "temporal": "this round"}
        result = verify_location_claim(claim, tl, n2i, 0, 5)
        assert result == "false"

    def test_near_miss_location(self) -> None:
        tl, n2i = self._make_timeline()
        # Check a range where Alice is in medbay for some ticks but not majority
        claim = {"type": "location", "subject": "Alice", "room": "medbay", "temporal": "this round"}
        result = verify_location_claim(claim, tl, n2i, 4, 10)
        # Ticks 4-5 in medbay (2 ticks), ticks 6-10 in electrical (5 ticks). 2/7 < 50% -> near_miss
        assert result == "near_miss"

    def test_unverifiable_unknown_player(self) -> None:
        tl, n2i = self._make_timeline()
        claim = {"type": "location", "subject": "Unknown", "room": "medbay", "temporal": "this round"}
        result = verify_location_claim(claim, tl, n2i, 0, 5)
        assert result == "unverifiable"


class TestVerifySightingClaim:
    def _make_timeline(self) -> tuple[GameTimeline, dict[str, str]]:
        tl = GameTimeline()
        tl.max_tick = 5
        tl.player_names = {"player_0": "Alice", "player_1": "Bob"}
        tl.player_timelines = {
            "player_0": [
                PlayerTickState(tick=t, room="medbay") for t in range(6)
            ],
            "player_1": [
                PlayerTickState(tick=t, room="medbay" if t <= 2 else "electrical")
                for t in range(6)
            ],
        }
        return tl, {"Alice": "player_0", "Bob": "player_1"}

    def test_true_sighting(self) -> None:
        tl, n2i = self._make_timeline()
        claim = {
            "type": "sighting", "subject": "Alice", "target": "Bob",
            "room": "medbay", "temporal": "this round",
        }
        result = verify_sighting_claim(claim, tl, n2i, 0, 5)
        assert result == "true"

    def test_wrong_room_sighting(self) -> None:
        tl, n2i = self._make_timeline()
        claim = {
            "type": "sighting", "subject": "Alice", "target": "Bob",
            "room": "electrical", "temporal": "this round",
        }
        # They were in the same room (medbay) but claim says electrical
        result = verify_sighting_claim(claim, tl, n2i, 0, 2)
        assert result == "wrong_room"

    def test_false_sighting(self) -> None:
        tl, n2i = self._make_timeline()
        claim = {
            "type": "sighting", "subject": "Alice", "target": "Bob",
            "room": "weapons", "temporal": "this round",
        }
        # Check only ticks 3-5 where they're never in the same room
        result = verify_sighting_claim(claim, tl, n2i, 3, 5)
        assert result == "false"


class TestVerifyActivityClaim:
    def test_task_true(self, simple_map: GameMap) -> None:
        events = build_minimal_game_events()
        timeline = GameReconstructor(events, simple_map).reconstruct()
        name_to_id = {"Bob": "player_1"}

        claim = {"type": "activity", "subject": "Bob", "activity": "task", "room": "medbay"}
        result = verify_activity_claim(claim, events, timeline, name_to_id, 0, 10)
        assert result == "true"

    def test_task_false(self, simple_map: GameMap) -> None:
        events = build_minimal_game_events()
        timeline = GameReconstructor(events, simple_map).reconstruct()
        name_to_id = {"Alice": "player_0"}

        claim = {"type": "activity", "subject": "Alice", "activity": "task", "room": "medbay"}
        result = verify_activity_claim(claim, events, timeline, name_to_id, 0, 10)
        assert result == "false"

    def test_unknown_activity(self, simple_map: GameMap) -> None:
        events = build_minimal_game_events()
        timeline = GameReconstructor(events, simple_map).reconstruct()
        name_to_id = {"Alice": "player_0"}

        claim = {"type": "activity", "subject": "Alice", "activity": "fighting", "room": None}
        result = verify_activity_claim(claim, events, timeline, name_to_id, 0, 10)
        assert result == "unverifiable"
