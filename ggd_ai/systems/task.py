"""Task system — assignment, tick-based progress, and completion tracking."""

from __future__ import annotations

import random
from typing import TYPE_CHECKING

from ggd_ai.engine.event_bus import EventBus, EventType, GameEvent
from ggd_ai.engine.game_state import TaskProgress, Team

if TYPE_CHECKING:
    from ggd_ai.engine.game_state import GameState, Player
    from ggd_ai.map.game_map import GameMap


class TaskSystem:
    """Manages task assignment and progress.

    Tasks are assigned at game start. A player completes a task by being
    in the correct room and choosing do_task() for `ticks_per_task` consecutive
    ticks (moving away resets progress to what was accumulated).
    """

    def __init__(
        self,
        game_map: GameMap,
        event_bus: EventBus,
        ticks_per_task: int = 3,
        tasks_per_player: int = 3,
    ):
        self.game_map = game_map
        self.event_bus = event_bus
        self.ticks_per_task = ticks_per_task
        self.tasks_per_player = tasks_per_player

    def assign_tasks(self, state: GameState) -> None:
        """Assign random tasks to all Goose players at game start."""
        task_rooms = self.game_map.get_task_rooms()
        if not task_rooms:
            return

        for player in state.players.values():
            if player.team != Team.GOOSE:
                player.tasks = self._generate_fake_tasks(task_rooms)
                continue
            player.tasks = self._generate_tasks(task_rooms)

    def _generate_tasks(self, task_rooms: list) -> list[TaskProgress]:
        count = min(self.tasks_per_player, len(task_rooms))
        chosen = random.sample(task_rooms, count)
        return [
            TaskProgress(
                task_name=room.task_name,
                room=room.name,
                ticks_required=self.ticks_per_task,
            )
            for room in chosen
        ]

    def _generate_fake_tasks(self, task_rooms: list) -> list[TaskProgress]:
        """Ducks get fake tasks so they appear to have objectives."""
        return self._generate_tasks(task_rooms)

    def do_task(self, player: Player, state: GameState) -> bool:
        """Advance task progress by one tick. Returns True if a task was completed."""
        task = player.get_current_task()
        if task is None:
            return False

        task.ticks_done += 1
        self.event_bus.emit(GameEvent(
            event_type=EventType.TASK_PROGRESS,
            data={
                "player_id": player.player_id,
                "task_name": task.task_name,
                "room": task.room,
                "progress": f"{task.ticks_done}/{task.ticks_required}",
            },
            tick=state.current_tick,
        ))

        if task.is_complete:
            self.event_bus.emit(GameEvent(
                event_type=EventType.TASK_COMPLETED,
                data={
                    "player_id": player.player_id,
                    "task_name": task.task_name,
                    "room": task.room,
                },
                tick=state.current_tick,
            ))
            return True
        return False

    def get_total_task_progress(self, state: GameState) -> tuple[int, int]:
        """Returns (completed, total) across all Goose players."""
        completed = 0
        total = 0
        for p in state.players.values():
            if p.team == Team.GOOSE:
                for t in p.tasks:
                    total += 1
                    if t.is_complete:
                        completed += 1
        return completed, total
