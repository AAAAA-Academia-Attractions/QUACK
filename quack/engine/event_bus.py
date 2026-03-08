"""Pub/sub event system for decoupled game communication."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable


class EventType(Enum):
    GAME_STARTED = "game_started"
    TICK_START = "tick_start"
    TICK_END = "tick_end"
    PLAYER_MOVED = "player_moved"
    PLAYER_KILLED = "player_killed"
    FREE_ROAM_CHAT = "free_roam_chat"
    BODY_REPORTED = "body_reported"
    MEETING_CALLED = "meeting_called"
    DISCUSSION_MESSAGE = "discussion_message"
    VOTE_CAST = "vote_cast"
    PLAYER_EJECTED = "player_ejected"
    VOTE_SKIPPED = "vote_skipped"
    TASK_PROGRESS = "task_progress"
    TASK_COMPLETED = "task_completed"
    PHASE_CHANGED = "phase_changed"
    GAME_OVER = "game_over"


@dataclass
class GameEvent:
    event_type: EventType
    data: dict[str, Any] = field(default_factory=dict)
    tick: int = 0


EventHandler = Callable[[GameEvent], None]


class EventBus:
    """Central event dispatcher. Systems subscribe to event types and get notified."""

    def __init__(self) -> None:
        self._handlers: dict[EventType, list[EventHandler]] = defaultdict(list)
        self._global_handlers: list[EventHandler] = []

    def subscribe(self, event_type: EventType, handler: EventHandler) -> None:
        self._handlers[event_type].append(handler)

    def subscribe_all(self, handler: EventHandler) -> None:
        """Subscribe to every event type (useful for logging)."""
        self._global_handlers.append(handler)

    def emit(self, event: GameEvent) -> None:
        for handler in self._global_handlers:
            handler(event)
        for handler in self._handlers.get(event.event_type, []):
            handler(event)

    def clear(self) -> None:
        self._handlers.clear()
        self._global_handlers.clear()
