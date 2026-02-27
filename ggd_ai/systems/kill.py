"""Kill system — Duck kill mechanics with cooldown."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ggd_ai.engine.event_bus import EventBus, EventType, GameEvent
from ggd_ai.engine.game_state import Body, Team

if TYPE_CHECKING:
    from ggd_ai.engine.game_state import GameState, Player


class KillSystem:
    def __init__(self, event_bus: EventBus, cooldown_ticks: int = 10, initial_cooldown: int = 15):
        self.event_bus = event_bus
        self.cooldown_ticks = cooldown_ticks
        self.initial_cooldown = initial_cooldown

    def initialize_cooldowns(self, state: GameState) -> None:
        for p in state.players.values():
            if p.team == Team.DUCK:
                p.kill_cooldown = self.initial_cooldown

    def tick_cooldowns(self, state: GameState) -> None:
        for p in state.alive_players:
            if p.team == Team.DUCK and p.kill_cooldown > 0:
                p.kill_cooldown -= 1

    def can_kill(self, killer: Player, target_id: str, state: GameState) -> tuple[bool, str]:
        if killer.team != Team.DUCK:
            return False, "Only Ducks can kill"
        if killer.kill_cooldown > 0:
            return False, f"Kill on cooldown ({killer.kill_cooldown} ticks remaining)"
        if not killer.is_alive:
            return False, "Dead players cannot kill"

        target = state.players.get(target_id)
        if target is None:
            return False, "Target not found"
        if not target.is_alive:
            return False, "Target is already dead"
        if target.team == Team.DUCK:
            return False, "Cannot kill fellow Ducks"
        if target.current_room != killer.current_room:
            return False, "Target not in the same room"

        return True, ""

    def execute_kill(self, killer: Player, target_id: str, state: GameState) -> bool:
        can, reason = self.can_kill(killer, target_id, state)
        if not can:
            return False

        target = state.players[target_id]
        target.is_alive = False
        killer.kill_cooldown = self.cooldown_ticks

        body = Body(
            player_id=target.player_id,
            room=target.current_room,
            killed_at_tick=state.current_tick,
        )
        state.bodies.append(body)

        self.event_bus.emit(GameEvent(
            event_type=EventType.PLAYER_KILLED,
            data={
                "killer_id": killer.player_id,
                "target_id": target.player_id,
                "room": target.current_room,
            },
            tick=state.current_tick,
        ))
        return True
