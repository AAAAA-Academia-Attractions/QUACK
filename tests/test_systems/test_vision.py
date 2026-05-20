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


def _three_room_map() -> GameMap:
    gm = GameMap()
    gm.add_room(Room("cafeteria", 0, 0))
    gm.add_room(Room("medbay", 2, 0))
    gm.add_room(Room("electrical", 4, 0))
    gm.add_corridor("cafeteria", "medbay", 2)
    gm.add_corridor("medbay", "electrical", 1)
    return gm


def _state(players: list[Player], tick: int = 0) -> GameState:
    state = GameState(phase=GamePhase.FREE_ROAM, current_tick=tick)
    for p in players:
        state.players[p.player_id] = p
    return state


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


# ---------------------------------------------------------------------------
# Witness departures / arrivals
# ---------------------------------------------------------------------------

def test_stationary_witness_sees_multi_tick_departure() -> None:
    gm = _three_room_map()
    vision = VisionSystem(gm, visibility_range=0)
    alice = Player(player_id="p0", name="Alice", current_room="medbay")
    bob = Player(player_id="p1", name="Bob", current_room="cafeteria",
                 moving_from="medbay", moving_to="cafeteria", move_ticks_remaining=1)
    state = _state([alice, bob], tick=5)
    state.tick_movements.append({
        "type": "departed", "player_id": "p1", "from_room": "medbay",
        "to_room": "cafeteria", "multi_tick": True, "tick": 5,
    })

    obs = vision.build_observation(alice, state, gm)

    deps = obs["transit_observations"]["departures"]
    assert len(deps) == 1
    assert deps[0]["name"] == "Bob"
    assert deps[0]["to_room"] == "cafeteria"
    assert deps[0]["multi_tick"] is True
    assert obs["transit_observations"]["arrivals"] == []


def test_stationary_witness_sees_instant_departure_and_arrival() -> None:
    gm = _three_room_map()
    vision = VisionSystem(gm, visibility_range=0)
    alice = Player(player_id="p0", name="Alice", current_room="medbay")
    bob = Player(player_id="p1", name="Bob", current_room="electrical")
    carol = Player(player_id="p2", name="Carol", current_room="medbay")
    state = _state([alice, bob, carol], tick=7)
    # Bob did an instant move medbay -> electrical (weight 1)
    state.tick_movements.append({
        "type": "departed", "player_id": "p1", "from_room": "medbay",
        "to_room": "electrical", "multi_tick": False, "tick": 7,
    })
    state.tick_movements.append({
        "type": "arrived", "player_id": "p1", "from_room": "medbay",
        "to_room": "electrical", "multi_tick": False, "tick": 7,
    })
    # Carol arrived from electrical (instant move)
    state.tick_movements.append({
        "type": "departed", "player_id": "p2", "from_room": "electrical",
        "to_room": "medbay", "multi_tick": False, "tick": 7,
    })
    state.tick_movements.append({
        "type": "arrived", "player_id": "p2", "from_room": "electrical",
        "to_room": "medbay", "multi_tick": False, "tick": 7,
    })

    obs = vision.build_observation(alice, state, gm)

    deps = obs["transit_observations"]["departures"]
    arrs = obs["transit_observations"]["arrivals"]
    assert len(deps) == 1 and deps[0]["name"] == "Bob"
    assert len(arrs) == 1 and arrs[0]["name"] == "Carol"
    assert arrs[0]["from_room"] == "electrical"


def test_stationary_witness_sees_multi_tick_arrival() -> None:
    gm = _three_room_map()
    vision = VisionSystem(gm, visibility_range=0)
    alice = Player(player_id="p0", name="Alice", current_room="medbay")
    bob = Player(player_id="p1", name="Bob", current_room="medbay")
    state = _state([alice, bob], tick=10)
    state.tick_movements.append({
        "type": "arrived", "player_id": "p1", "from_room": "cafeteria",
        "to_room": "medbay", "multi_tick": True, "tick": 10,
    })

    obs = vision.build_observation(alice, state, gm)

    arrs = obs["transit_observations"]["arrivals"]
    assert len(arrs) == 1
    assert arrs[0]["name"] == "Bob"
    assert arrs[0]["from_room"] == "cafeteria"


def test_self_movement_not_reported_to_self() -> None:
    """The agent that itself moved should not see its own departure."""
    gm = _three_room_map()
    vision = VisionSystem(gm, visibility_range=0)
    alice = Player(
        player_id="p0", name="Alice", current_room="cafeteria",
        moving_from="medbay", moving_to="cafeteria", move_ticks_remaining=0,
    )
    state = _state([alice], tick=4)
    state.tick_movements.append({
        "type": "departed", "player_id": "p0", "from_room": "medbay",
        "to_room": "cafeteria", "multi_tick": False, "tick": 4,
    })
    state.tick_movements.append({
        "type": "arrived", "player_id": "p0", "from_room": "medbay",
        "to_room": "cafeteria", "multi_tick": False, "tick": 4,
    })

    obs = vision.build_observation(alice, state, gm)

    assert obs["transit_observations"]["departures"] == []
    assert obs["transit_observations"]["arrivals"] == []


def test_transit_viewer_sees_no_room_movements_but_co_direction() -> None:
    gm = _three_room_map()
    vision = VisionSystem(gm, visibility_range=0)
    alice = Player(
        player_id="p0", name="Alice", current_room="cafeteria",
        moving_from="cafeteria", moving_to="medbay", move_ticks_remaining=1,
    )
    bob = Player(
        player_id="p1", name="Bob", current_room="cafeteria",
        moving_from="cafeteria", moving_to="medbay", move_ticks_remaining=1,
    )
    carol = Player(
        player_id="p2", name="Carol", current_room="medbay",
        moving_from="medbay", moving_to="cafeteria", move_ticks_remaining=1,
    )
    state = _state([alice, bob, carol], tick=6)
    # Random unrelated room movement that a stationary viewer in cafeteria
    # would see — but Alice is in transit, so she must NOT see it.
    state.tick_movements.append({
        "type": "departed", "player_id": "x", "from_room": "cafeteria",
        "to_room": "electrical", "multi_tick": True, "tick": 6,
    })

    obs = vision.build_observation(alice, state, gm)

    assert obs["transit_observations"]["departures"] == []
    assert obs["transit_observations"]["arrivals"] == []
    by_name = {p["name"]: p for p in obs["visible_players"]}
    assert by_name["Bob"]["co_direction"] == "same"
    assert by_name["Bob"]["in_transit"] is True
    assert by_name["Carol"]["co_direction"] == "opposite"


def test_get_witnessed_movements_filters_other_rooms() -> None:
    gm = _three_room_map()
    vision = VisionSystem(gm, visibility_range=0)
    alice = Player(player_id="p0", name="Alice", current_room="medbay")
    state = _state([alice], tick=3)
    state.tick_movements.append({
        "type": "departed", "player_id": "x", "from_room": "cafeteria",
        "to_room": "electrical", "multi_tick": False, "tick": 3,
    })
    state.tick_movements.append({
        "type": "arrived", "player_id": "y", "from_room": "electrical",
        "to_room": "cafeteria", "multi_tick": True, "tick": 3,
    })

    result = vision.get_witnessed_movements(alice, state)
    assert result == []
