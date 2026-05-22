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


def test_visual_transit_two_ticks_left_on_weight2() -> None:
    renderer = MapRenderer(_storage_medbay_map())
    vt = renderer._visual_transit(_frank_in_transit(remaining=2))
    assert vt is not None
    assert vt.on_corridor is True
    assert vt.corridor_progress == 0.25
    assert vt.display_room == "storage"


def test_visual_transit_one_tick_left_on_weight2() -> None:
    renderer = MapRenderer(_storage_medbay_map())
    vt = renderer._visual_transit(_frank_in_transit(remaining=1))
    assert vt is not None
    assert vt.on_corridor is True
    assert vt.corridor_progress == 0.5


def test_snapshot_next_tick_start_completes_weight2_arrival() -> None:
    renderer = MapRenderer(_storage_medbay_map())
    state = GameState(phase=GamePhase.FREE_ROAM, current_tick=23)
    state.players["player_5"] = _frank_in_transit(remaining=1)

    snap = renderer._snapshot_next_tick_start(state)
    frank = snap.players["player_5"]
    assert not frank.is_in_transit
    assert frank.current_room == "medbay"
    assert renderer._visual_transit(frank) is None
    assert renderer._player_display_room(frank) == "medbay"


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
    assert abs(vt.corridor_progress - 0.25) < 0.01

    p.move_ticks_remaining = 2
    vt = renderer._visual_transit(p)
    assert vt is not None and vt.on_corridor
    assert abs(vt.corridor_progress - 1 / 3) < 0.01

    p.move_ticks_remaining = 1
    vt = renderer._visual_transit(p)
    assert vt is not None and vt.on_corridor
    assert abs(vt.corridor_progress - 2 / 3) < 0.01


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
    display = renderer._snapshot_next_tick_start(state).players["player_5"]
    corridor = renderer._transit_corridor_xy(display, scale)
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


def test_god_view_pov_uses_next_tick_start_visibility() -> None:
    """Tick N end frame shows tick N+1 start: Frank sees Charlie in storage."""
    from quack.systems.vision import VisionSystem

    gm = _storage_medbay_map()
    gm.add_room(Room("lower_engine", 1, 9, size=2))
    gm.add_corridor("lower_engine", "storage", 2)

    renderer = MapRenderer(gm)
    renderer.assign_player_colors(["player_2", "player_5"])
    renderer.set_player_names({"player_2": "Charlie", "player_5": "Frank"})

    state = GameState(phase=GamePhase.FREE_ROAM, current_tick=23)
    charlie = Player(
        player_id="player_2",
        name="Charlie",
        current_room="lower_engine",
        moving_to="storage",
        move_ticks_remaining=1,
    )
    frank = Player(
        player_id="player_5",
        name="Frank",
        team=Team.GOOSE,
        current_room="storage",
    )
    state.players["player_2"] = charlie
    state.players["player_5"] = frank

    vision = VisionSystem(gm, visibility_range=0)
    display = renderer._snapshot_next_tick_start(state)
    charlie_display = display.players["player_2"]
    assert charlie_display.current_room == "storage"
    assert not charlie_display.is_in_transit

    vis = vision.compute_visibility(charlie_display, display)
    assert vis.visible_rooms == {"storage"}
    assert vis.visible_players == ["player_5"]

    vis_frank = vision.compute_visibility(display.players["player_5"], display)
    assert vis_frank.visible_players == ["player_2"]


def test_respawn_frame_does_not_advance_transit() -> None:
    renderer = MapRenderer(_storage_medbay_map())
    state = GameState(phase=GamePhase.FREE_ROAM, current_tick=21)
    state.players["player_5"] = _frank_in_transit(remaining=1)

    assert not renderer._use_next_tick_snapshot(state, "Respawn (post-meeting)")
    display = state
    if renderer._use_next_tick_snapshot(state, "Respawn (post-meeting)"):
        display = renderer._snapshot_next_tick_start(state)
    frank = display.players["player_5"]
    assert frank.is_in_transit
    assert frank.current_room == "storage"


def test_max_ticks_game_over_still_uses_next_tick_snapshot() -> None:
    """Last frame on max ticks: phase is GAME_OVER but tick_end completed."""
    renderer = MapRenderer(_storage_medbay_map())
    state = GameState(phase=GamePhase.GAME_OVER, current_tick=50)
    state.max_ticks = 50
    state.players["player_5"] = _frank_in_transit(remaining=1)

    assert renderer._use_next_tick_snapshot(state, None)
    snap = renderer._snapshot_next_tick_start(state)
    frank = snap.players["player_5"]
    assert not frank.is_in_transit
    assert frank.current_room == "medbay"


def test_partial_tick_meeting_interrupt_does_not_advance() -> None:
    renderer = MapRenderer(_storage_medbay_map())
    state = GameState(phase=GamePhase.DISCUSSION, current_tick=10)
    state.players["player_5"] = _frank_in_transit(remaining=1)

    assert not renderer._use_next_tick_snapshot(state, None)
    display = state
    frank = display.players["player_5"]
    assert frank.is_in_transit
    assert renderer._visual_transit(frank) is not None


def test_dead_player_local_view_is_grayscale() -> None:
    renderer = MapRenderer(_storage_medbay_map())
    state = GameState(phase=GamePhase.FREE_ROAM, current_tick=5)
    alive = Player(
        player_id="player_0", name="Alice", team=Team.GOOSE,
        current_room="storage", is_alive=True,
    )
    dead = Player(
        player_id="player_1", name="Eve", team=Team.GOOSE,
        current_room="storage", is_alive=False,
    )
    state.players["player_0"] = alive
    state.players["player_1"] = dead

    img_alive = renderer.render_local_view(
        state, alive, {"storage"}, [], [], witnessed_events=[],
    )
    img_dead = renderer.render_local_view(
        state, dead, {"storage"}, [], [], witnessed_events=[],
    )
    assert img_alive.tobytes() != img_dead.tobytes()

    # Grayscale pixels have R == G == B for the map region (below title bar).
    title_h = 58
    px = img_dead.getpixel((img_dead.width // 2, title_h + 20))
    assert px[0] == px[1] == px[2]
