"""Pixel-art room decoration renderer.

Draws themed interior elements inside rooms based on their name.
All drawing is done with Pillow primitives to maintain the pixel-art style.
"""

from __future__ import annotations

from PIL import ImageDraw

# Room-specific fill colors (subtle thematic tints)
ROOM_THEME_FILLS: dict[str, tuple[int, int, int]] = {
    "cafeteria":    (225, 218, 205),
    "engine_room":  (195, 200, 210),
    "upper_engine": (195, 200, 210),
    "lower_engine": (195, 200, 210),
    "medbay":       (215, 235, 230),
    "electrical":   (220, 215, 200),
    "navigation":   (200, 210, 225),
    "weapons":      (210, 200, 200),
    "oxygen":       (210, 230, 220),
    "security":     (200, 200, 215),
    "storage":      (215, 210, 200),
}

# Decoration colors
_TABLE = (140, 110, 80)
_TABLE_TOP = (170, 140, 100)
_CHAIR = (100, 85, 70)
_PLATE = (240, 240, 235)
_BED = (230, 235, 240)
_BED_FRAME = (160, 165, 175)
_PILLOW = (210, 220, 235)
_CROSS = (220, 60, 60)
_WIRE = (220, 180, 50)
_WIRE2 = (60, 180, 220)
_PANEL_FACE = (70, 80, 95)
_PANEL_BORDER = (50, 55, 65)
_LED_GREEN = (60, 220, 80)
_LED_RED = (220, 60, 50)
_LED_AMBER = (230, 180, 40)
_GEAR_OUTER = (130, 135, 145)
_GEAR_INNER = (100, 105, 115)
_PIPE = (150, 155, 165)
_PIPE_DARK = (110, 115, 125)
_SCREEN_BG = (15, 25, 45)
_SCREEN_BORDER = (80, 90, 110)
_STAR = (220, 230, 255)
_COMPASS = (200, 180, 100)


def get_room_fill(room_name: str) -> tuple[int, int, int] | None:
    """Return themed fill color for a room, or None for default."""
    return ROOM_THEME_FILLS.get(room_name)


def draw_room_decoration(
    draw: ImageDraw.Draw,
    room_name: str,
    rect: tuple[int, int, int, int],
    scale: float = 1.0,
) -> None:
    """Draw thematic interior decorations for a room."""
    x1, y1, x2, y2 = rect
    w = x2 - x1
    h = y2 - y1
    cx = (x1 + x2) // 2
    cy = (y1 + y2) // 2

    fn = _DECORATORS.get(room_name)
    if fn:
        fn(draw, x1, y1, w, h, cx, cy, scale)


def _draw_cafeteria(
    draw: ImageDraw.Draw,
    x: int, y: int, w: int, h: int, cx: int, cy: int, scale: float,
) -> None:
    """Tables with plates, benches."""
    s = max(1, int(scale))

    # Two tables
    for tx_offset in (-w // 4, w // 4):
        tx = cx + tx_offset
        ty = cy + h // 6

        # Table top
        tw, th = int(26 * s), int(10 * s)
        draw.rectangle((tx - tw // 2, ty - th // 2, tx + tw // 2, ty + th // 2),
                        fill=_TABLE_TOP, outline=_TABLE)
        # Legs
        for lx in (tx - tw // 3, tx + tw // 3):
            draw.rectangle((lx - s, ty + th // 2, lx + s, ty + th // 2 + 5 * s),
                            fill=_TABLE)
        # Plates
        for px in (tx - 6 * s, tx + 6 * s):
            r = 3 * s
            draw.ellipse((px - r, ty - r - 1, px + r, ty + r - 1), fill=_PLATE, outline=_TABLE)

        # Chairs/benches
        for bx_off in (-8 * s, 8 * s):
            bx = tx + bx_off
            by = ty - th // 2 - 4 * s
            draw.rectangle((bx - 3 * s, by, bx + 3 * s, by + 3 * s), fill=_CHAIR)


def _draw_medbay(
    draw: ImageDraw.Draw,
    x: int, y: int, w: int, h: int, cx: int, cy: int, scale: float,
) -> None:
    """Hospital beds, red cross."""
    s = max(1, int(scale))

    # Two beds
    for bx_offset in (-w // 4, w // 4):
        bx = cx + bx_offset
        by = cy + h // 8

        # Bed frame
        bw, bh = int(20 * s), int(12 * s)
        draw.rectangle((bx - bw // 2, by - bh // 2, bx + bw // 2, by + bh // 2),
                        fill=_BED, outline=_BED_FRAME)
        # Pillow
        pw = int(6 * s)
        draw.rectangle((bx - bw // 2 + s, by - bh // 2 + s,
                         bx - bw // 2 + pw, by - bh // 2 + bh // 2),
                        fill=_PILLOW)

    # Red cross
    cross_x = cx
    cross_y = cy - h // 4
    cs = int(3 * s)
    draw.rectangle((cross_x - cs, cross_y - cs * 3, cross_x + cs, cross_y + cs * 3),
                    fill=_CROSS)
    draw.rectangle((cross_x - cs * 3, cross_y - cs, cross_x + cs * 3, cross_y + cs),
                    fill=_CROSS)


def _draw_electrical(
    draw: ImageDraw.Draw,
    x: int, y: int, w: int, h: int, cx: int, cy: int, scale: float,
) -> None:
    """Electrical panels with wires and LEDs."""
    s = max(1, int(scale))

    # Panel boxes along bottom
    for i, px_off in enumerate((-w // 3, 0, w // 3)):
        px = cx + px_off
        py = cy + h // 6

        pw, ph = int(14 * s), int(16 * s)
        draw.rectangle((px - pw // 2, py - ph // 2, px + pw // 2, py + ph // 2),
                        fill=_PANEL_FACE, outline=_PANEL_BORDER)

        # LEDs
        led_colors = [_LED_GREEN, _LED_RED, _LED_AMBER]
        for j, lc in enumerate(led_colors):
            ly = py - ph // 3 + j * (4 * s)
            lr = s + 1
            draw.ellipse((px - 2 * s - lr, ly - lr, px - 2 * s + lr, ly + lr), fill=lc)

    # Wires hanging from top
    for wx_off, wc in ((-w // 5, _WIRE), (0, _WIRE2), (w // 5, _WIRE)):
        wx = cx + wx_off
        wy_start = cy - h // 3
        wy_end = cy - h // 8
        draw.line([(wx, wy_start), (wx + 3 * s, (wy_start + wy_end) // 2),
                    (wx - 2 * s, wy_end)], fill=wc, width=max(1, s))


def _draw_engine_room(
    draw: ImageDraw.Draw,
    x: int, y: int, w: int, h: int, cx: int, cy: int, scale: float,
) -> None:
    """Gears, pipes, machinery."""
    s = max(1, int(scale))

    # Central gear
    gr = int(10 * s)
    draw.ellipse((cx - gr, cy - gr + h // 8, cx + gr, cy + gr + h // 8),
                  fill=_GEAR_INNER, outline=_GEAR_OUTER, width=max(1, 2 * s))
    # Inner circle
    gir = gr // 2
    draw.ellipse((cx - gir, cy - gir + h // 8, cx + gir, cy + gir + h // 8),
                  fill=_PANEL_FACE, outline=_GEAR_OUTER)

    # Teeth (small rectangles)
    import math
    for angle in range(0, 360, 45):
        rad = math.radians(angle)
        tx = int(cx + gr * math.cos(rad))
        ty = int(cy + h // 8 + gr * math.sin(rad))
        ts = max(2, int(3 * s))
        draw.rectangle((tx - ts, ty - ts, tx + ts, ty + ts), fill=_GEAR_OUTER)

    # Pipes
    for pipe_x in (cx - w // 3, cx + w // 3):
        draw.rectangle((pipe_x - 3 * s, cy - h // 4, pipe_x + 3 * s, cy + h // 4),
                        fill=_PIPE, outline=_PIPE_DARK)


def _draw_navigation(
    draw: ImageDraw.Draw,
    x: int, y: int, w: int, h: int, cx: int, cy: int, scale: float,
) -> None:
    """Navigation screens, star map, compass."""
    s = max(1, int(scale))

    # Main screen
    sw, sh = int(30 * s), int(18 * s)
    screen_y = cy + h // 10
    draw.rectangle((cx - sw // 2, screen_y - sh // 2, cx + sw // 2, screen_y + sh // 2),
                    fill=_SCREEN_BG, outline=_SCREEN_BORDER, width=max(1, s))

    # Stars on screen
    import random as _rng
    rng = _rng.Random(42)
    for _ in range(8):
        sx = cx - sw // 2 + rng.randint(3, sw - 3)
        sy = screen_y - sh // 2 + rng.randint(3, sh - 3)
        sr = max(1, s)
        draw.ellipse((sx - sr, sy - sr, sx + sr, sy + sr), fill=_STAR)

    # Small compass indicator
    comp_x = cx - w // 4
    comp_y = cy - h // 5
    cr = int(6 * s)
    draw.ellipse((comp_x - cr, comp_y - cr, comp_x + cr, comp_y + cr),
                  outline=_COMPASS, width=max(1, s))
    # N arrow
    draw.line([(comp_x, comp_y), (comp_x, comp_y - cr + s)],
              fill=_CROSS, width=max(1, s))
    draw.line([(comp_x, comp_y), (comp_x, comp_y + cr - s)],
              fill=_SCREEN_BORDER, width=max(1, s))


def _draw_weapons(
    draw: ImageDraw.Draw,
    x: int, y: int, w: int, h: int, cx: int, cy: int, scale: float,
) -> None:
    """Targeting reticle and weapon rack."""
    s = max(1, int(scale))

    # Targeting reticle
    tr = int(12 * s)
    draw.ellipse((cx - tr, cy - tr + h // 8, cx + tr, cy + tr + h // 8),
                  outline=(200, 60, 60), width=max(1, s))
    draw.ellipse((cx - tr // 2, cy - tr // 2 + h // 8, cx + tr // 2, cy + tr // 2 + h // 8),
                  outline=(200, 60, 60), width=max(1, s))
    draw.line([(cx - tr - 3 * s, cy + h // 8), (cx + tr + 3 * s, cy + h // 8)],
              fill=(200, 60, 60), width=max(1, s))
    draw.line([(cx, cy - tr - 3 * s + h // 8), (cx, cy + tr + 3 * s + h // 8)],
              fill=(200, 60, 60), width=max(1, s))

    # Weapon rack on the side
    rack_x = cx - w // 3
    rack_y = cy - h // 6
    rw = int(6 * s)
    rh = int(20 * s)
    draw.rectangle((rack_x - rw // 2, rack_y, rack_x + rw // 2, rack_y + rh),
                    fill=_PANEL_FACE, outline=_PANEL_BORDER)
    for i in range(3):
        iy = rack_y + 3 * s + i * 6 * s
        draw.line([(rack_x - rw // 3, iy), (rack_x + rw // 3, iy)],
                  fill=_GEAR_OUTER, width=max(1, s))


def _draw_oxygen(
    draw: ImageDraw.Draw,
    x: int, y: int, w: int, h: int, cx: int, cy: int, scale: float,
) -> None:
    """O2 tanks and filter system."""
    s = max(1, int(scale))

    # O2 tanks
    for tx_off in (-w // 4, 0, w // 4):
        tx = cx + tx_off
        ty = cy + h // 6
        tw, th = int(8 * s), int(18 * s)
        draw.rounded_rectangle(
            (tx - tw // 2, ty - th // 2, tx + tw // 2, ty + th // 2),
            radius=3 * s, fill=(180, 220, 200), outline=(120, 160, 140),
        )
        # Valve on top
        vw = int(4 * s)
        draw.rectangle((tx - vw // 2, ty - th // 2 - 3 * s, tx + vw // 2, ty - th // 2),
                        fill=_GEAR_OUTER)

    # O2 label
    draw.text((cx, cy - h // 4), "O₂", fill=(80, 180, 120),
              font=None, anchor="mm")


def _draw_security(
    draw: ImageDraw.Draw,
    x: int, y: int, w: int, h: int, cx: int, cy: int, scale: float,
) -> None:
    """Security camera monitors."""
    s = max(1, int(scale))

    # Camera monitor grid (2x2)
    for row in range(2):
        for col in range(2):
            mx = cx + (col - 1) * int(16 * s) + int(8 * s)
            my = cy + (row - 1) * int(12 * s) + int(6 * s) + h // 10
            mw, mh = int(12 * s), int(8 * s)
            draw.rectangle((mx - mw // 2, my - mh // 2, mx + mw // 2, my + mh // 2),
                            fill=_SCREEN_BG, outline=_SCREEN_BORDER, width=max(1, s))
            # Static-like dots
            import random as _rng
            rng = _rng.Random(42 + row * 2 + col)
            for _ in range(4):
                px = mx - mw // 2 + rng.randint(2, mw - 2)
                py = my - mh // 2 + rng.randint(2, mh - 2)
                draw.point((px, py), fill=(60, 80, 60))

    # Small camera icon above
    cam_y = cy - h // 4
    cs = int(5 * s)
    draw.rectangle((cx - cs, cam_y - cs // 2, cx + cs, cam_y + cs // 2),
                    fill=_PANEL_FACE, outline=_PANEL_BORDER)
    draw.polygon([(cx + cs, cam_y - cs // 3), (cx + cs + 3 * s, cam_y - cs),
                   (cx + cs + 3 * s, cam_y + cs), (cx + cs, cam_y + cs // 3)],
                  fill=_PANEL_FACE, outline=_PANEL_BORDER)
    # LED on camera
    draw.ellipse((cx - 2 * s, cam_y - s, cx, cam_y + s), fill=_LED_RED)


def _draw_storage(
    draw: ImageDraw.Draw,
    x: int, y: int, w: int, h: int, cx: int, cy: int, scale: float,
) -> None:
    """Cargo boxes and crates."""
    s = max(1, int(scale))
    _CRATE = (160, 130, 90)
    _CRATE_DARK = (130, 105, 70)
    _CRATE_STRIPE = (180, 150, 100)

    crate_positions = [
        (-w // 4, h // 8, 14, 12),
        (w // 6, h // 6, 12, 10),
        (-w // 6, -h // 8, 10, 10),
        (w // 4, -h // 10, 8, 8),
    ]
    for ox, oy, cw_base, ch_base in crate_positions:
        bx = cx + ox
        by = cy + oy
        cw = int(cw_base * s)
        ch = int(ch_base * s)
        draw.rectangle((bx - cw // 2, by - ch // 2, bx + cw // 2, by + ch // 2),
                        fill=_CRATE, outline=_CRATE_DARK)
        draw.line([(bx - cw // 2, by), (bx + cw // 2, by)],
                  fill=_CRATE_STRIPE, width=max(1, s))
        draw.line([(bx, by - ch // 2), (bx, by + ch // 2)],
                  fill=_CRATE_STRIPE, width=max(1, s))


_DECORATORS: dict[str, callable] = {
    "cafeteria": _draw_cafeteria,
    "engine_room": _draw_engine_room,
    "upper_engine": _draw_engine_room,
    "lower_engine": _draw_engine_room,
    "medbay": _draw_medbay,
    "electrical": _draw_electrical,
    "navigation": _draw_navigation,
    "weapons": _draw_weapons,
    "oxygen": _draw_oxygen,
    "security": _draw_security,
    "storage": _draw_storage,
}
