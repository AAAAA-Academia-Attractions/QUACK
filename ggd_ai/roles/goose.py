"""Goose (crew) role — complete tasks and identify Ducks."""

from __future__ import annotations

from ggd_ai.engine.game_state import Team
from ggd_ai.roles.base_role import BaseRole


class Goose(BaseRole):
    name = "Goose"
    team = Team.GOOSE

    @property
    def objective(self) -> str:
        return (
            "Complete all your tasks or identify and vote out all Ducks to win. "
            "Stay alive and report any suspicious activity."
        )
