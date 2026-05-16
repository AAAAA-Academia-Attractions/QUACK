"""CLI: Evaluate all game logs under a directory through the QUACK evaluation pipeline.

Recursively discovers ``game.jsonl`` files (new structure) and ``game_*.jsonl``
files (legacy flat structure).  Results are grouped by experiment condition
parsed from the directory path.

Usage:
    # Evaluate all games for a specific homogeneous model
    python scripts/evaluate_batch.py game_logs/homogeneous/gpt5.4/

    # Evaluate all homogeneous models
    python scripts/evaluate_batch.py game_logs/homogeneous/

    # Evaluate a heterogeneous condition
    python scripts/evaluate_batch.py game_logs/heterogeneous/geese_gpt5.4_duck_claude_opus4.6/

    # Evaluate everything
    python scripts/evaluate_batch.py game_logs/
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quack.evaluation.evaluator import BatchResult, GameEvaluator, EvaluationResult
from quack.evaluation.report import format_batch_report, save_json_report

logger = logging.getLogger(__name__)


def _discover_log_files(root: Path) -> list[Path]:
    """Recursively find all game log JSONL files."""
    logs: list[Path] = []
    for p in sorted(root.rglob("game.jsonl")):
        logs.append(p)
    for p in sorted(root.glob("game_*.jsonl")):
        if p not in logs:
            logs.append(p)
    return logs


def _infer_condition(log_path: Path, search_root: Path) -> str:
    """Derive the experiment condition name from the directory structure.

    Expected structures:
        game_logs/homogeneous/<model>/<run>/game.jsonl  -> homogeneous/<model>
        game_logs/heterogeneous/<condition>/<run>/game.jsonl -> heterogeneous/<condition>
        game_logs/game_XXXXX.jsonl  -> legacy
    """
    try:
        rel = log_path.parent.relative_to(search_root)
    except ValueError:
        return "unknown"

    parts = rel.parts
    if len(parts) >= 2 and parts[0] in ("homogeneous", "heterogeneous"):
        return f"{parts[0]}/{parts[1]}"
    if len(parts) >= 1 and parts[0] in ("homogeneous", "heterogeneous"):
        return parts[0]
    if log_path.name.startswith("game_") and log_path.name.endswith(".jsonl"):
        return "legacy"
    return "/".join(parts) if parts else "root"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Evaluate all QUACK game logs in a directory",
    )
    parser.add_argument(
        "log_dir",
        help="Directory containing game logs (searched recursively)",
    )
    parser.add_argument(
        "--tier3",
        action="store_true",
        help="Run Tier 3 statement verification (requires LLM API key)",
    )
    parser.add_argument(
        "--api-key",
        default="",
        help="API key for the LLM used in Tier 3 claim extraction",
    )
    parser.add_argument(
        "--base-url",
        default="https://endpoint.greatrouter.com",
        help="Base URL for the LLM API endpoint",
    )
    parser.add_argument(
        "--model",
        default="gpt-5.2",
        help="LLM model for Tier 3 claim extraction (default: gpt-5.2)",
    )
    parser.add_argument(
        "--map-config",
        default="configs/maps/simple_ship.yaml",
        help="Path to the map config YAML",
    )
    parser.add_argument(
        "--output", "-o",
        default=None,
        help="Save aggregated results as JSON to this path",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose logging",
    )
    parser.add_argument(
        "--save-tier3-audit",
        action="store_true",
        default=False,
        help="Write per-claim audit to tier3_claims.jsonl alongside each game's evaluation.json",
    )
    args = parser.parse_args()

    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    api_key = args.api_key
    if args.tier3 and not api_key:
        key_path = Path(__file__).resolve().parent.parent / "api_key.txt"
        if key_path.exists():
            api_key = key_path.read_text().strip()
            print(f"Loaded API key from {key_path}")

    search_root = Path(args.log_dir)
    log_files = _discover_log_files(search_root)

    if not log_files:
        print(f"No game log files found under {search_root}")
        sys.exit(0)

    print(f"Found {len(log_files)} game log(s) under {search_root}")

    evaluator = GameEvaluator(map_config_path=args.map_config)

    condition_results: dict[str, list[EvaluationResult]] = {}
    all_results: list[EvaluationResult] = []

    for i, log_file in enumerate(log_files, 1):
        condition = _infer_condition(log_file, search_root)
        logger.info("Processing game %d/%d (%s): %s", i, len(log_files), condition, log_file)

        try:
            result = evaluator.evaluate(
                str(log_file),
                run_tier3=args.tier3,
                llm_api_key=api_key,
                llm_model=args.model,
                llm_base_url=args.base_url,
                save_tier3_audit=args.save_tier3_audit,
            )
            all_results.append(result)
            condition_results.setdefault(condition, []).append(result)

            # Save per-game evaluation.json alongside the log if it's the new structure
            if log_file.name == "game.jsonl":
                eval_path = log_file.parent / "evaluation.json"
                save_json_report(result, str(eval_path))
                logger.info("Saved per-game evaluation to %s", eval_path)

        except Exception as e:
            logger.error("Failed to evaluate %s: %s", log_file, e)

    # Print per-condition summaries
    from quack.evaluation.evaluator import _aggregate_numeric_fields
    for condition, results in sorted(condition_results.items()):
        print(f"\n{'=' * 60}")
        print(f"Condition: {condition} ({len(results)} games)")
        print("=" * 60)
        batch = BatchResult(
            num_games=len(results),
            results=results,
            aggregated=_build_aggregated(results),
        )
        print(format_batch_report(batch))

    # Overall summary
    overall_batch = BatchResult(
        num_games=len(all_results),
        results=all_results,
        aggregated=_build_aggregated(all_results),
    )

    print(f"\n{'=' * 60}")
    print(f"OVERALL ({len(all_results)} games)")
    print("=" * 60)
    print(format_batch_report(overall_batch))

    # Save outputs
    eval_dir = search_root / "evaluation"
    eval_dir.mkdir(parents=True, exist_ok=True)

    for condition, results in sorted(condition_results.items()):
        cond_filename = condition.replace("/", "_") + ".json"
        cond_batch = BatchResult(
            num_games=len(results),
            results=results,
            aggregated=_build_aggregated(results),
        )
        save_json_report(cond_batch, str(eval_dir / cond_filename))

    save_json_report(overall_batch, str(eval_dir / "summary.json"))
    print(f"\nAggregated results saved to {eval_dir}/")

    if args.output:
        save_json_report(overall_batch, args.output)
        print(f"Full results also saved to: {args.output}")


def _build_aggregated(results: list[EvaluationResult]) -> dict[str, Any]:
    """Replicate BatchEvaluator._aggregate without needing the class."""
    from quack.evaluation.evaluator import _aggregate_numeric_fields

    if not results:
        return {}

    agg: dict[str, Any] = {}

    t1_metrics = [r.tier1 for r in results if r.tier1]
    if t1_metrics:
        agg["tier1"] = _aggregate_numeric_fields(
            [m.to_dict() for m in t1_metrics],
            [
                "game_duration_ticks", "tasks_completed", "tasks_total",
                "task_completion_rate", "total_kills", "total_meetings",
                "total_ejections", "correct_ejections", "wrong_ejections",
                "ejection_accuracy",
            ],
        )
        winners = [m.winner for m in t1_metrics]
        agg["tier1"]["goose_win_rate"] = winners.count("goose") / len(winners)
        agg["tier1"]["duck_win_rate"] = winners.count("duck") / len(winners)

    t2_metrics = [r.tier2 for r in results if r.tier2]
    if t2_metrics:
        agg["tier2"] = _aggregate_numeric_fields(
            [m.to_dict() for m in t2_metrics],
            [
                "goose_voting_accuracy", "goose_skip_rate", "task_efficiency",
                "avg_rooms_visited_goose", "avg_rooms_visited_duck",
                "avg_kills_per_game", "avg_post_kill_displacement",
                "self_report_rate", "cooldown_utilization",
            ],
        )

    t3_metrics = [r.tier3 for r in results if r.tier3]
    if t3_metrics:
        agg["tier3"] = _aggregate_numeric_fields(
            [m.to_dict() for m in t3_metrics],
            [
                "goose_truthfulness", "duck_truthfulness",
                "spatial_hallucination_rate", "deception_rate",
                "deception_sophistication", "accusation_accuracy",
                "lie_detection_rate",
            ],
        )

    return agg


if __name__ == "__main__":
    main()
