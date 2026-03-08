"""Parse JSONL game logs into structured event lists."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def parse_log(log_path: str | Path) -> list[dict[str, Any]]:
    """Parse a JSONL game log file into a list of event dicts.

    Each event dict has keys: timestamp, event_type, tick, data.
    Events are returned in file order (chronological).

    Raises:
        FileNotFoundError: If the log file does not exist.
        ValueError: If the log contains no valid events.
    """
    log_path = Path(log_path)
    if not log_path.exists():
        raise FileNotFoundError(f"Game log not found: {log_path}")

    events: list[dict[str, Any]] = []
    with open(log_path) as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
                events.append(event)
            except json.JSONDecodeError as e:
                logger.warning("Skipping malformed line %d in %s: %s", line_num, log_path, e)

    if not events:
        raise ValueError(f"No valid events in log file: {log_path}")

    logger.info("Parsed %d events from %s", len(events), log_path)
    return events


def get_game_id_from_path(log_path: str | Path) -> str:
    """Extract game ID from a log file path (e.g., 'game_1234567890')."""
    return Path(log_path).stem


def get_initial_state(events: list[dict[str, Any]]) -> dict[str, Any]:
    """Extract the initial_state dict from the game_started event.

    Returns a mapping of player_id -> {name, role, team, room, tasks}.
    """
    for event in events:
        if event.get("event_type") == "game_started":
            return event["data"].get("initial_state", {})
    raise ValueError("No game_started event found in log")


def get_game_config(events: list[dict[str, Any]]) -> dict[str, Any]:
    """Extract the config dict from the game_started event."""
    for event in events:
        if event.get("event_type") == "game_started":
            return event["data"].get("config", {})
    return {}


def get_player_name_map(events: list[dict[str, Any]]) -> dict[str, str]:
    """Build a player_id -> player_name mapping from the game_started event."""
    initial = get_initial_state(events)
    return {pid: info["name"] for pid, info in initial.items()}


def get_player_role_map(events: list[dict[str, Any]]) -> dict[str, str]:
    """Build a player_id -> team ('goose'|'duck') mapping."""
    initial = get_initial_state(events)
    return {pid: info["team"] for pid, info in initial.items()}


def filter_events(
    events: list[dict[str, Any]],
    event_type: str | None = None,
    tick_range: tuple[int, int] | None = None,
) -> list[dict[str, Any]]:
    """Filter events by type and/or tick range."""
    result = events
    if event_type is not None:
        result = [e for e in result if e.get("event_type") == event_type]
    if tick_range is not None:
        lo, hi = tick_range
        result = [e for e in result if lo <= e.get("tick", 0) <= hi]
    return result
