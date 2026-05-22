"""Tests for game_reconstructor module."""

from __future__ import annotations


from quack.evaluation.game_reconstructor import (
    GameReconstructor,
    GameTimeline,
    hop_distance,
)
from quack.map.game_map import GameMap

from .conftest import make_event


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
        """Test that multi-tick travel is reconstructed correctly.

        Weight-W corridor in the engine logs ``ticks_remaining = W`` on the
        action tick, then the reconstructor decrements that counter at the
        start of every subsequent tick — so arrival happens at
        ``action_tick + W``. For weight-2 (cafeteria -> oxygen) this means
        the player is in transit on ticks 1 and 2 and only arrives at tick 3.
        """
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
            # Weight-2 corridor: cafeteria -> oxygen (weight=2). The engine
            # logs ticks_remaining=2 so the reconstructor models 2 transit
            # ticks before arrival.
            make_event("player_moved", 1, {
                "player_id": "player_0",
                "from": "cafeteria",
                "to": "oxygen",
                "ticks_remaining": 2,
            }),
            make_event("tick_end", 1, {"tick": 1}),
            make_event("tick_start", 2, {"tick": 2}),
            make_event("tick_end", 2, {"tick": 2}),
            make_event("tick_start", 3, {"tick": 3}),
            make_event("tick_end", 3, {"tick": 3}),
            make_event("game_over", 3, {"winner": "goose", "reason": "tasks done"}),
        ]
        timeline = GameReconstructor(events, simple_map).reconstruct()

        # Tick 1: player issues move, in transit, displayed at the `from` room.
        s1 = timeline.get_player_state("player_0", 1)
        assert s1 is not None
        assert s1.in_transit
        assert s1.room == "cafeteria"

        # Tick 2: still in transit (ticks_remaining 2 -> 1 after start-of-tick
        # decrement).
        s2 = timeline.get_player_state("player_0", 2)
        assert s2 is not None
        assert s2.in_transit
        assert s2.room == "cafeteria"

        # Tick 3: transit completes (ticks_remaining 1 -> 0), player is at oxygen.
        s3 = timeline.get_player_state("player_0", 3)
        assert s3 is not None
        assert not s3.in_transit
        assert s3.room == "oxygen"


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


class TestRoomsTouchedAndPassThrough:
    """Bug A: transit-destination and same-tick pass-through rooms must be
    queryable, even when the engine logs the *next* hop on the same tick the
    previous transit completes (the "Diana arrives at medbay, immediately
    moves on to electrical" case).
    """

    def _diana_events(self) -> list[dict]:
        """Build a minimal event log reproducing the Diana / medbay case.

        Tick 17: Diana issues storage -> medbay with weight 2.
                 Engine logs ``ticks_remaining=2``, so transit ticks down
                 over ticks 18 and 19.
        Tick 19: Transit completes at start-of-tick (Diana enters medbay)
                 and the engine logs a same-tick instantaneous
                 ``medbay -> electrical`` move.

        With the pre-fix reconstructor Diana's medbay arrival was lost
        because ``current_room`` was immediately overwritten to
        ``electrical``.
        """
        return [
            make_event("game_started", 0, {
                "players": ["Diana"],
                "config": {"num_players": 1, "num_ducks": 0, "map": "configs/maps/simple_ship.yaml"},
                "initial_state": {
                    "player_0": {
                        "name": "Diana", "role": "Goose", "team": "goose",
                        "room": "storage", "tasks": [],
                    }
                },
            }),
            make_event("tick_start", 17, {"tick": 17}),
            make_event("player_moved", 17, {
                "player_id": "player_0",
                "from": "storage",
                "to": "medbay",
                "ticks_remaining": 2,
            }),
            make_event("tick_end", 17, {"tick": 17}),
            make_event("tick_start", 18, {"tick": 18}),
            make_event("tick_end", 18, {"tick": 18}),
            make_event("tick_start", 19, {"tick": 19}),
            # Pass-through: transit completes -> medbay at start of tick 19,
            # then a same-tick instantaneous move medbay -> electrical.
            make_event("player_moved", 19, {
                "player_id": "player_0",
                "from": "medbay",
                "to": "electrical",
            }),
            make_event("tick_end", 19, {"tick": 19}),
            make_event("game_over", 21, {"winner": "goose", "reason": "test"}),
        ]

    def test_was_in_room_recovers_pass_through_medbay(self, simple_map) -> None:
        """The headline regression: Diana's medbay arrival must be
        recoverable from the timeline even though the engine logged the
        next hop on the same tick. Without ``rooms_touched`` this returned
        ``[]`` and a truthful claim got scored ``false``.
        """
        timeline = GameReconstructor(self._diana_events(), simple_map).reconstruct()
        medbay_ticks = timeline.was_in_room("player_0", "medbay", 0, 21)
        # At minimum, the arrival tick (19) must be flagged. Whether tick 18
        # also counts depends on the transit-accounting convention; the
        # current implementation reports medbay touched at tick 19 only.
        assert medbay_ticks, (
            f"medbay arrival was lost from the timeline (was_in_room returned {medbay_ticks!r}). "
            "Bug A regression: same-tick pass-through rooms are not being recorded."
        )
        assert 19 in medbay_ticks

    def test_was_in_room_reports_origin_and_destination_for_full_route(
        self, simple_map,
    ) -> None:
        """All three rooms Diana touched (storage, medbay, electrical)
        must be queryable from the timeline.
        """
        timeline = GameReconstructor(self._diana_events(), simple_map).reconstruct()
        assert timeline.was_in_room("player_0", "storage", 0, 21), \
            "Origin room storage should be queryable from before transit"
        assert timeline.was_in_room("player_0", "medbay", 0, 21), \
            "Pass-through room medbay should be queryable"
        assert timeline.was_in_room("player_0", "electrical", 0, 21), \
            "Destination room electrical should be queryable"

    def test_was_in_room_returns_empty_for_unvisited_room(self, simple_map) -> None:
        """Sanity: a room the player never entered must not show up."""
        timeline = GameReconstructor(self._diana_events(), simple_map).reconstruct()
        assert timeline.was_in_room("player_0", "weapons", 0, 21) == []

    def test_was_in_room_skips_dead_ticks(self, minimal_game_events, simple_map) -> None:
        """A dead player must not match any room even if their scalar
        ``state.room`` still reads as the room they died in (we don't want
        ghost matches polluting Tier 3)."""
        timeline = GameReconstructor(minimal_game_events, simple_map).reconstruct()
        # Eve dies at tick 5 in security in the minimal fixture.
        eve_security = timeline.was_in_room("player_4", "security", 6, 10)
        assert eve_security == [], (
            f"dead player matched on room state (got {eve_security!r}); "
            "was_in_room must skip dead ticks"
        )

    def test_rooms_touched_scalar_room_unchanged(self, simple_map) -> None:
        """The scalar ``state.room`` field must keep its end-of-tick
        semantics — the rooms_touched addition is non-breaking."""
        timeline = GameReconstructor(self._diana_events(), simple_map).reconstruct()
        # End-of-tick room at tick 19 is electrical (the final destination).
        s19 = timeline.get_player_state("player_0", 19)
        assert s19 is not None
        assert s19.room == "electrical"
        # End-of-tick room at tick 18 is still storage (still in transit).
        s18 = timeline.get_player_state("player_0", 18)
        assert s18 is not None
        assert s18.room == "storage"

    def test_get_visited_rooms_returns_ordered_chain(self, simple_map) -> None:
        """get_visited_rooms must surface the ordered chain
        ``storage -> medbay -> electrical`` for the Diana case so route
        verification can use it directly."""
        timeline = GameReconstructor(self._diana_events(), simple_map).reconstruct()
        chain = timeline.get_visited_rooms("player_0", 0, 21)
        assert chain[0] == "storage"
        assert "medbay" in chain
        assert chain[-1] == "electrical"
        # No adjacent duplicates
        for a, b in zip(chain, chain[1:]):
            assert a != b
