"""Vision system — fog of war and local visibility."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ggd_ai.engine.game_state import GameState, Player
    from ggd_ai.map.game_map import GameMap


@dataclass
class PlayerVisibility:
    """What a player can currently see."""
    visible_rooms: set[str] = field(default_factory=set)
    visible_players: list[str] = field(default_factory=list)
    visible_bodies: list[str] = field(default_factory=list)


class VisionSystem:
    """Computes per-player visibility based on map graph distance.

    - A player can see all rooms within `visibility_range` hops.
    - A player can see other players/bodies in those visible rooms.
    - Fog memory: rooms remain "revealed" on the global map for N ticks after visiting.
    """

    def __init__(self, game_map: GameMap, visibility_range: int = 1, fog_memory_ticks: int = 20):
        self.game_map = game_map
        self.visibility_range = visibility_range
        self.fog_memory_ticks = fog_memory_ticks
        self._last_visit: dict[str, dict[str, int]] = {}

    def update_visit(self, player_id: str, room: str, tick: int) -> None:
        if player_id not in self._last_visit:
            self._last_visit[player_id] = {}
        self._last_visit[player_id][room] = tick

    def get_visible_rooms(self, player_id: str, current_room: str) -> set[str]:
        """Rooms the player can currently observe (for local vision)."""
        return self.game_map.get_rooms_within_distance(current_room, self.visibility_range)

    def get_fog_revealed_rooms(self, player_id: str, current_tick: int) -> set[str]:
        """Rooms revealed on the global map (recently visited + currently visible)."""
        revealed: set[str] = set()
        visits = self._last_visit.get(player_id, {})
        for room, last_tick in visits.items():
            if current_tick - last_tick <= self.fog_memory_ticks:
                revealed.add(room)
        return revealed

    def compute_visibility(self, player: Player, state: GameState) -> PlayerVisibility:
        current_room = player.current_room
        visible_rooms = self.get_visible_rooms(player.player_id, current_room)

        visible_players: list[str] = []
        for p in state.alive_players:
            if p.player_id == player.player_id:
                continue

            if player.is_in_transit:
                # In a corridor: can see others in the same corridor
                if (p.is_in_transit
                        and p.current_room == player.current_room
                        and p.moving_to == player.moving_to):
                    visible_players.append(p.player_id)
                elif (p.is_in_transit
                        and p.current_room == player.moving_to
                        and p.moving_to == player.current_room):
                    visible_players.append(p.player_id)
            else:
                # In a room: can only see others in the same room (not in transit)
                if not p.is_in_transit and p.current_room == current_room:
                    visible_players.append(p.player_id)

        visible_bodies = [
            b.player_id
            for b in state.bodies
            if b.room == current_room and not player.is_in_transit
        ]

        return PlayerVisibility(
            visible_rooms=visible_rooms,
            visible_players=visible_players,
            visible_bodies=visible_bodies,
        )

    def build_observation(
        self,
        player: Player,
        state: GameState,
        game_map: GameMap,
    ) -> dict[str, Any]:
        """Build the text observation dict sent to an agent each tick."""
        vis = self.compute_visibility(player, state)
        fog_revealed = self.get_fog_revealed_rooms(player.player_id, state.current_tick)
        all_revealed = fog_revealed | vis.visible_rooms

        neighbors = game_map.get_neighbors(player.current_room)
        current_task = player.get_current_task()

        adjacent_with_distance = [
            {
                "room": n,
                "travel_ticks": game_map.get_corridor_weight(player.current_room, n),
            }
            for n in neighbors
        ]

        return {
            "current_room": player.current_room,
            "in_transit": player.is_in_transit,
            "moving_to": player.moving_to if player.is_in_transit else None,
            "move_ticks_remaining": player.move_ticks_remaining if player.is_in_transit else 0,
            "visible_rooms": sorted(vis.visible_rooms),
            "fog_revealed_rooms": sorted(all_revealed),
            "visible_players": [
                {
                    "id": pid,
                    "name": state.players[pid].name,
                    "room": state.players[pid].current_room,
                }
                for pid in vis.visible_players
            ],
            "visible_bodies": [
                {
                    "id": bid,
                    "name": state.players[bid].name,
                    "room": next(b.room for b in state.bodies if b.player_id == bid),
                }
                for bid in vis.visible_bodies
            ],
            "adjacent_rooms": neighbors,
            "adjacent_rooms_detail": adjacent_with_distance,
            "tasks": [
                {
                    "name": t.task_name,
                    "room": t.room,
                    "done": t.is_complete,
                    "progress": f"{t.ticks_done}/{t.ticks_required}",
                    "distance_ticks": game_map.distance(player.current_room, t.room)
                        if not player.is_in_transit else -1,
                }
                for t in player.tasks
            ],
            "current_task_here": {
                "name": current_task.task_name,
                "progress": f"{current_task.ticks_done}/{current_task.ticks_required}",
            } if current_task else None,
            "kill_cooldown": player.kill_cooldown if player.team.value == "duck" else None,
        }
