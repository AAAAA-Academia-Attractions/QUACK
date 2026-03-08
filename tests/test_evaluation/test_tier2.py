"""Tests for Tier 2 behavioral metrics."""

from __future__ import annotations

import pytest

from quack.evaluation.game_reconstructor import GameReconstructor
from quack.evaluation.tier2_behavioral import compute_tier2_metrics
from quack.map.game_map import GameMap

from .conftest import build_minimal_game_events


class TestTier2Metrics:
    @pytest.fixture
    def tier2_setup(self, simple_map: GameMap):
        events = build_minimal_game_events()
        timeline = GameReconstructor(events, simple_map).reconstruct()
        return events, timeline, simple_map

    def test_goose_voting_accuracy(self, tier2_setup) -> None:
        events, timeline, game_map = tier2_setup
        metrics = compute_tier2_metrics(events, timeline, game_map)
        # 3 goose votes for duck, 1 skip, so accuracy = 3/3 = 100%
        # (player_0 votes player_5, player_1 votes player_5, player_3 votes player_5)
        # player_2 skips
        assert metrics.goose_voting_accuracy == 1.0

    def test_goose_skip_rate(self, tier2_setup) -> None:
        events, timeline, game_map = tier2_setup
        metrics = compute_tier2_metrics(events, timeline, game_map)
        # 1 skip out of 4 goose votes = 25%
        assert abs(metrics.goose_skip_rate - 0.25) < 0.01

    def test_spatial_coverage(self, tier2_setup) -> None:
        events, timeline, game_map = tier2_setup
        metrics = compute_tier2_metrics(events, timeline, game_map)
        # Each player visits at least 1 room
        assert metrics.avg_rooms_visited_goose >= 1.0
        assert metrics.avg_rooms_visited_duck >= 1.0

    def test_avg_kills_per_game(self, tier2_setup) -> None:
        events, timeline, game_map = tier2_setup
        metrics = compute_tier2_metrics(events, timeline, game_map)
        assert metrics.avg_kills_per_game == 1.0

    def test_no_kills_game(self, simple_map: GameMap) -> None:
        events = build_minimal_game_events(include_kill=False, include_meeting=False)
        timeline = GameReconstructor(events, simple_map).reconstruct()
        metrics = compute_tier2_metrics(events, timeline, simple_map)
        assert metrics.avg_kills_per_game == 0.0
        assert metrics.post_kill_displacement == []
        assert metrics.self_report_rate == 0.0

    def test_to_dict(self, tier2_setup) -> None:
        events, timeline, game_map = tier2_setup
        metrics = compute_tier2_metrics(events, timeline, game_map)
        d = metrics.to_dict()
        assert isinstance(d, dict)
        assert "goose_voting_accuracy" in d
        assert "task_efficiency" in d
