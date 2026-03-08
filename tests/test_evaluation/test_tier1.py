"""Tests for Tier 1 game-level metrics."""

from __future__ import annotations

from quack.evaluation.tier1_game_metrics import compute_tier1_metrics

from .conftest import build_minimal_game_events


class TestTier1Metrics:
    def test_winner(self, minimal_game_events) -> None:
        metrics = compute_tier1_metrics(minimal_game_events)
        assert metrics.winner == "goose"
        assert "ejected" in metrics.win_reason.lower()

    def test_game_duration(self, minimal_game_events) -> None:
        metrics = compute_tier1_metrics(minimal_game_events)
        assert metrics.game_duration_ticks == 10

    def test_roles(self, minimal_game_events) -> None:
        metrics = compute_tier1_metrics(minimal_game_events)
        assert len(metrics.duck_player_ids) == 1
        assert "player_5" in metrics.duck_player_ids
        assert "Frank" in metrics.duck_player_names
        assert len(metrics.goose_player_ids) == 5

    def test_kills(self, minimal_game_events) -> None:
        metrics = compute_tier1_metrics(minimal_game_events)
        assert metrics.total_kills == 1
        assert metrics.first_kill_tick == 5
        assert len(metrics.kill_events) == 1
        assert metrics.kill_events[0]["killer_id"] == "player_5"

    def test_meetings(self, minimal_game_events) -> None:
        metrics = compute_tier1_metrics(minimal_game_events)
        assert metrics.total_meetings == 1
        assert metrics.body_report_meetings == 1
        assert metrics.emergency_meetings == 0

    def test_ejections(self, minimal_game_events) -> None:
        metrics = compute_tier1_metrics(minimal_game_events)
        assert metrics.total_ejections == 1
        assert metrics.correct_ejections == 1
        assert metrics.wrong_ejections == 0
        assert metrics.ejection_accuracy == 1.0

    def test_task_counting(self, minimal_game_events) -> None:
        metrics = compute_tier1_metrics(minimal_game_events)
        # 5 geese * 5 tasks each = 25 total
        assert metrics.tasks_total == 25

    def test_survival(self, minimal_game_events) -> None:
        metrics = compute_tier1_metrics(minimal_game_events)
        assert metrics.final_alive_ducks == 0
        assert metrics.final_alive_geese == 4  # Eve was killed

    def test_no_kills_game(self) -> None:
        events = build_minimal_game_events(num_ticks=5, include_kill=False, include_meeting=False)
        metrics = compute_tier1_metrics(events)
        assert metrics.total_kills == 0
        assert metrics.first_kill_tick is None
        assert metrics.avg_inter_kill_interval is None

    def test_to_dict(self, minimal_game_events) -> None:
        metrics = compute_tier1_metrics(minimal_game_events)
        d = metrics.to_dict()
        assert isinstance(d, dict)
        assert d["winner"] == "goose"
        assert "duck_player_ids" in d

    def test_inter_kill_interval_single_kill(self, minimal_game_events) -> None:
        metrics = compute_tier1_metrics(minimal_game_events)
        assert metrics.avg_inter_kill_interval is None  # Only 1 kill
