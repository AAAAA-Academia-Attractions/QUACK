"""Abstract agent interface defining the observation/action contract."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BaseAgent(ABC):
    """Every agent (VLM, human, rule-based) implements this interface.

    The engine calls:
    - choose_action() during Free Roam (returns an action string)
    - speak() during Discussion (returns a natural language message)
    - vote() during Voting (returns a player_id or None to skip)
    """

    def __init__(self, player_id: str, name: str):
        self.player_id = player_id
        self.name = name

    @abstractmethod
    async def choose_action(self, observation: dict[str, Any], phase: str) -> str:
        """Given the current observation, return an action string like 'move(medbay)'."""
        ...

    @abstractmethod
    async def speak(self, observation: dict[str, Any]) -> str:
        """Generate a natural language message during discussion."""
        ...

    @abstractmethod
    async def vote(self, observation: dict[str, Any]) -> str | None:
        """Return a player_id to vote for, or None to skip."""
        ...

    async def on_game_start(
        self,
        role_name: str,
        team: str,
        objective: str,
        *,
        total_geese: int = 0,
        total_ducks: int = 0,
        teammates: list[str] | None = None,
        all_players: list[str] | None = None,
    ) -> None:
        """Called once at game start to inform the agent of its role and team composition."""
        pass

    async def on_game_end(self, result: dict[str, Any]) -> None:
        """Called once at game end with the final result."""
        pass
