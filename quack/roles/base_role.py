"""Abstract base role that all roles subclass."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from quack.engine.game_state import Team

if TYPE_CHECKING:
    from quack.engine.game_state import GameState, Player


class BaseRole(ABC):
    """Every role must declare its team, objective text, and available abilities."""

    name: str = "base"
    team: Team = Team.GOOSE

    @property
    @abstractmethod
    def objective(self) -> str:
        """One-line description shown to the agent."""
        ...

    def can_kill(self) -> bool:
        return False

    def can_call_meeting(self, player: Player, state: GameState) -> bool:
        """Check if emergency meetings are still available (global pool)."""
        return state.emergency_meetings_remaining > 0

    def on_night_action(self, player: Player, state: GameState) -> None:
        """Override for roles with special phase actions."""
        pass

    def get_extra_actions(self, player: Player, state: GameState) -> list[str]:
        """Return role-specific actions beyond the standard set."""
        return []
