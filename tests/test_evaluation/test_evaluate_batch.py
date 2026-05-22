"""Tests for the batch-evaluator helper functions (``_infer_condition``).

The condition-inference helper used to silently degrade to per-game
"conditions" whenever the user scoped the search root below
``game_logs/``. These tests pin the post-fix behavior so the
condition name is stable regardless of search-root depth — that's
the precondition for the per-condition aggregation written into
``<eval_dir>/<condition>.json``.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


def _import_evaluate_batch():
    """Load ``scripts/evaluate_batch.py`` as a module without
    executing its ``main()`` (the file is normally invoked as a CLI).
    """
    path = Path(__file__).resolve().parents[2] / "scripts" / "evaluate_batch.py"
    spec = importlib.util.spec_from_file_location("evaluate_batch", path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["evaluate_batch"] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def evaluate_batch():
    return _import_evaluate_batch()


class TestInferCondition:
    @staticmethod
    def _make_game(tmp_path: Path, category: str, condition: str,
                   run: str = "20260520_120000_seed1") -> Path:
        """Create a fake game.jsonl under
        ``tmp_path/game_logs/<category>/<condition>/<run>/game.jsonl``.
        """
        path = tmp_path / "game_logs" / category / condition / run / "game.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
        return path

    def test_homogeneous_search_from_game_logs_root(
        self, tmp_path: Path, evaluate_batch,
    ) -> None:
        """Top-level search root: condition resolves to
        ``homogeneous/<model>``."""
        log = self._make_game(tmp_path, "homogeneous", "gpt5.5")
        cond = evaluate_batch._infer_condition(log, tmp_path / "game_logs")
        assert cond == "homogeneous/gpt5.5"

    def test_homogeneous_search_from_category_dir(
        self, tmp_path: Path, evaluate_batch,
    ) -> None:
        """Scoped to the category dir: condition is still
        ``homogeneous/<model>`` (the Bug-fix preserves this)."""
        log = self._make_game(tmp_path, "homogeneous", "claude_opus4.7")
        cond = evaluate_batch._infer_condition(
            log, tmp_path / "game_logs" / "homogeneous",
        )
        assert cond == "homogeneous/claude_opus4.7"

    def test_homogeneous_search_from_model_dir(
        self, tmp_path: Path, evaluate_batch,
    ) -> None:
        """Scoped to a single model: condition still resolves to
        ``homogeneous/<model>`` — pre-fix this returned
        ``<run>`` (per-game), which broke aggregation."""
        log = self._make_game(tmp_path, "homogeneous", "gemini3.1pro")
        cond = evaluate_batch._infer_condition(
            log, tmp_path / "game_logs" / "homogeneous" / "gemini3.1pro",
        )
        assert cond == "homogeneous/gemini3.1pro"

    def test_heterogeneous_search_from_game_logs_root(
        self, tmp_path: Path, evaluate_batch,
    ) -> None:
        log = self._make_game(
            tmp_path, "heterogeneous", "geese_gpt5.5_duck_claude_opus4.7",
        )
        cond = evaluate_batch._infer_condition(log, tmp_path / "game_logs")
        assert cond == "heterogeneous/geese_gpt5.5_duck_claude_opus4.7"

    def test_heterogeneous_search_from_condition_dir(
        self, tmp_path: Path, evaluate_batch,
    ) -> None:
        """Scoping to the specific heterogeneous-condition dir still
        returns the full ``heterogeneous/<condition>`` name."""
        log = self._make_game(
            tmp_path, "heterogeneous",
            "geese_gemini3.1pro_duck_gpt5.5",
        )
        cond = evaluate_batch._infer_condition(
            log,
            tmp_path / "game_logs" / "heterogeneous"
            / "geese_gemini3.1pro_duck_gpt5.5",
        )
        assert cond == "heterogeneous/geese_gemini3.1pro_duck_gpt5.5"

    def test_legacy_flat_log(self, tmp_path: Path, evaluate_batch) -> None:
        """Flat ``game_XYZ.jsonl`` (no category in the path)."""
        log = tmp_path / "game_logs" / "game_001.jsonl"
        log.parent.mkdir(parents=True, exist_ok=True)
        log.touch()
        cond = evaluate_batch._infer_condition(log, tmp_path / "game_logs")
        assert cond == "legacy"

    def test_two_invocations_same_condition_consistent(
        self, tmp_path: Path, evaluate_batch,
    ) -> None:
        """Same game evaluated via two different search-root depths
        must yield the same condition name — otherwise per-condition
        aggregation would write to different output files depending
        on how the script was invoked."""
        log = self._make_game(tmp_path, "homogeneous", "gpt5.5",
                               run="20260101_seedX")
        a = evaluate_batch._infer_condition(log, tmp_path / "game_logs")
        b = evaluate_batch._infer_condition(
            log, tmp_path / "game_logs" / "homogeneous",
        )
        c = evaluate_batch._infer_condition(
            log, tmp_path / "game_logs" / "homogeneous" / "gpt5.5",
        )
        assert a == b == c == "homogeneous/gpt5.5"


class TestDiscoverLogFiles:
    def test_discovers_nested_game_jsonl(
        self, tmp_path: Path, evaluate_batch,
    ) -> None:
        """``_discover_log_files`` recursively finds all
        ``game.jsonl`` under the search root."""
        root = tmp_path / "game_logs"
        for cond in ("homogeneous/gpt5.5", "homogeneous/claude_opus4.7",
                     "heterogeneous/geese_gpt5.5_duck_gemini3.1pro"):
            for seed in (1, 2):
                p = root / cond / f"run_seed{seed}" / "game.jsonl"
                p.parent.mkdir(parents=True, exist_ok=True)
                p.touch()
        found = evaluate_batch._discover_log_files(root)
        assert len(found) == 6
        # The discovered list must be deterministically sorted so
        # condition-batch ordering is stable across invocations.
        assert found == sorted(found)
