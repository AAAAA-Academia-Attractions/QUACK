"""Offline re-verify: re-run Tier 3 verification on the structured claims
already present in an existing ``tier3_claims.jsonl`` (skipping the LLM
extraction step).

Use this to demonstrate the impact of Tier 3 verifier-side fixes (Bug A,
B, D, F) without re-paying for LLM extraction. The extraction step
(Bug C / cache / dedup) is a separate concern and not exercised here.

Outputs alongside the input run directory:
- ``tier3_claims_reverified.jsonl`` — same structured claims, new verdicts
- ``evaluation_reverified.json``   — Tier 3 metrics computed from the new verdicts

Run::

    python scripts/reverify_tier3_from_audit.py game_logs/<run_dir>/

Then::

    python scripts/validate_tier3_audit.py --check game_logs/<run_dir>/

… would normally check the live tier3_claims.jsonl + evaluation.json
(the reverified shadow files are not picked up automatically).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quack.evaluation.game_reconstructor import GameReconstructor
from quack.evaluation.log_parser import (
    get_initial_state, get_player_role_map, parse_log,
)
from quack.evaluation.tier3_statement_verification import (
    StatementVerificationPipeline, Tier3Metrics,
    _canonical_claim_signature,
)
from quack.map.game_map import GameMap


def reverify(run_dir: Path, map_yaml: Path) -> None:
    game_log = run_dir / "game.jsonl"
    audit_path = run_dir / "tier3_claims.jsonl"
    if not audit_path.exists():
        print(f"ERROR: no tier3_claims.jsonl in {run_dir}", file=sys.stderr)
        sys.exit(1)

    events = parse_log(str(game_log))
    with open(map_yaml) as f:
        game_map = GameMap.from_config(yaml.safe_load(f))
    timeline = GameReconstructor(events, game_map).reconstruct()

    pipeline = StatementVerificationPipeline.__new__(StatementVerificationPipeline)
    pipeline.events = events
    pipeline.timeline = timeline
    pipeline.game_map = game_map
    initial = get_initial_state(events)
    pipeline.role_map = get_player_role_map(events)
    pipeline.name_to_id = {info["name"]: pid for pid, info in initial.items()}
    pipeline.id_to_name = {pid: info["name"] for pid, info in initial.items()}
    pipeline.player_names = list(pipeline.id_to_name.values())
    pipeline.duck_ids = {pid for pid, t in pipeline.role_map.items() if t == "duck"}
    pipeline.claim_audits = []

    audits_in: list[dict] = []
    with open(audit_path) as f:
        for line in f:
            if line.strip():
                audits_in.append(json.loads(line))

    print(f"Loaded {len(audits_in)} audit entries from {audit_path}")

    # Group existing audits by meeting so we can rebuild meeting context.
    meetings_by_idx: dict[int, dict] = {}
    for a in audits_in:
        midx = a["meeting"]["meeting_idx"]
        if midx not in meetings_by_idx:
            meetings_by_idx[midx] = {
                "tick": a["meeting"]["meeting_tick"],
                "type": a["meeting"]["meeting_type"],
                "caller": a["meeting"]["caller_id"],
            }

    # Apply Bug C dedup to the input audits before re-verifying, so the
    # output mirrors what a full re-run of the pipeline (with extraction
    # cache + dedup) would produce. Duplicates from the OLD pipeline get
    # collapsed here. ``dedup_collapsed_n`` is summed per (speaker,
    # meeting) so the surviving entry carries the dropped count.
    seen: set[tuple[str, int, tuple]] = set()
    collapsed_by_key: dict[tuple[str, int], int] = {}
    deduped_in: list[dict] = []
    for a in audits_in:
        sc = a["structured_claim"]
        sig = _canonical_claim_signature({
            "type": sc["claim_type"],
            "subject": sc.get("subject", ""),
            "target": sc.get("target", ""),
            "room": sc.get("room") or "",
            "activity": sc.get("activity") or "",
            "temporal": sc.get("temporal_ref") or "",
        })
        key_full = (a["speaker"]["speaker_id"], a["meeting"]["meeting_idx"], sig)
        key_partial = (a["speaker"]["speaker_id"], a["meeting"]["meeting_idx"])
        if key_full in seen:
            collapsed_by_key[key_partial] = collapsed_by_key.get(key_partial, 0) + 1
            continue
        seen.add(key_full)
        deduped_in.append(a)

    audits_in = deduped_in
    print(f"After Bug C dedup: {len(audits_in)} unique claims (dropped {sum(collapsed_by_key.values())})")

    all_verified: list[dict] = []
    new_audits: list[dict] = []
    meeting_duck_lies: dict[int, bool] = {}
    meeting_duck_caught: dict[int, bool] = {}
    verdict_diff: dict[str, int] = {}

    for a in audits_in:
        sc = a["structured_claim"]
        midx = a["meeting"]["meeting_idx"]
        meeting_tick = a["meeting"]["meeting_tick"]
        speaker_id = a["speaker"]["speaker_id"]
        speaker_name = a["speaker"]["speaker_name"]

        claim = {
            "type": sc["claim_type"],
            "subject": sc.get("subject", ""),
            "target": sc.get("target"),
            "room": sc.get("room"),
            "activity": sc.get("activity"),
            "temporal": sc.get("temporal_ref", "this round"),
            "_speaker_id": speaker_id,
            "_speaker_name": speaker_name,
            "_meeting_idx": midx,
            "_meeting_tick": meeting_tick,
        }
        if sc.get("route"):
            claim["route"] = sc["route"]

        old_verdict = a["verification"]["verdict"]
        new_result = pipeline._verify_claim(claim, meeting_tick)
        new_verdict = new_result.verdict
        verdict_diff[f"{old_verdict}->{new_verdict}"] = (
            verdict_diff.get(f"{old_verdict}->{new_verdict}", 0) + 1
        )
        claim["_verdict"] = new_verdict
        claim["_verification"] = new_result
        all_verified.append(claim)

        meeting = meetings_by_idx[midx]
        raw_utt = a["utterance"]["raw"]
        new_audit = pipeline._build_audit_entry(
            claim, meeting, midx, new_result, raw_utt,
        )
        # Preserve provenance metadata (cache_hit etc.) from the old audit
        # if present, otherwise tag as a reverify run. Stamp the dedup
        # count we computed above onto every audit entry for that
        # (speaker, meeting).
        new_audit["extraction"] = a.get("extraction") or {
            "cache_hit": True, "dedup_collapsed_n": 0,
            "prompt_version": "reverify-no-llm-call",
            "model": "<not-called>",
        }
        new_audit["extraction"]["dedup_collapsed_n"] = (
            collapsed_by_key.get((speaker_id, midx), 0)
        )
        new_audit["reverified_from"] = {
            "old_verdict": old_verdict,
            "new_verdict": new_verdict,
        }
        new_audits.append(new_audit)
        pipeline.claim_audits.append(new_audit)

    # Build meeting_duck_lies / caught from new verdicts
    for midx in meetings_by_idx:
        had_lies = any(
            c["_speaker_id"] in pipeline.duck_ids
            and c["_verdict"] in ("false", "wrong_room")
            for c in all_verified if c["_meeting_idx"] == midx
        )
        meeting_duck_lies[midx] = had_lies
        meeting_duck_caught[midx] = False

    metrics = Tier3Metrics()
    pipeline._compute_metrics(
        metrics, all_verified, meeting_duck_lies, meeting_duck_caught,
    )

    out_audit = run_dir / "tier3_claims_reverified.jsonl"
    out_eval = run_dir / "evaluation_reverified.json"
    with open(out_audit, "w") as f:
        for entry in new_audits:
            f.write(json.dumps(entry, default=str) + "\n")
    with open(out_eval, "w") as f:
        json.dump({"tier3": metrics.to_dict()}, f, indent=2, default=str)

    print("\nVerdict transitions (old -> new):")
    for k, v in sorted(verdict_diff.items(), key=lambda x: -x[1]):
        if v > 0:
            print(f"  {k:<30} {v:>4}")
    print(f"\nWrote {out_audit}")
    print(f"Wrote {out_eval}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=str,
                        help="Directory containing game.jsonl + tier3_claims.jsonl")
    parser.add_argument("--map-config", type=str,
                        default="configs/maps/simple_ship.yaml",
                        help="Path to map config YAML")
    args = parser.parse_args()
    reverify(Path(args.run_dir), Path(args.map_config))
