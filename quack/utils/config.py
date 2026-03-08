"""YAML configuration loader."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def load_yaml(path: str | Path) -> dict[str, Any]:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    with open(path) as f:
        return yaml.safe_load(f)


def load_game_config(path: str | Path) -> dict[str, Any]:
    return load_yaml(path)


def load_map_config(path: str | Path) -> dict[str, Any]:
    return load_yaml(path)
