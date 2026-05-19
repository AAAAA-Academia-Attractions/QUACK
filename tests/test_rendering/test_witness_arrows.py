"""Tests for witness-arrow rendering in render_local_view."""

from __future__ import annotations

from quack.engine.game_state import GamePhase, GameState, Player, Team
from quack.map.game_map import GameMap, Room
from quack.rendering.map_renderer import MapRenderer
from quack.systems.vision import VisionSystem


def _three_room_map() -> GameMap:
    gm = GameMap()
    gm.add_room(Room("cafeteria", 1, 1))
    gm.add_room(Room("medbay", 5, 1))
    gm.add_room(Room("electrical", 9, 1))
    gm.add_corridor("cafeteria", "medbay", 2)
    gm.add_corridor("medbay", "electrical", 1)
    return gm


def _setup_state(tick: int = 5) -> tuple[GameState, MapRenderer, Player]:
    gm = _three_room_map()
    renderer = MapRenderer(gm)
    renderer.assign_player_colors(["p0", "p1", "p2"])
    renderer.set_player_names({"p0": "Alice", "p1": "Bob", "p2": "Carol"})
    state = GameState(phase=GamePhase.FREE_ROAM, current_tick=tick)
    state.players["p0"] = Player(
        player_id="p0", name="Alice", team=Team.GOOSE, current_room="medbay",
    )
    state.players["p1"] = Player(
        player_id="p1", name="Bob", team=Team.GOOSE, current_room="medbay",
    )
    state.players["p2"] = Player(
        player_id="p2", name="Carol", team=Team.GOOSE, current_room="medbay",
    )
    viewer = state.players["p0"]
    return state, renderer, viewer


def test_render_local_view_empty_events_matches_no_events() -> None:
    state, renderer, viewer = _setup_state()
    img_a = renderer.render_local_view(
        state=state, player=viewer,
        visible_rooms={"medbay"}, visible_players=["p1", "p2"], visible_bodies=[],
        witnessed_events=[],
    )
    img_b = renderer.render_local_view(
        state=state, player=viewer,
        visible_rooms={"medbay"}, visible_players=["p1", "p2"], visible_bodies=[],
    )
    assert img_a.tobytes() == img_b.tobytes()


def test_render_local_view_with_events_differs_from_empty() -> None:
    state, renderer, viewer = _setup_state()
    witnessed = [
        {"type": "departed", "player_id": "p1", "from_room": "medbay",
         "to_room": "cafeteria", "multi_tick": True, "tick": 5},
        {"type": "arrived", "player_id": "p2", "from_room": "electrical",
         "to_room": "medbay", "multi_tick": True, "tick": 5},
    ]
    img_a = renderer.render_local_view(
        state=state, player=viewer,
        visible_rooms={"medbay"}, visible_players=[], visible_bodies=[],
        witnessed_events=witnessed,
    )
    img_b = renderer.render_local_view(
        state=state, player=viewer,
        visible_rooms={"medbay"}, visible_players=[], visible_bodies=[],
        witnessed_events=[],
    )
    assert img_a.tobytes() != img_b.tobytes()


def test_arrows_only_drawn_for_viewer_room_events() -> None:
    """Events on corridors not touching the viewer's room must not change the image."""
    state, renderer, viewer = _setup_state()
    irrelevant = [
        {"type": "departed", "player_id": "p1", "from_room": "cafeteria",
         "to_room": "electrical", "multi_tick": False, "tick": 5},
    ]
    img_a = renderer.render_local_view(
        state=state, player=viewer,
        visible_rooms={"medbay"}, visible_players=[], visible_bodies=[],
        witnessed_events=irrelevant,
    )
    img_b = renderer.render_local_view(
        state=state, player=viewer,
        visible_rooms={"medbay"}, visible_players=[], visible_bodies=[],
        witnessed_events=[],
    )
    assert img_a.tobytes() == img_b.tobytes()


def test_transit_viewer_skips_arrows() -> None:
    state, renderer, viewer = _setup_state()
    viewer.moving_from = "medbay"
    viewer.moving_to = "electrical"
    viewer.move_ticks_remaining = 1
    witnessed = [
        {"type": "departed", "player_id": "p1", "from_room": "medbay",
         "to_room": "cafeteria", "multi_tick": True, "tick": 5},
    ]
    img_a = renderer.render_local_view(
        state=state, player=viewer,
        visible_rooms={"medbay", "electrical"}, visible_players=[], visible_bodies=[],
        witnessed_events=witnessed,
    )
    img_b = renderer.render_local_view(
        state=state, player=viewer,
        visible_rooms={"medbay", "electrical"}, visible_players=[], visible_bodies=[],
        witnessed_events=[],
    )
    assert img_a.tobytes() == img_b.tobytes()


def test_image_arrow_set_matches_observation_filter() -> None:
    """The events used to draw arrows must match the observation's transit_observations."""
    gm = _three_room_map()
    vision = VisionSystem(gm, visibility_range=0)
    state, renderer, viewer = _setup_state(tick=12)
    state.tick_movements.append({
        "type": "departed", "player_id": "p1", "from_room": "medbay",
        "to_room": "cafeteria", "multi_tick": True, "tick": 12,
    })
    state.tick_movements.append({
        "type": "arrived", "player_id": "p2", "from_room": "electrical",
        "to_room": "medbay", "multi_tick": True, "tick": 12,
    })
    state.tick_movements.append({
        "type": "departed", "player_id": "p1", "from_room": "cafeteria",
        "to_room": "electrical", "multi_tick": True, "tick": 12,
    })

    obs = vision.build_observation(viewer, state, gm)
    witnessed = vision.get_witnessed_movements(viewer, state)

    dep_obs = {(d["name"], d["to_room"]) for d in obs["transit_observations"]["departures"]}
    arr_obs = {(a["name"], a["from_room"]) for a in obs["transit_observations"]["arrivals"]}

    dep_render = {
        (state.players[ev["player_id"]].name, ev["to_room"])
        for ev in witnessed if ev["type"] == "departed"
    }
    arr_render = {
        (state.players[ev["player_id"]].name, ev["from_room"])
        for ev in witnessed if ev["type"] == "arrived"
    }
    assert dep_obs == dep_render
    assert arr_obs == arr_render
