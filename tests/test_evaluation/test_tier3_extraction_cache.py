"""Acceptance tests for Bug C (deterministic extraction + cache + dedup)
and Bug E (audit/metrics consistency).

These tests mock ``litellm.completion`` so they run without API keys and
without making any network calls.
"""

from __future__ import annotations

import json
import sys
import types
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from quack.evaluation.game_reconstructor import GameReconstructor
from quack.evaluation.tier3_statement_verification import (
    ExtractionCache,
    StatementVerificationPipeline,
    _canonical_claim_signature,
    _dedup_claims,
    _extract_claims_sync,
    _parse_extraction_response,
)
from quack.map.game_map import GameMap

from .conftest import build_minimal_game_events


# ---------- helpers ----------

def _install_mock_litellm(claims_returned: list[dict[str, Any]] | str) -> MagicMock:
    """Install a fake ``litellm`` module whose ``completion`` returns the
    JSON-serialized ``claims_returned`` (or a string verbatim).
    Returns the mock so tests can inspect call counts."""
    fake_litellm = types.ModuleType("litellm")
    completion = MagicMock()
    if isinstance(claims_returned, str):
        body = claims_returned
    else:
        body = json.dumps(claims_returned)

    def _completion(*args, **kwargs):
        choice = types.SimpleNamespace(message=types.SimpleNamespace(content=body))
        return types.SimpleNamespace(choices=[choice])

    completion.side_effect = _completion
    fake_litellm.completion = completion
    sys.modules["litellm"] = fake_litellm
    return completion


@pytest.fixture
def cache_path(tmp_path: Path) -> Path:
    return tmp_path / "tier3_extraction_cache.jsonl"


@pytest.fixture
def restore_litellm():
    """Snapshot/restore sys.modules['litellm'] around each test so mocks
    in one test don't leak into the next."""
    saved = sys.modules.get("litellm")
    yield
    if saved is None:
        sys.modules.pop("litellm", None)
    else:
        sys.modules["litellm"] = saved


# ---------- Cache key + parse ----------

class TestExtractionCacheKey:
    def test_key_includes_prompt_version(self) -> None:
        k1 = ExtractionCache.make_key(
            model="gpt-5.5", prompt_version="v1",
            speaker_id="player_0", meeting_idx=0, message="hi",
        )
        k2 = ExtractionCache.make_key(
            model="gpt-5.5", prompt_version="v2",
            speaker_id="player_0", meeting_idx=0, message="hi",
        )
        assert k1 != k2, "bumping prompt_version must invalidate cache"

    def test_key_hashes_message(self) -> None:
        k1 = ExtractionCache.make_key(
            "gpt-5.5", "v1", "player_0", 0, "I was in medbay",
        )
        k2 = ExtractionCache.make_key(
            "gpt-5.5", "v1", "player_0", 0, "I was in electrical",
        )
        assert k1 != k2

    def test_cache_roundtrip(self, cache_path: Path) -> None:
        cache = ExtractionCache(cache_path)
        assert cache.get("k") is None
        cache.set("k", [{"type": "location", "subject": "Alice", "room": "medbay"}])
        # New cache instance must find the entry on disk
        cache2 = ExtractionCache(cache_path)
        got = cache2.get("k")
        assert got == [{"type": "location", "subject": "Alice", "room": "medbay"}]


class TestParseExtractionResponse:
    def test_plain_array(self) -> None:
        out = _parse_extraction_response('[{"type": "location"}]')
        assert out == [{"type": "location"}]

    def test_code_fence_wrapper(self) -> None:
        out = _parse_extraction_response(
            "```json\n[{\"type\": \"location\"}]\n```"
        )
        assert out == [{"type": "location"}]

    def test_single_dict_becomes_list(self) -> None:
        out = _parse_extraction_response('{"type": "location"}')
        assert out == [{"type": "location"}]

    def test_garbage_returns_empty(self) -> None:
        assert _parse_extraction_response("definitely not json") == []


# ---------- Dedup ----------

class TestDedupClaims:
    def test_exact_duplicates_collapsed(self) -> None:
        claims = [
            {"type": "location", "subject": "Alice", "room": "medbay",
             "temporal": "this round"},
            {"type": "location", "subject": "Alice", "room": "medbay",
             "temporal": "this round"},
            {"type": "location", "subject": "Alice", "room": "medbay",
             "temporal": "this round"},
        ]
        deduped, collapsed = _dedup_claims(claims)
        assert len(deduped) == 1
        assert collapsed == 2

    def test_paraphrased_duplicates_collapsed(self) -> None:
        """Different but synonymous temporal phrasings bucket together."""
        claims = [
            {"type": "location", "subject": "Alice", "room": "medbay",
             "temporal": "this round"},
            {"type": "location", "subject": "Alice", "room": "medbay",
             "temporal": "since last meeting"},
        ]
        deduped, collapsed = _dedup_claims(claims)
        assert len(deduped) == 1
        assert collapsed == 1

    def test_different_rooms_not_collapsed(self) -> None:
        claims = [
            {"type": "location", "subject": "Alice", "room": "medbay",
             "temporal": "this round"},
            {"type": "location", "subject": "Alice", "room": "electrical",
             "temporal": "this round"},
        ]
        deduped, collapsed = _dedup_claims(claims)
        assert len(deduped) == 2
        assert collapsed == 0

    def test_different_subjects_not_collapsed(self) -> None:
        claims = [
            {"type": "location", "subject": "Alice", "room": "medbay",
             "temporal": "this round"},
            {"type": "location", "subject": "Bob", "room": "medbay",
             "temporal": "this round"},
        ]
        deduped, collapsed = _dedup_claims(claims)
        assert len(deduped) == 2

    def test_canonical_signature_normalizes_room_aliases(self) -> None:
        """med bay / medbay / med must share the same signature."""
        sigs = {
            _canonical_claim_signature({
                "type": "location", "subject": "Alice", "room": r,
                "temporal": "this round",
            })
            for r in ("medbay", "med bay", "MEDBAY", "med")
        }
        assert len(sigs) == 1


# ---------- End-to-end caching + determinism ----------

class TestPipelineCachingAndDeterminism:
    """Spec acceptance:
    - Two pipeline runs over identical events with caching produce
      byte-identical tier3_claims.jsonl and identical metrics.
    - Second run performs zero LLM calls.
    - Dedup of triplicate extraction yields exactly 1 verified record.
    """

    def test_second_run_is_cache_only(self, simple_map: GameMap, cache_path: Path,
                                       restore_litellm) -> None:
        completion = _install_mock_litellm([
            {"type": "location", "subject": "Bob", "room": "medbay",
             "temporal": "this round"},
        ])
        events = build_minimal_game_events()
        timeline = GameReconstructor(events, simple_map).reconstruct()

        # First run: warms the cache, the LLM is called at least once
        # (the minimal fixture has a discussion at tick 7 with messages
        # from Alice and Frank).
        p1 = StatementVerificationPipeline(
            events=events, timeline=timeline, game_map=simple_map,
            api_key="dummy", model="mock", base_url="",
            cache_path=cache_path,
        )
        m1 = p1.run()
        first_call_count = completion.call_count
        assert first_call_count > 0, "first run should have called the LLM"

        # Second run: should be entirely served from cache.
        p2 = StatementVerificationPipeline(
            events=events, timeline=timeline, game_map=simple_map,
            api_key="dummy", model="mock", base_url="",
            cache_path=cache_path,
        )
        m2 = p2.run()
        assert completion.call_count == first_call_count, (
            "second run should not have called the LLM "
            f"(was {first_call_count}, now {completion.call_count})"
        )

        # Metrics must be byte-identical.
        assert m1.to_dict() == m2.to_dict()
        # Audit JSONL must be substantively identical. The only legitimate
        # cross-run difference is ``extraction.cache_hit`` (False on the
        # first run, True on the second) — that's debugging metadata
        # about how THIS run produced the entry, not part of the verdict
        # itself. Strip it before comparing.
        def _strip_provenance(a: dict) -> dict:
            out = {k: v for k, v in a.items() if k != "extraction"}
            return out
        s1 = [json.dumps(_strip_provenance(a), default=str, sort_keys=True)
              for a in p1.claim_audits]
        s2 = [json.dumps(_strip_provenance(a), default=str, sort_keys=True)
              for a in p2.claim_audits]
        assert s1 == s2

        # And the substantive parts of ``extraction`` (everything except
        # cache_hit) must also match.
        for a1, a2 in zip(p1.claim_audits, p2.claim_audits):
            e1 = {k: v for k, v in a1["extraction"].items() if k != "cache_hit"}
            e2 = {k: v for k, v in a2["extraction"].items() if k != "cache_hit"}
            assert e1 == e2
            assert a1["extraction"]["cache_hit"] is False
            assert a2["extraction"]["cache_hit"] is True

    def test_triplicate_extraction_collapses_to_one(
        self, simple_map: GameMap, cache_path: Path, restore_litellm,
    ) -> None:
        """If the LLM returns the same claim 3x, exactly one survives
        after dedup and the dropped-count is preserved on the surviving
        audit entry."""
        triplicate = [
            {"type": "location", "subject": "Bob", "room": "medbay",
             "temporal": "this round"},
            {"type": "location", "subject": "Bob", "room": "medbay",
             "temporal": "this round"},
            {"type": "location", "subject": "Bob", "room": "medbay",
             "temporal": "this round"},
        ]
        _install_mock_litellm(triplicate)
        events = build_minimal_game_events()
        timeline = GameReconstructor(events, simple_map).reconstruct()
        pipeline = StatementVerificationPipeline(
            events=events, timeline=timeline, game_map=simple_map,
            api_key="dummy", model="mock", base_url="",
            cache_path=cache_path,
        )
        pipeline.run()

        # Per (speaker, meeting) we extracted 3 identical Bob/medbay claims;
        # exactly 1 should survive each call. The minimal fixture has 2
        # discussion messages, so we expect 2 surviving claims with
        # dedup_collapsed_n=2 each.
        for audit in pipeline.claim_audits:
            assert audit["extraction"]["dedup_collapsed_n"] == 2

    def test_force_reextract_bypasses_cache(
        self, simple_map: GameMap, cache_path: Path, restore_litellm,
    ) -> None:
        completion = _install_mock_litellm([
            {"type": "location", "subject": "Bob", "room": "medbay",
             "temporal": "this round"},
        ])
        events = build_minimal_game_events()
        timeline = GameReconstructor(events, simple_map).reconstruct()
        p1 = StatementVerificationPipeline(
            events=events, timeline=timeline, game_map=simple_map,
            api_key="dummy", model="mock", base_url="",
            cache_path=cache_path,
        )
        p1.run()
        first_count = completion.call_count

        # force_reextract=True should re-call the LLM even with a warm cache.
        p2 = StatementVerificationPipeline(
            events=events, timeline=timeline, game_map=simple_map,
            api_key="dummy", model="mock", base_url="",
            cache_path=cache_path, force_reextract=True,
        )
        p2.run()
        assert completion.call_count > first_count


# ---------- Determinism fallback ----------

class TestExtractionCallShape:
    """The LLM call must use provider defaults — no custom
    ``temperature`` / ``seed``. Reproducibility comes from the on-disk
    cache, not from sampling parameters (gpt-5.5 rejects
    ``temperature=0`` outright).
    """

    def test_call_uses_provider_defaults(self, restore_litellm) -> None:
        fake_litellm = types.ModuleType("litellm")
        calls: list[dict] = []

        def _completion(**kwargs):
            calls.append(dict(kwargs))
            choice = types.SimpleNamespace(
                message=types.SimpleNamespace(content='[]'),
            )
            return types.SimpleNamespace(choices=[choice])

        fake_litellm.completion = _completion
        sys.modules["litellm"] = fake_litellm

        _extract_claims_sync(
            speaker_name="Alice", message="msg1", meeting_tick=7,
            player_names=["Alice"], model="gpt-5.5",
            api_key="", base_url="",
        )
        # Exactly ONE call, with NO custom sampling params. Both
        # ``temperature`` and ``seed`` must be absent so we never get
        # bitten by the gpt-5 / greatrouter / Gemini rejection of
        # those parameters.
        assert len(calls) == 1
        assert "temperature" not in calls[0]
        assert "seed" not in calls[0]
        assert calls[0]["model"] == "gpt-5.5"

    def test_legacy_seed_kwarg_is_accepted_but_ignored(self, restore_litellm) -> None:
        """Older callers may still pass ``seed=...`` — that must not
        crash and must not leak into the LLM call."""
        fake_litellm = types.ModuleType("litellm")
        calls: list[dict] = []

        def _completion(**kwargs):
            calls.append(dict(kwargs))
            choice = types.SimpleNamespace(
                message=types.SimpleNamespace(content='[]'),
            )
            return types.SimpleNamespace(choices=[choice])

        fake_litellm.completion = _completion
        sys.modules["litellm"] = fake_litellm

        _extract_claims_sync(  # type: ignore[call-arg]
            speaker_name="Alice", message="msg1", meeting_tick=7,
            player_names=["Alice"], model="gpt-5.5",
            api_key="", base_url="", seed=42,  # legacy kwarg
        )
        assert len(calls) == 1
        assert "seed" not in calls[0]


# ---------- Bug E consistency assertion ----------

class TestAuditMetricsConsistency:
    def test_run_succeeds_when_consistent(
        self, simple_map: GameMap, cache_path: Path, restore_litellm,
    ) -> None:
        _install_mock_litellm([
            {"type": "location", "subject": "Bob", "room": "medbay",
             "temporal": "this round"},
        ])
        events = build_minimal_game_events()
        timeline = GameReconstructor(events, simple_map).reconstruct()
        pipeline = StatementVerificationPipeline(
            events=events, timeline=timeline, game_map=simple_map,
            api_key="dummy", model="mock", base_url="",
            cache_path=cache_path,
        )
        metrics = pipeline.run()
        # Consistency holds by construction
        assert metrics.total_claims == len(pipeline.claim_audits)

    def test_audit_jsonl_can_recompute_metrics(
        self, simple_map: GameMap, cache_path: Path, restore_litellm,
    ) -> None:
        """The audit file alone must contain enough information to
        recompute the headline metrics (Bug E: the audit IS the source
        of truth for the run)."""
        _install_mock_litellm([
            {"type": "location", "subject": "Bob", "room": "medbay",
             "temporal": "this round"},
        ])
        events = build_minimal_game_events()
        timeline = GameReconstructor(events, simple_map).reconstruct()
        pipeline = StatementVerificationPipeline(
            events=events, timeline=timeline, game_map=simple_map,
            api_key="dummy", model="mock", base_url="",
            cache_path=cache_path,
        )
        metrics = pipeline.run()

        verifiable_types = {"location", "sighting", "activity"}
        verifiable_verdicts = {"true", "false", "near_miss", "wrong_room"}
        recomputed_total = len(pipeline.claim_audits)
        recomputed_verifiable = sum(
            1 for a in pipeline.claim_audits
            if a["structured_claim"]["claim_type"] in verifiable_types
            and a["verification"]["verdict"] in verifiable_verdicts
        )
        assert metrics.total_claims == recomputed_total
        assert metrics.verifiable_claims == recomputed_verifiable
