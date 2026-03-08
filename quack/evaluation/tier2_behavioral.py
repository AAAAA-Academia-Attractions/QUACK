"""Tier 2: Behavioral metrics from spatial trajectory reconstruction."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from quack.evaluation.game_reconstructor import GameTimeline, hop_distance
from quack.evaluation.log_parser import (
    get_initial_state,
    get_player_role_map,
)
from quack.map.game_map import GameMap

logger = logging.getLogger(__name__)


@dataclass
class Tier2Metrics:
    """Behavioral and spatial metrics derived from game timeline reconstruction."""

    # Goose voting behavior
    goose_voting_accuracy: float = 0.0
    goose_skip_rate: float = 0.0

    # Report behavior
    avg_report_latency: float | None = None

    # Task efficiency (goose only)
    task_efficiency: float = 0.0

    # Spatial coverage
    avg_rooms_visited_goose: float = 0.0
    avg_rooms_visited_duck: float = 0.0

    # Duck-specific
    avg_kills_per_game: float = 0.0
    post_kill_displacement: list[float] = field(default_factory=list)
    avg_post_kill_displacement: float = 0.0
    self_report_count: int = 0
    self_report_rate: float = 0.0

    # Duck kill timing
    cooldown_utilization: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dict."""
        return {
            "goose_voting_accuracy": self.goose_voting_accuracy,
            "goose_skip_rate": self.goose_skip_rate,
            "avg_report_latency": self.avg_report_latency,
            "task_efficiency": self.task_efficiency,
            "avg_rooms_visited_goose": self.avg_rooms_visited_goose,
            "avg_rooms_visited_duck": self.avg_rooms_visited_duck,
            "avg_kills_per_game": self.avg_kills_per_game,
            "post_kill_displacement": self.post_kill_displacement,
            "avg_post_kill_displacement": self.avg_post_kill_displacement,
            "self_report_count": self.self_report_count,
            "self_report_rate": self.self_report_rate,
            "cooldown_utilization": self.cooldown_utilization,
        }


def compute_tier2_metrics(
    events: list[dict[str, Any]],
    timeline: GameTimeline,
    game_map: GameMap,
) -> Tier2Metrics:
    """Compute all Tier 2 behavioral metrics."""
    metrics = Tier2Metrics()
    initial_state = get_initial_state(events)
    role_map = get_player_role_map(events)

    duck_ids = [pid for pid, team in role_map.items() if team == "duck"]
    goose_ids = [pid for pid, team in role_map.items() if team == "goose"]

    _compute_voting_metrics(events, role_map, duck_ids, goose_ids, metrics)
    _compute_report_latency(events, timeline, role_map, duck_ids, metrics)
    _compute_task_efficiency(events, timeline, initial_state, goose_ids, game_map, metrics)
    _compute_spatial_coverage(timeline, goose_ids, duck_ids, metrics)
    _compute_kill_metrics(events, timeline, game_map, duck_ids, metrics)
    _compute_cooldown_utilization(events, timeline, initial_state, duck_ids, goose_ids, metrics)
    _compute_self_reports(events, duck_ids, metrics)

    return metrics


def _compute_voting_metrics(
    events: list[dict[str, Any]],
    role_map: dict[str, str],
    duck_ids: list[str],
    goose_ids: list[str],
    metrics: Tier2Metrics,
) -> None:
    """Compute goose voting accuracy and skip rate."""
    goose_votes_total = 0
    goose_votes_for_duck = 0
    goose_skips = 0

    duck_set = set(duck_ids)
    goose_set = set(goose_ids)

    for event in events:
        if event.get("event_type") != "vote_cast":
            continue
        data = event["data"]
        voter = data.get("voter", "")
        target = data.get("target")

        if voter not in goose_set:
            continue

        goose_votes_total += 1
        if target is None:
            goose_skips += 1
        elif target in duck_set:
            goose_votes_for_duck += 1

    non_skip_votes = goose_votes_total - goose_skips
    metrics.goose_voting_accuracy = (
        goose_votes_for_duck / non_skip_votes if non_skip_votes > 0 else 0.0
    )
    metrics.goose_skip_rate = (
        goose_skips / goose_votes_total if goose_votes_total > 0 else 0.0
    )


def _compute_report_latency(
    events: list[dict[str, Any]],
    timeline: GameTimeline,
    role_map: dict[str, str],
    duck_ids: list[str],
    metrics: Tier2Metrics,
) -> None:
    """Compute average ticks between body appearing and goose reporting it."""
    duck_set = set(duck_ids)

    # Collect kill events and body_reported events
    kills: list[dict[str, Any]] = []
    reports: list[dict[str, Any]] = []
    for event in events:
        if event["event_type"] == "player_killed":
            kills.append(event)
        elif event["event_type"] == "body_reported":
            reports.append(event)

    latencies: list[int] = []
    for report_event in reports:
        report_tick = report_event["tick"]
        caller = report_event["data"].get("caller", "")

        # Skip duck self-reports for this metric
        if caller in duck_set:
            continue

        # Find bodies that existed at report time
        for kill in kills:
            kill_tick = kill["tick"]
            kill_room = kill["data"]["room"]
            if kill_tick > report_tick:
                continue

            # Check if the reporter was in the kill room at any tick
            # between the kill and the report
            reporter_entered_tick = None
            for t in range(kill_tick, report_tick + 1):
                r = timeline.get_player_room(caller, t)
                if r == kill_room:
                    reporter_entered_tick = t
                    break

            if reporter_entered_tick is not None:
                latency = report_tick - max(kill_tick, reporter_entered_tick)
                latencies.append(latency)

    metrics.avg_report_latency = (
        sum(latencies) / len(latencies) if latencies else None
    )


def _compute_task_efficiency(
    events: list[dict[str, Any]],
    timeline: GameTimeline,
    initial_state: dict[str, Any],
    goose_ids: list[str],
    game_map: GameMap,
    metrics: Tier2Metrics,
) -> None:
    """Compute fraction of goose free-roam ticks spent productively.

    Productive = doing a task OR moving toward a room with an incomplete task.
    """
    # Build per-player incomplete task rooms at each tick
    # Track task completions chronologically
    task_completions: list[tuple[int, str, str]] = []  # (tick, player_id, task_name)
    for event in events:
        if event["event_type"] == "task_completed":
            d = event["data"]
            task_completions.append((event["tick"], d["player_id"], d["task_name"]))

    productive_ticks = 0
    total_free_roam_ticks = 0

    for pid in goose_ids:
        # Build the list of this goose's incomplete task rooms over time
        task_rooms = set()
        for task_info in initial_state[pid].get("tasks", []):
            task_rooms.add(task_info["room"])

        completed_tasks: set[str] = set()

        states = timeline.player_timelines.get(pid, [])
        for tick in range(1, len(states)):
            s = states[tick]
            if not s.is_alive:
                continue
            if not s.action or s.action == "":
                continue  # Not in free-roam

            total_free_roam_ticks += 1

            # Update completed tasks up to this tick
            for ct_tick, ct_pid, ct_name in task_completions:
                if ct_pid == pid and ct_tick <= tick and ct_name not in completed_tasks:
                    completed_tasks.add(ct_name)

            # Rebuild incomplete task rooms for this tick
            incomplete_rooms = set()
            for task_info in initial_state[pid].get("tasks", []):
                if task_info["name"] not in completed_tasks:
                    incomplete_rooms.add(task_info["room"])

            if s.action == "do_task()":
                productive_ticks += 1
            elif s.action.startswith("move("):
                target_room = s.action[5:-1]
                if target_room in incomplete_rooms:
                    productive_ticks += 1
                elif incomplete_rooms:
                    # Check if target is on shortest path to any incomplete task room
                    current_room = s.room
                    for task_room in incomplete_rooms:
                        path = game_map.shortest_path(current_room, task_room)
                        if path and len(path) > 1 and path[1] == target_room:
                            productive_ticks += 1
                            break

    metrics.task_efficiency = (
        productive_ticks / total_free_roam_ticks
        if total_free_roam_ticks > 0
        else 0.0
    )


def _compute_spatial_coverage(
    timeline: GameTimeline,
    goose_ids: list[str],
    duck_ids: list[str],
    metrics: Tier2Metrics,
) -> None:
    """Compute average distinct rooms visited per player per role."""
    goose_rooms: list[int] = []
    duck_rooms: list[int] = []

    for pid in goose_ids:
        states = timeline.player_timelines.get(pid, [])
        visited = {s.room for s in states if not s.in_transit}
        visited.discard("unknown")
        goose_rooms.append(len(visited))

    for pid in duck_ids:
        states = timeline.player_timelines.get(pid, [])
        visited = {s.room for s in states if not s.in_transit}
        visited.discard("unknown")
        duck_rooms.append(len(visited))

    metrics.avg_rooms_visited_goose = (
        sum(goose_rooms) / len(goose_rooms) if goose_rooms else 0.0
    )
    metrics.avg_rooms_visited_duck = (
        sum(duck_rooms) / len(duck_rooms) if duck_rooms else 0.0
    )


def _compute_kill_metrics(
    events: list[dict[str, Any]],
    timeline: GameTimeline,
    game_map: GameMap,
    duck_ids: list[str],
    metrics: Tier2Metrics,
) -> None:
    """Compute kill count, post-kill displacement, and self-report rate."""
    kill_events = [e for e in events if e["event_type"] == "player_killed"]
    metrics.avg_kills_per_game = len(kill_events) / max(len(duck_ids), 1)

    displacements: list[float] = []
    for kill in kill_events:
        tick = kill["tick"]
        killer_id = kill["data"]["killer_id"]
        kill_room = kill["data"]["room"]

        target_tick = tick + 3
        if target_tick > timeline.max_tick:
            target_tick = timeline.max_tick

        killer_room = timeline.get_player_room(killer_id, target_tick)
        if killer_room and killer_room != "unknown":
            dist = hop_distance(game_map, kill_room, killer_room)
            if dist >= 0:
                displacements.append(float(dist))

    metrics.post_kill_displacement = displacements
    metrics.avg_post_kill_displacement = (
        sum(displacements) / len(displacements) if displacements else 0.0
    )


def _compute_self_reports(
    events: list[dict[str, Any]],
    duck_ids: list[str],
    metrics: Tier2Metrics,
) -> None:
    """Count kills where the duck reported its own body."""
    duck_set = set(duck_ids)
    kill_events = [e for e in events if e["event_type"] == "player_killed"]
    report_events = [e for e in events if e["event_type"] == "body_reported"]

    # Build a map: victim_id -> killer_id for all kills
    kill_map: dict[str, str] = {}
    for kill in kill_events:
        kill_map[kill["data"]["target_id"]] = kill["data"]["killer_id"]

    total_kills = len(kill_events)
    self_reports = 0

    for report in report_events:
        caller = report["data"].get("caller", "")
        if caller not in duck_set:
            continue
        # Check if any of the reported bodies were killed by this duck
        bodies = report["data"].get("bodies", [])
        for body in bodies:
            victim_name = body.get("victim_name", "")
            # Need to map victim name back to ID
            for vid, kid in kill_map.items():
                if kid == caller:
                    self_reports += 1
                    break

    metrics.self_report_count = self_reports
    metrics.self_report_rate = self_reports / total_kills if total_kills > 0 else 0.0


def _compute_cooldown_utilization(
    events: list[dict[str, Any]],
    timeline: GameTimeline,
    initial_state: dict[str, Any],
    duck_ids: list[str],
    goose_ids: list[str],
    metrics: Tier2Metrics,
) -> None:
    """Compute fraction of kill opportunities the duck did not take.

    An opportunity = tick where cooldown=0 AND at least one goose is in the same room.
    """
    if not duck_ids:
        return

    # Get config values from game_started
    kill_config_cooldown = 5
    initial_cooldown = 5
    for event in events:
        if event["event_type"] == "game_started":
            config = event["data"].get("config", {})
            break

    kill_events = [e for e in events if e["event_type"] == "player_killed"]
    kill_ticks = {e["tick"]: e["data"]["killer_id"] for e in kill_events}
    goose_set = set(goose_ids)

    total_opportunities = 0
    kills_taken = 0

    for duck_id in duck_ids:
        cooldown = initial_cooldown

        for tick in range(1, timeline.max_tick + 1):
            duck_state = timeline.get_player_state(duck_id, tick)
            if not duck_state or not duck_state.is_alive:
                break
            if duck_state.in_transit or duck_state.action == "":
                # Not in free-roam or in transit — cooldown still ticks
                if cooldown > 0:
                    cooldown -= 1
                continue

            # Tick cooldown
            if cooldown > 0:
                cooldown -= 1

            if cooldown == 0:
                # Check if any alive goose is in the same room
                room = duck_state.room
                goose_present = False
                for gid in goose_set:
                    gs = timeline.get_player_state(gid, tick)
                    if gs and gs.is_alive and gs.room == room and not gs.in_transit:
                        goose_present = True
                        break

                if goose_present:
                    total_opportunities += 1
                    if tick in kill_ticks and kill_ticks[tick] == duck_id:
                        kills_taken += 1
                        cooldown = kill_config_cooldown

    if total_opportunities > 0:
        metrics.cooldown_utilization = (
            (total_opportunities - kills_taken) / total_opportunities
        )
    else:
        metrics.cooldown_utilization = 0.0
