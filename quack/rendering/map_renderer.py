"""Pillow-based map renderer — generates global fog map and local view images.

Produces two views per agent per tick:
1. Global map with fog of war, legend, and HUD
2. Local zoomed-in view of current room + neighbors
"""

from __future__ import annotations

import os
import platform
from copy import copy
from typing import TYPE_CHECKING, NamedTuple

from PIL import Image, ImageDraw, ImageFont, ImageOps

from quack.rendering.colors import (BACKGROUND_COLOR, BODY_FILL, CELL_SIZE,
                                     CORRIDOR_COLOR, CORRIDOR_COLOR_DIM,
                                     EMERGENCY_BORDER, EMERGENCY_FILL,
                                     FOG_BORDER, FOG_FILL, FOG_LABEL_COLOR,
                                     GOD_EVENT_KILL_COLOR, GOD_EVENT_MOVE_COLOR,
                                     GOD_EVENT_TASK_COLOR, GOD_PANEL_BG,
                                     GOD_PANEL_BORDER, GOD_ROLE_DUCK_COLOR,
                                     GOD_ROLE_GOOSE_COLOR, GOD_SPRITE_SCALE,
                                     GOD_VIEW_HUD_H, GOD_VIEW_PANEL_W,
                                     GOD_VIEW_POV_LABEL_H, GOD_VIEW_SCALE,
                                     HUD_BG, HUD_BORDER, LOCAL_VIEW_CROP_HALF,
                                     LOCAL_VIEW_SCALE, LOCAL_VIEW_SPRITE_SCALE,
                                     LOCAL_VIEW_TITLE_H, PADDING, PLAYER_COLORS, ROOM_BORDER,
                                     ROOM_BORDER_CURRENT, ROOM_FILL,
                                     ROOM_FILL_CURRENT, ROOM_TITLE_BG,
                                     DEAD_POV_TITLE_BG, DEAD_POV_TITLE_TEXT,
                                     TASK_COMPLETE_BORDER, TASK_COMPLETE_FILL,
                                     TASK_INCOMPLETE_BORDER,
                                     TASK_INCOMPLETE_FILL, TEXT_DIM,
                                     TEXT_LIGHT, TEXT_WHITE,
                                     VISION_HALO_ALPHA, WEIGHT_BADGE_BORDER,
                                     WEIGHT_BADGE_FILL)
from quack.rendering.room_decor import draw_room_decoration, get_room_fill
from quack.rendering.sprites import SpriteSheet

if TYPE_CHECKING:
    from quack.engine.game_state import GameState, Player
    from quack.map.game_map import GameMap, Room


class _VisualTransit(NamedTuple):
    """Renderer-only end-of-tick placement (does not mutate engine state)."""

    on_corridor: bool
    corridor_progress: float
    display_room: str


_CHINESE_FONT_PATHS = [
    "/usr/share/fonts/opentype/noto-cjk/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    "/usr/share/fonts/wqy-zenhei/wqy-zenhei.ttc",
]

_DEJAVU_FONT_PATHS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/TTF/DejaVuSans.ttf",
]

_WINDOWS_FONT_PATHS = [
    os.path.expandvars(r"C:\Windows\Fonts\segoeuib.ttf"),
    os.path.expandvars(r"C:\Windows\Fonts\segoeui.ttf"),
    os.path.expandvars(r"C:\Windows\Fonts\arialbd.ttf"),
    os.path.expandvars(r"C:\Windows\Fonts\arial.ttf"),
    os.path.expandvars(r"C:\Windows\Fonts\msyh.ttc"),
]


def _try_load_font(size: int = 12, prefer_chinese: bool = True) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Load a font. Tries Chinese-capable fonts first (for CJK speech rendering)."""
    paths = list(_CHINESE_FONT_PATHS if prefer_chinese else [])
    if platform.system() == "Windows":
        paths.extend(_WINDOWS_FONT_PATHS)
    paths.extend(_DEJAVU_FONT_PATHS)
    for p in paths:
        try:
            return ImageFont.truetype(p, size)
        except OSError:
            continue
    return ImageFont.load_default()


class MapRenderer:
    """Renders the game map to PIL Images with clear, VLM-readable visuals."""

    def __init__(self, game_map: GameMap, player_color_map: dict[str, int] | None = None):
        self.game_map = game_map
        self.player_color_map = player_color_map or {}
        self._player_names: dict[str, str] = {}
        self.sprites = SpriteSheet()
        self.last_actions: dict[str, str] = {}

        self._font_xs = _try_load_font(11)
        self._font_sm = _try_load_font(14)
        self._font_md = _try_load_font(17)
        self._font_lg = _try_load_font(22)
        self._font_xl = _try_load_font(28)
        self._font_room = _try_load_font(24)
        self._font_weight = _try_load_font(28)
        self._font_log = _try_load_font(15)

        xs = [r.x for r in game_map.rooms.values()]
        ys = [r.y for r in game_map.rooms.values()]
        sizes = [r.size for r in game_map.rooms.values()]
        max_size = max(sizes) if sizes else 2
        self._min_x = min(xs) - max_size
        self._min_y = min(ys) - max_size
        self._max_x = max(xs) + max_size
        self._max_y = max(ys) + max_size

    def assign_player_colors(self, player_ids: list[str]) -> None:
        for i, pid in enumerate(player_ids):
            self.player_color_map[pid] = i
        color_map = {pid: self._get_player_color(pid) for pid in player_ids}
        self.sprites.generate_all(player_ids, color_map)

    def set_player_names(self, names: dict[str, str]) -> None:
        self._player_names = dict(names)

    def _get_player_color(self, player_id: str) -> tuple[int, int, int]:
        idx = self.player_color_map.get(player_id, hash(player_id) % len(PLAYER_COLORS))
        return PLAYER_COLORS[idx % len(PLAYER_COLORS)]

    def _get_player_name(self, player_id: str) -> str:
        return self._player_names.get(player_id, player_id)

    def _snapshot_next_tick_start(self, state: GameState) -> GameState:
        """Render-only copy of *state* after one ``_advance_transit`` pass.

        God-view frames are saved at tick *N* end; for visualization we show
        what the map looks like at tick *N+1* start (before anyone acts).
        """
        snap = copy(state)
        snap.players = {}
        for pid, player in state.players.items():
            p = copy(player)
            if p.is_in_transit:
                p.move_ticks_remaining -= 1
                if p.move_ticks_remaining <= 0:
                    p.current_room = p.moving_to
                    p.moving_from = ""
                    p.moving_to = ""
                    p.move_ticks_remaining = 0
            snap.players[pid] = p
        return snap

    def _use_next_tick_snapshot(
        self, state: GameState, phase_override: str | None,
    ) -> bool:
        """Whether god-view should show tick N+1 start (one transit advance).

        Skip for spawn / post-meeting respawn and for partial free-roam ticks
        cut short by a meeting (no ``tick_end`` — phase already left FREE_ROAM).
        """
        if phase_override in ("Spawn", "Respawn (post-meeting)"):
            return False
        from quack.engine.game_state import GamePhase
        return state.phase == GamePhase.FREE_ROAM

    def _visual_transit(self, player: Player) -> _VisualTransit | None:
        """Corridor placement for a player still ``is_in_transit``.

        Expects the post-``_advance_transit`` room/remaining values used by
        god-view rendering (see ``_snapshot_next_tick_start``).  Arrivals are
        committed to ``current_room`` and return ``None`` here.
        """
        if not player.is_in_transit or not player.moving_to:
            return None
        if (
            player.current_room not in self.game_map.rooms
            or player.moving_to not in self.game_map.rooms
        ):
            return None
        weight = self.game_map.get_corridor_weight(
            player.current_room, player.moving_to,
        )
        total = max(1, weight)
        elapsed = total - player.move_ticks_remaining
        progress = elapsed / total
        progress = max(0.25, min(0.75, progress))
        return _VisualTransit(
            on_corridor=True,
            corridor_progress=progress,
            display_room=player.current_room,
        )

    def _player_display_room(self, player: Player) -> str:
        """Human-readable room label for panels / POV captions."""
        if not player.is_alive:
            return player.current_room
        vt = self._visual_transit(player)
        if vt is None:
            return player.current_room
        return f"{player.current_room} → {player.moving_to}"

    def _transit_corridor_xy(
        self, player: Player, scale: float, offset_y: int = 0,
    ) -> tuple[int, int] | None:
        """Pixel position when the player is visually on a corridor segment."""
        vt = self._visual_transit(player)
        if vt is None or not vt.on_corridor:
            return None
        room_a = self.game_map.rooms.get(player.current_room)
        room_b = self.game_map.rooms.get(player.moving_to)
        if not room_a or not room_b:
            return None
        ca = self._room_center(room_a, scale)
        cb = self._room_center(room_b, scale)
        ca = (ca[0], ca[1] + offset_y)
        cb = (cb[0], cb[1] + offset_y)
        p = vt.corridor_progress
        return (
            int(ca[0] + (cb[0] - ca[0]) * p),
            int(ca[1] + (cb[1] - ca[1]) * p),
        )

    def _get_sprite_variant(self, player_id: str, is_alive: bool = True) -> str:
        if not is_alive:
            return "dead"
        action = self.last_actions.get(player_id, "")
        if action.startswith("move"):
            return "walk"
        if action.startswith("do_task"):
            return "task"
        if action.startswith("report"):
            return "report"
        return "idle"

    def _paste_sprite(
        self, img: Image.Image, player_id: str, x: int, y: int,
        scale: int = 2, variant: str | None = None,
    ) -> None:
        """Paste a sprite centered at (x, y) onto img."""
        if variant is None:
            variant = self._get_sprite_variant(player_id)
        sprite = self.sprites.get_sprite(player_id, variant, scale)
        sw, sh = sprite.size
        paste_x = x - sw // 2
        paste_y = y - sh // 2
        img.paste(sprite, (paste_x, paste_y), sprite)

    # ---- Coordinate helpers ----

    def _room_rect(self, room: Room, scale: float = 1.0) -> tuple[int, int, int, int]:
        half = room.size * CELL_SIZE * scale / 2
        cx, cy = self._room_center(room, scale)
        return (int(cx - half), int(cy - half), int(cx + half), int(cy + half))

    def _room_center(self, room: Room, scale: float = 1.0) -> tuple[int, int]:
        cx = (room.x - self._min_x) * CELL_SIZE * scale + PADDING
        cy = (room.y - self._min_y) * CELL_SIZE * scale + PADDING
        return int(cx), int(cy)

    def _canvas_size(self, scale: float = 1.0) -> tuple[int, int]:
        w = int((self._max_x - self._min_x) * CELL_SIZE * scale + 2 * PADDING)
        h = int((self._max_y - self._min_y) * CELL_SIZE * scale + 2 * PADDING)
        return w, h

    def _draw_room_title_bar(
        self,
        draw: ImageDraw.Draw,
        rect: tuple[int, int, int, int],
        title: str,
        *,
        highlight: bool = False,
    ) -> None:
        """Full-width title band at the top of a room (schematic style)."""
        x1, y1, x2, y2 = rect
        bar_h = max(26, int((x2 - x1) * 0.16))
        inner = (x1 + 3, y1 + 3, x2 - 3, y1 + 3 + bar_h)
        bg = (45, 75, 130) if highlight else ROOM_TITLE_BG
        draw.rounded_rectangle(inner, radius=6, fill=bg)
        draw.text(
            ((x1 + x2) // 2, y1 + 3 + bar_h // 2),
            title.replace("_", " ").upper(),
            fill=TEXT_WHITE,
            font=self._font_room,
            anchor="mm",
        )

    def _draw_nameplate(
        self,
        draw: ImageDraw.Draw,
        x: int,
        y: int,
        label: str,
        color: tuple[int, int, int],
        *,
        font: ImageFont.FreeTypeFont | ImageFont.ImageFont | None = None,
        accent: tuple[int, int, int] | None = None,
    ) -> None:
        """Color-coded name tag — easy to spot in god view and POV."""
        font = font or self._font_md
        bbox = draw.textbbox((0, 0), label, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        pad_x, pad_y = (12, 6) if font is self._font_lg else (10, 5)
        bx0 = x - tw // 2 - pad_x
        by0 = y - th // 2 - pad_y
        bx1 = x + tw // 2 + pad_x
        by1 = y + th // 2 + pad_y
        fill = accent or color
        draw.rounded_rectangle(
            (bx0, by0, bx1, by1), radius=5,
            fill=fill, outline=TEXT_WHITE, width=1,
        )
        draw.text((x, y), label, fill=TEXT_WHITE, font=font, anchor="mm")

    def _draw_weight_badge(
        self,
        draw: ImageDraw.Draw,
        mx: int,
        my: int,
        weight: int,
    ) -> None:
        """Prominent corridor travel-time badge."""
        label = str(weight)
        bbox = draw.textbbox((0, 0), label, font=self._font_weight)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        r = max(28, max(tw, th) // 2 + 16)
        draw.ellipse(
            (mx - r, my - r, mx + r, my + r),
            fill=WEIGHT_BADGE_FILL,
            outline=WEIGHT_BADGE_BORDER,
            width=3,
        )
        draw.text((mx, my), label, fill=TEXT_WHITE, font=self._font_weight, anchor="mm")

    def _draw_agent_marker(
        self,
        img: Image.Image,
        draw: ImageDraw.Draw,
        pid: str,
        x: int,
        y: int,
        *,
        sprite_scale: int = GOD_SPRITE_SCALE,
        variant: str | None = None,
        name_override: str | None = None,
        accent: tuple[int, int, int] | None = None,
        name_font: ImageFont.FreeTypeFont | ImageFont.ImageFont | None = None,
    ) -> None:
        """Small sprite + colored nameplate (shared by god view and local view)."""
        self._paste_sprite(img, pid, x, y - 6, scale=sprite_scale, variant=variant)
        label = name_override or self._get_player_name(pid)
        plate_y = y + int(8 * sprite_scale + 4)
        self._draw_nameplate(
            draw, x, plate_y, label,
            self._get_player_color(pid),
            accent=accent,
            font=name_font,
        )

    # ================================================================
    #  GLOBAL MAP
    # ================================================================

    def render_global_map(
        self,
        state: GameState,
        revealed_rooms: set[str],
        viewer_room: str,
        visible_players: list[str],
        visible_bodies: list[str],
        viewer_id: str = "",
        tick: int = 0,
    ) -> Image.Image:
        """Render the full map with fog of war, player icons, legend, and HUD."""
        scale = 1.0
        w, h = self._canvas_size(scale)

        hud_height = 50
        legend_height = self._calc_legend_height(state, visible_players, viewer_id)
        total_h = hud_height + h + legend_height

        img = Image.new("RGB", (w, total_h), BACKGROUND_COLOR)
        draw = ImageDraw.Draw(img)

        self._draw_hud(draw, w, hud_height, state, viewer_id, tick)

        map_offset_y = hud_height
        self._draw_corridors_global(draw, scale, revealed_rooms, map_offset_y)
        self._draw_rooms_global(draw, scale, state, revealed_rooms, viewer_room, map_offset_y)
        self._draw_task_markers(draw, scale, state, revealed_rooms, map_offset_y)
        self._draw_body_markers(img, draw, scale, state, visible_bodies, map_offset_y)
        self._draw_player_markers(img, draw, scale, state, visible_players, viewer_id, map_offset_y)
        self._draw_transit_players(img, draw, scale, state, visible_players, viewer_id, map_offset_y)
        self._draw_viewer_marker(img, draw, scale, viewer_room, viewer_id, map_offset_y, state)

        legend_y = hud_height + h
        self._draw_legend(draw, w, legend_y, legend_height, state, visible_players, viewer_id)

        return img

    # ---- HUD ----

    def _draw_hud(
        self, draw: ImageDraw.Draw, width: int, height: int,
        state: GameState, viewer_id: str, tick: int,
    ) -> None:
        draw.rectangle((0, 0, width, height), fill=HUD_BG, outline=HUD_BORDER)

        viewer = state.players.get(viewer_id)

        left_text = f"Tick: {tick}  |  Phase: {state.phase.value.replace('_', ' ').title()}"
        draw.text((12, 15), left_text, fill=TEXT_WHITE, font=self._font_lg)

        if viewer:
            completed, total = 0, 0
            from quack.engine.game_state import Team
            for p in state.players.values():
                if p.team == Team.GOOSE:
                    for t in p.tasks:
                        total += 1
                        if t.is_complete:
                            completed += 1
            right_text = f"Tasks: {completed}/{total}  |  Alive: {len(state.alive_players)}/{len(state.players)}"
            bbox = draw.textbbox((0, 0), right_text, font=self._font_md)
            tw = bbox[2] - bbox[0]
            draw.text((width - tw - 12, 17), right_text, fill=TEXT_LIGHT, font=self._font_md)

    # ---- Corridors ----

    def _draw_corridors_global(
        self, draw: ImageDraw.Draw, scale: float, revealed: set[str], offset_y: int,
    ) -> None:
        drawn: set[tuple[str, ...]] = set()
        for room_name in self.game_map.rooms:
            for neighbor in self.game_map.get_neighbors(room_name):
                key = tuple(sorted((room_name, neighbor)))
                if key in drawn:
                    continue
                drawn.add(key)

                room_a = self.game_map.rooms[room_name]
                room_b = self.game_map.rooms[neighbor]
                ca = self._room_center(room_a, scale)
                cb = self._room_center(room_b, scale)
                ca = (ca[0], ca[1] + offset_y)
                cb = (cb[0], cb[1] + offset_y)

                both_visible = room_name in revealed and neighbor in revealed
                color = CORRIDOR_COLOR if both_visible else CORRIDOR_COLOR_DIM
                # Draw corridors a bit thicker so in-transit players clearly
                # appear "in the hallway" instead of overlapping rooms.
                draw.line([ca, cb], fill=color, width=max(4, int(9 * scale)))

                # Weight label at midpoint
                w = self.game_map.get_corridor_weight(room_name, neighbor)
                if w > 1 and both_visible:
                    mx, my = (ca[0] + cb[0]) // 2, (ca[1] + cb[1]) // 2
                    self._draw_weight_badge(draw, mx, my, w)

    # ---- Rooms ----

    def _draw_rooms_global(
        self, draw: ImageDraw.Draw, scale: float, state: GameState,
        revealed: set[str], viewer_room: str, offset_y: int,
    ) -> None:
        for room_name, room in self.game_map.rooms.items():
            rect = self._room_rect(room, scale)
            rect = (rect[0], rect[1] + offset_y, rect[2], rect[3] + offset_y)
            cx, cy = self._room_center(room, scale)
            cy += offset_y

            is_viewer = room_name == viewer_room
            is_revealed = room_name in revealed

            if not is_revealed:
                draw.rectangle(rect, fill=FOG_FILL, outline=FOG_BORDER, width=1)
                label = room_name.replace("_", " ")
                draw.text((cx, cy), label, fill=FOG_LABEL_COLOR, font=self._font_sm, anchor="mm")
                continue

            theme_fill = get_room_fill(room_name)
            fill = ROOM_FILL_CURRENT if is_viewer else (theme_fill or ROOM_FILL)
            border = ROOM_BORDER_CURRENT if is_viewer else ROOM_BORDER
            border_w = 3 if is_viewer else 2
            draw.rounded_rectangle(rect, fill=fill, outline=border, width=border_w)
            draw_room_decoration(draw, room_name, rect, scale)
            if is_revealed:
                self._draw_room_title_bar(draw, rect, room_name, highlight=is_viewer)

            if room.is_emergency_button:
                btn_y = rect[3] - 16
                r = 7
                draw.ellipse((cx - r, btn_y - r, cx + r, btn_y + r),
                             fill=EMERGENCY_FILL, outline=EMERGENCY_BORDER, width=2)
                draw.text((cx, btn_y), "!", fill=TEXT_WHITE, font=self._font_sm, anchor="mm")

    # ---- Task markers ----

    def _draw_task_markers(
        self, draw: ImageDraw.Draw, scale: float, state: GameState,
        revealed: set[str], offset_y: int,
    ) -> None:
        task_info: dict[str, tuple[str, bool]] = {}
        for p in state.players.values():
            for t in p.tasks:
                if t.room in revealed:
                    if t.room not in task_info:
                        task_info[t.room] = (t.task_name, t.is_complete)
                    elif not t.is_complete:
                        task_info[t.room] = (t.task_name, False)

        for room_name, (task_name, completed) in task_info.items():
            room = self.game_map.rooms[room_name]
            rect = self._room_rect(room, scale)
            rect_offset = (rect[0], rect[1] + offset_y, rect[2], rect[3] + offset_y)

            fill = TASK_COMPLETE_FILL if completed else TASK_INCOMPLETE_FILL
            border = TASK_COMPLETE_BORDER if completed else TASK_INCOMPLETE_BORDER
            status_char = "V" if completed else "T"

            icon_x = rect_offset[2] - int(14 * scale)
            icon_y = rect_offset[1] + int(12 * scale)
            r = max(5, int(6 * scale))
            draw.rounded_rectangle(
                (icon_x - r, icon_y - r, icon_x + r, icon_y + r),
                radius=2, fill=fill, outline=border, width=1,
            )
            draw.text((icon_x, icon_y), status_char, fill=TEXT_WHITE, font=self._font_xs, anchor="mm")

    # ---- Body markers ----

    def _draw_body_markers(
        self, img: Image.Image, draw: ImageDraw.Draw, scale: float, state: GameState,
        visible_body_ids: list[str], offset_y: int,
    ) -> None:
        room_bodies: dict[str, list[str]] = {}
        for b in state.bodies:
            if b.player_id in visible_body_ids:
                room_bodies.setdefault(b.room, []).append(b.player_id)

        for room_name, body_ids in room_bodies.items():
            room = self.game_map.rooms[room_name]
            cx, cy = self._room_center(room, scale)
            cy += offset_y

            for i, bid in enumerate(body_ids):
                bx = cx - 20 + i * 36
                by = cy + 18
                self._paste_sprite(img, bid, bx, by, scale=2, variant="dead")

                body_name = self._get_player_name(bid)
                draw.text((bx, by + 18), body_name[:8], fill=BODY_FILL,
                          font=self._font_sm, anchor="mt")

    # ---- Player markers ----

    def _draw_player_markers(
        self, img: Image.Image, draw: ImageDraw.Draw, scale: float, state: GameState,
        visible_ids: list[str], viewer_id: str, offset_y: int,
    ) -> None:
        room_players: dict[str, list[str]] = {}
        for pid in visible_ids:
            p = state.players.get(pid)
            if p and p.is_alive and pid != viewer_id:
                room_players.setdefault(p.current_room, []).append(pid)

        for room_name, pids in room_players.items():
            room = self.game_map.rooms[room_name]
            cx, cy = self._room_center(room, scale)
            cy += offset_y

            viewer_here = (state.players.get(viewer_id, None) is not None
                           and state.players[viewer_id].current_room == room_name)
            base_y = cy - 20 if viewer_here else cy
            spacing = 40
            n = len(pids)
            start_x = cx - (n - 1) * spacing // 2
            for i, pid in enumerate(pids):
                px = start_x + i * spacing
                py = base_y
                name = self._get_player_name(pid)
                self._paste_sprite(img, pid, px, py, scale=2)
                draw.text((px, py - 26), name[:8], fill=TEXT_WHITE,
                          font=self._font_sm, anchor="mb")

    # ---- In-transit players ----

    def _draw_transit_players(
        self, img: Image.Image, draw: ImageDraw.Draw, scale: float, state: GameState,
        visible_ids: list[str], viewer_id: str, offset_y: int,
    ) -> None:
        """Draw players currently traveling between rooms on the corridor."""
        for pid in visible_ids:
            p = state.players.get(pid)
            if not p or not p.is_alive or pid == viewer_id:
                continue
            pos = self._transit_corridor_xy(p, scale, offset_y)
            if pos is None:
                continue
            px, py = pos
            self._draw_agent_marker(
                img, draw, pid, px, py,
                sprite_scale=GOD_SPRITE_SCALE, variant="walk",
            )

    # ---- Viewer (YOU) marker ----

    def _draw_viewer_marker(
        self, img: Image.Image, draw: ImageDraw.Draw, scale: float, viewer_room: str,
        viewer_id: str, offset_y: int, state: GameState | None = None,
    ) -> None:
        viewer_player = state.players.get(viewer_id) if state else None

        if viewer_player and viewer_player.is_in_transit:
            pos = self._transit_corridor_xy(viewer_player, scale, offset_y)
            if pos is not None:
                self._draw_agent_marker(
                    img, draw, viewer_id, pos[0], pos[1],
                    sprite_scale=GOD_SPRITE_SCALE, variant="walk",
                    name_override="YOU", accent=(45, 110, 210),
                )
                return
            vt = self._visual_transit(viewer_player)
            if vt is not None and not vt.on_corridor:
                viewer_room = vt.display_room
                room = self.game_map.rooms.get(viewer_room)
                if room:
                    cx, cy = self._room_center(room, scale)
                    cy += offset_y + 16
                    self._draw_agent_marker(
                        img, draw, viewer_id, cx, cy,
                        sprite_scale=GOD_SPRITE_SCALE, variant="walk",
                        name_override="YOU", accent=(45, 110, 210),
                    )
                    return

        room = self.game_map.rooms.get(viewer_room)
        if not room:
            return
        cx, cy = self._room_center(room, scale)
        cy += offset_y + 16
        self._draw_agent_marker(
            img, draw, viewer_id, cx, cy,
            sprite_scale=GOD_SPRITE_SCALE,
            name_override="YOU", accent=(45, 110, 210),
        )

    # ---- Legend ----

    def _calc_legend_height(
        self, state: GameState, visible_players: list[str], viewer_id: str,
    ) -> int:
        all_ids = [viewer_id] + [pid for pid in visible_players if pid != viewer_id]
        all_ids = [pid for pid in all_ids if pid in state.players]
        rows = (len(all_ids) + 2) // 3
        return max(60, 30 + rows * 28 + 10)

    def _draw_legend(
        self, draw: ImageDraw.Draw, width: int, y_start: int, height: int,
        state: GameState, visible_players: list[str], viewer_id: str,
    ) -> None:
        draw.rectangle((0, y_start, width, y_start + height), fill=HUD_BG, outline=HUD_BORDER)
        draw.text((12, y_start + 6), "Players:", fill=TEXT_LIGHT, font=self._font_md)

        all_ids = []
        if viewer_id and viewer_id in state.players:
            all_ids.append(viewer_id)
        for pid in visible_players:
            if pid != viewer_id and pid in state.players:
                all_ids.append(pid)

        col_width = max(1, (width - 24) // 3)
        for i, pid in enumerate(all_ids):
            col = i % 3
            row = i // 3
            x = 16 + col * col_width
            y = y_start + 28 + row * 26

            color = self._get_player_color(pid)
            name = self._get_player_name(pid)
            p = state.players[pid]

            r = 6
            draw.ellipse((x, y - r, x + 2 * r, y + r), fill=color, outline=TEXT_WHITE, width=1)

            status = ""
            if not p.is_alive:
                status = " [DEAD]"
            elif pid == viewer_id:
                status = " (you)"

            label = f"{name}{status}"
            draw.text((x + 2 * r + 6, y), label, fill=TEXT_WHITE, font=self._font_sm, anchor="lm")

    # ================================================================
    #  LOCAL VIEW
    # ================================================================

    def _gray_local_view(self, img: Image.Image) -> Image.Image:
        """Desaturate a local-view crop for dead players."""
        return ImageOps.grayscale(img).convert("RGB")

    def render_local_view(
        self,
        state: GameState,
        player: Player,
        visible_rooms: set[str],
        visible_players: list[str],
        visible_bodies: list[str],
        witnessed_events: list[dict] | None = None,
    ) -> Image.Image:
        """Render a zoomed view centered on the player's current room."""
        scale = LOCAL_VIEW_SCALE
        w, h = self._canvas_size(scale)
        img = Image.new("RGB", (w, h), BACKGROUND_COLOR)
        draw = ImageDraw.Draw(img)

        vt = self._visual_transit(player)
        highlight_room = player.current_room

        self._draw_corridors_local(draw, scale, visible_rooms)
        self._draw_rooms_local(draw, scale, state, visible_rooms, highlight_room)
        self._draw_task_markers_local(draw, scale, state, visible_rooms)
        self._draw_body_markers_local(img, draw, scale, state, visible_bodies)
        self._draw_players_local(img, draw, scale, state, visible_players, player)
        self._draw_witness_arrows_local(draw, scale, player, witnessed_events or [])
        self._draw_viewer_local(img, draw, scale, player)

        if vt is not None:
            pos = self._transit_corridor_xy(player, scale)
            if pos is not None:
                view_cx, view_cy = pos
            else:
                center_room = self.game_map.rooms[player.current_room]
                view_cx, view_cy = self._room_center(center_room, scale)
        else:
            center_room = self.game_map.rooms[player.current_room]
            view_cx, view_cy = self._room_center(center_room, scale)
        crop_half = LOCAL_VIEW_CROP_HALF
        left = max(0, view_cx - crop_half)
        top = max(0, view_cy - crop_half)
        right = min(w, view_cx + crop_half)
        bottom = min(h, view_cy + crop_half)
        cropped = img.crop((left, top, right, bottom))
        if not player.is_alive:
            cropped = self._gray_local_view(cropped)

        title_h = LOCAL_VIEW_TITLE_H
        title_bg = DEAD_POV_TITLE_BG if not player.is_alive else HUD_BG
        title_text = DEAD_POV_TITLE_TEXT if not player.is_alive else TEXT_WHITE
        final = Image.new("RGB", (cropped.width, cropped.height + title_h), title_bg)
        final_draw = ImageDraw.Draw(final)
        room_label = self._player_display_room(player).replace("_", " ").upper()
        final_draw.rectangle((0, 0, cropped.width, title_h), fill=title_bg, outline=HUD_BORDER)
        final_draw.text(
            (cropped.width // 2, title_h // 2),
            room_label,
            fill=title_text, font=self._font_xl, anchor="mm",
        )
        final_draw.line((0, title_h - 1, cropped.width, title_h - 1), fill=HUD_BORDER)
        final.paste(cropped, (0, title_h))
        return final

    def _draw_corridors_local(
        self, draw: ImageDraw.Draw, scale: float, visible: set[str],
    ) -> None:
        drawn: set[tuple[str, ...]] = set()
        for room_name in self.game_map.rooms:
            for neighbor in self.game_map.get_neighbors(room_name):
                key = tuple(sorted((room_name, neighbor)))
                if key in drawn:
                    continue
                drawn.add(key)
                if room_name not in visible and neighbor not in visible:
                    continue

                room_a = self.game_map.rooms[room_name]
                room_b = self.game_map.rooms[neighbor]
                ca = self._room_center(room_a, scale)
                cb = self._room_center(room_b, scale)
                both = room_name in visible and neighbor in visible
                color = CORRIDOR_COLOR if both else CORRIDOR_COLOR_DIM
                # Thicker corridors in local view so moving players sit clearly
                # in the hallway space.
                draw.line([ca, cb], fill=color, width=max(5, int(10 * scale)))

                w = self.game_map.get_corridor_weight(room_name, neighbor)
                if w > 1 and both:
                    mx, my = (ca[0] + cb[0]) // 2, (ca[1] + cb[1]) // 2
                    self._draw_weight_badge(draw, mx, my, w)

    def _draw_rooms_local(
        self, draw: ImageDraw.Draw, scale: float, state: GameState,
        visible: set[str], current_room: str,
    ) -> None:
        for room_name in visible:
            room = self.game_map.rooms[room_name]
            rect = self._room_rect(room, scale)
            cx, cy = self._room_center(room, scale)

            is_current = room_name == current_room
            theme_fill = get_room_fill(room_name)
            fill = ROOM_FILL_CURRENT if is_current else (theme_fill or ROOM_FILL)
            border = ROOM_BORDER_CURRENT if is_current else ROOM_BORDER
            border_w = 4 if is_current else 2

            draw.rounded_rectangle(rect, fill=fill, outline=border, width=border_w)
            self._draw_room_title_bar(draw, rect, room_name, highlight=is_current)
            draw_room_decoration(draw, room_name, rect, scale)

            if room.is_emergency_button:
                btn_y = rect[3] - 22
                r = 10
                draw.ellipse((cx - r, btn_y - r, cx + r, btn_y + r),
                             fill=EMERGENCY_FILL, outline=EMERGENCY_BORDER, width=2)
                draw.text((cx, btn_y), "!", fill=TEXT_WHITE, font=self._font_md, anchor="mm")

    def _draw_task_markers_local(
        self, draw: ImageDraw.Draw, scale: float, state: GameState, visible: set[str],
    ) -> None:
        task_info: dict[str, tuple[str, bool]] = {}
        for p in state.players.values():
            for t in p.tasks:
                if t.room in visible:
                    if t.room not in task_info:
                        task_info[t.room] = (t.task_name, t.is_complete)
                    elif not t.is_complete:
                        task_info[t.room] = (t.task_name, False)

        for room_name, (task_name, completed) in task_info.items():
            room = self.game_map.rooms[room_name]
            rect = self._room_rect(room, scale)

            fill = TASK_COMPLETE_FILL if completed else TASK_INCOMPLETE_FILL
            border = TASK_COMPLETE_BORDER if completed else TASK_INCOMPLETE_BORDER
            status_char = "V" if completed else "T"

            icon_x = rect[2] - 18
            icon_y = rect[1] + 14
            r = 7
            draw.rounded_rectangle(
                (icon_x - r, icon_y - r, icon_x + r, icon_y + r),
                radius=2, fill=fill, outline=border, width=1,
            )
            draw.text((icon_x, icon_y), status_char, fill=TEXT_WHITE, font=self._font_xs, anchor="mm")

            draw.text(
                (icon_x - r - 3, icon_y), task_name[:12],
                fill=fill, font=self._font_xs, anchor="rm",
            )

    def _draw_body_markers_local(
        self, img: Image.Image, draw: ImageDraw.Draw, scale: float, state: GameState,
        visible_body_ids: list[str],
    ) -> None:
        room_bodies: dict[str, list[str]] = {}
        for b in state.bodies:
            if b.player_id in visible_body_ids:
                room_bodies.setdefault(b.room, []).append(b.player_id)

        for room_name, body_ids in room_bodies.items():
            room = self.game_map.rooms[room_name]
            cx, cy = self._room_center(room, scale)

            for i, bid in enumerate(body_ids):
                bx = cx - 28 + i * 50
                by = cy + 30
                self._paste_sprite(img, bid, bx, by, scale=LOCAL_VIEW_SPRITE_SCALE, variant="dead")

                body_name = self._get_player_name(bid)
                self._draw_nameplate(draw, bx, by + int(10 * LOCAL_VIEW_SPRITE_SCALE), body_name, BODY_FILL)

    def _draw_players_local(
        self, img: Image.Image, draw: ImageDraw.Draw, scale: float, state: GameState,
        visible_ids: list[str], viewer: Player,
    ) -> None:
        ss = LOCAL_VIEW_SPRITE_SCALE
        viewer_vt = self._visual_transit(viewer)
        viewer_on_corridor = viewer_vt is not None and viewer_vt.on_corridor

        def _draw_other(pid: str, px: int, py: int, variant: str | None = None) -> None:
            self._draw_agent_marker(
                img, draw, pid, px, py, sprite_scale=ss, variant=variant,
            )

        if viewer_on_corridor:
            for pid in visible_ids:
                p = state.players.get(pid)
                if not p or not p.is_alive or pid == viewer.player_id:
                    continue
                pos = self._transit_corridor_xy(p, scale)
                if pos is not None:
                    _draw_other(pid, pos[0], pos[1])
                    continue
                p_vt = self._visual_transit(p)
                if p_vt is not None and not p_vt.on_corridor:
                    room = self.game_map.rooms.get(p_vt.display_room)
                    if room:
                        cx, cy = self._room_center(room, scale)
                        _draw_other(pid, cx, cy)
            return

        room_players: dict[str, list[str]] = {}
        corridor_ids: list[str] = []
        for pid in visible_ids:
            p = state.players.get(pid)
            if not p or not p.is_alive or pid == viewer.player_id:
                continue
            p_vt = self._visual_transit(p)
            if p_vt is not None and p_vt.on_corridor:
                corridor_ids.append(pid)
            else:
                display = p_vt.display_room if p_vt is not None else p.current_room
                room_players.setdefault(display, []).append(pid)

        for pid in corridor_ids:
            pos = self._transit_corridor_xy(state.players[pid], scale)
            if pos is not None:
                _draw_other(pid, pos[0], pos[1], variant="walk")

        viewer_display = (
            viewer_vt.display_room if viewer_vt is not None else viewer.current_room
        )
        for room_name, pids in room_players.items():
            room = self.game_map.rooms[room_name]
            cx, cy = self._room_center(room, scale)
            viewer_here = viewer_display == room_name
            base_y = cy - 20 if viewer_here else cy + 12
            spacing = max(72, int(18 * ss))
            n = len(pids)
            start_x = cx - (n - 1) * spacing // 2
            for i, pid in enumerate(pids):
                _draw_other(pid, start_x + i * spacing, base_y)

    def _draw_witness_arrows_local(
        self,
        draw: ImageDraw.Draw,
        scale: float,
        viewer: Player,
        witnessed_events: list[dict],
    ) -> None:
        """Draw single-tick arrows for departures from / arrivals into viewer's room.

        For each event, anchor a small arrowhead about 30% along the corridor
        between the viewer's room and the corresponding neighbor; departures
        point outward, arrivals point inward. Multiple events on the same
        corridor stack vertically so labels don't overlap.
        """
        if not witnessed_events or viewer.is_in_transit:
            return
        viewer_room_name = viewer.current_room
        viewer_room = self.game_map.rooms.get(viewer_room_name)
        if viewer_room is None:
            return
        viewer_center = self._room_center(viewer_room, scale)

        per_corridor: dict[str, list[dict]] = {}
        for ev in witnessed_events:
            etype = ev.get("type")
            if etype == "departed" and ev.get("from_room") == viewer_room_name:
                neighbor = ev.get("to_room")
            elif etype == "arrived" and ev.get("to_room") == viewer_room_name:
                neighbor = ev.get("from_room")
            else:
                continue
            if not neighbor or neighbor not in self.game_map.rooms:
                continue
            per_corridor.setdefault(neighbor, []).append(ev)

        for neighbor_name, events in per_corridor.items():
            neighbor_room = self.game_map.rooms[neighbor_name]
            neighbor_center = self._room_center(neighbor_room, scale)
            dx = neighbor_center[0] - viewer_center[0]
            dy = neighbor_center[1] - viewer_center[1]
            length = max(1.0, (dx * dx + dy * dy) ** 0.5)
            ux, uy = dx / length, dy / length
            anchor_t = 0.30
            ax = int(viewer_center[0] + dx * anchor_t)
            ay = int(viewer_center[1] + dy * anchor_t)
            nx, ny = -uy, ux

            line_h = 14
            n = len(events)
            for i, ev in enumerate(events):
                offset = (i - (n - 1) / 2.0) * line_h
                cx = int(ax + nx * offset)
                cy = int(ay + ny * offset)
                pid = ev.get("player_id", "")
                color = self._get_player_color(pid)
                name = self._get_player_name(pid) or pid
                arrow_len = 22
                if ev.get("type") == "departed":
                    tip_x = int(cx + ux * arrow_len)
                    tip_y = int(cy + uy * arrow_len)
                    tail_x, tail_y = cx, cy
                    label = f"{name} -> {ev.get('to_room', '?')}"
                else:
                    tip_x = int(cx - ux * arrow_len)
                    tip_y = int(cy - uy * arrow_len)
                    tail_x = int(cx + ux * arrow_len * 0.2)
                    tail_y = int(cy + uy * arrow_len * 0.2)
                    label = f"{name} <- {ev.get('from_room', '?')}"

                draw.line([(tail_x, tail_y), (tip_x, tip_y)], fill=color, width=4)
                head_w = 7
                left_x = int(tip_x - ux * head_w + nx * head_w)
                left_y = int(tip_y - uy * head_w + ny * head_w)
                right_x = int(tip_x - ux * head_w - nx * head_w)
                right_y = int(tip_y - uy * head_w - ny * head_w)
                draw.polygon(
                    [(tip_x, tip_y), (left_x, left_y), (right_x, right_y)],
                    fill=color,
                )
                swatch_r = 4
                draw.ellipse(
                    (cx - swatch_r, cy - swatch_r, cx + swatch_r, cy + swatch_r),
                    fill=color,
                )
                draw.text(
                    (cx + nx * 12, cy + ny * 12),
                    label,
                    fill=TEXT_WHITE,
                    font=self._font_sm,
                    anchor="mm",
                )

    def _draw_viewer_local(
        self, img: Image.Image, draw: ImageDraw.Draw, scale: float, player: Player,
    ) -> None:
        vt = self._visual_transit(player)
        if vt is not None and not vt.on_corridor:
            room = self.game_map.rooms[vt.display_room]
            cx, cy = self._room_center(room, scale)
            cy += 24
        elif vt is not None and vt.on_corridor:
            pos = self._transit_corridor_xy(player, scale)
            if pos is None:
                return
            cx, cy = pos
        else:
            room = self.game_map.rooms[player.current_room]
            cx, cy = self._room_center(room, scale)
            cy += 24

        r = int(14 + 6 * LOCAL_VIEW_SPRITE_SCALE)
        if not player.is_alive:
            self._paste_sprite(
                img, player.player_id, cx, cy,
                scale=LOCAL_VIEW_SPRITE_SCALE, variant="dead",
            )
            return

        draw.ellipse((cx - r, cy - r, cx + r, cy + r),
                     outline=(255, 255, 255), width=3)
        self._draw_agent_marker(
            img, draw, player.player_id, cx, cy,
            sprite_scale=LOCAL_VIEW_SPRITE_SCALE,
            name_override="YOU",
            accent=(45, 110, 210),
        )

    # ================================================================
    #  GOD VIEW — omniscient observer view
    # ================================================================

    def render_god_view(
        self,
        state: GameState,
        vision_system: object,
        event_log: list[str] | None = None,
        tick: int = 0,
        frame_idx: int | None = None,
        phase_override: str | None = None,
    ) -> Image.Image:
        """Render a god-view: all players, vision halos, roles, actions, event log,
        plus a grid of per-player local views at the bottom."""
        scale = GOD_VIEW_SCALE
        map_w, map_h = self._canvas_size(scale)

        panel_w = GOD_VIEW_PANEL_W
        hud_h = GOD_VIEW_HUD_H
        top_w = map_w + panel_w
        top_h = hud_h + map_h

        # Complete free-roam tick ends visualize tick N+1 start; partial ticks
        # (meeting interrupt) and post-meeting respawns use raw engine state.
        if self._use_next_tick_snapshot(state, phase_override):
            display_state = self._snapshot_next_tick_start(state)
        else:
            display_state = state

        # Build per-player local views from the display snapshot.
        all_players = list(display_state.players.values())
        local_views: list[tuple[str, Image.Image]] = []
        for p in all_players:
            if hasattr(vision_system, "compute_visibility"):
                vis = vision_system.compute_visibility(p, display_state)
                witnessed: list[dict] = []
                if hasattr(vision_system, "get_witnessed_movements"):
                    witnessed = vision_system.get_witnessed_movements(p, display_state)
                local_img = self.render_local_view(
                    state=display_state,
                    player=p,
                    visible_rooms=vis.visible_rooms,
                    visible_players=vis.visible_players,
                    visible_bodies=vis.visible_bodies,
                    witnessed_events=witnessed,
                )
            else:
                local_img = self.render_local_view(
                    state=display_state,
                    player=p,
                    visible_rooms={p.current_room},
                    visible_players=[],
                    visible_bodies=[],
                )
            local_views.append((p.player_id, local_img))

        # Layout: single horizontal row of per-player POVs (keeps video landscape)
        n = len(local_views)
        cols = max(1, n)
        rows = 1
        thumb_w = top_w // cols
        if local_views:
            sample = local_views[0][1]
            aspect = sample.size[1] / sample.size[0]
            thumb_h = int(thumb_w * aspect)
        else:
            thumb_h = 240

        label_h = GOD_VIEW_POV_LABEL_H
        grid_h = rows * (thumb_h + label_h) + 10

        separator_h = 40
        total_h = top_h + separator_h + grid_h

        img = Image.new("RGBA", (top_w, total_h), (*BACKGROUND_COLOR, 255))
        draw = ImageDraw.Draw(img)

        # HUD
        draw.rectangle((0, 0, top_w, hud_h), fill=(*HUD_BG, 255))
        draw.line((0, hud_h - 1, top_w, hud_h - 1), fill=(*HUD_BORDER, 255))

        from quack.engine.game_state import Team
        completed, total_tasks = 0, 0
        for p in state.players.values():
            if p.team == Team.GOOSE:
                for t in p.tasks:
                    total_tasks += 1
                    if t.is_complete:
                        completed += 1

        phase_label = (
            phase_override
            if phase_override is not None
            else state.phase.value.replace("_", " ").title()
        )
        if frame_idx is not None:
            hud_left = (
                f"GOD VIEW   Frame {frame_idx:04d}   Tick {tick}   {phase_label}"
            )
        else:
            hud_left = f"GOD VIEW   Tick {tick}   {phase_label}"
        draw.text((20, hud_h // 2), hud_left, fill=TEXT_WHITE, font=self._font_xl, anchor="lm")

        hud_right = f"Tasks {completed}/{total_tasks}   Alive {len(state.alive_players)}/{len(state.players)}"
        bbox = draw.textbbox((0, 0), hud_right, font=self._font_lg)
        draw.text(
            (top_w - (bbox[2] - bbox[0]) - 20, hud_h // 2),
            hud_right, fill=TEXT_LIGHT, font=self._font_lg, anchor="lm",
        )

        map_y = hud_h

        # Draw corridors (all visible in god view)
        all_rooms = set(self.game_map.room_names)
        self._god_draw_corridors(draw, scale, all_rooms, map_y)

        # Draw rooms (all visible)
        self._god_draw_rooms(draw, scale, display_state, map_y)

        # Draw vision halos
        self._god_draw_vision_halos(img, scale, display_state, vision_system, map_y)

        # Draw task markers
        self._draw_task_markers(draw, scale, display_state, all_rooms, map_y)

        # Draw bodies
        all_body_ids = [b.player_id for b in state.bodies]
        self._draw_body_markers(img, draw, scale, display_state, all_body_ids, map_y)

        # Build per-player chat map for this tick (free-roam chat)
        chat_by_player: dict[str, str] = {}
        for msgs in getattr(state, "room_messages", {}).values():
            for msg in msgs:
                if msg.get("tick") == tick and msg.get("player_id"):
                    chat_by_player[msg["player_id"]] = msg.get("message", "")

        # Draw all players with role labels and any chat bubbles
        self._god_draw_all_players(img, draw, scale, display_state, map_y, chat_by_player)

        # Right panel: player list + event log
        self._god_draw_panel(draw, map_w, 0, panel_w, top_h, display_state, event_log)

        # Separator between god map and local views
        sep_y = top_h
        draw.rectangle((0, sep_y, top_w, sep_y + separator_h),
                        fill=(*HUD_BG, 255))
        draw.text(
            (top_w // 2, sep_y + separator_h // 2),
            "Player POV",
            fill=(130, 190, 255), font=self._font_lg, anchor="mm",
        )

        # Draw local views in 2-column grid
        grid_start_y = sep_y + separator_h
        for idx, (pid, local_img) in enumerate(local_views):
            col = idx % cols
            row = idx // cols
            x = col * thumb_w
            y = grid_start_y + row * (thumb_h + label_h)

            # Resize local view to thumbnail
            thumb = local_img.resize((thumb_w, thumb_h), Image.Resampling.LANCZOS)
            if thumb.mode == "RGBA":
                img.paste(thumb, (x, y + label_h), thumb)
            else:
                img.paste(thumb, (x, y + label_h))

            # Player label above each thumbnail
            player = display_state.players.get(pid)
            if player:
                color = self._get_player_color(pid)
                status = "DEAD" if not player.is_alive else self._player_display_room(player)
                label = f"{player.name}  ·  {status.replace('_', ' ')}"
                draw.rectangle((x, y, x + thumb_w, y + label_h), fill=(*HUD_BG, 255))
                draw.text(
                    (x + thumb_w // 2, y + label_h // 2), label,
                    fill=(*color, 255), font=self._font_lg, anchor="mm",
                )

            # Border
            draw.rectangle((x, y, x + thumb_w - 1, y + thumb_h + label_h - 1),
                            outline=(*HUD_BORDER, 255), width=1)

        return img.convert("RGB")

    def _god_draw_corridors(
        self, draw: ImageDraw.Draw, scale: float, visible: set[str], offset_y: int,
    ) -> None:
        drawn: set[tuple[str, ...]] = set()
        for room_name in self.game_map.rooms:
            for neighbor in self.game_map.get_neighbors(room_name):
                key = tuple(sorted((room_name, neighbor)))
                if key in drawn:
                    continue
                drawn.add(key)
                room_a = self.game_map.rooms[room_name]
                room_b = self.game_map.rooms[neighbor]
                ca = self._room_center(room_a, scale)
                cb = self._room_center(room_b, scale)
                ca = (ca[0], ca[1] + offset_y)
                cb = (cb[0], cb[1] + offset_y)
                draw.line([ca, cb], fill=CORRIDOR_COLOR, width=max(3, int(7 * scale)))

                w = self.game_map.get_corridor_weight(room_name, neighbor)
                if w > 1:
                    mx, my = (ca[0] + cb[0]) // 2, (ca[1] + cb[1]) // 2
                    self._draw_weight_badge(draw, mx, my, w)

    def _god_draw_rooms(
        self, draw: ImageDraw.Draw, scale: float, state: GameState, offset_y: int,
    ) -> None:
        for room_name, room in self.game_map.rooms.items():
            rect = self._room_rect(room, scale)
            rect = (rect[0], rect[1] + offset_y, rect[2], rect[3] + offset_y)
            cx, cy = self._room_center(room, scale)
            cy += offset_y

            theme_fill = get_room_fill(room_name)
            fill = theme_fill or ROOM_FILL
            draw.rounded_rectangle(rect, radius=int(10 * scale), fill=(*fill, 255),
                                   outline=(*ROOM_BORDER, 255), width=2)
            self._draw_room_title_bar(draw, rect, room_name)
            draw_room_decoration(draw, room_name, rect, scale)

            if room.is_emergency_button:
                btn_y = rect[3] - int(18 * scale)
                r = int(9 * scale)
                draw.ellipse((cx - r, btn_y - r, cx + r, btn_y + r),
                             fill=(*EMERGENCY_FILL, 255), outline=(*EMERGENCY_BORDER, 255), width=2)
                draw.text((cx, btn_y), "!", fill=TEXT_WHITE, font=self._font_md, anchor="mm")

    def _god_draw_vision_halos(
        self, img: Image.Image, scale: float, state: GameState,
        vision_system: object, offset_y: int,
    ) -> None:
        """Draw semi-transparent colored circles showing each player's vision range."""
        overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
        ov_draw = ImageDraw.Draw(overlay)

        for player in state.alive_players:
            color = self._get_player_color(player.player_id)
            # Get visible rooms for this player
            if hasattr(vision_system, "get_visible_rooms"):
                vis_rooms = vision_system.get_visible_rooms(
                    player.player_id, player.current_room,
                )
            else:
                vis_rooms = {player.current_room}

            for room_name in vis_rooms:
                room = self.game_map.rooms.get(room_name)
                if not room:
                    continue
                rect = self._room_rect(room, scale)
                rect = (rect[0], rect[1] + offset_y, rect[2], rect[3] + offset_y)
                # Expand slightly beyond room
                margin = int(8 * scale)
                halo_rect = (
                    rect[0] - margin, rect[1] - margin,
                    rect[2] + margin, rect[3] + margin,
                )
                ov_draw.rounded_rectangle(
                    halo_rect, radius=int(12 * scale),
                    fill=(*color, VISION_HALO_ALPHA),
                )

        img_composite = Image.alpha_composite(img, overlay)
        img.paste(img_composite)

    def _god_draw_all_players(
        self, img: Image.Image, draw: ImageDraw.Draw, scale: float,
        state: GameState, offset_y: int,
        chat_by_player: dict[str, str] | None = None,
    ) -> None:
        """Draw all players (alive and dead) with action annotations and chat bubbles."""
        # Stationary alive players (arrived or never moved)
        room_alive: dict[str, list[str]] = {}
        for p in state.alive_players:
            if self._visual_transit(p) is None:
                room_alive.setdefault(p.current_room, []).append(p.player_id)

        for room_name, pids in room_alive.items():
            room = self.game_map.rooms[room_name]
            cx, cy = self._room_center(room, scale)
            cy += offset_y

            spacing = int(58 * scale)
            n = len(pids)
            start_x = cx - (n - 1) * spacing // 2
            for i, pid in enumerate(pids):
                px = start_x + i * spacing
                py = cy + int(12 * scale)
                self._god_draw_single_player(
                    img, draw, px, py, pid, state, scale, chat_by_player,
                )

        # In-transit players still on the corridor (end-of-tick visual step)
        for p in state.alive_players:
            pos = self._transit_corridor_xy(p, scale, offset_y)
            if pos is None:
                continue
            px, py = pos
            self._draw_agent_marker(
                img, draw, p.player_id, px, py,
                sprite_scale=GOD_SPRITE_SCALE, variant="walk",
                name_font=self._font_lg,
            )

    def _god_draw_single_player(
        self, img: Image.Image, draw: ImageDraw.Draw,
        px: int, py: int, pid: str, state: GameState, scale: float,
        chat_by_player: dict[str, str] | None = None,
    ) -> None:
        variant = self._get_sprite_variant(pid, state.players[pid].is_alive)
        self._draw_agent_marker(
            img, draw, pid, px, py,
            sprite_scale=GOD_SPRITE_SCALE, variant=variant,
            name_font=self._font_lg,
        )

        action = self.last_actions.get(pid, "")
        if action:
            action_short = action[:22]
            acolor = GOD_EVENT_MOVE_COLOR
            if "kill" in action:
                acolor = GOD_EVENT_KILL_COLOR
            elif "task" in action:
                acolor = GOD_EVENT_TASK_COLOR
            label_y = py + int(22 * GOD_SPRITE_SCALE)
            draw.text((px, label_y), action_short, fill=acolor, font=self._font_sm, anchor="mt")

        if chat_by_player and pid in chat_by_player:
            msg = chat_by_player[pid]
            msg_short = (msg[:28] + "…") if len(msg) > 28 else msg
            chat_y = py + int(36 * GOD_SPRITE_SCALE)
            bbox = draw.textbbox((0, 0), msg_short, font=self._font_sm)
            bw = bbox[2] - bbox[0] + 12
            bh = bbox[3] - bbox[1] + 8
            bx = px - bw // 2
            by = chat_y - bh // 2
            draw.rounded_rectangle(
                (bx, by, bx + bw, by + bh), radius=6,
                fill=(28, 36, 50), outline=GOD_PANEL_BORDER, width=1,
            )
            draw.text((px, chat_y), msg_short, fill=TEXT_LIGHT, font=self._font_sm, anchor="mm")

    def _god_draw_panel(
        self, draw: ImageDraw.Draw, x: int, y: int, w: int, h: int,
        state: GameState, event_log: list[str] | None,
    ) -> None:
        """Draw the right-side info panel with player roster and event log."""
        from quack.engine.game_state import Team

        draw.rectangle((x, y, x + w, h), fill=(*GOD_PANEL_BG, 255))
        draw.line((x, y, x, h), fill=(*GOD_PANEL_BORDER, 255), width=2)

        draw.text((x + 16, y + 16), "Players", fill=TEXT_WHITE, font=self._font_lg)
        draw.line((x + 16, y + 44, x + w - 16, y + 44), fill=(*GOD_PANEL_BORDER, 255))

        roster_y = y + 54
        row_h = 28
        for pid, player in state.players.items():
            color = self._get_player_color(pid)
            name = self._get_player_name(pid)
            role_color = GOD_ROLE_DUCK_COLOR if player.team == Team.DUCK else GOD_ROLE_GOOSE_COLOR

            r = 7
            dot_x = x + 24
            draw.ellipse((dot_x - r, roster_y - r, dot_x + r, roster_y + r),
                         fill=color, outline=TEXT_WHITE, width=1)

            status = " [DEAD]" if not player.is_alive else ""
            label = f"{name}{status}"
            draw.text((dot_x + r + 8, roster_y), label,
                      fill=role_color if player.is_alive else TEXT_DIM,
                      font=self._font_md, anchor="lm")

            room_label = self._player_display_room(player).replace("_", " ")
            draw.text((x + w - 16, roster_y), room_label,
                      fill=TEXT_LIGHT, font=self._font_md, anchor="rm")

            roster_y += row_h

        log_y = roster_y + 18
        draw.text((x + 16, log_y), "Event Log", fill=TEXT_WHITE, font=self._font_lg)
        draw.line((x + 16, log_y + 30, x + w - 16, log_y + 30), fill=(*GOD_PANEL_BORDER, 255))
        log_y += 40

        if event_log:
            line_h = 24
            max_lines = max(1, (h - log_y - 12) // line_h)
            visible_events = event_log[-max_lines:]
            for line in visible_events:
                ecolor = TEXT_LIGHT
                if "kill" in line.lower():
                    ecolor = GOD_EVENT_KILL_COLOR
                elif "task" in line.lower():
                    ecolor = GOD_EVENT_TASK_COLOR
                elif "report" in line.lower() or "meeting" in line.lower():
                    ecolor = (255, 200, 80)
                elif "eject" in line.lower():
                    ecolor = (200, 130, 255)

                display = line[:52]
                draw.text((x + 16, log_y), display, fill=ecolor, font=self._font_log)
                log_y += line_h
        else:
            draw.text((x + 16, log_y), "No events yet", fill=TEXT_DIM, font=self._font_md)

    # ================================================================
    #  MEETING FRAMES — for god-view meeting sequence
    # ================================================================

    def render_meeting_called(
        self, state: GameState, reason: str, tick: int,
    ) -> Image.Image:
        """Render a meeting-called frame (1280x720): who triggered it and why."""
        w, h = 1280, 720
        img = Image.new("RGB", (w, h), (20, 22, 32))
        draw = ImageDraw.Draw(img)

        # Header bar
        draw.rectangle((0, 0, w, 56), fill=HUD_BG, outline=HUD_BORDER)
        draw.text((w // 2, 28), "EMERGENCY MEETING", fill=(255, 80, 80),
                  font=self._font_xl, anchor="mm")

        # Tick info
        draw.text((16, 18), f"Tick: {tick}", fill=TEXT_LIGHT, font=self._font_md)

        # Reason in the center
        draw.text((w // 2, 100), reason, fill=TEXT_WHITE, font=self._font_lg, anchor="mm")

        # Dead players section
        dead = [p for p in state.players.values() if not p.is_alive]
        if dead:
            draw.text((w // 2, 150), "Dead players:", fill=(220, 100, 100),
                      font=self._font_md, anchor="mm")
            for i, p in enumerate(dead):
                color = self._get_player_color(p.player_id)
                name = self._get_player_name(p.player_id)
                bx = w // 2 - (len(dead) - 1) * 50 + i * 100
                by = 200
                # Dead sprite
                dead_img = self.sprites.get_sprite(p.player_id, "dead", scale=3)
                sw, sh = dead_img.size
                img.paste(dead_img, (bx - sw // 2, by - sh // 2), dead_img)
                draw.text((bx, by + 30), name, fill=color, font=self._font_md, anchor="mt")

        # Alive players at bottom
        alive = state.alive_players
        draw.text((w // 2, h - 160), "Participants:", fill=TEXT_LIGHT,
                  font=self._font_md, anchor="mm")
        n = len(alive)
        spacing = min(90, (w - 80) // max(1, n))
        start_x = w // 2 - (n - 1) * spacing // 2
        for i, p in enumerate(alive):
            px = start_x + i * spacing
            py = h - 100
            sprite = self.sprites.get_sprite(p.player_id, "idle", scale=2)
            sw, sh = sprite.size
            img.paste(sprite, (px - sw // 2, py - sh // 2), sprite)
            name = self._get_player_name(p.player_id)
            draw.text((px, py + 26), name[:6], fill=TEXT_WHITE,
                      font=self._font_sm, anchor="mt")

        return img

    def _abbreviate_speech(self, text: str, max_chars: int = 60) -> str:
        """Shorten a past speech to its first sentence + ellipsis."""
        for sep in (". ", "! ", "? ", "。", "！", "？"):
            idx = text.find(sep)
            if 0 < idx < max_chars:
                return text[:idx + len(sep)].rstrip() + "..."
        if len(text) <= max_chars:
            return text
        return text[:max_chars].rstrip() + "..."

    def _wrap_text(self, draw: ImageDraw.Draw, text: str,
                   font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
                   max_width: int) -> list[str]:
        """Word-wrap text to fit within max_width. Handles CJK (no spaces) via char wrap."""
        words = text.split()
        lines: list[str] = []
        current = ""
        for word in words:
            test = f"{current} {word}".strip() if current else word
            bbox = draw.textbbox((0, 0), test, font=font)
            if bbox[2] - bbox[0] <= max_width:
                current = test
            else:
                if current:
                    lines.append(current)
                # Word itself may exceed max_width (e.g. CJK with no spaces)
                bbox_word = draw.textbbox((0, 0), word, font=font)
                if bbox_word[2] - bbox_word[0] <= max_width:
                    current = word
                else:
                    current = ""
                    for ch in word:
                        trial = current + ch
                        b = draw.textbbox((0, 0), trial, font=font)
                        if b[2] - b[0] <= max_width:
                            current = trial
                        else:
                            if current:
                                lines.append(current)
                            current = ch
        if current:
            lines.append(current)
        return lines if lines else [""]

    def render_speech(
        self, state: GameState, speaker_id: str, message: str,
        discussion_history: list[dict[str, str]], tick: int,
    ) -> Image.Image:
        """Render a discussion frame (1280x720, 16:9). Two-panel layout: past
        speeches on left, current speaker full message on right. God view: shows
        actual body locations so observer can see if reporter is lying."""
        w, h = 1280, 720
        header_h = 56
        body_banner_h = 0
        if state.bodies:
            body_banner_h = 32
        content_y = header_h + body_banner_h
        content_h = h - content_y

        left_w = int(w * 0.38)
        right_w = w - left_w - 20
        sep_x = left_w + 10

        img = Image.new("RGB", (w, h), (20, 22, 32))
        draw = ImageDraw.Draw(img)

        # Header
        draw.rectangle((0, 0, w, header_h), fill=HUD_BG, outline=HUD_BORDER)
        draw.text((w // 2, 28), "DISCUSSION", fill=(100, 200, 255),
                  font=self._font_xl, anchor="mm")
        draw.text((20, 18), f"Tick: {tick}", fill=TEXT_LIGHT, font=self._font_md)

        # Actual body locations (God view — truth so observer can spot lies)
        if state.bodies:
            room_to_victims: dict[str, list[str]] = {}
            for b in state.bodies:
                name = state.players[b.player_id].name
                room_to_victims.setdefault(b.room, []).append(name)
            parts = [f"{r} ({', '.join(v)})" for r, v in room_to_victims.items()]
            truth_line = "Actual body locations: " + " | ".join(parts)
            draw.rectangle((0, header_h, w, header_h + body_banner_h),
                           fill=(40, 30, 50))
            draw.text((w // 2, header_h + body_banner_h // 2),
                      truth_line, fill=(255, 180, 100), font=self._font_md,
                      anchor="mm")

        # Past speeches — left panel
        past_entries = [e for e in discussion_history if not (
            e["player_id"] == speaker_id and e is discussion_history[-1]
        )]
        left_x = 20
        left_max_w = left_w - 40
        past_line_h = 20
        y = content_y + 12
        draw.text((left_x, y - 4), "Previous:", fill=TEXT_DIM, font=self._font_sm)
        y += 20
        for entry in past_entries:
            if y > content_y + content_h - 30:
                break
            pid = entry["player_id"]
            name = entry.get("name", self._get_player_name(pid))
            color = self._get_player_color(pid)
            abbreviated = self._abbreviate_speech(entry["message"], max_chars=50)
            r = 4
            draw.ellipse((left_x - r, y + 6 - r, left_x + r, y + 6 + r), fill=color)
            draw.text((left_x + 12, y + 6), f"{name}:", fill=color,
                      font=self._font_sm, anchor="lm")
            bbox = draw.textbbox((0, 0), f"{name}:", font=self._font_sm)
            msg_x = left_x + 14 + (bbox[2] - bbox[0])
            draw.text((msg_x, y + 6), abbreviated, fill=TEXT_DIM,
                      font=self._font_sm, anchor="lm")
            y += past_line_h + 4

        # Current speaker — right panel (full message, larger font)
        right_x = sep_x + 20
        msg_max_w = right_w - 50
        wrapped = self._wrap_text(draw, message, self._font_md, msg_max_w)
        line_h = 24

        speaker_color = self._get_player_color(speaker_id)
        speaker_name = self._get_player_name(speaker_id)

        box_y = content_y + 12
        box_h = min(content_h - 100, 28 + len(wrapped) * line_h + 16)
        draw.rectangle(
            (right_x - 8, box_y, right_x + msg_max_w + 24, box_y + box_h),
            outline=(100, 200, 255), width=2,
        )
        draw.rectangle(
            (right_x - 7, box_y + 1, right_x + msg_max_w + 23, box_y + 6),
            fill=(100, 200, 255),
        )
        inner_y = box_y + 14
        r = 6
        draw.ellipse((right_x - r, inner_y + 8 - r, right_x + r, inner_y + 8 + r),
                     fill=speaker_color)
        draw.text((right_x + 16, inner_y + 8), f"{speaker_name}:",
                  fill=speaker_color, font=self._font_lg, anchor="lm")
        inner_y += 28
        for wline in wrapped:
            draw.text((right_x, inner_y), wline, fill=TEXT_WHITE, font=self._font_md)
            inner_y += line_h

        # Speaker sprite at bottom of right panel
        speaker = state.players.get(speaker_id)
        if speaker:
            sp_x = right_x + msg_max_w // 2
            sp_y = h - 40
            sprite = self.sprites.get_sprite(speaker_id, "idle", scale=3)
            sw, sh = sprite.size
            img.paste(sprite, (sp_x - sw // 2, sp_y - sh // 2), sprite)
            draw.text((sp_x, sp_y - sh // 2 - 8), f"{speaker_name} speaking",
                      fill=speaker_color, font=self._font_md, anchor="mb")

        return img

    def render_vote_result(
        self, state: GameState, votes: dict[str, str | None],
        ejected_id: str | None, tick: int,
    ) -> Image.Image:
        """Render the vote result frame with tally bars (1280x720)."""
        from collections import Counter

        w, h = 1280, 720
        img = Image.new("RGB", (w, h), (20, 22, 32))
        draw = ImageDraw.Draw(img)

        # Header
        draw.rectangle((0, 0, w, 50), fill=HUD_BG, outline=HUD_BORDER)
        draw.text((w // 2, 25), "VOTE RESULTS", fill=(200, 160, 255),
                  font=self._font_xl, anchor="mm")
        draw.text((16, 16), f"Tick: {tick}", fill=TEXT_LIGHT, font=self._font_md)

        # Count votes per target (only counts, not who voted whom)
        vote_counts: Counter[str | None] = Counter()
        for target in votes.values():
            vote_counts[target] += 1

        skip_count = vote_counts.pop(None, 0)
        total_votes = len(votes)

        # Draw vote bars for each player
        bar_y = 80
        bar_x = 60
        bar_max_w = w - 200
        max_votes = max(vote_counts.values()) if vote_counts else 1
        max_votes = max(max_votes, skip_count, 1)

        alive_ids = [p.player_id for p in state.alive_players]
        all_ids = alive_ids + [
            p.player_id for p in state.players.values()
            if not p.is_alive and p.player_id not in alive_ids
        ]

        for pid in all_ids:
            if pid not in state.players:
                continue
            player = state.players[pid]
            name = self._get_player_name(pid)
            color = self._get_player_color(pid)
            count = vote_counts.get(pid, 0)

            # Sprite
            variant = "idle" if player.is_alive else "dead"
            sprite = self.sprites.get_sprite(pid, variant, scale=2)
            sw, sh = sprite.size
            img.paste(sprite, (bar_x - 40, bar_y - sh // 2), sprite)

            # Name
            draw.text((bar_x, bar_y), name, fill=color,
                      font=self._font_md, anchor="lm")

            # Vote bar
            bar_start = bar_x + 100
            bar_w = int((count / max_votes) * (bar_max_w - 100)) if max_votes > 0 else 0
            bar_h = 16
            if bar_w > 0:
                draw.rectangle(
                    (bar_start, bar_y - bar_h // 2, bar_start + bar_w, bar_y + bar_h // 2),
                    fill=color,
                )
            # Vote count
            draw.text((bar_start + bar_w + 8, bar_y), str(count),
                      fill=TEXT_WHITE, font=self._font_md, anchor="lm")

            bar_y += 48

        # Skip votes
        draw.text((bar_x, bar_y + 10), "Skip / Abstain:", fill=TEXT_DIM,
                  font=self._font_md, anchor="lm")
        skip_bar_start = bar_x + 140
        skip_bar_w = int((skip_count / max_votes) * (bar_max_w - 140)) if max_votes > 0 else 0
        if skip_bar_w > 0:
            draw.rectangle(
                (skip_bar_start, bar_y + 10 - 8, skip_bar_start + skip_bar_w, bar_y + 10 + 8),
                fill=TEXT_DIM,
            )
        draw.text((skip_bar_start + skip_bar_w + 8, bar_y + 10), str(skip_count),
                  fill=TEXT_WHITE, font=self._font_md, anchor="lm")

        # Outcome
        outcome_y = h - 70
        draw.line((40, outcome_y - 20, w - 40, outcome_y - 20), fill=HUD_BORDER)
        if ejected_id:
            ejected = state.players[ejected_id]
            ejected_name = self._get_player_name(ejected_id)
            ejected_color = self._get_player_color(ejected_id)
            outcome = f"{ejected_name} was ejected! ({ejected.role_name} / {ejected.team.value})"
            draw.text((w // 2, outcome_y), outcome,
                      fill=ejected_color, font=self._font_lg, anchor="mm")
        else:
            draw.text((w // 2, outcome_y), "No one was ejected (tie or skip).",
                      fill=TEXT_DIM, font=self._font_lg, anchor="mm")

        draw.text((w // 2, outcome_y + 28), f"Total votes: {total_votes}",
                  fill=TEXT_DIM, font=self._font_sm, anchor="mm")

        return img
