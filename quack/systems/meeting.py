"""Meeting system — body report and emergency button trigger."""

from __future__ import annotations

import random
from typing import TYPE_CHECKING

from quack.engine.event_bus import EventBus, EventType, GameEvent
from quack.engine.game_state import GamePhase

if TYPE_CHECKING:
    from quack.engine.game_state import GameState, Player
    from quack.map.game_map import GameMap


class MeetingSystem:
    def __init__(self, event_bus: EventBus, game_map: GameMap, max_discussion_rounds: int = 2):
        self.event_bus = event_bus
        self.game_map = game_map
        self.max_discussion_rounds = max_discussion_rounds

    def can_report_body(self, player: Player, state: GameState) -> bool:
        if not player.is_alive:
            return False
        bodies = state.get_bodies_in_room(player.current_room)
        return len(bodies) > 0

    def can_call_emergency(self, player: Player, state: GameState) -> bool:
        if not player.is_alive:
            return False
        if state.emergency_meetings_remaining <= 0:
            return False
        eb_room = self.game_map.get_emergency_button_room()
        if eb_room is None:
            return False
        return player.current_room == eb_room.name

    def report_body(self, reporter: Player, state: GameState) -> bool:
        if not self.can_report_body(reporter, state):
            return False
        bodies = state.get_bodies_in_room(reporter.current_room)
        body_names = [state.players[b.player_id].name for b in bodies]

        self._start_meeting(
            state,
            caller=reporter.player_id,
            reason=f"{reporter.name} reported a dead body",
            event_type=EventType.BODY_REPORTED,
        )
        return True

    def call_emergency(self, caller: Player, state: GameState) -> bool:
        if not self.can_call_emergency(caller, state):
            return False
        state.emergency_meetings_remaining -= 1

        self._start_meeting(
            state,
            caller=caller.player_id,
            reason=f"{caller.name} called an emergency meeting",
            event_type=EventType.MEETING_CALLED,
        )
        return True

    def _start_meeting(
        self,
        state: GameState,
        caller: str,
        reason: str,
        event_type: EventType,
    ) -> None:
        state.phase = GamePhase.DISCUSSION
        state.meeting_caller = caller
        state.meeting_reason = reason
        state.discussion_messages = []
        state.votes = {}
        state.discussion_round = 0
        state.max_discussion_rounds = self.max_discussion_rounds

        # Cancel all in-transit movement
        for p in state.alive_players:
            if p.is_in_transit:
                p.moving_from = ""
                p.moving_to = ""
                p.move_ticks_remaining = 0

        alive_ids = list(state.alive_player_ids)
        rest = [p for p in alive_ids if p != caller]
        random.shuffle(rest)
        state.discussion_order = [caller] + rest
        state.current_speaker_idx = 0

        bodies_data = []
        for b in state.bodies:
            bodies_data.append({
                "room": b.room,
                "victim_name": state.players[b.player_id].name,
            })
        self.event_bus.emit(GameEvent(
            event_type=event_type,
            data={"caller": caller, "reason": reason, "bodies": bodies_data},
            tick=state.current_tick,
        ))
        self.event_bus.emit(GameEvent(
            event_type=EventType.PHASE_CHANGED,
            data={"phase": GamePhase.DISCUSSION.value},
            tick=state.current_tick,
        ))

    def add_discussion_message(self, player_id: str, message: str, state: GameState) -> None:
        state.discussion_messages.append({
            "player_id": player_id,
            "name": state.players[player_id].name,
            "message": message,
        })
        self.event_bus.emit(GameEvent(
            event_type=EventType.DISCUSSION_MESSAGE,
            data={"player_id": player_id, "message": message},
            tick=state.current_tick,
        ))

    def advance_speaker(self, state: GameState) -> str | None:
        """Move to the next speaker. Returns their player_id, or None if the round is over."""
        state.current_speaker_idx += 1
        if state.current_speaker_idx >= len(state.discussion_order):
            state.discussion_round += 1
            if state.discussion_round >= state.max_discussion_rounds:
                return None
            state.current_speaker_idx = 0
        return state.discussion_order[state.current_speaker_idx]

    def get_current_speaker(self, state: GameState) -> str | None:
        if state.current_speaker_idx >= len(state.discussion_order):
            return None
        return state.discussion_order[state.current_speaker_idx]
