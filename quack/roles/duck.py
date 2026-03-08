"""Duck (impostor) role — eliminate Geese without getting caught."""

from __future__ import annotations

from typing import TYPE_CHECKING

from quack.engine.game_state import Team
from quack.roles.base_role import BaseRole

if TYPE_CHECKING:
    from quack.engine.game_state import GameState, Player


class Duck(BaseRole):
    name = "Duck"
    team = Team.DUCK

    @property
    def objective(self) -> str:
        return (
            "Eliminate Geese until Ducks have voting majority. "
            "Blend in, fake tasks, and avoid suspicion during meetings."
        )

    def can_kill(self) -> bool:
        return True

    def get_extra_actions(self, player: Player, state: GameState) -> list[str]:
        actions: list[str] = []
        if player.kill_cooldown <= 0:
            visible_geese = [
                p for p in state.get_players_in_room(player.current_room)
                if p.player_id != player.player_id and p.team != Team.DUCK
            ]
            for target in visible_geese:
                actions.append(f"kill({target.player_id})")
        return actions
