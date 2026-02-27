"""Pathfinding utilities (re-exported from GameMap for convenience)."""

from __future__ import annotations

from ggd_ai.map.game_map import GameMap


def shortest_path(game_map: GameMap, start: str, end: str) -> list[str] | None:
    return game_map.shortest_path(start, end)


def distance(game_map: GameMap, room_a: str, room_b: str) -> int:
    return game_map.distance(room_a, room_b)


def rooms_within(game_map: GameMap, room: str, max_dist: int) -> set[str]:
    return game_map.get_rooms_within_distance(room, max_dist)
