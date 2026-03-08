"""Procedural pixel-art sprite generator for player characters.

Generates small (16x24 base) pixel-art figures with:
- Round head, body, arms, legs
- Player-specific color for the body
- Variants: idle, walking, doing_task, dead
- Scaled up with nearest-neighbor for crispy pixel look
"""

from __future__ import annotations

from PIL import Image, ImageDraw

# Base sprite is drawn on a small canvas then upscaled
SPRITE_W = 16
SPRITE_H = 24


def _darken(color: tuple[int, int, int], factor: float = 0.6) -> tuple[int, int, int]:
    return (int(color[0] * factor), int(color[1] * factor), int(color[2] * factor))


def _lighten(color: tuple[int, int, int], factor: float = 1.4) -> tuple[int, int, int]:
    return (min(255, int(color[0] * factor)),
            min(255, int(color[1] * factor)),
            min(255, int(color[2] * factor)))


SKIN_COLOR = (255, 220, 185)
SKIN_SHADOW = (220, 185, 150)
SHOE_COLOR = (60, 50, 45)
EYE_COLOR = (30, 30, 40)


def generate_sprite_idle(body_color: tuple[int, int, int]) -> Image.Image:
    """Standing character facing forward."""
    img = Image.new("RGBA", (SPRITE_W, SPRITE_H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    dark = _darken(body_color)

    # Head
    draw.rectangle((5, 0, 10, 5), fill=SKIN_COLOR)
    draw.rectangle((5, 5, 10, 6), fill=SKIN_SHADOW)
    # Eyes
    draw.point((6, 2), fill=EYE_COLOR)
    draw.point((9, 2), fill=EYE_COLOR)

    # Body (shirt/suit)
    draw.rectangle((4, 6, 11, 15), fill=body_color)
    draw.rectangle((4, 6, 5, 15), fill=dark)
    draw.rectangle((10, 6, 11, 15), fill=dark)

    # Arms
    draw.rectangle((2, 7, 4, 14), fill=body_color)
    draw.rectangle((11, 7, 13, 14), fill=body_color)
    # Hands
    draw.rectangle((2, 14, 4, 15), fill=SKIN_COLOR)
    draw.rectangle((11, 14, 13, 15), fill=SKIN_COLOR)

    # Legs
    draw.rectangle((5, 16, 7, 21), fill=dark)
    draw.rectangle((8, 16, 10, 21), fill=dark)

    # Shoes
    draw.rectangle((4, 21, 7, 23), fill=SHOE_COLOR)
    draw.rectangle((8, 21, 11, 23), fill=SHOE_COLOR)

    return img


def generate_sprite_walk(body_color: tuple[int, int, int]) -> Image.Image:
    """Walking pose with legs apart."""
    img = Image.new("RGBA", (SPRITE_W, SPRITE_H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    dark = _darken(body_color)

    # Head
    draw.rectangle((5, 0, 10, 5), fill=SKIN_COLOR)
    draw.rectangle((5, 5, 10, 6), fill=SKIN_SHADOW)
    draw.point((6, 2), fill=EYE_COLOR)
    draw.point((9, 2), fill=EYE_COLOR)

    # Body
    draw.rectangle((4, 6, 11, 15), fill=body_color)
    draw.rectangle((4, 6, 5, 15), fill=dark)
    draw.rectangle((10, 6, 11, 15), fill=dark)

    # Arms (swinging)
    draw.rectangle((1, 8, 4, 13), fill=body_color)
    draw.rectangle((11, 9, 14, 14), fill=body_color)
    draw.rectangle((1, 13, 3, 14), fill=SKIN_COLOR)
    draw.rectangle((12, 14, 14, 15), fill=SKIN_COLOR)

    # Legs (apart)
    draw.rectangle((4, 16, 6, 20), fill=dark)
    draw.rectangle((9, 16, 11, 21), fill=dark)

    # Shoes (stride)
    draw.rectangle((3, 20, 6, 22), fill=SHOE_COLOR)
    draw.rectangle((9, 21, 12, 23), fill=SHOE_COLOR)

    return img


def generate_sprite_task(body_color: tuple[int, int, int]) -> Image.Image:
    """Doing a task — arms raised/working."""
    img = Image.new("RGBA", (SPRITE_W, SPRITE_H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    dark = _darken(body_color)
    light = _lighten(body_color)

    # Head (slightly tilted forward)
    draw.rectangle((5, 1, 10, 6), fill=SKIN_COLOR)
    draw.rectangle((5, 6, 10, 7), fill=SKIN_SHADOW)
    draw.point((6, 3), fill=EYE_COLOR)
    draw.point((9, 3), fill=EYE_COLOR)

    # Body
    draw.rectangle((4, 7, 11, 16), fill=body_color)
    draw.rectangle((4, 7, 5, 16), fill=dark)

    # Arms raised (working)
    draw.rectangle((2, 4, 4, 10), fill=body_color)
    draw.rectangle((11, 4, 13, 10), fill=body_color)
    draw.rectangle((2, 3, 4, 4), fill=SKIN_COLOR)
    draw.rectangle((11, 3, 13, 4), fill=SKIN_COLOR)

    # Tool sparkle
    draw.point((3, 1), fill=light)
    draw.point((12, 1), fill=light)
    draw.point((2, 2), fill=light)
    draw.point((13, 2), fill=light)

    # Legs
    draw.rectangle((5, 17, 7, 21), fill=dark)
    draw.rectangle((8, 17, 10, 21), fill=dark)
    draw.rectangle((4, 21, 7, 23), fill=SHOE_COLOR)
    draw.rectangle((8, 21, 11, 23), fill=SHOE_COLOR)

    return img


def generate_sprite_dead(body_color: tuple[int, int, int]) -> Image.Image:
    """Dead body — lying flat, X eyes."""
    img = Image.new("RGBA", (SPRITE_W, SPRITE_H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    dark = _darken(body_color, 0.4)
    gray_skin = _darken(SKIN_COLOR, 0.7)

    # Lying horizontally — rotated concept: body is wider, shorter
    # Head (on left side)
    draw.rectangle((1, 10, 5, 15), fill=gray_skin)
    # X eyes
    draw.point((2, 11), fill=(200, 50, 50))
    draw.point((4, 11), fill=(200, 50, 50))
    draw.point((3, 12), fill=(200, 50, 50))
    draw.point((2, 13), fill=(200, 50, 50))
    draw.point((4, 13), fill=(200, 50, 50))

    # Body (horizontal)
    draw.rectangle((5, 9, 14, 16), fill=dark)
    draw.rectangle((5, 9, 14, 10), fill=body_color)

    # Legs (sticking out right)
    draw.rectangle((14, 10, 15, 13), fill=dark)
    draw.rectangle((14, 14, 15, 16), fill=dark)

    return img


def generate_sprite_report(body_color: tuple[int, int, int]) -> Image.Image:
    """Reporting a body — arms up in alarm."""
    img = Image.new("RGBA", (SPRITE_W, SPRITE_H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    dark = _darken(body_color)

    # Head
    draw.rectangle((5, 0, 10, 5), fill=SKIN_COLOR)
    draw.rectangle((5, 5, 10, 6), fill=SKIN_SHADOW)
    # Open mouth (surprise)
    draw.point((7, 4), fill=(200, 80, 80))
    draw.point((8, 4), fill=(200, 80, 80))
    # Eyes wide
    draw.rectangle((6, 1, 7, 3), fill=EYE_COLOR)
    draw.rectangle((9, 1, 10, 3), fill=EYE_COLOR)

    # Body
    draw.rectangle((4, 6, 11, 15), fill=body_color)

    # Arms raised high
    draw.rectangle((1, 2, 4, 8), fill=body_color)
    draw.rectangle((11, 2, 14, 8), fill=body_color)
    draw.rectangle((1, 1, 3, 2), fill=SKIN_COLOR)
    draw.rectangle((12, 1, 14, 2), fill=SKIN_COLOR)

    # Exclamation mark above head
    draw.rectangle((7, -3, 8, -1), fill=(255, 80, 80))

    # Legs
    draw.rectangle((5, 16, 7, 21), fill=dark)
    draw.rectangle((8, 16, 10, 21), fill=dark)
    draw.rectangle((4, 21, 7, 23), fill=SHOE_COLOR)
    draw.rectangle((8, 21, 11, 23), fill=SHOE_COLOR)

    return img


class SpriteSheet:
    """Pre-generates and caches all sprite variants for a set of players."""

    def __init__(self) -> None:
        self._cache: dict[str, dict[str, Image.Image]] = {}

    def generate_for_player(self, player_id: str, color: tuple[int, int, int]) -> None:
        self._cache[player_id] = {
            "idle": generate_sprite_idle(color),
            "walk": generate_sprite_walk(color),
            "task": generate_sprite_task(color),
            "dead": generate_sprite_dead(color),
            "report": generate_sprite_report(color),
        }

    def get_sprite(
        self,
        player_id: str,
        variant: str = "idle",
        scale: int = 2,
    ) -> Image.Image:
        """Get a scaled sprite. Nearest-neighbor for pixel-art crispness."""
        sprites = self._cache.get(player_id)
        if sprites is None:
            self.generate_for_player(player_id, (150, 150, 150))
            sprites = self._cache[player_id]

        base = sprites.get(variant, sprites["idle"])
        if scale == 1:
            return base
        w, h = base.size
        return base.resize((w * scale, h * scale), Image.Resampling.NEAREST)

    def generate_all(
        self, player_ids: list[str], colors: dict[str, tuple[int, int, int]],
    ) -> None:
        for pid in player_ids:
            color = colors.get(pid, (150, 150, 150))
            self.generate_for_player(pid, color)
