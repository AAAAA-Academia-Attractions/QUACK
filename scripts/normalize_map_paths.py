"""Normalize map paths inside game.jsonl logs to a repo-relative path.

Each ``game_started`` event stores ``data.config.map``. Older runs
recorded the absolute path on whoever's machine generated the log.
This script rewrites that field to ``configs/maps/simple_ship.yaml``
so replay/evaluation works on any checkout.

Usage:
    python scripts/normalize_map_paths.py                  # dry-run
    python scripts/normalize_map_paths.py --write          # apply
    python scripts/normalize_map_paths.py --write game_logs/homogeneous/
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

TARGET_MAP = "configs/maps/simple_ship.yaml"


def normalize_log(log_path: Path, *, write: bool) -> tuple[bool, str | None]:
    """Return (changed, old_map_path)."""
    lines = log_path.read_text().splitlines(keepends=True)
    if not lines:
        return False, None

    changed = False
    old_map: str | None = None
    new_lines: list[str] = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            new_lines.append(line)
            continue
        event = json.loads(stripped)
        if event.get("event_type") == "game_started":
            config = event.setdefault("data", {}).setdefault("config", {})
            current = config.get("map")
            if current != TARGET_MAP:
                old_map = current if isinstance(current, str) else str(current)
                config["map"] = TARGET_MAP
                changed = True
                new_lines.append(json.dumps(event, ensure_ascii=False) + "\n")
                continue
        new_lines.append(line)

    if changed and write:
        log_path.write_text("".join(new_lines))

    return changed, old_map


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "root",
        nargs="?",
        default="game_logs",
        help="Directory to search recursively (default: game_logs)",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Apply changes (default: dry-run only)",
    )
    args = parser.parse_args()

    root = Path(args.root)
    if not root.exists():
        print(f"ERROR: not found: {root}", file=sys.stderr)
        sys.exit(1)

    logs = sorted(root.rglob("game.jsonl"))
    if not logs:
        print(f"No game.jsonl under {root}")
        sys.exit(0)

    changed_files = 0
    old_paths: Counter[str] = Counter()

    for log_path in logs:
        changed, old_map = normalize_log(log_path, write=args.write)
        if changed:
            changed_files += 1
            if old_map:
                old_paths[old_map] += 1

    mode = "Updated" if args.write else "Would update"
    print(f"{mode} {changed_files} / {len(logs)} game.jsonl files → {TARGET_MAP}")
    if old_paths:
        print("\nPrevious map paths:")
        for path, count in old_paths.most_common():
            print(f"  {count:3d}x  {path}")

    if not args.write and changed_files:
        print("\nRe-run with --write to apply.")


if __name__ == "__main__":
    main()
