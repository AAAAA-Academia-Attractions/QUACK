"""Structured JSON logger for game events."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from ggd_ai.engine.event_bus import GameEvent


class GameLogger:
    """Subscribes to all events via the event bus and writes structured JSON logs.

    Each line is a JSON object with: timestamp, event_type, tick, data.
    """

    def __init__(self, log_dir: str = "game_logs"):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self._game_id = f"game_{int(time.time())}"
        self._log_path = self.log_dir / f"{self._game_id}.jsonl"
        self._entries: list[dict[str, Any]] = []

    @property
    def game_id(self) -> str:
        return self._game_id

    @property
    def log_path(self) -> Path:
        return self._log_path

    def handle_event(self, event: GameEvent) -> None:
        """Event handler compatible with EventBus.subscribe_all()."""
        entry = {
            "timestamp": time.time(),
            "event_type": event.event_type.value,
            "tick": event.tick,
            "data": event.data,
        }
        self._entries.append(entry)
        self._write_entry(entry)

    def _write_entry(self, entry: dict[str, Any]) -> None:
        with open(self._log_path, "a") as f:
            f.write(json.dumps(entry, default=str) + "\n")

    def log_custom(self, event_name: str, tick: int, data: dict[str, Any]) -> None:
        entry = {
            "timestamp": time.time(),
            "event_type": event_name,
            "tick": tick,
            "data": data,
        }
        self._entries.append(entry)
        self._write_entry(entry)

    def get_entries(self) -> list[dict[str, Any]]:
        return list(self._entries)

    def summary(self) -> dict[str, Any]:
        if not self._entries:
            return {"game_id": self._game_id, "events": 0}
        return {
            "game_id": self._game_id,
            "events": len(self._entries),
            "first_tick": self._entries[0].get("tick", 0),
            "last_tick": self._entries[-1].get("tick", 0),
            "log_path": str(self._log_path),
        }
