"""Reconstruct tick-by-tick game state from event logs.

Produces a GameTimeline that answers spatial queries like
"where was player X at tick T?" and "who was in room R at tick T?"
"""

from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass, field
from typing import Any

from quack.evaluation.log_parser import get_initial_state
from quack.map.game_map import GameMap

logger = logging.getLogger(__name__)


@dataclass
class PlayerTickState:
    """Snapshot of a single player's state at one tick."""

    tick: int
    room: str
    in_transit: bool = False
    moving_to: str | None = None
    is_alive: bool = True
    action: str = ""


class GameTimeline:
    """Tick-by-tick reconstruction of the full game state.

    Provides efficient spatial queries over the entire game history.
    """

    def __init__(self) -> None:
        self.player_timelines: dict[str, list[PlayerTickState]] = {}
        self.max_tick: int = 0
        self.player_names: dict[str, str] = {}
        self.player_teams: dict[str, str] = {}
        self.meeting_boundaries: list[dict[str, Any]] = []
        self.free_roam_segments: list[dict[str, int]] = []

    def get_player_room(self, player_id: str, tick: int) -> str | None:
        """Return the room a player was in at a given tick, or None if unknown."""
        states = self.player_timelines.get(player_id)
        if not states or tick < 0 or tick >= len(states):
            return None
        return states[tick].room

    def get_player_state(self, player_id: str, tick: int) -> PlayerTickState | None:
        """Return the full PlayerTickState at a given tick."""
        states = self.player_timelines.get(player_id)
        if not states or tick < 0 or tick >= len(states):
            return None
        return states[tick]

    def get_players_in_room(self, room: str, tick: int, alive_only: bool = True) -> list[str]:
        """Return all player IDs in a given room at a given tick."""
        result = []
        for pid, states in self.player_timelines.items():
            if tick < 0 or tick >= len(states):
                continue
            s = states[tick]
            if s.room == room and not s.in_transit:
                if not alive_only or s.is_alive:
                    result.append(pid)
        return result

    def were_in_same_room(self, pid1: str, pid2: str, tick: int) -> bool:
        """Check if two players were in the same room at a given tick."""
        r1 = self.get_player_room(pid1, tick)
        r2 = self.get_player_room(pid2, tick)
        if r1 is None or r2 is None:
            return False
        s1 = self.get_player_state(pid1, tick)
        s2 = self.get_player_state(pid2, tick)
        if s1 is None or s2 is None:
            return False
        if s1.in_transit or s2.in_transit:
            return False
        return r1 == r2

    def get_room_sequence(self, player_id: str, start_tick: int, end_tick: int) -> list[str]:
        """Return the sequence of rooms a player was in over a tick range."""
        states = self.player_timelines.get(player_id, [])
        result = []
        for t in range(start_tick, min(end_tick + 1, len(states))):
            result.append(states[t].room)
        return result

    def is_alive(self, player_id: str, tick: int) -> bool:
        """Check if a player was alive at a given tick."""
        s = self.get_player_state(player_id, tick)
        return s.is_alive if s else False

    def get_round_boundaries(self) -> list[tuple[int, int]]:
        """Return (start_tick, end_tick) pairs for each free-roam round.

        A round is the free-roam period between meetings (or game start to
        first meeting, or last meeting to game end).
        """
        if not self.free_roam_segments:
            return [(0, self.max_tick)]
        return [(seg["start"], seg["end"]) for seg in self.free_roam_segments]


def hop_distance(game_map: GameMap, room_a: str, room_b: str) -> int:
    """Compute unweighted shortest distance (number of hops) between two rooms.

    Returns -1 if rooms are not connected.
    """
    if room_a == room_b:
        return 0
    visited = {room_a}
    queue: deque[tuple[str, int]] = deque([(room_a, 0)])
    while queue:
        current, dist = queue.popleft()
        for neighbor in game_map.get_neighbors(current):
            if neighbor == room_b:
                return dist + 1
            if neighbor not in visited:
                visited.add(neighbor)
                queue.append((neighbor, dist + 1))
    return -1


@dataclass
class _TransitInfo:
    """Internal tracker for multi-tick travel."""

    moving_to: str
    ticks_remaining: int


class GameReconstructor:
    """Processes event logs to build a complete GameTimeline.

    Handles multi-tick travel, post-meeting respawns, kills, ejections,
    and infers player positions when explicit events are absent.
    """

    def __init__(self, events: list[dict[str, Any]], game_map: GameMap) -> None:
        self.events = events
        self.game_map = game_map

    def reconstruct(self) -> GameTimeline:
        """Build the full game timeline from events."""
        timeline = GameTimeline()
        initial_state = get_initial_state(self.events)

        player_ids = list(initial_state.keys())
        name_map = {pid: info["name"] for pid, info in initial_state.items()}
        team_map = {pid: info["team"] for pid, info in initial_state.items()}
        timeline.player_names = name_map
        timeline.player_teams = team_map

        max_tick = self._find_max_tick()
        timeline.max_tick = max_tick

        current_room: dict[str, str] = {}
        is_alive: dict[str, bool] = {}
        transit: dict[str, _TransitInfo] = {}
        actions_this_tick: dict[str, str] = {}

        for pid, info in initial_state.items():
            current_room[pid] = info["room"]
            is_alive[pid] = True
            timeline.player_timelines[pid] = []

        # Tick 0 state (initial positions before any action)
        for pid in player_ids:
            timeline.player_timelines[pid].append(PlayerTickState(
                tick=0,
                room=current_room[pid],
                in_transit=False,
                moving_to=None,
                is_alive=True,
                action="",
            ))

        events_by_tick = self._group_events_by_tick()
        phase = "free_roam"
        free_roam_segment_start = 0
        post_meeting_respawn_pending = False

        for tick in range(1, max_tick + 1):
            # Advance transit at start of tick (mirrors engine behavior)
            arrived = []
            for pid, ti in list(transit.items()):
                ti.ticks_remaining -= 1
                if ti.ticks_remaining <= 0:
                    current_room[pid] = ti.moving_to
                    arrived.append(pid)
            for pid in arrived:
                del transit[pid]

            actions_this_tick.clear()
            tick_events = events_by_tick.get(tick, [])

            for event in tick_events:
                et = event["event_type"]
                data = event["data"]

                if et == "player_moved":
                    pid = data["player_id"]
                    if not is_alive.get(pid, False):
                        continue
                    ticks_remaining = data.get("ticks_remaining", 0)
                    if ticks_remaining and ticks_remaining > 0:
                        current_room[pid] = data["from"]
                        transit[pid] = _TransitInfo(
                            moving_to=data["to"],
                            ticks_remaining=ticks_remaining,
                        )
                        actions_this_tick[pid] = f"move({data['to']})"
                    else:
                        current_room[pid] = data["to"]
                        if pid in transit:
                            del transit[pid]
                        actions_this_tick[pid] = f"move({data['to']})"
                    if post_meeting_respawn_pending:
                        # First move after respawn reveals spawn position in 'from'
                        # (already handled by the event data)
                        pass

                elif et == "player_killed":
                    target_id = data["target_id"]
                    is_alive[target_id] = False
                    killer_id = data["killer_id"]
                    actions_this_tick[killer_id] = f"kill({target_id})"

                elif et == "task_progress":
                    pid = data["player_id"]
                    actions_this_tick.setdefault(pid, "do_task()")
                    # Infer room from task event
                    if data.get("room"):
                        current_room[pid] = data["room"]

                elif et == "task_completed":
                    pid = data["player_id"]
                    actions_this_tick.setdefault(pid, "do_task()")
                    if data.get("room"):
                        current_room[pid] = data["room"]

                elif et in ("body_reported", "meeting_called"):
                    caller = data.get("caller", "")
                    if et == "body_reported":
                        actions_this_tick.setdefault(caller, "report()")
                    else:
                        actions_this_tick.setdefault(caller, "call_meeting()")
                    phase = "discussion"
                    # Cancel all transit
                    transit.clear()
                    meeting_tick = tick
                    # Record the preceding free-roam segment
                    if tick - 1 >= free_roam_segment_start:
                        timeline.free_roam_segments.append({
                            "start": free_roam_segment_start,
                            "end": tick - 1,
                        })
                    preceding_idx = len(timeline.free_roam_segments) - 1 if timeline.free_roam_segments else None
                    timeline.meeting_boundaries.append({
                        "meeting_tick": meeting_tick,
                        "meeting_type": et,
                        "resume_tick": None,
                        "preceding_free_roam_index": preceding_idx,
                    })

                elif et == "player_ejected":
                    ejected_pid = data.get("player_id", "")
                    is_alive[ejected_pid] = False
                    post_meeting_respawn_pending = True

                elif et == "vote_skipped":
                    post_meeting_respawn_pending = True

                elif et == "phase_changed":
                    new_phase = data.get("phase", "")
                    if new_phase == "free_roam" and phase != "free_roam":
                        phase = "free_roam"
                        post_meeting_respawn_pending = True
                        # Mark positions as potentially unknown after respawn
                        # Positions will be inferred from next events
                        if timeline.meeting_boundaries:
                            timeline.meeting_boundaries[-1]["resume_tick"] = tick
                        free_roam_segment_start = tick
                    else:
                        phase = new_phase

                elif et == "free_roam_chat":
                    pid = data.get("player_id", "")
                    if data.get("room") and pid:
                        current_room[pid] = data["room"]

            # Build tick state for each player
            for pid in player_ids:
                in_transit = pid in transit
                room = current_room.get(pid, "unknown")
                action = actions_this_tick.get(pid, "")
                if phase == "free_roam" and not action and is_alive.get(pid, False):
                    action = "wait()"
                elif phase != "free_roam":
                    action = ""

                timeline.player_timelines[pid].append(PlayerTickState(
                    tick=tick,
                    room=room,
                    in_transit=in_transit,
                    moving_to=transit[pid].moving_to if in_transit else None,
                    is_alive=is_alive.get(pid, False),
                    action=action,
                ))

        # Record the final free-roam segment (after last meeting to game end)
        if phase == "free_roam" and free_roam_segment_start <= max_tick:
            timeline.free_roam_segments.append({
                "start": free_roam_segment_start,
                "end": max_tick,
            })

        # Fill in resume_tick for any meetings that didn't get one
        for mb in timeline.meeting_boundaries:
            if mb["resume_tick"] is None:
                mb["resume_tick"] = max_tick

        return timeline

    def _find_max_tick(self) -> int:
        """Find the maximum tick number in the event log."""
        max_tick = 0
        for event in self.events:
            tick = event.get("tick", 0)
            if tick > max_tick:
                max_tick = tick
        return max_tick

    def _group_events_by_tick(self) -> dict[int, list[dict[str, Any]]]:
        """Group events by their tick number, preserving order within each tick."""
        groups: dict[int, list[dict[str, Any]]] = {}
        for event in self.events:
            tick = event.get("tick", 0)
            groups.setdefault(tick, []).append(event)
        return groups
