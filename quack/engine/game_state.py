"""Central game state representation."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class GamePhase(Enum):
    LOBBY = "lobby"
    FREE_ROAM = "free_roam"
    MEETING_CALLED = "meeting_called"
    DISCUSSION = "discussion"
    VOTING = "voting"
    EJECTION = "ejection"
    GAME_OVER = "game_over"


class Team(Enum):
    GOOSE = "goose"
    DUCK = "duck"
    NEUTRAL = "neutral"


@dataclass
class TaskProgress:
    task_name: str
    room: str
    ticks_required: int
    ticks_done: int = 0

    @property
    def is_complete(self) -> bool:
        return self.ticks_done >= self.ticks_required

    @property
    def remaining(self) -> int:
        return max(0, self.ticks_required - self.ticks_done)


@dataclass
class Body:
    """A dead player's body on the map."""
    player_id: str
    room: str
    killed_at_tick: int


@dataclass
class Player:
    player_id: str
    name: str
    role_name: str = ""
    team: Team = Team.GOOSE
    is_alive: bool = True
    current_room: str = ""
    tasks: list[TaskProgress] = field(default_factory=list)
    kill_cooldown: int = 0
    emergency_meetings_left: int = 1
    visited_rooms: set[str] = field(default_factory=set)

    # In-transit state: player is traveling between rooms
    moving_from: str = ""
    moving_to: str = ""
    move_ticks_remaining: int = 0

    @property
    def is_in_transit(self) -> bool:
        return self.move_ticks_remaining > 0

    @property
    def all_tasks_complete(self) -> bool:
        return all(t.is_complete for t in self.tasks)

    def get_current_task(self) -> TaskProgress | None:
        """Return the incomplete task in the player's current room, if any."""
        if self.is_in_transit:
            return None
        for t in self.tasks:
            if t.room == self.current_room and not t.is_complete:
                return t
        return None


@dataclass
class GameState:
    players: dict[str, Player] = field(default_factory=dict)
    phase: GamePhase = GamePhase.LOBBY
    current_tick: int = 0
    bodies: list[Body] = field(default_factory=list)
    # Free-roam chat: messages spoken during the current tick, grouped by room.
    # Reset at the start of each free-roam tick.
    room_messages: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    max_ticks: int = 200

    # Meeting state
    meeting_caller: str | None = None
    meeting_reason: str | None = None
    discussion_messages: list[dict[str, str]] = field(default_factory=list)
    votes: dict[str, str | None] = field(default_factory=dict)
    discussion_round: int = 0
    max_discussion_rounds: int = 2
    discussion_order: list[str] = field(default_factory=list)
    current_speaker_idx: int = 0
    emergency_meetings_remaining: int = 1  # global pool, set to num_ducks at game start

    # Win state
    winner: Team | None = None
    win_reason: str = ""

    @property
    def alive_players(self) -> list[Player]:
        return [p for p in self.players.values() if p.is_alive]

    @property
    def alive_player_ids(self) -> list[str]:
        return [p.player_id for p in self.alive_players]

    @property
    def alive_goose_count(self) -> int:
        return sum(1 for p in self.alive_players if p.team == Team.GOOSE)

    @property
    def alive_duck_count(self) -> int:
        return sum(1 for p in self.alive_players if p.team == Team.DUCK)

    @property
    def all_goose_tasks_complete(self) -> bool:
        return all(
            p.all_tasks_complete
            for p in self.players.values()
            if p.team == Team.GOOSE
        )

    def get_bodies_in_room(self, room: str) -> list[Body]:
        return [b for b in self.bodies if b.room == room]

    def get_players_in_room(self, room: str, alive_only: bool = True) -> list[Player]:
        return [
            p for p in self.players.values()
            if p.current_room == room
            and not p.is_in_transit
            and (not alive_only or p.is_alive)
        ]

    @property
    def dead_player_names(self) -> list[dict[str, str]]:
        """Summary of all dead players (visible to all during meetings)."""
        return [
            {"id": p.player_id, "name": p.name}
            for p in self.players.values()
            if not p.is_alive
        ]

    def to_dict(self) -> dict[str, Any]:
        """Serialize for logging."""
        return {
            "phase": self.phase.value,
            "tick": self.current_tick,
            "players": {
                pid: {
                    "name": p.name,
                    "role": p.role_name,
                    "team": p.team.value,
                    "alive": p.is_alive,
                    "room": p.current_room,
                    "in_transit": p.is_in_transit,
                    "moving_to": p.moving_to if p.is_in_transit else None,
                    "tasks_done": sum(1 for t in p.tasks if t.is_complete),
                    "tasks_total": len(p.tasks),
                }
                for pid, p in self.players.items()
            },
            "bodies": [
                {"player_id": b.player_id, "room": b.room, "tick": b.killed_at_tick}
                for b in self.bodies
            ],
            "winner": self.winner.value if self.winner else None,
        }
