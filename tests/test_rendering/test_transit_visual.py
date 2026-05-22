"""Tests for end-of-tick visual transit placement in MapRenderer."""

from __future__ import annotations

from quack.engine.game_state import GamePhase, GameState, Player, Team
from quack.map.game_map import GameMap, Room
from quack.rendering.map_renderer import MapRenderer


def _storage_medbay_map() -> GameMap:
    gm = GameMap()
    gm.add_room(Room("storage", 7, 9, size=3))
    gm.add_room(Room("medbay", 5, 5, size=2))
    gm.add_room(Room("cafeteria", 7, 1, size=3))
    gm.add_corridor("storage", "medbay", 2)
    gm.add_corridor("medbay", "cafeteria", 1)
    return gm


def _frank_in_transit(remaining: int) -> Player:
    return Player(
        player_id="player_5",
        name="Frank",
        team=Team.GOOSE,
        current_room="storage",
        moving_from="storage",
        moving_to="medbay",
        move_ticks_remaining=remaining,
    )


def test_visual_transit_departure_tick_weight2() -> None:
    renderer = MapRenderer(_storage_medbay_map())
    vt = renderer._visual_transit(_frank_in_transit(remaining=2))
    assert vt is not None
    assert vt.on_corridor is True
    assert vt.corridor_progress == 0.5
    assert vt.display_room == "storage"
    assert renderer._player_display_room(_frank_in_transit(2)) == "storage → medbay"


def test_visual_transit_penultimate_tick_weight2_shows_arrived() -> None:
    renderer = MapRenderer(_storage_medbay_map())
    frank = _frank_in_transit(remaining=1)
    vt = renderer._visual_transit(frank)
    assert vt is not None
    assert vt.on_corridor is False
    assert vt.display_room == "medbay"
    assert renderer._player_display_room(frank) == "medbay"
    assert renderer._transit_corridor_xy(frank, scale=1.2) is None


def test_visual_transit_weight3_progression() -> None:
    gm = GameMap()
    gm.add_room(Room("a", 0, 0))
    gm.add_room(Room("b", 5, 0))
    gm.add_corridor("a", "b", 3)
    renderer = MapRenderer(gm)
    p = Player(
        player_id="p0",
        name="P",
        current_room="a",
        moving_to="b",
        move_ticks_remaining=3,
    )
    vt = renderer._visual_transit(p)
    assert vt is not None and vt.on_corridor
    assert abs(vt.corridor_progress - 1 / 3) < 0.01

    p.move_ticks_remaining = 2
    vt = renderer._visual_transit(p)
    assert vt is not None and vt.on_corridor
    assert abs(vt.corridor_progress - 2 / 3) < 0.01

    p.move_ticks_remaining = 1
    vt = renderer._visual_transit(p)
    assert vt is not None and not vt.on_corridor and vt.display_room == "b"


def test_god_view_places_frank_on_corridor_after_departure() -> None:
    gm = _storage_medbay_map()
    renderer = MapRenderer(gm)
    renderer.assign_player_colors(["player_5"])
    renderer.set_player_names({"player_5": "Frank"})
    state = GameState(phase=GamePhase.FREE_ROAM, current_tick=25)
    state.players["player_5"] = _frank_in_transit(remaining=2)

    img = renderer.render_god_view(state=state, vision_system=object(), tick=25)
    storage = gm.rooms["storage"]
    medbay = gm.rooms["medbay"]
    scale = 1.2

    def room_center(room: Room) -> tuple[int, int]:
        return renderer._room_center(room, scale)

    sc = room_center(storage)
    mc = room_center(medbay)
    corridor = renderer._transit_corridor_xy(state.players["player_5"], scale)
    assert corridor is not None
    cx, cy = corridor
    expected_x = int(sc[0] + (mc[0] - sc[0]) * 0.5)
    expected_y = int(sc[1] + (mc[1] - sc[1]) * 0.5)
    assert abs(cx - expected_x) <= 2
    assert abs(cy - expected_y) <= 2
    assert abs(cx - sc[0]) > 20 or abs(cy - sc[1]) > 20

    state.players["player_5"].move_ticks_remaining = 0
    state.players["player_5"].moving_to = ""
    img_standing = renderer.render_god_view(state=state, vision_system=object(), tick=24)
    assert img.tobytes() != img_standing.tobytes()


def test_god_view_places_frank_in_medbay_when_remaining_one() -> None:
    gm = _storage_medbay_map()
    renderer = MapRenderer(gm)
    renderer.assign_player_colors(["player_5"])
    renderer.set_player_names({"player_5": "Frank"})
    state = GameState(phase=GamePhase.FREE_ROAM, current_tick=26)
    state.players["player_5"] = _frank_in_transit(remaining=1)

    img_arrived = renderer.render_god_view(state=state, vision_system=object(), tick=26)

    state.players["player_5"].move_ticks_remaining = 0
    state.players["player_5"].moving_to = ""
    state.players["player_5"].current_room = "storage"
    img_storage = renderer.render_god_view(state=state, vision_system=object(), tick=25)

    state.players["player_5"] = _frank_in_transit(remaining=2)
    img_corridor = renderer.render_god_view(state=state, vision_system=object(), tick=25)

    assert img_arrived.tobytes() != img_storage.tobytes()
    assert img_arrived.tobytes() != img_corridor.tobytes()
