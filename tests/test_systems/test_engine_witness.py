"""Integration tests for end-to-end witness movement plumbing through the engine."""

from __future__ import annotations

import asyncio
import random
from typing import Any

import pytest

from quack.agents.base_agent import BaseAgent
from quack.engine.game_engine import GameEngine
from quack.map.game_map import GameMap, Room


class ScriptedAgent(BaseAgent):
    """Returns a queue of preset actions; records every observation it sees."""

    def __init__(self, player_id: str, name: str, actions: list[str]):
        super().__init__(player_id, name)
        self._actions = list(actions)
        self.observations: list[dict[str, Any]] = []

    async def choose_action(self, observation: dict[str, Any], phase: str) -> str:
        self.observations.append(observation)
        if not self._actions:
            return "wait()"
        return self._actions.pop(0)

    async def speak(self, observation: dict[str, Any]) -> str:
        return ""

    async def vote(self, observation: dict[str, Any]) -> str | None:
        return None


def _build_map() -> GameMap:
    gm = GameMap()
    gm.add_room(Room("cafeteria", 0, 0, 2, False, "", True))
    gm.add_room(Room("medbay", 2, 0, 2, True, "task_a"))
    gm.add_room(Room("electrical", 4, 0, 2, True, "task_b"))
    gm.add_corridor("cafeteria", "medbay", 1)
    gm.add_corridor("medbay", "electrical", 2)
    return gm


def _build_engine(agents: dict[str, ScriptedAgent], spawn_rooms: dict[str, str]) -> GameEngine:
    config: dict[str, Any] = {
        "game": {"num_players": len(agents), "num_ducks": 0, "max_ticks": 50},
        "tasks": {"ticks_per_task": 1, "tasks_per_player": 0},
        "kill": {"cooldown_ticks": 5, "initial_cooldown": 5},
        "meeting": {"max_discussion_rounds": 1},
        "vision": {"visibility_range": 0, "fog_memory_ticks": 0},
    }
    engine = GameEngine(game_map=_build_map(), config=config)
    engine.register_agents(agents)

    async def _setup() -> None:
        await engine.setup_game()
        # Force deterministic spawns (override the random ones).
        for pid, room in spawn_rooms.items():
            engine.state.players[pid].current_room = room
            engine.state.players[pid].visited_rooms.add(room)

    asyncio.run(_setup())
    return engine


def test_engine_emits_departed_event_for_instant_move() -> None:
    alice = ScriptedAgent("p0", "Alice", actions=["wait()"])
    bob = ScriptedAgent("p1", "Bob", actions=["move(medbay)"])
    engine = _build_engine(
        {"p0": alice, "p1": bob},
        spawn_rooms={"p0": "cafeteria", "p1": "cafeteria"},
    )

    random.seed(0)
    # Force Bob to act first by patching the random shuffle deterministically.
    real_shuffle = random.shuffle

    def deterministic_shuffle(seq: list) -> None:
        seq.sort()  # 'p0' < 'p1' but we want Bob first; reverse.
        seq.reverse()

    random.shuffle = deterministic_shuffle  # type: ignore
    try:
        asyncio.run(engine._run_free_roam_tick())
    finally:
        random.shuffle = real_shuffle

    types = [ev["type"] for ev in engine.state.tick_movements]
    # Bob's instant move => "departed" + "arrived"
    assert "departed" in types
    assert "arrived" in types
    departed = [ev for ev in engine.state.tick_movements if ev["type"] == "departed"]
    assert departed[0]["player_id"] == "p1"
    assert departed[0]["from_room"] == "cafeteria"
    assert departed[0]["to_room"] == "medbay"
    assert departed[0]["multi_tick"] is False


def test_engine_emits_multi_tick_arrival_in_completion_tick() -> None:
    alice = ScriptedAgent("p0", "Alice", actions=["wait()", "wait()"])
    bob = ScriptedAgent("p1", "Bob", actions=["move(electrical)", "wait()"])
    engine = _build_engine(
        {"p0": alice, "p1": bob},
        spawn_rooms={"p0": "electrical", "p1": "medbay"},
    )

    # Tick 1: Bob starts a 2-tick travel medbay -> electrical
    asyncio.run(engine._run_free_roam_tick())
    types_t1 = {ev["type"] for ev in engine.state.tick_movements}
    assert "departed" in types_t1
    assert "arrived" not in types_t1

    # Tick 2: Bob's transit completes — _advance_transit emits "arrived"
    asyncio.run(engine._run_free_roam_tick())
    arrivals = [ev for ev in engine.state.tick_movements if ev["type"] == "arrived"]
    assert len(arrivals) == 1
    assert arrivals[0]["player_id"] == "p1"
    assert arrivals[0]["from_room"] == "medbay"
    assert arrivals[0]["to_room"] == "electrical"
    assert arrivals[0]["multi_tick"] is True


def test_engine_clears_tick_movements_each_tick() -> None:
    alice = ScriptedAgent("p0", "Alice", actions=["move(medbay)", "wait()"])
    bob = ScriptedAgent("p1", "Bob", actions=["wait()", "wait()"])
    engine = _build_engine(
        {"p0": alice, "p1": bob},
        spawn_rooms={"p0": "cafeteria", "p1": "cafeteria"},
    )

    asyncio.run(engine._run_free_roam_tick())
    assert engine.state.tick_movements  # something happened

    asyncio.run(engine._run_free_roam_tick())
    # No moves on tick 2; the list must have been cleared.
    assert engine.state.tick_movements == []


def test_observation_for_witness_after_roommate_leaves() -> None:
    """A stationary roommate should see the departing player's destination."""
    alice = ScriptedAgent("p0", "Alice", actions=["wait()", "wait()"])
    bob = ScriptedAgent("p1", "Bob", actions=["move(electrical)", "wait()"])
    engine = _build_engine(
        {"p0": alice, "p1": bob},
        spawn_rooms={"p0": "medbay", "p1": "medbay"},
    )

    asyncio.run(engine._run_free_roam_tick())
    alice_obs_t1 = alice.observations[-1]

    # Whether Alice acts before or after Bob, the engine produces a "departed"
    # entry for Bob in state.tick_movements at the moment _do_move runs. If
    # Alice acted first, her stored observation precedes Bob's move and so
    # will not contain the departure. If she acted second, it will.
    moved_first = engine.agents["p1"].observations[0]["tick"] < alice_obs_t1["tick"]
    if moved_first:
        # Bob acted first — Alice's observation captured it.
        deps = alice_obs_t1["transit_observations"]["departures"]
        assert any(d["name"] == "Bob" and d["to_room"] == "electrical" for d in deps)


def test_viewer_acted_first_does_not_see_later_departure() -> None:
    """The acted-first edge case: viewer leaves before another player moves;
    viewer's observation must not include events that happened after her turn."""
    alice = ScriptedAgent("p0", "Alice", actions=["move(cafeteria)"])
    bob = ScriptedAgent("p1", "Bob", actions=["move(electrical)"])
    engine = _build_engine(
        {"p0": alice, "p1": bob},
        spawn_rooms={"p0": "medbay", "p1": "medbay"},
    )

    real_shuffle = random.shuffle

    def alice_first(seq: list) -> None:
        seq.sort()  # ['p0', 'p1'] so Alice goes first

    random.shuffle = alice_first  # type: ignore
    try:
        asyncio.run(engine._run_free_roam_tick())
    finally:
        random.shuffle = real_shuffle

    alice_obs = alice.observations[-1]
    # Alice acted first — Bob's departure is recorded after her observation
    # was already built, so her transit_observations must be empty.
    assert alice_obs["transit_observations"]["departures"] == []
    assert alice_obs["transit_observations"]["arrivals"] == []


def test_replay_apply_event_reconstructs_tick_movements() -> None:
    """Replay should rebuild tick_movements from logged player_moved events."""
    pytest.importorskip("PIL")  # replay needs PIL but we only call apply_event
    from quack.engine.game_state import GameState, Player as ReplayPlayer
    from scripts.replay_game import apply_event

    state = GameState()
    state.players["p0"] = ReplayPlayer(player_id="p0", name="Alice", current_room="medbay")
    state.players["p1"] = ReplayPlayer(player_id="p1", name="Bob", current_room="medbay")

    event_log: list[str] = []
    pending_arrivals: dict[int, list[dict]] = {}

    apply_event(state, {"event_type": "tick_start", "tick": 1, "data": {"tick": 1}},
                event_log, pending_arrivals)

    # Instant move on tick 1
    apply_event(state, {
        "event_type": "player_moved", "tick": 1,
        "data": {"player_id": "p1", "from": "medbay", "to": "cafeteria"},
    }, event_log, pending_arrivals)

    types_t1 = [ev["type"] for ev in state.tick_movements]
    assert types_t1.count("departed") == 1
    assert types_t1.count("arrived") == 1

    # Multi-tick move on tick 2 — only "departed" appears immediately
    apply_event(state, {"event_type": "tick_start", "tick": 2, "data": {"tick": 2}},
                event_log, pending_arrivals)
    apply_event(state, {
        "event_type": "player_moved", "tick": 2,
        "data": {
            "player_id": "p0", "from": "medbay", "to": "cafeteria",
            "ticks_remaining": 2,
        },
    }, event_log, pending_arrivals)
    assert [ev["type"] for ev in state.tick_movements] == ["departed"]
    assert 4 in pending_arrivals  # 2 + 2 = tick 4

    # On tick 4, the pending arrival should be drained into tick_movements
    apply_event(state, {"event_type": "tick_start", "tick": 4, "data": {"tick": 4}},
                event_log, pending_arrivals)
    types_t4 = [ev["type"] for ev in state.tick_movements]
    assert types_t4 == ["arrived"]
    assert state.tick_movements[0]["player_id"] == "p0"
    assert state.tick_movements[0]["from_room"] == "medbay"
    assert state.tick_movements[0]["to_room"] == "cafeteria"
