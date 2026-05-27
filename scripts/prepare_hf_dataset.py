"""Copy raw game.jsonl logs into a Hugging Face–ready dataset folder.

Preserves the experiment layout under ``homogeneous/`` and
``heterogeneous/``, writes a manifest, and a short README.

Usage:
    python scripts/prepare_hf_dataset.py
    python scripts/prepare_hf_dataset.py -o hf_dataset/QUACK --force

Then upload:
    huggingface-cli upload 5a-academia-attractions/QUACK hf_dataset/QUACK --repo-type=dataset
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
from pathlib import Path

_SEED_RE = re.compile(r"seed(\d+)")


def _parse_run_meta(
    log_path: Path, category: str, condition: str, repo_root: Path,
) -> dict:
    run_dir = log_path.parent.name
    m = _SEED_RE.search(run_dir)
    seed = int(m.group(1)) if m else None
    try:
        source_rel = str(log_path.relative_to(repo_root))
    except ValueError:
        source_rel = str(log_path)
    return {
        "category": category,
        "condition": condition,
        "run_dir": run_dir,
        "seed": seed,
        "source_path": source_rel,
        "dataset_path": f"{category}/{condition}/{run_dir}/game.jsonl",
    }


def prepare(
    source_root: Path,
    output_root: Path,
    *,
    force: bool,
) -> None:
    if output_root.exists():
        if not force:
            raise SystemExit(
                f"{output_root} already exists. Pass --force to replace it."
            )
        shutil.rmtree(output_root)

    output_root.mkdir(parents=True, exist_ok=True)
    manifest_path = output_root / "manifest.jsonl"
    copied = 0
    repo_root = source_root.parent

    with manifest_path.open("w") as manifest_f:
        for category in ("homogeneous", "heterogeneous"):
            cat_src = source_root / category
            if not cat_src.is_dir():
                continue
            for condition_dir in sorted(cat_src.iterdir()):
                if not condition_dir.is_dir():
                    continue
                condition = condition_dir.name
                for run_dir in sorted(condition_dir.iterdir()):
                    if not run_dir.is_dir():
                        continue
                    src_log = run_dir / "game.jsonl"
                    if not src_log.is_file():
                        continue

                    dest = output_root / category / condition / run_dir.name / "game.jsonl"
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src_log, dest)
                    copied += 1

                    meta = _parse_run_meta(src_log, category, condition, repo_root)
                    manifest_f.write(json.dumps(meta, ensure_ascii=False) + "\n")

    readme = output_root / "README.md"
    readme.write_text(
        f"""---
license: mit
task_categories:
  - other
language:
  - en
  - zh
tags:
  - social-deduction
  - multi-agent
  - vision-language-model
  - game-logs
size_categories:
  - n<1K
---

# QUACK Game Logs

Raw structured event logs (`game.jsonl`) from the QUACK multimodal social deduction benchmark.

## Contents

- **{copied}** games across **9** experimental conditions
- **3** homogeneous (all players same VLM): `gpt5.5`, `claude_opus4.7`, `gemini3.1pro`
- **6** heterogeneous (geese vs duck model pairs)
- **30** seeds per condition (seeds 1–30)

## Layout

```
homogeneous/<model>/<run_dir>/game.jsonl
heterogeneous/geese_<goose>_duck_<duck>/<run_dir>/game.jsonl
manifest.jsonl   # one metadata record per game
```

## Log format

Each `game.jsonl` line is a JSON event (`event_type`, `tick`, `data`, ...).
The `game_started` event includes `initial_state` and `config` for full replay.

See the [QUACK repository](https://github.com/) for evaluation and rendering tools.

## Citation

If you use this dataset, please cite the QUACK paper (TBD).
""",
        encoding="utf-8",
    )

    print(f"Copied {copied} game.jsonl files → {output_root}")
    print(f"Manifest: {manifest_path}")
    print(f"README:   {readme}")
    print()
    print("Upload:")
    print(
        f"  huggingface-cli upload 5a-academia-attractions/QUACK "
        f"{output_root} --repo-type=dataset"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source", default="game_logs",
        help="Source game_logs root (default: game_logs)",
    )
    parser.add_argument(
        "-o", "--output", default="hf_dataset/QUACK",
        help="Output dataset folder (default: hf_dataset/QUACK)",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Replace output folder if it exists",
    )
    args = parser.parse_args()
    prepare(
        Path(args.source).resolve(),
        Path(args.output).resolve(),
        force=args.force,
    )


if __name__ == "__main__":
    main()
