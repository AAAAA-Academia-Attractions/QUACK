"""Tier 1: Game-level metrics computed directly from engine events."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from quack.evaluation.log_parser import get_initial_state, get_player_role_map

logger = logging.getLogger(__name__)


@dataclass
class Tier1Metrics:
    """Game-level outcome and summary metrics."""

    # Game outcome
    winner: str = ""  # "goose" | "duck" | "timeout"
    win_reason: str = ""
    game_duration_ticks: int = 0

    # Roles
    duck_player_ids: list[str] = field(default_factory=list)
    duck_player_names: list[str] = field(default_factory=list)
    goose_player_ids: list[str] = field(default_factory=list)
    goose_player_names: list[str] = field(default_factory=list)

    # Tasks
    tasks_completed: int = 0
    tasks_total: int = 0
    task_completion_rate: float = 0.0

    # Kills
    total_kills: int = 0
    kill_events: list[dict[str, Any]] = field(default_factory=list)
    avg_inter_kill_interval: float | None = None
    first_kill_tick: int | None = None

    # Meetings
    total_meetings: int = 0
    body_report_meetings: int = 0
    emergency_meetings: int = 0

    # Ejections
    total_ejections: int = 0
    correct_ejections: int = 0
    wrong_ejections: int = 0
    no_ejection_votes: int = 0
    ejection_accuracy: float = 0.0

    # Survival
    final_alive_count: int = 0
    final_alive_geese: int = 0
    final_alive_ducks: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dict."""
        return {
            "winner": self.winner,
            "win_reason": self.win_reason,
            "game_duration_ticks": self.game_duration_ticks,
            "duck_player_ids": self.duck_player_ids,
            "duck_player_names": self.duck_player_names,
            "goose_player_ids": self.goose_player_ids,
            "goose_player_names": self.goose_player_names,
            "tasks_completed": self.tasks_completed,
            "tasks_total": self.tasks_total,
            "task_completion_rate": self.task_completion_rate,
            "total_kills": self.total_kills,
            "kill_events": self.kill_events,
            "avg_inter_kill_interval": self.avg_inter_kill_interval,
            "first_kill_tick": self.first_kill_tick,
            "total_meetings": self.total_meetings,
            "body_report_meetings": self.body_report_meetings,
            "emergency_meetings": self.emergency_meetings,
            "total_ejections": self.total_ejections,
            "correct_ejections": self.correct_ejections,
            "wrong_ejections": self.wrong_ejections,
            "no_ejection_votes": self.no_ejection_votes,
            "ejection_accuracy": self.ejection_accuracy,
            "final_alive_count": self.final_alive_count,
            "final_alive_geese": self.final_alive_geese,
            "final_alive_ducks": self.final_alive_ducks,
        }


def compute_tier1_metrics(events: list[dict[str, Any]]) -> Tier1Metrics:
    """Compute all Tier 1 metrics from a parsed event list."""
    metrics = Tier1Metrics()
    initial_state = get_initial_state(events)
    role_map = get_player_role_map(events)

    # Roles
    for pid, info in initial_state.items():
        if info["team"] == "duck":
            metrics.duck_player_ids.append(pid)
            metrics.duck_player_names.append(info["name"])
        else:
            metrics.goose_player_ids.append(pid)
            metrics.goose_player_names.append(info["name"])

    # Tasks total: count all goose tasks
    for pid, info in initial_state.items():
        if info["team"] == "goose":
            metrics.tasks_total += len(info.get("tasks", []))

    # Track alive status
    alive: dict[str, bool] = {pid: True for pid in initial_state}
    kill_ticks: list[int] = []

    for event in events:
        et = event.get("event_type", "")
        data = event.get("data", {})
        tick = event.get("tick", 0)

        if et == "task_completed":
            pid = data.get("player_id", "")
            if role_map.get(pid) == "goose":
                metrics.tasks_completed += 1

        elif et == "player_killed":
            metrics.total_kills += 1
            kill_ticks.append(tick)
            kill_entry = {
                "tick": tick,
                "killer_id": data.get("killer_id", ""),
                "target_id": data.get("target_id", ""),
                "room": data.get("room", ""),
            }
            metrics.kill_events.append(kill_entry)
            target_id = data.get("target_id", "")
            alive[target_id] = False

        elif et == "body_reported":
            metrics.total_meetings += 1
            metrics.body_report_meetings += 1

        elif et == "meeting_called":
            metrics.total_meetings += 1
            metrics.emergency_meetings += 1

        elif et == "player_ejected":
            metrics.total_ejections += 1
            ejected_pid = data.get("player_id", "")
            ejected_team = data.get("team", "")
            alive[ejected_pid] = False
            if ejected_team == "duck":
                metrics.correct_ejections += 1
            else:
                metrics.wrong_ejections += 1

        elif et == "vote_skipped":
            metrics.no_ejection_votes += 1

        elif et == "game_over":
            winner = data.get("winner", "")
            reason = data.get("reason", "")
            metrics.winner = winner if winner else "timeout"
            metrics.win_reason = reason
            metrics.game_duration_ticks = tick

    # If no game_over event, infer outcome from final state
    if metrics.game_duration_ticks == 0:
        max_tick = max((e.get("tick", 0) for e in events), default=0)
        metrics.game_duration_ticks = max_tick
        if not metrics.winner:
            # Infer winner: if all ducks dead → goose win; otherwise check alive counts
            duck_alive = sum(1 for pid in metrics.duck_player_ids if alive.get(pid, False))
            goose_alive = sum(1 for pid in metrics.goose_player_ids if alive.get(pid, False))
            if duck_alive == 0:
                metrics.winner = "goose"
                metrics.win_reason = "All Ducks have been ejected (inferred)"
            elif duck_alive >= goose_alive:
                metrics.winner = "duck"
                metrics.win_reason = "Ducks have voting majority (inferred)"
            else:
                metrics.winner = "timeout"
                metrics.win_reason = "No game_over event — assumed timeout"

    # Task completion rate
    if metrics.tasks_total > 0:
        metrics.task_completion_rate = metrics.tasks_completed / metrics.tasks_total

    # Kill timing
    if kill_ticks:
        metrics.first_kill_tick = kill_ticks[0]
        if len(kill_ticks) > 1:
            intervals = [
                kill_ticks[i] - kill_ticks[i - 1]
                for i in range(1, len(kill_ticks))
            ]
            metrics.avg_inter_kill_interval = sum(intervals) / len(intervals)

    # Ejection accuracy
    if metrics.total_ejections > 0:
        metrics.ejection_accuracy = metrics.correct_ejections / metrics.total_ejections

    # Final alive counts
    for pid, is_alive in alive.items():
        if is_alive:
            metrics.final_alive_count += 1
            if role_map.get(pid) == "goose":
                metrics.final_alive_geese += 1
            else:
                metrics.final_alive_ducks += 1

    return metrics
