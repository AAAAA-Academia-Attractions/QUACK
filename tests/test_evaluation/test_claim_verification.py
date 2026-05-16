"""Tests for Tier 3 claim verification logic (without LLM calls)."""

from __future__ import annotations

import pytest

from quack.evaluation.game_reconstructor import GameReconstructor, GameTimeline, PlayerTickState
from quack.evaluation.tier3_statement_verification import (
    VerificationResult,
    _determine_round_range,
    _infer_duration_semantics,
    can_see,
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
        assert result.verdict == "true"

    def test_false_location(self) -> None:
        tl, n2i = self._make_timeline()
        claim = {"type": "location", "subject": "Alice", "room": "weapons", "temporal": "this round"}
        result = verify_location_claim(claim, tl, n2i, 0, 5)
        assert result.verdict == "false"

    def test_near_miss_location(self) -> None:
        tl, n2i = self._make_timeline()
        claim = {"type": "location", "subject": "Alice", "room": "medbay", "temporal": "this round"}
        result = verify_location_claim(claim, tl, n2i, 4, 10)
        assert result.verdict == "near_miss"

    def test_unverifiable_unknown_player(self) -> None:
        tl, n2i = self._make_timeline()
        claim = {"type": "location", "subject": "Unknown", "room": "medbay", "temporal": "this round"}
        result = verify_location_claim(claim, tl, n2i, 0, 5)
        assert result.verdict == "unverifiable"


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
        assert result.verdict == "true"

    def test_wrong_room_sighting(self) -> None:
        tl, n2i = self._make_timeline()
        claim = {
            "type": "sighting", "subject": "Alice", "target": "Bob",
            "room": "electrical", "temporal": "this round",
        }
        # They were in the same room (medbay) but claim says electrical
        result = verify_sighting_claim(claim, tl, n2i, 0, 2)
        assert result.verdict == "wrong_room"

    def test_false_sighting(self) -> None:
        tl, n2i = self._make_timeline()
        claim = {
            "type": "sighting", "subject": "Alice", "target": "Bob",
            "room": "weapons", "temporal": "this round",
        }
        # Check only ticks 3-5 where they're never in the same room
        result = verify_sighting_claim(claim, tl, n2i, 3, 5)
        assert result.verdict == "false"


class TestVerifyActivityClaim:
    def test_task_true(self, simple_map: GameMap) -> None:
        events = build_minimal_game_events()
        timeline = GameReconstructor(events, simple_map).reconstruct()
        name_to_id = {"Bob": "player_1"}

        claim = {"type": "activity", "subject": "Bob", "activity": "task", "room": "medbay"}
        result = verify_activity_claim(claim, events, timeline, name_to_id, 0, 10)
        assert result.verdict == "true"

    def test_task_false(self, simple_map: GameMap) -> None:
        events = build_minimal_game_events()
        timeline = GameReconstructor(events, simple_map).reconstruct()
        name_to_id = {"Alice": "player_0"}

        claim = {"type": "activity", "subject": "Alice", "activity": "task", "room": "medbay"}
        result = verify_activity_claim(claim, events, timeline, name_to_id, 0, 10)
        assert result.verdict == "false"

    def test_unknown_activity(self, simple_map: GameMap) -> None:
        events = build_minimal_game_events()
        timeline = GameReconstructor(events, simple_map).reconstruct()
        name_to_id = {"Alice": "player_0"}

        claim = {"type": "activity", "subject": "Alice", "activity": "fighting", "room": None}
        result = verify_activity_claim(claim, events, timeline, name_to_id, 0, 10)
        assert result.verdict == "unverifiable"


class TestDetermineRoundRange:
    """Tests for _determine_round_range temporal window semantics."""

    @staticmethod
    def _make_timeline(segments: list[tuple[int, int]], max_tick: int = 20) -> GameTimeline:
        """Build a GameTimeline with given free_roam_segments."""
        tl = GameTimeline()
        tl.max_tick = max_tick
        tl.free_roam_segments = [
            {"start": s, "end": e} for s, e in segments
        ]
        return tl

    def test_this_round_preceding_free_roam(self) -> None:
        """Meeting at tick 7 -> 'this round' = [0, 6], NOT [7, 7]."""
        tl = self._make_timeline([(0, 6), (7, 10)])
        rs, re = _determine_round_range(7, tl, "this round")
        assert rs == 0
        assert re == 6

    def test_body_at_tick_17_this_round(self) -> None:
        """Meeting at tick 17 -> 'this round' = [0, 16], not [17, 17]."""
        tl = self._make_timeline([(0, 16), (17, 20)])
        rs, re = _determine_round_range(17, tl, "this round")
        assert rs == 0
        assert re == 16

    def test_two_meetings_second_meeting(self) -> None:
        """Second meeting at tick 17 -> 'this round' = [7, 16]."""
        tl = self._make_timeline([(0, 6), (7, 16), (17, 20)])
        rs, re = _determine_round_range(17, tl, "this round")
        assert rs == 7
        assert re == 16

    def test_at_start_clamps_to_first_five(self) -> None:
        """'at the start' should clamp round_end to start + 5."""
        tl = self._make_timeline([(0, 16), (17, 20)])
        rs, re = _determine_round_range(17, tl, "at the start")
        assert rs == 0
        assert re == 5

    def test_since_last_meeting_same_as_this_round(self) -> None:
        """'since last meeting' is semantically equivalent to 'this round'."""
        tl = self._make_timeline([(0, 6), (7, 10)])
        rs1, re1 = _determine_round_range(7, tl, "this round")
        rs2, re2 = _determine_round_range(7, tl, "since last meeting")
        assert (rs1, re1) == (rs2, re2) == (0, 6)

    def test_empty_temporal_defaults(self) -> None:
        """Empty temporal string defaults to the preceding free-roam segment."""
        tl = self._make_timeline([(0, 6), (7, 10)])
        rs, re = _determine_round_range(7, tl, "")
        assert rs == 0
        assert re == 6

    def test_integration_full_reconstruction(self, minimal_game_events, simple_map: GameMap) -> None:
        """End-to-end: reconstruct a game, verify 'this round' at meeting tick 7."""
        from quack.evaluation.game_reconstructor import GameReconstructor
        timeline = GameReconstructor(minimal_game_events, simple_map).reconstruct()
        rs, re = _determine_round_range(7, timeline, "this round")
        assert rs == 0
        assert re == 6


class TestDurationSemantics:
    """Tests for _infer_duration_semantics rule-based inference."""

    def test_any_time_transient_phrases(self) -> None:
        assert _infer_duration_semantics("passed through") == "any_time"
        assert _infer_duration_semantics("went to") == "any_time"
        assert _infer_duration_semantics("visited") == "any_time"
        assert _infer_duration_semantics("came from") == "any_time"
        assert _infer_duration_semantics("entered") == "any_time"
        assert _infer_duration_semantics("stopped by") == "any_time"
        assert _infer_duration_semantics("popped into medbay") == "any_time"

    def test_entire_time_phrases(self) -> None:
        assert _infer_duration_semantics("the whole time") == "entire_time"
        assert _infer_duration_semantics("entire round") == "entire_time"
        assert _infer_duration_semantics("all round") == "entire_time"
        assert _infer_duration_semantics("never left") == "entire_time"
        assert _infer_duration_semantics("stayed in") == "entire_time"

    def test_most_time_phrases(self) -> None:
        assert _infer_duration_semantics("mostly") == "most_time"
        assert _infer_duration_semantics("spent most of") == "most_time"

    def test_unknown_fallback(self) -> None:
        """Plain 'was in X' without duration modifier stays as unknown_fallback."""
        assert _infer_duration_semantics("this round") == "unknown_fallback"
        assert _infer_duration_semantics("since last meeting") == "unknown_fallback"
        assert _infer_duration_semantics("") == "unknown_fallback"

    def test_location_verifier_respects_any_time(self) -> None:
        """With any_time semantics, a single visit should be true."""
        tl = GameTimeline()
        tl.max_tick = 5
        tl.player_timelines = {
            "player_0": [
                PlayerTickState(tick=t, room="cafeteria" if t != 3 else "medbay")
                for t in range(6)
            ]
        }
        claim = {"type": "location", "subject": "Alice", "room": "medbay", "temporal": "passed through"}
        result = verify_location_claim(claim, tl, {"Alice": "player_0"}, 0, 5,
                                       duration_semantics="any_time")
        assert result.verdict == "true"
        assert result.evidence["matched_ticks"] == [3]

    def test_location_verifier_entire_time_fails_partial(self) -> None:
        """With entire_time, partial presence is false, not near_miss."""
        tl = GameTimeline()
        tl.max_tick = 5
        tl.player_timelines = {
            "player_0": [
                PlayerTickState(tick=t, room="medbay" if t <= 2 else "electrical")
                for t in range(6)
            ]
        }
        claim = {"type": "location", "subject": "Alice", "room": "medbay",
                 "temporal": "the whole time"}
        result = verify_location_claim(claim, tl, {"Alice": "player_0"}, 0, 5,
                                       duration_semantics="entire_time")
        assert result.verdict == "false"
        assert result.evidence["num_valid_ticks"] == 6
        assert result.evidence["num_matched_ticks"] == 3

    def test_location_verifier_entire_time_excludes_dead_ticks(self) -> None:
        """entire_time excludes ticks where the player is dead."""
        tl = GameTimeline()
        tl.max_tick = 5
        tl.player_timelines = {
            "player_0": [
                PlayerTickState(tick=0, room="medbay", is_alive=True),
                PlayerTickState(tick=1, room="medbay", is_alive=True),
                PlayerTickState(tick=2, room="medbay", is_alive=True),
                PlayerTickState(tick=3, room="medbay", is_alive=False),
                PlayerTickState(tick=4, room="medbay", is_alive=False),
                PlayerTickState(tick=5, room="medbay", is_alive=False),
            ]
        }
        claim = {"type": "location", "subject": "Alice", "room": "medbay",
                 "temporal": "the whole time"}
        result = verify_location_claim(claim, tl, {"Alice": "player_0"}, 0, 5,
                                       duration_semantics="entire_time")
        assert result.verdict == "true"
        assert result.evidence["num_valid_ticks"] == 3  # ticks 0-2 only
        assert 3 in result.evidence["excluded_ticks"]
        assert result.evidence["exclusion_reasons"].get(3) == "player_dead"


class TestCanSee:
    """Tests for can_see() visibility re-implementation."""

    def _make_timeline_with_transit(self) -> GameTimeline:
        tl = GameTimeline()
        tl.max_tick = 5
        # Alice: stationary in medbay entire time
        # Bob: moving medbay→electrical at tick 2, arrived tick 3
        tl.player_timelines = {
            "player_0": [
                PlayerTickState(tick=t, room="medbay", in_transit=False)
                for t in range(6)
            ],
            "player_1": [
                PlayerTickState(tick=0, room="medbay", in_transit=False),
                PlayerTickState(tick=1, room="medbay", in_transit=False),
                PlayerTickState(tick=2, room="medbay", in_transit=True, moving_to="electrical"),
                PlayerTickState(tick=3, room="electrical", in_transit=False),
                PlayerTickState(tick=4, room="electrical", in_transit=False),
                PlayerTickState(tick=5, room="electrical", in_transit=False),
            ],
        }
        return tl

    def test_same_room_both_stationary(self) -> None:
        tl = self._make_timeline_with_transit()
        assert can_see("player_0", "player_1", 0, tl) is True

    def test_stationary_cannot_see_transit(self) -> None:
        """Stationary player cannot see a player in corridor."""
        tl = self._make_timeline_with_transit()
        assert can_see("player_0", "player_1", 2, tl) is False

    def test_different_rooms_cannot_see(self) -> None:
        tl = self._make_timeline_with_transit()
        assert can_see("player_0", "player_1", 4, tl) is False

    def test_transit_can_see_same_corridor_same_direction(self) -> None:
        tl = GameTimeline()
        tl.max_tick = 2
        tl.player_timelines = {
            "player_0": [
                PlayerTickState(tick=0, room="cafeteria", in_transit=False),
                PlayerTickState(tick=1, room="cafeteria", in_transit=True, moving_to="medbay"),
                PlayerTickState(tick=2, room="cafeteria", in_transit=True, moving_to="medbay"),
            ],
            "player_1": [
                PlayerTickState(tick=0, room="cafeteria", in_transit=False),
                PlayerTickState(tick=1, room="cafeteria", in_transit=True, moving_to="medbay"),
                PlayerTickState(tick=2, room="cafeteria", in_transit=True, moving_to="medbay"),
            ],
        }
        assert can_see("player_0", "player_1", 1, tl) is True

    def test_transit_can_see_opposite_direction(self) -> None:
        tl = GameTimeline()
        tl.max_tick = 2
        tl.player_timelines = {
            "player_0": [
                PlayerTickState(tick=0, room="cafeteria", in_transit=False),
                PlayerTickState(tick=1, room="cafeteria", in_transit=True, moving_to="medbay"),
                PlayerTickState(tick=2, room="medbay", in_transit=False),
            ],
            "player_1": [
                PlayerTickState(tick=0, room="medbay", in_transit=False),
                PlayerTickState(tick=1, room="medbay", in_transit=True, moving_to="cafeteria"),
                PlayerTickState(tick=2, room="cafeteria", in_transit=False),
            ],
        }
        assert can_see("player_0", "player_1", 1, tl) is True


class TestVerifyActivityNewTypes:
    """Tests for newly supported activity types."""

    def test_waiting_true(self, simple_map: GameMap) -> None:
        events = build_minimal_game_events()
        timeline = GameReconstructor(events, simple_map).reconstruct()
        name_to_id = {"Charlie": "player_2"}
        # Charlie stays in electrical from tick 0-10
        claim = {"type": "activity", "subject": "Charlie", "activity": "waiting"}
        result = verify_activity_claim(claim, events, timeline, name_to_id, 0, 6)
        assert result.verdict == "true"

    def test_waiting_false_when_moving(self) -> None:
        """Waiting should be false if subject changed rooms."""
        tl = GameTimeline()
        tl.max_tick = 3
        tl.player_timelines = {
            "player_0": [
                PlayerTickState(tick=0, room="cafeteria"),
                PlayerTickState(tick=1, room="cafeteria"),
                PlayerTickState(tick=2, room="medbay"),
                PlayerTickState(tick=3, room="medbay"),
            ]
        }
        claim = {"type": "activity", "subject": "Alice", "activity": "waiting"}
        result = verify_activity_claim(claim, [], tl, {"Alice": "player_0"}, 0, 3)
        assert result.verdict == "false"
        assert len(result.evidence["unique_rooms"]) > 1

    def test_reporting_body_true(self, simple_map: GameMap) -> None:
        events = build_minimal_game_events()
        timeline = GameReconstructor(events, simple_map).reconstruct()
        name_to_id = {"Alice": "player_0"}
        # Alice reports body at tick 7
        claim = {"type": "activity", "subject": "Alice", "activity": "reporting body"}
        result = verify_activity_claim(claim, events, timeline, name_to_id, 0, 10,
                                        meeting_tick=7)
        assert result.verdict == "true"

    def test_reporting_body_false(self, simple_map: GameMap) -> None:
        events = build_minimal_game_events()
        timeline = GameReconstructor(events, simple_map).reconstruct()
        name_to_id = {"Bob": "player_1"}
        # Bob did NOT report body
        claim = {"type": "activity", "subject": "Bob", "activity": "reporting body"}
        result = verify_activity_claim(claim, events, timeline, name_to_id, 0, 10,
                                        meeting_tick=7)
        assert result.verdict == "false"

    def test_calling_meeting_false_no_event(self, simple_map: GameMap) -> None:
        events = build_minimal_game_events()
        timeline = GameReconstructor(events, simple_map).reconstruct()
        name_to_id = {"Alice": "player_0"}
        claim = {"type": "activity", "subject": "Alice", "activity": "calling meeting"}
        result = verify_activity_claim(claim, events, timeline, name_to_id, 0, 10,
                                        meeting_tick=7)
        assert result.verdict == "false"


class TestVerificationResultEvidence:
    """Tests that VerificationResult contains evidence and reason."""

    def test_location_result_has_evidence(self) -> None:
        tl = GameTimeline()
        tl.max_tick = 5
        tl.player_timelines = {
            "player_0": [
                PlayerTickState(tick=t, room="medbay") for t in range(6)
            ]
        }
        claim = {"type": "location", "subject": "Alice", "room": "medbay"}
        result = verify_location_claim(claim, tl, {"Alice": "player_0"}, 0, 5)
        assert result.verifier_name == "verify_location_claim"
        assert "ticks_checked" in result.evidence
        assert "matched_ticks" in result.evidence
        assert "duration_semantics" in result.evidence
        assert len(result.reason) > 0

    def test_sighting_result_records_visibility_source(self) -> None:
        tl = GameTimeline()
        tl.max_tick = 2
        tl.player_timelines = {
            "player_0": [PlayerTickState(tick=t, room="cafeteria") for t in range(3)],
            "player_1": [PlayerTickState(tick=t, room="cafeteria") for t in range(3)],
        }
        claim = {"type": "sighting", "subject": "Alice", "target": "Bob", "room": "cafeteria"}
        result = verify_sighting_claim(claim, tl, {"Alice": "player_0", "Bob": "player_1"}, 0, 2)
        assert result.verdict == "true"
        assert result.evidence["visibility_source"] == "same_room_fallback"

    def test_activity_reason_not_contradict_evidence(self) -> None:
        """Reason string must be mechanically derived from evidence."""
        tl = GameTimeline()
        tl.max_tick = 3
        tl.player_timelines = {
            "player_0": [
                PlayerTickState(tick=t, room="cafeteria") for t in range(4)
            ]
        }
        claim = {"type": "activity", "subject": "Alice", "activity": "task"}
        result = verify_activity_claim(claim, [], tl, {"Alice": "player_0"}, 0, 3)
        assert result.verdict == "false"
        # Reason mentions the window range
        assert "[0, 3]" in result.reason


class TestDefenseVerifier:
    """Tests that defense claims return unverifiable with a clear reason."""

    def test_defense_returns_unverifiable_with_reason(self) -> None:
        """A generic defense claim is unverifiable but has a reason."""
        from quack.evaluation.tier3_statement_verification import StatementVerificationPipeline
        tl = GameTimeline()
        tl.max_tick = 5
        tl.player_names = {"player_0": "Alice"}
        tl.player_teams = {"player_0": "goose"}
        pipeline = StatementVerificationPipeline.__new__(StatementVerificationPipeline)
        pipeline.timeline = tl
        pipeline.name_to_id = {"Alice": "player_0"}
        pipeline.role_map = {"player_0": "goose"}
        pipeline.game_map = None
        pipeline.duck_ids = set()
        pipeline.events = []

        claim = {"type": "defense", "defender": "Alice", "defended": "Alice",
                 "basis": "I was doing tasks"}
        result = pipeline._verify_claim(claim, 5)
        assert result.verdict == "unverifiable"
        assert "decompos" in result.reason.lower()
        assert result.verifier_name == "verify_defense_claim"


class TestAuditOutput:
    """Tests for claim-level audit entries."""

    def test_audit_entry_has_required_sections(self, simple_map: GameMap) -> None:
        """Each audit entry must have meeting, temporal_window, speaker,
        utterance, structured_claim, and verification sections."""
        from quack.evaluation.tier3_statement_verification import StatementVerificationPipeline
        events = build_minimal_game_events()
        timeline = GameReconstructor(events, simple_map).reconstruct()

        pipeline = StatementVerificationPipeline.__new__(StatementVerificationPipeline)
        pipeline.timeline = timeline
        pipeline.game_map = simple_map
        pipeline.events = events
        pipeline.name_to_id = {"Alice": "player_0", "Bob": "player_1",
                                "Charlie": "player_2", "Diana": "player_3",
                                "Eve": "player_4", "Frank": "player_5"}
        pipeline.id_to_name = {v: k for k, v in pipeline.name_to_id.items()}
        pipeline.role_map = {"player_0": "goose", "player_1": "goose",
                             "player_2": "goose", "player_3": "goose",
                             "player_4": "goose", "player_5": "duck"}
        pipeline.duck_ids = {"player_5"}

        claim = {
            "type": "location", "subject": "Alice", "room": "medbay",
            "temporal": "this round",
            "_speaker_id": "player_0", "_speaker_name": "Alice",
            "_meeting_idx": 0, "_meeting_tick": 7,
        }
        meeting = {"tick": 7, "type": "body_reported", "caller": "player_0"}
        result = pipeline._verify_claim(claim, 7)
        audit = pipeline._build_audit_entry(claim, meeting, 0, result,
                                            "I was in medbay the whole time.")

        assert "meeting" in audit
        assert audit["meeting"]["meeting_tick"] == 7
        assert audit["meeting"]["meeting_type"] == "body_reported"
        assert "temporal_window" in audit
        assert audit["temporal_window"]["start_tick"] == 0
        assert audit["temporal_window"]["end_tick"] == 6
        assert audit["temporal_window"]["resolution_source"] == "preceding_free_roam"
        assert "speaker" in audit
        assert audit["speaker"]["speaker_name"] == "Alice"
        assert audit["speaker"]["team"] == "goose"
        assert "utterance" in audit
        assert audit["utterance"]["raw"] == "I was in medbay the whole time."
        assert "structured_claim" in audit
        assert audit["structured_claim"]["claim_type"] == "location"
        assert audit["structured_claim"]["subject_id"] == "player_0"
        assert audit["structured_claim"]["duration_semantics"] is not None
        assert "verification" in audit
        assert audit["verification"]["verdict"] in ("true", "false", "near_miss",
                                                     "wrong_room", "unverifiable")
        assert "reason" in audit["verification"]
        assert "evidence" in audit["verification"]
        # Evidence includes actual tick IDs
        assert "ticks_checked" in audit["verification"]["evidence"]
        assert isinstance(audit["verification"]["evidence"]["ticks_checked"], list)

    def test_audit_temporal_window_reflects_preceding_free_roam(self, simple_map: GameMap) -> None:
        """At meeting_tick=17, the audit temporal_window should be [0, 16] not [17, 17]."""
        from quack.evaluation.tier3_statement_verification import StatementVerificationPipeline
        events = build_minimal_game_events()
        timeline = GameReconstructor(events, simple_map).reconstruct()
        # Inject a second meeting at tick 17
        timeline.meeting_boundaries.append({
            "meeting_tick": 17,
            "meeting_type": "meeting_called",
            "resume_tick": 18,
            "preceding_free_roam_index": 1,
        })
        timeline.free_roam_segments.append({"start": 7, "end": 16})
        timeline.max_tick = 20

        pipeline = StatementVerificationPipeline.__new__(StatementVerificationPipeline)
        pipeline.timeline = timeline
        pipeline.game_map = simple_map
        pipeline.events = events
        pipeline.name_to_id = {"Alice": "player_0"}
        pipeline.id_to_name = {"player_0": "Alice"}
        pipeline.role_map = {"player_0": "goose"}
        pipeline.duck_ids = set()

        claim = {"type": "location", "subject": "Alice", "room": "cafeteria",
                 "temporal": "this round",
                 "_speaker_id": "player_0", "_speaker_name": "Alice",
                 "_meeting_idx": 1, "_meeting_tick": 17}
        meeting = {"tick": 17, "type": "meeting_called", "caller": "player_0"}
        result = pipeline._verify_claim(claim, 17)
        audit = pipeline._build_audit_entry(claim, meeting, 1, result)

        assert audit["temporal_window"]["start_tick"] == 7
        assert audit["temporal_window"]["end_tick"] == 16


class TestBackwardCompatibility:
    """Tests that existing evaluation output structure is preserved."""

    def test_tier3_metrics_to_dict_keys_unchanged(self) -> None:
        from quack.evaluation.tier3_statement_verification import Tier3Metrics
        metrics = Tier3Metrics()
        d = metrics.to_dict()
        expected_keys = {
            "total_claims", "verifiable_claims",
            "goose_truthfulness", "duck_truthfulness",
            "goose_false_claims", "goose_total_verifiable",
            "spatial_hallucination_rate",
            "duck_false_claims", "duck_near_miss_claims",
            "duck_total_verifiable", "deception_rate",
            "deception_sophistication",
            "total_accusations", "correct_accusations",
            "false_accusations", "accusation_accuracy",
            "meetings_with_duck_lies", "meetings_duck_caught_after_lie",
            "lie_detection_rate",
            "per_player_claims", "claim_type_distribution",
        }
        assert set(d.keys()) == expected_keys

    def test_evaluation_result_audit_path_in_to_dict(self) -> None:
        """EvaluationResult.to_dict includes tier3_audit_path when set."""
        from quack.evaluation.evaluator import EvaluationResult
        from quack.evaluation.tier3_statement_verification import Tier3Metrics
        result = EvaluationResult(
            game_id="test_game",
            log_path="/tmp/test/game.jsonl",
            tier3=Tier3Metrics(),
            tier3_audit_path="/tmp/test/tier3_claims.jsonl",
        )
        d = result.to_dict()
        assert "tier3" in d
        assert d["tier3"]["tier3_audit_path"] == "/tmp/test/tier3_claims.jsonl"

    def test_evaluation_result_no_audit_path_when_none(self) -> None:
        """EvaluationResult.to_dict omits tier3_audit_path when None."""
        from quack.evaluation.evaluator import EvaluationResult
        from quack.evaluation.tier3_statement_verification import Tier3Metrics
        result = EvaluationResult(
            game_id="test_game",
            log_path="/tmp/test/game.jsonl",
            tier3=Tier3Metrics(),
            tier3_audit_path=None,
        )
        d = result.to_dict()
        assert "tier3" in d
        assert "tier3_audit_path" not in d["tier3"]
