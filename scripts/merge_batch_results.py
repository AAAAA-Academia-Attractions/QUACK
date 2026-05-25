"""CLI: Merge multiple per-game ``batch_results.json``-style files and
re-aggregate them as if they had been produced by a single
``evaluate_batch.py`` invocation.

Use this when a few extra games were evaluated in a separate pass
(e.g. supplements/reruns landing in ``/tmp``) and you want the
combined Tier 1/2/3 means and standard deviations.

Aggregation reuses ``quack.evaluation.evaluator._aggregate_numeric_fields``
so the output schema is identical to a fresh batch run. Duplicate game
runs (same run-directory basename across inputs) are de-duplicated; the
record from the **last** file passed on the CLI wins (so put your
preferred-source file last).

Usage:
    # Merge a supplement of 3 games into the canonical 27-game file
    python scripts/merge_batch_results.py \
        game_logs/heterogeneous/<cond>/batch_results.json \
        game_logs/heterogeneous/<cond>/supplement_4_10_27_results.json \
        -o game_logs/heterogeneous/<cond>/batch_results.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quack.evaluation.evaluator import _aggregate_numeric_fields


_TIER1_FIELDS = [
    "game_duration_ticks", "tasks_completed", "tasks_total",
    "task_completion_rate", "total_kills", "total_meetings",
    "total_ejections", "correct_ejections", "wrong_ejections",
    "ejection_accuracy",
]
_TIER2_FIELDS = [
    "goose_voting_accuracy", "goose_skip_rate", "task_efficiency",
    "avg_rooms_visited_goose", "avg_rooms_visited_duck",
    "avg_kills_per_game", "avg_post_kill_displacement",
    "self_report_rate", "cooldown_utilization",
]
_TIER3_FIELDS = [
    "goose_truthfulness", "duck_truthfulness",
    "spatial_hallucination_rate", "deception_rate",
    "deception_sophistication", "accusation_accuracy",
    "unsupported_accusation_rate", "lie_detection_rate",
]


def _run_key(per_game_entry: dict[str, Any]) -> str:
    """Stable de-dup key derived from the run directory name (the
    parent of ``game.jsonl``), so the same run evaluated from
    ``/tmp/...`` and from ``game_logs/...`` collapses correctly.
    """
    lp = per_game_entry.get("log_path", "")
    if not lp:
        return per_game_entry.get("game_id", "") or json.dumps(per_game_entry)
    return Path(lp).parent.name or lp


def _normalize_log_path(
    entry: dict[str, Any], canonical_root: Path | None,
) -> dict[str, Any]:
    """If the entry's log_path points outside ``canonical_root`` but a
    same-named run directory exists under it, rewrite the log_path to
    that canonical location. This keeps the merged file self-consistent
    when supplements were evaluated from ``/tmp``.
    """
    if canonical_root is None:
        return entry
    lp = entry.get("log_path", "")
    if not lp:
        return entry
    run_dir_name = Path(lp).parent.name
    if not run_dir_name:
        return entry
    candidate = canonical_root / run_dir_name / "game.jsonl"
    if candidate.exists():
        new_entry = dict(entry)
        new_entry["log_path"] = str(candidate)
        return new_entry
    return entry


def _aggregate(per_game: list[dict[str, Any]]) -> dict[str, Any]:
    """Re-run the same aggregation that ``BatchEvaluator._aggregate``
    performs, but on raw per-game dicts (as serialized in
    ``batch_results.json``).
    """
    if not per_game:
        return {}

    agg: dict[str, Any] = {}

    t1_dicts = [g["tier1"] for g in per_game if g.get("tier1")]
    if t1_dicts:
        agg["tier1"] = _aggregate_numeric_fields(t1_dicts, _TIER1_FIELDS)
        winners = [d.get("winner") for d in t1_dicts]
        n = len(winners)
        agg["tier1"]["goose_win_rate"] = winners.count("goose") / n
        agg["tier1"]["duck_win_rate"] = winners.count("duck") / n

    t2_dicts = [g["tier2"] for g in per_game if g.get("tier2")]
    if t2_dicts:
        agg["tier2"] = _aggregate_numeric_fields(t2_dicts, _TIER2_FIELDS)

    t3_dicts = [g["tier3"] for g in per_game if g.get("tier3")]
    if t3_dicts:
        agg["tier3"] = _aggregate_numeric_fields(t3_dicts, _TIER3_FIELDS)

    return agg


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "inputs", nargs="+",
        help="Two or more batch_results-style JSON files. When the "
             "same run appears in multiple files, the entry from the "
             "LAST file wins.",
    )
    parser.add_argument(
        "-o", "--output", required=True,
        help="Where to write the merged + re-aggregated JSON.",
    )
    parser.add_argument(
        "--canonical-root",
        default=None,
        help="If set, log_paths from supplements pointing to ephemeral "
             "locations (e.g. /tmp) are rewritten to "
             "``<canonical-root>/<run-dir>/game.jsonl`` when that file "
             "exists. Defaults to the parent of the FIRST input.",
    )
    args = parser.parse_args()

    if len(args.inputs) < 2:
        parser.error("Need at least two input files to merge.")

    canonical_root: Path | None = None
    if args.canonical_root:
        canonical_root = Path(args.canonical_root)
    else:
        first = Path(args.inputs[0]).resolve().parent
        # Heuristic: only auto-pick canonical_root if it looks like a
        # condition dir (contains run directories with ``game.jsonl``).
        if any((p / "game.jsonl").exists() for p in first.iterdir() if p.is_dir()):
            canonical_root = first

    # Last-wins dedup keyed on run-dir basename.
    by_run: dict[str, dict[str, Any]] = {}
    source_counts: dict[str, int] = {}
    for in_path in args.inputs:
        data = json.loads(Path(in_path).read_text())
        per_game = data.get("per_game") or []
        added = 0
        replaced = 0
        for entry in per_game:
            entry = _normalize_log_path(entry, canonical_root)
            key = _run_key(entry)
            if key in by_run:
                replaced += 1
            else:
                added += 1
            by_run[key] = entry
        source_counts[in_path] = len(per_game)
        print(f"  {in_path}: {len(per_game)} games "
              f"({added} new, {replaced} replaced earlier entries)")

    merged_per_game = sorted(
        by_run.values(),
        key=lambda g: _seed_sort_key(g.get("log_path", "") or g.get("game_id", "")),
    )

    aggregated = _aggregate(merged_per_game)

    out = {
        "num_games": len(merged_per_game),
        "aggregated": aggregated,
        "per_game": merged_per_game,
    }

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2, default=str))
    print(
        f"\nMerged {sum(source_counts.values())} entries from "
        f"{len(args.inputs)} files into {len(merged_per_game)} unique "
        f"games → {out_path}"
    )


_SEED_RE = re.compile(r"seed(\d+)")


def _seed_sort_key(s: str) -> tuple[int, str]:
    """Sort by numeric seed if present, else lexicographically."""
    m = _SEED_RE.search(s)
    return (int(m.group(1)) if m else 10**9, s)


if __name__ == "__main__":
    main()
