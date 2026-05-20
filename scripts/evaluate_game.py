"""CLI: Evaluate a single game log through the QUACK evaluation pipeline.

Usage:
    python scripts/evaluate_game.py game_logs/homogeneous/gpt5.4/20260308_143022_seed42/game.jsonl
    python scripts/evaluate_game.py game_logs/game_XXXXX.jsonl   # legacy flat logs
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quack.evaluation.evaluator import GameEvaluator
from quack.evaluation.report import format_game_report, save_json_report


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Evaluate a single QUACK game log",
    )
    parser.add_argument(
        "log_path",
        help="Path to the game log JSONL file",
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
        help="Path to the map config YAML (default: configs/maps/simple_ship.yaml)",
    )
    parser.add_argument(
        "--output", "-o",
        default=None,
        help="Save results as JSON to this path (default: evaluation.json next to the log)",
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
        help="Write per-claim audit to tier3_claims.jsonl alongside evaluation.json",
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
        else:
            print("WARNING: --tier3 requires an API key. Provide --api-key or create api_key.txt")

    evaluator = GameEvaluator(map_config_path=args.map_config)

    try:
        result = evaluator.evaluate(
            log_path=args.log_path,
            run_tier3=args.tier3,
            llm_api_key=api_key,
            llm_model=args.model,
            llm_base_url=args.base_url,
            save_tier3_audit=args.save_tier3_audit,
        )
    except Exception as e:
        print(f"ERROR: Evaluation failed: {e}")
        sys.exit(1)

    report = format_game_report(result)
    print(report)

    # Determine output path: explicit flag > auto-detect alongside game.jsonl
    output_path = args.output
    if output_path is None:
        log_p = Path(args.log_path)
        if log_p.name == "game.jsonl":
            output_path = str(log_p.parent / "evaluation.json")
        else:
            output_path = None

    if output_path:
        save_json_report(result, output_path)
        print(f"\nResults saved to: {output_path}")


if __name__ == "__main__":
    main()
