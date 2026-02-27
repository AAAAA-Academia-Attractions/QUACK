"""Agent memory system for tracking observations across ticks.

Each agent maintains a structured memory of what they've seen, where they've been,
who they've encountered, and what was said in meetings. This memory is serialized
into natural language for inclusion in VLM prompts.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class TickMemory:
    """What happened during a single tick."""
    tick: int
    room: str
    action: str = ""
    players_seen: list[str] = field(default_factory=list)
    bodies_seen: list[str] = field(default_factory=list)
    in_transit: bool = False
    moving_to: str = ""


@dataclass
class MeetingMemory:
    """Record of a single meeting."""
    tick: int
    reason: str
    dead_players: list[str] = field(default_factory=list)
    speeches: list[dict[str, str]] = field(default_factory=list)
    my_speech: str = ""
    votes_result: str = ""
    ejected: str = ""


class AgentMemory:
    """Tracks all observations for a single agent across the game."""

    def __init__(self, player_name: str) -> None:
        self.player_name = player_name
        self.tick_history: list[TickMemory] = []
        self.meeting_history: list[MeetingMemory] = []
        self._current_meeting: MeetingMemory | None = None

    def record_tick(
        self,
        tick: int,
        room: str,
        action: str,
        players_seen: list[str],
        bodies_seen: list[str],
        in_transit: bool = False,
        moving_to: str = "",
    ) -> None:
        self.tick_history.append(TickMemory(
            tick=tick,
            room=room,
            action=action,
            players_seen=players_seen,
            bodies_seen=bodies_seen,
            in_transit=in_transit,
            moving_to=moving_to,
        ))

    def start_meeting(self, tick: int, reason: str, dead_players: list[str]) -> None:
        self._current_meeting = MeetingMemory(
            tick=tick,
            reason=reason,
            dead_players=list(dead_players),
        )

    def record_speech(self, speaker_name: str, message: str) -> None:
        if self._current_meeting:
            self._current_meeting.speeches.append({
                "name": speaker_name,
                "message": message,
            })

    def record_my_speech(self, message: str) -> None:
        if self._current_meeting:
            self._current_meeting.my_speech = message

    def record_vote_result(self, result: str, ejected: str = "") -> None:
        if self._current_meeting:
            self._current_meeting.votes_result = result
            self._current_meeting.ejected = ejected
            self.meeting_history.append(self._current_meeting)
            self._current_meeting = None

    def build_movement_summary(self, last_n: int = 15) -> str:
        """Summarize recent movement and observations."""
        if not self.tick_history:
            return "No movement history yet."

        recent = self.tick_history[-last_n:]
        lines = []
        for t in recent:
            if t.in_transit:
                lines.append(f"  Tick {t.tick}: Traveling to {t.moving_to}")
                continue
            parts = [f"  Tick {t.tick}: In {t.room}"]
            if t.action:
                parts.append(f"did '{t.action}'")
            if t.players_seen:
                parts.append(f"saw [{', '.join(t.players_seen)}]")
            if t.bodies_seen:
                parts.append(f"FOUND BODY of [{', '.join(t.bodies_seen)}]!")
            lines.append(", ".join(parts))
        return "\n".join(lines)

    def build_encounter_summary(self) -> str:
        """Who has this agent seen and where."""
        encounters: dict[str, list[str]] = {}
        for t in self.tick_history:
            for p in t.players_seen:
                encounters.setdefault(p, []).append(f"tick {t.tick} in {t.room}")

        if not encounters:
            return "Haven't encountered anyone yet."

        lines = []
        for name, sightings in encounters.items():
            recent = sightings[-3:]
            lines.append(f"  {name}: seen at {'; '.join(recent)}")
        return "\n".join(lines)

    def build_meeting_summary(self) -> str:
        """Summary of past meetings for context."""
        if not self.meeting_history:
            return "No previous meetings."

        lines = []
        for i, m in enumerate(self.meeting_history, 1):
            lines.append(f"  Meeting {i} (tick {m.tick}): {m.reason}")
            if m.dead_players:
                lines.append(f"    Dead at that time: {', '.join(m.dead_players)}")
            if m.ejected:
                lines.append(f"    Result: {m.ejected} was ejected")
            else:
                lines.append(f"    Result: No one ejected")
        return "\n".join(lines)

    def get_route_description(self) -> str:
        """Describe the agent's route since last meeting/game start."""
        last_meeting_tick = 0
        if self.meeting_history:
            last_meeting_tick = self.meeting_history[-1].tick

        recent = [t for t in self.tick_history if t.tick > last_meeting_tick]
        if not recent:
            return "I haven't moved since the last meeting."

        rooms_visited = []
        for t in recent:
            if not t.in_transit and (not rooms_visited or rooms_visited[-1] != t.room):
                rooms_visited.append(t.room)

        return " -> ".join(rooms_visited) if rooms_visited else "Stayed in place."
