"""CLI: Evaluate all game logs in a directory through the QUACK evaluation pipeline.

Usage:
    python scripts/evaluate_batch.py game_logs/ [--tier3] [--api-key KEY] [--output batch_results.json]
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quack.evaluation.evaluator import BatchEvaluator
from quack.evaluation.report import format_batch_report, save_json_report


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Evaluate all QUACK game logs in a directory",
    )
    parser.add_argument(
        "log_dir",
        help="Directory containing game log JSONL files",
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
        default="",
        help="Base URL for the LLM API endpoint",
    )
    parser.add_argument(
        "--model",
        default="gpt-4o-mini",
        help="LLM model for Tier 3 claim extraction (default: gpt-4o-mini)",
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

    evaluator = BatchEvaluator(map_config_path=args.map_config)

    try:
        batch_result = evaluator.evaluate_batch(
            log_dir=args.log_dir,
            run_tier3=args.tier3,
            llm_api_key=api_key,
            llm_model=args.model,
            llm_base_url=args.base_url,
        )
    except Exception as e:
        print(f"ERROR: Batch evaluation failed: {e}")
        sys.exit(1)

    report = format_batch_report(batch_result)
    print(report)

    if args.output:
        save_json_report(batch_result, args.output)
        print(f"\nResults saved to: {args.output}")


if __name__ == "__main__":
    main()
