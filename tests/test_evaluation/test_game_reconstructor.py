"""Tests for game_reconstructor module."""

from __future__ import annotations

import pytest

from quack.evaluation.game_reconstructor import (
    GameReconstructor,
    GameTimeline,
    hop_distance,
)
from quack.map.game_map import GameMap

from .conftest import build_minimal_game_events, make_event


class TestHopDistance:
    def test_same_room(self, simple_map: GameMap) -> None:
        assert hop_distance(simple_map, "cafeteria", "cafeteria") == 0

    def test_adjacent_rooms(self, simple_map: GameMap) -> None:
        # cafeteria -> medbay: 1 hop (weight 1, but hop=1)
        assert hop_distance(simple_map, "cafeteria", "medbay") == 1

    def test_two_hops(self, simple_map: GameMap) -> None:
        # cafeteria -> electrical -> security
        assert hop_distance(simple_map, "cafeteria", "security") == 2

    def test_unreachable(self) -> None:
        from quack.map.game_map import Room
        gm = GameMap()
        gm.add_room(Room("a", 0, 0))
        gm.add_room(Room("b", 1, 0))
        assert hop_distance(gm, "a", "b") == -1


class TestGameReconstructor:
    def test_basic_reconstruction(self, minimal_game_events, simple_map) -> None:
        timeline = GameReconstructor(minimal_game_events, simple_map).reconstruct()
        assert isinstance(timeline, GameTimeline)
        assert len(timeline.player_timelines) == 6
        assert timeline.max_tick == 10

    def test_initial_positions(self, minimal_game_events, simple_map) -> None:
        timeline = GameReconstructor(minimal_game_events, simple_map).reconstruct()
        # Player 0 starts in cafeteria
        assert timeline.get_player_room("player_0", 0) == "cafeteria"

    def test_movement_tracking(self, minimal_game_events, simple_map) -> None:
        timeline = GameReconstructor(minimal_game_events, simple_map).reconstruct()
        # Player 0 moves to medbay at tick 3
        assert timeline.get_player_room("player_0", 2) == "cafeteria"
        assert timeline.get_player_room("player_0", 3) == "medbay"

    def test_kill_marks_dead(self, minimal_game_events, simple_map) -> None:
        timeline = GameReconstructor(minimal_game_events, simple_map).reconstruct()
        # Player 4 is killed at tick 5
        assert timeline.is_alive("player_4", 4)
        assert not timeline.is_alive("player_4", 5)

    def test_ejection_marks_dead(self, minimal_game_events, simple_map) -> None:
        timeline = GameReconstructor(minimal_game_events, simple_map).reconstruct()
        # Player 5 is ejected at tick 7
        assert not timeline.is_alive("player_5", 7)

    def test_get_players_in_room(self, minimal_game_events, simple_map) -> None:
        timeline = GameReconstructor(minimal_game_events, simple_map).reconstruct()
        # At tick 0, player_0 should be in cafeteria
        players = timeline.get_players_in_room("cafeteria", 0)
        assert "player_0" in players

    def test_were_in_same_room(self, minimal_game_events, simple_map) -> None:
        timeline = GameReconstructor(minimal_game_events, simple_map).reconstruct()
        # Player 5 and player 4 should be in the same room at tick 5 (security)
        state_5 = timeline.get_player_state("player_5", 5)
        state_4 = timeline.get_player_state("player_4", 5)
        assert state_5 is not None
        assert state_4 is not None
        assert state_5.room == "security"

    def test_room_sequence(self, minimal_game_events, simple_map) -> None:
        timeline = GameReconstructor(minimal_game_events, simple_map).reconstruct()
        seq = timeline.get_room_sequence("player_0", 0, 5)
        assert len(seq) == 6  # ticks 0-5 inclusive
        assert seq[0] == "cafeteria"
        assert seq[3] == "medbay"  # moved at tick 3

    def test_meeting_boundaries(self, minimal_game_events, simple_map) -> None:
        timeline = GameReconstructor(minimal_game_events, simple_map).reconstruct()
        assert len(timeline.meeting_boundaries) >= 1
        assert timeline.meeting_boundaries[0]["meeting_tick"] == 7

    def test_multi_tick_travel(self, simple_map) -> None:
        """Test that multi-tick travel is reconstructed correctly."""
        events = [
            make_event("game_started", 0, {
                "players": ["Alice"],
                "config": {"num_players": 1, "num_ducks": 0, "map": "configs/maps/simple_ship.yaml"},
                "initial_state": {
                    "player_0": {
                        "name": "Alice", "role": "Goose", "team": "goose",
                        "room": "cafeteria", "tasks": [],
                    }
                },
            }),
            make_event("tick_start", 1, {"tick": 1}),
            # Weight-2 corridor: cafeteria -> oxygen (weight=2)
            make_event("player_moved", 1, {
                "player_id": "player_0",
                "from": "cafeteria",
                "to": "oxygen",
                "ticks_remaining": 1,
            }),
            make_event("tick_end", 1, {"tick": 1}),
            make_event("tick_start", 2, {"tick": 2}),
            make_event("tick_end", 2, {"tick": 2}),
            make_event("tick_start", 3, {"tick": 3}),
            make_event("tick_end", 3, {"tick": 3}),
            make_event("game_over", 3, {"winner": "goose", "reason": "tasks done"}),
        ]
        timeline = GameReconstructor(events, simple_map).reconstruct()

        # At tick 1: player starts move, in transit, room = cafeteria (from)
        s1 = timeline.get_player_state("player_0", 1)
        assert s1 is not None
        assert s1.in_transit
        assert s1.room == "cafeteria"

        # At tick 2: transit completes (ticks_remaining was 1, decremented at start of tick 2)
        s2 = timeline.get_player_state("player_0", 2)
        assert s2 is not None
        assert not s2.in_transit
        assert s2.room == "oxygen"


class TestGameTimeline:
    def test_round_boundaries_no_meetings(self, simple_map) -> None:
        events = [
            make_event("game_started", 0, {
                "players": ["Alice"],
                "config": {},
                "initial_state": {
                    "player_0": {
                        "name": "Alice", "role": "Goose", "team": "goose",
                        "room": "cafeteria", "tasks": [],
                    }
                },
            }),
            make_event("tick_start", 1, {"tick": 1}),
            make_event("tick_end", 1, {"tick": 1}),
            make_event("game_over", 1, {"winner": "goose", "reason": "done"}),
        ]
        timeline = GameReconstructor(events, simple_map).reconstruct()
        bounds = timeline.get_round_boundaries()
        assert len(bounds) == 1
        assert bounds[0] == (0, 1)

    def test_free_roam_segments_after_reconstruction(self, minimal_game_events, simple_map) -> None:
        """Reconstructed timeline should have correct free_roam_segments."""
        timeline = GameReconstructor(minimal_game_events, simple_map).reconstruct()
        assert len(timeline.free_roam_segments) == 2
        assert timeline.free_roam_segments[0] == {"start": 0, "end": 6}
        assert timeline.free_roam_segments[1]["start"] == 7

    def test_meeting_preceding_free_roam_index(self, minimal_game_events, simple_map) -> None:
        """Meeting boundaries should link to their preceding free-roam segment."""
        timeline = GameReconstructor(minimal_game_events, simple_map).reconstruct()
        assert len(timeline.meeting_boundaries) == 1
        assert timeline.meeting_boundaries[0]["preceding_free_roam_index"] == 0
