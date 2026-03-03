"""Test that the renderer can display Simplified Chinese.
Run: python scripts/test_chinese_font.py
Output: renders/test_chinese.png, renders/test_chinese_speech.png
Inspect to confirm characters render correctly (no empty squares).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PIL import Image, ImageDraw

from ggd_ai.engine.game_state import GameState, Player, Team
from ggd_ai.map.game_map import GameMap
from ggd_ai.rendering.map_renderer import MapRenderer, _try_load_font
from ggd_ai.utils.config import load_map_config

SAMPLES = ["测试中文", "简体中文显示正常", "我在餐厅发现了尸体。"]


def test_simple_font() -> None:
    font = _try_load_font(20)
    img = Image.new("RGB", (400, 120), (30, 32, 40))
    draw = ImageDraw.Draw(img)
    y = 10
    for line in SAMPLES:
        draw.text((20, y), line, fill=(255, 255, 255), font=font)
        y += 35
    out = Path("renders/test_chinese.png")
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out)
    print(f"Saved {out}")


def test_speech_frame() -> None:
    """Test render_speech with Chinese discussion content."""
    map_config = load_map_config("configs/maps/simple_ship.yaml")
    game_map = GameMap.from_config(map_config)
    renderer = MapRenderer(game_map)
    renderer.assign_player_colors(["p0", "p1"])
    renderer.set_player_names({"p0": "Alice", "p1": "Bob"})

    state = GameState()
    state.players["p0"] = Player("p0", "Alice", "Goose", Team.GOOSE, True, "cafeteria")
    state.players["p1"] = Player("p1", "Bob", "Goose", Team.GOOSE, True, "medbay")

    discussion = [
        {"player_id": "p0", "name": "Alice", "message": "我在餐厅发现了尸体，是Charlie。"},
    ]
    speech_img = renderer.render_speech(
        state, "p1", "我一直在医疗舱做任务，没看到任何人。我认为应该票出Alice。",
        discussion, tick=10,
    )
    out = Path("renders/test_chinese_speech.png")
    speech_img.save(out)
    print(f"Saved {out}")


def main() -> None:
    test_simple_font()
    test_speech_frame()
    print("Done. Open the PNGs — if you see 简体中文 (not squares), fonts work.")


if __name__ == "__main__":
    main()
