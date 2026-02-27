"""Discrete graph-based game map."""

from __future__ import annotations

import heapq
from collections import deque
from dataclasses import dataclass
from typing import Any


@dataclass
class Room:
    name: str
    x: float
    y: float
    size: float = 2.0
    has_task: bool = False
    task_name: str = ""
    is_emergency_button: bool = False


class GameMap:
    """Graph of rooms connected by weighted corridors.

    Rooms are nodes, corridors are undirected weighted edges. The weight
    represents the number of ticks needed to traverse a corridor.
    """

    def __init__(self) -> None:
        self.rooms: dict[str, Room] = {}
        self._adjacency: dict[str, set[str]] = {}
        self._weights: dict[tuple[str, str], int] = {}

    # ---- Construction ----

    def add_room(self, room: Room) -> None:
        self.rooms[room.name] = room
        self._adjacency.setdefault(room.name, set())

    def add_corridor(self, room_a: str, room_b: str, weight: int = 1) -> None:
        if room_a not in self.rooms or room_b not in self.rooms:
            raise ValueError(f"Both rooms must exist: {room_a}, {room_b}")
        self._adjacency[room_a].add(room_b)
        self._adjacency[room_b].add(room_a)
        key = tuple(sorted((room_a, room_b)))
        self._weights[(key[0], key[1])] = weight

    def get_corridor_weight(self, room_a: str, room_b: str) -> int:
        """Travel time (ticks) between two adjacent rooms. Default 1."""
        key = tuple(sorted((room_a, room_b)))
        return self._weights.get((key[0], key[1]), 1)

    # ---- Queries ----

    def get_neighbors(self, room_name: str) -> list[str]:
        return sorted(self._adjacency.get(room_name, set()))

    def are_adjacent(self, room_a: str, room_b: str) -> bool:
        return room_b in self._adjacency.get(room_a, set())

    def shortest_path(self, start: str, end: str) -> list[str] | None:
        """Dijkstra shortest path using corridor weights. Returns room list including start and end."""
        if start == end:
            return [start]
        dist: dict[str, int] = {start: 0}
        prev: dict[str, str | None] = {start: None}
        heap: list[tuple[int, str]] = [(0, start)]

        while heap:
            d, current = heapq.heappop(heap)
            if current == end:
                path: list[str] = []
                node: str | None = end
                while node is not None:
                    path.append(node)
                    node = prev[node]
                return list(reversed(path))
            if d > dist.get(current, float("inf")):
                continue
            for neighbor in self._adjacency.get(current, set()):
                w = self.get_corridor_weight(current, neighbor)
                nd = d + w
                if nd < dist.get(neighbor, float("inf")):
                    dist[neighbor] = nd
                    prev[neighbor] = current
                    heapq.heappush(heap, (nd, neighbor))
        return None

    def distance(self, room_a: str, room_b: str) -> int:
        """Weighted shortest distance (total ticks) between two rooms, or -1 if unreachable."""
        if room_a == room_b:
            return 0
        dist: dict[str, int] = {room_a: 0}
        heap: list[tuple[int, str]] = [(0, room_a)]
        while heap:
            d, current = heapq.heappop(heap)
            if current == room_b:
                return d
            if d > dist.get(current, float("inf")):
                continue
            for neighbor in self._adjacency.get(current, set()):
                w = self.get_corridor_weight(current, neighbor)
                nd = d + w
                if nd < dist.get(neighbor, float("inf")):
                    dist[neighbor] = nd
                    heapq.heappush(heap, (nd, neighbor))
        return -1

    def get_rooms_within_distance(self, room: str, max_dist: int) -> set[str]:
        """All rooms within max_dist hops (inclusive of the starting room)."""
        result: set[str] = set()
        visited = {room}
        queue: deque[tuple[str, int]] = deque([(room, 0)])
        while queue:
            current, dist = queue.popleft()
            result.add(current)
            if dist < max_dist:
                for neighbor in self._adjacency.get(current, set()):
                    if neighbor not in visited:
                        visited.add(neighbor)
                        queue.append((neighbor, dist + 1))
        return result

    def get_task_rooms(self) -> list[Room]:
        return [r for r in self.rooms.values() if r.has_task]

    def get_emergency_button_room(self) -> Room | None:
        for r in self.rooms.values():
            if r.is_emergency_button:
                return r
        return None

    @property
    def room_names(self) -> list[str]:
        return sorted(self.rooms.keys())

    # ---- Serialization ----

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> GameMap:
        """Build a GameMap from a YAML-loaded dict."""
        gm = cls()

        emergency_button_room = config.get("emergency_button", "")

        task_room_map: dict[str, str] = {}
        for task_def in config.get("task_locations", []):
            task_room_map[task_def["room"]] = task_def["name"]

        for room_name, room_data in config.get("rooms", {}).items():
            has_task = room_name in task_room_map
            room = Room(
                name=room_name,
                x=room_data["x"],
                y=room_data["y"],
                size=room_data.get("size", 2.0),
                has_task=has_task,
                task_name=task_room_map.get(room_name, ""),
                is_emergency_button=(room_name == emergency_button_room),
            )
            gm.add_room(room)

        for corridor in config.get("corridors", []):
            if isinstance(corridor, dict):
                gm.add_corridor(corridor["from"], corridor["to"], corridor.get("weight", 1))
            elif len(corridor) >= 3:
                gm.add_corridor(corridor[0], corridor[1], int(corridor[2]))
            else:
                gm.add_corridor(corridor[0], corridor[1])

        return gm
