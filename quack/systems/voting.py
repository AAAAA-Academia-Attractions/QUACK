"""Voting system — collect votes, tally, and eject."""

from __future__ import annotations

from collections import Counter
from typing import TYPE_CHECKING, Any

from quack.engine.event_bus import EventBus, EventType, GameEvent
from quack.engine.game_state import GamePhase

if TYPE_CHECKING:
    from quack.engine.game_state import GameState


class VotingSystem:
    def __init__(self, event_bus: EventBus):
        self.event_bus = event_bus

    def start_voting(self, state: GameState) -> None:
        state.phase = GamePhase.VOTING
        state.votes = {}
        self.event_bus.emit(GameEvent(
            event_type=EventType.PHASE_CHANGED,
            data={"phase": GamePhase.VOTING.value},
            tick=state.current_tick,
        ))

    def cast_vote(self, voter_id: str, target_id: str | None, state: GameState) -> bool:
        """Cast a vote. target_id=None means skip."""
        if voter_id not in state.alive_player_ids:
            return False
        if target_id is not None and target_id not in state.alive_player_ids:
            return False
        if voter_id in state.votes:
            return False

        state.votes[voter_id] = target_id
        self.event_bus.emit(GameEvent(
            event_type=EventType.VOTE_CAST,
            data={"voter": voter_id, "target": target_id},
            tick=state.current_tick,
        ))
        return True

    def all_votes_in(self, state: GameState) -> bool:
        return set(state.votes.keys()) >= set(state.alive_player_ids)

    def tally_votes(self, state: GameState) -> str | None:
        """Tally votes and return the player_id to eject, or None if skipped/tied."""
        vote_counts: Counter[str | None] = Counter()
        for target in state.votes.values():
            vote_counts[target] += 1

        if not vote_counts:
            return None

        most_common = vote_counts.most_common()
        top_vote = most_common[0]

        if top_vote[0] is None:
            return None

        if len(most_common) > 1 and most_common[0][1] == most_common[1][1]:
            return None

        return top_vote[0]

    def execute_ejection(self, state: GameState) -> dict[str, Any]:
        """Run the full vote tally and eject the result.

        Returns a dict with 'ejected' (player_id or None) and 'summary'.
        """
        ejected_id = self.tally_votes(state)

        # Build vote count summary (without revealing who voted for whom)
        vote_counts: Counter[str | None] = Counter()
        for target in state.votes.values():
            vote_counts[target] += 1
        skip_count = vote_counts.pop(None, 0)

        tally_parts = []
        for target_id, count in vote_counts.most_common():
            name = state.players[target_id].name if target_id in state.players else target_id
            tally_parts.append(f"{name}: {count} votes")
        if skip_count:
            tally_parts.append(f"Skip: {skip_count}")
        tally_str = ", ".join(tally_parts) if tally_parts else "No votes"

        if ejected_id is None:
            self.event_bus.emit(GameEvent(
                event_type=EventType.VOTE_SKIPPED,
                data={"reason": "tie_or_skip"},
                tick=state.current_tick,
            ))
            summary = f"Vote result: {tally_str}. No one was ejected."
        else:
            player = state.players[ejected_id]
            player.is_alive = False
            self.event_bus.emit(GameEvent(
                event_type=EventType.PLAYER_EJECTED,
                data={
                    "player_id": ejected_id,
                    "name": player.name,
                    "role": player.role_name,
                    "team": player.team.value,
                    "votes": dict(state.votes),
                },
                tick=state.current_tick,
            ))
            summary = f"Vote result: {tally_str}. {player.name} was ejected."

        state.phase = GamePhase.EJECTION
        return {"ejected": ejected_id, "summary": summary, "tally": tally_str}
