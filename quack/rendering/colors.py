"""Color and rendering constants for map visualization."""

from __future__ import annotations

# Each player gets a distinct, high-contrast color
PLAYER_COLORS: list[tuple[int, int, int]] = [
    (231, 76, 60),    # red
    (46, 134, 222),   # blue
    (39, 174, 96),    # green
    (241, 196, 15),   # yellow
    (155, 89, 182),   # purple
    (230, 126, 34),   # orange
    (26, 188, 156),   # teal
    (236, 135, 191),  # pink
    (149, 165, 166),  # gray
    (52, 73, 94),     # dark blue
]

# Map elements
ROOM_FILL = (215, 225, 240)
ROOM_FILL_CURRENT = (190, 220, 255)
ROOM_BORDER = (80, 100, 130)
ROOM_BORDER_CURRENT = (40, 120, 220)
CORRIDOR_COLOR = (160, 175, 195)
CORRIDOR_COLOR_DIM = (60, 65, 75)

# Fog
FOG_FILL = (45, 48, 58)
FOG_BORDER = (55, 58, 68)
FOG_LABEL_COLOR = (100, 105, 120)

# Background
BACKGROUND_COLOR = (25, 28, 38)

# Bodies
BODY_FILL = (200, 40, 40)
BODY_OUTLINE = (255, 80, 80)

# Tasks
TASK_INCOMPLETE_FILL = (255, 200, 50)
TASK_INCOMPLETE_BORDER = (200, 150, 0)
TASK_COMPLETE_FILL = (50, 200, 80)
TASK_COMPLETE_BORDER = (30, 150, 50)

# Emergency button
EMERGENCY_FILL = (220, 50, 50)
EMERGENCY_BORDER = (180, 30, 30)

# Text
TEXT_WHITE = (255, 255, 255)
TEXT_LIGHT = (200, 210, 225)
TEXT_DIM = (130, 140, 160)
TEXT_DARK = (40, 45, 60)

# HUD / legend
HUD_BG = (35, 38, 50)
HUD_BORDER = (60, 65, 80)

# Viewer highlight
VIEWER_HIGHLIGHT = (40, 120, 220, 60)

# Vision halo (semi-transparent, per-player glow)
VISION_HALO_ALPHA = 30

# God view
GOD_EVENT_KILL_COLOR = (255, 60, 60)
GOD_EVENT_TASK_COLOR = (80, 220, 120)
GOD_EVENT_MOVE_COLOR = (150, 170, 200)
GOD_ROLE_GOOSE_COLOR = (100, 200, 120)
GOD_ROLE_DUCK_COLOR = (230, 80, 80)
GOD_PANEL_BG = (30, 32, 42)
GOD_PANEL_BORDER = (55, 58, 72)

# Sizes
CELL_SIZE = 80
PADDING = 50
PLAYER_RADIUS = 10
PLAYER_RADIUS_LOCAL = 14
