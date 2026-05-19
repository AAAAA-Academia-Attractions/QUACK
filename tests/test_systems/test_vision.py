"""Tests for vision system observations."""

from __future__ import annotations

from quack.engine.game_state import GamePhase, GameState, Player, Team
from quack.map.game_map import GameMap, Room
from quack.systems.vision import VisionSystem


def _minimal_map() -> GameMap:
    gm = GameMap()
    gm.add_room(Room("cafeteria", 0, 0))
    gm.add_room(Room("medbay", 2, 0))
    gm.add_corridor("cafeteria", "medbay", 1)
    return gm


def test_build_observation_includes_current_tick() -> None:
    game_map = _minimal_map()
    vision = VisionSystem(game_map, visibility_range=0)
    state = GameState(phase=GamePhase.FREE_ROAM, current_tick=42)
    state.players["player_0"] = Player(
        player_id="player_0",
        name="Alice",
        team=Team.GOOSE,
        current_room="cafeteria",
    )

    obs = vision.build_observation(state.players["player_0"], state, game_map)

    assert obs["tick"] == 42
