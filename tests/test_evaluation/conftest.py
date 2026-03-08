"""Shared test fixtures for evaluation tests."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

import pytest

from quack.map.game_map import GameMap, Room


@pytest.fixture
def simple_map() -> GameMap:
    """Build a minimal test map matching the simple_ship layout."""
    gm = GameMap()
    rooms = [
        Room("cafeteria", 7, 1, 3, False, "", True),
        Room("oxygen", 1, 1, 2, True, "Clean O2 Filter"),
        Room("weapons", 13, 1, 2, True, "Clear Asteroids"),
        Room("upper_engine", 1, 5, 2, True, "Align Engine Output"),
        Room("medbay", 5, 5, 2, True, "Submit Scan"),
        Room("electrical", 9, 5, 2, True, "Calibrate Distributor"),
        Room("security", 13, 5, 2, True, "Check Cameras"),
        Room("lower_engine", 1, 9, 2, True, "Fuel Engines"),
        Room("storage", 7, 9, 3, True, "Sort Cargo"),
        Room("navigation", 13, 9, 2, True, "Chart Course"),
    ]
    for r in rooms:
        gm.add_room(r)

    corridors = [
        ("oxygen", "cafeteria", 2),
        ("cafeteria", "weapons", 2),
        ("oxygen", "upper_engine", 1),
        ("upper_engine", "lower_engine", 2),
        ("cafeteria", "medbay", 1),
        ("cafeteria", "electrical", 2),
        ("medbay", "electrical", 1),
        ("medbay", "storage", 2),
        ("weapons", "security", 1),
        ("electrical", "security", 2),
        ("security", "navigation", 2),
        ("lower_engine", "storage", 2),
        ("storage", "navigation", 3),
        ("upper_engine", "medbay", 2),
    ]
    for a, b, w in corridors:
        gm.add_corridor(a, b, w)
    return gm


def make_event(event_type: str, tick: int, data: dict[str, Any]) -> dict[str, Any]:
    """Create a test event dict."""
    return {
        "timestamp": 1000000.0 + tick,
        "event_type": event_type,
        "tick": tick,
        "data": data,
    }


def build_minimal_game_events(
    num_ticks: int = 10,
    include_kill: bool = True,
    include_meeting: bool = True,
    include_tasks: bool = True,
) -> list[dict[str, Any]]:
    """Build a complete minimal game event log for testing.

    Creates a 6-player game: 5 geese + 1 duck (player_5 = duck).
    """
    events: list[dict[str, Any]] = []
    rooms = ["cafeteria", "medbay", "electrical", "weapons", "security", "oxygen"]

    initial_state = {}
    for i in range(6):
        pid = f"player_{i}"
        name = ["Alice", "Bob", "Charlie", "Diana", "Eve", "Frank"][i]
        team = "duck" if i == 5 else "goose"
        role = "Duck" if i == 5 else "Goose"
        tasks = [
            {"name": f"Task_{j}", "room": rooms[(i + j) % len(rooms)], "ticks_required": 3}
            for j in range(5)
        ] if team == "goose" else [
            {"name": f"FakeTask_{j}", "room": rooms[(i + j) % len(rooms)], "ticks_required": 3}
            for j in range(5)
        ]
        initial_state[pid] = {
            "name": name,
            "role": role,
            "team": team,
            "room": rooms[i % len(rooms)],
            "tasks": tasks,
        }

    events.append(make_event("game_started", 0, {
        "players": ["Alice", "Bob", "Charlie", "Diana", "Eve", "Frank"],
        "config": {"num_players": 6, "num_ducks": 1, "map": "configs/maps/simple_ship.yaml"},
        "initial_state": initial_state,
    }))

    current_rooms = {f"player_{i}": rooms[i % len(rooms)] for i in range(6)}

    for tick in range(1, num_ticks + 1):
        events.append(make_event("tick_start", tick, {"tick": tick}))

        # Tick 3: Alice moves from cafeteria to medbay
        if tick == 3:
            events.append(make_event("player_moved", tick, {
                "player_id": "player_0",
                "from": "cafeteria",
                "to": "medbay",
            }))
            current_rooms["player_0"] = "medbay"

        # Tick 4: Bob does a task
        if tick == 4 and include_tasks:
            events.append(make_event("task_progress", tick, {
                "player_id": "player_1",
                "task_name": "Task_0",
                "room": "medbay",
                "progress": "1/3",
            }))

        # Tick 5: Frank (duck) kills Eve in security
        if tick == 5 and include_kill:
            current_rooms["player_5"] = "security"
            current_rooms["player_4"] = "security"
            events.append(make_event("player_moved", tick, {
                "player_id": "player_5",
                "from": "oxygen",
                "to": "security",
            }))
            events.append(make_event("player_killed", tick, {
                "killer_id": "player_5",
                "target_id": "player_4",
                "room": "security",
            }))

        # Tick 7: Body reported, discussion, voting
        if tick == 7 and include_kill and include_meeting:
            events.append(make_event("body_reported", tick, {
                "caller": "player_0",
                "reason": "Alice reported a dead body",
                "bodies": [{"room": "security", "victim_name": "Eve"}],
            }))
            events.append(make_event("phase_changed", tick, {"phase": "discussion"}))
            events.append(make_event("discussion_message", tick, {
                "player_id": "player_0",
                "message": "I found Eve's body in security!",
            }))
            events.append(make_event("discussion_message", tick, {
                "player_id": "player_5",
                "message": "I was in electrical the whole time doing tasks.",
            }))
            events.append(make_event("phase_changed", tick, {"phase": "voting"}))
            events.append(make_event("vote_cast", tick, {"voter": "player_0", "target": "player_5"}))
            events.append(make_event("vote_cast", tick, {"voter": "player_1", "target": "player_5"}))
            events.append(make_event("vote_cast", tick, {"voter": "player_2", "target": None}))
            events.append(make_event("vote_cast", tick, {"voter": "player_3", "target": "player_5"}))
            events.append(make_event("vote_cast", tick, {"voter": "player_5", "target": "player_0"}))
            events.append(make_event("player_ejected", tick, {
                "player_id": "player_5",
                "name": "Frank",
                "role": "Duck",
                "team": "duck",
                "votes": {
                    "player_0": "player_5", "player_1": "player_5",
                    "player_2": None, "player_3": "player_5",
                    "player_5": "player_0",
                },
            }))
            events.append(make_event("phase_changed", tick, {"phase": "free_roam"}))

        events.append(make_event("tick_end", tick, {"tick": tick}))

    events.append(make_event("game_over", num_ticks, {
        "winner": "goose",
        "reason": "All Ducks have been ejected",
    }))

    return events


@pytest.fixture
def minimal_game_events() -> list[dict[str, Any]]:
    """A minimal complete game event log for testing."""
    return build_minimal_game_events()


@pytest.fixture
def minimal_log_file(minimal_game_events: list[dict[str, Any]]) -> str:
    """Write minimal game events to a temp JSONL file and return its path."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        for event in minimal_game_events:
            f.write(json.dumps(event) + "\n")
        return f.name
