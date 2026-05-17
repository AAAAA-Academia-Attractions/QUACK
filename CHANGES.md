# Changes on `fix/tier3-temporal-window`

Branch: `fix/tier3-temporal-window`  
Base: `main`  
Commit: `0285947 Tier3 three fixes`

## Summary

Three interdependent fixes and improvements to the Tier 3 statement verification pipeline:

1. **Fix temporal window resolution** — "this round" / "since last meeting" now map to the free-roam segment that *precedes* the meeting, not the meeting tick or the post-meeting segment.
2. **Add claim-level audit output** — per-game `tier3_claims.jsonl` sidecar with full per-claim evidence, reason, and resolution metadata.
3. **Improve verifier semantics** — duration-aware location verification, visibility-based sighting, new activity types, explicit defense reasons, structured `VerificationResult` return type.

Tier 1 and Tier 2 are unchanged. All aggregate metric names are preserved.

---

## Files changed

| File | Δ | Purpose |
|------|---|---------|
| `quack/evaluation/game_reconstructor.py` | +36 −14 | Explicit free-roam segment tracking |
| `quack/evaluation/tier3_statement_verification.py` | +697 −47 | VerificationResult, verifier improvements, audit |
| `quack/evaluation/evaluator.py` | +21 −2 | `tier3_audit_path` field, `--save-tier3-audit` flag |
| `scripts/evaluate_game.py` | +7 | `--save-tier3-audit` CLI flag |
| `scripts/evaluate_batch.py` | +7 | `--save-tier3-audit` CLI flag |
| `scripts/validate_tier3_audit.py` | +326 (new) | Validation script |
| `tests/test_evaluation/test_claim_verification.py` | +528 −10 | 25 new tests (8 new test classes) |
| `tests/test_evaluation/test_game_reconstructor.py` | +13 | Free-roam segment + meeting link tests |

## Detailed changes

### 1. Fix temporal window resolution

**Problem:** `_determine_round_range()` used `end >= meeting_tick` to find the containing round. Since meeting ticks sit at segment boundaries, the first match was always the *post-meeting* free-roam segment. For a meeting at tick 7 with segments `[(0,6), (7,10)]`, "this round" resolved to `[7, 7]` instead of `[0, 6]`.

**Fix:** Changed the loop condition from `end >= meeting_tick` to `end < meeting_tick`, tracking the *last* segment ending before the meeting tick. This correctly selects the preceding free-roam segment.

**Supporting change in `game_reconstructor.py`:**
- Added `GameTimeline.free_roam_segments` — explicit list of `{start, end}` dicts recorded during reconstruction.
- `GameReconstructor.reconstruct()` now tracks `free_roam_segment_start` and records a segment when a meeting starts (the preceding free-roam) and at game end (the final segment).
- Each meeting boundary dict gains a `preceding_free_roam_index` key linking to its preceding segment.
- `get_round_boundaries()` now derives directly from `free_roam_segments` instead of recomputing from meeting boundaries.

### 2. Claim-level audit output

**New: `VerificationResult` dataclass** (`tier3_statement_verification.py:22-34`)

Every verifier returns a `VerificationResult` with:
- `verdict` — `"true"`, `"false"`, `"near_miss"`, `"wrong_room"`, `"unverifiable"`
- `reason` — mechanically derived human-readable explanation
- `evidence` — dict with actual tick IDs, matched ticks, observed rooms, visibility source, relevant events
- `verifier_name` — which verifier produced this result
- `resolution_source` — how the temporal window was resolved

**New: `StatementVerificationPipeline.claim_audits`** — populated during `run()` with one audit dict per claim. The pipeline's `run()` method still returns `Tier3Metrics` as before (backward compatible). The evaluator reads `pipeline.claim_audits` after `run()`.

**New: `_build_audit_entry()`** — assembles per-claim audit records with sections:
- `meeting` — meeting_idx, meeting_tick, meeting_type, caller_id
- `temporal_window` — start_tick, end_tick, resolution_source
- `speaker` — speaker_id, name, team, role, alive_at_meeting
- `utterance` — raw message text
- `structured_claim` — claim_type, subject, target, room, activity, temporal_ref, duration_semantics, confidence
- `verification` — verdict, verifier_name, reason, resolution_source, evidence

**New: `EvaluationResult.tier3_audit_path`** — when `--save-tier3-audit` is enabled, `GameEvaluator.evaluate()` writes `tier3_claims.jsonl` alongside `evaluation.json` and stores the path in the result. The path is included in `evaluation.json` under `tier3.tier3_audit_path`. When the flag is off (default), `tier3_audit_path` is not written to `evaluation.json` at all.

**CLI flags:** `--save-tier3-audit` added to both `evaluate_game.py` and `evaluate_batch.py`. Defaults to `False`.

### 3. Improved verifier semantics

#### Location verifier (`verify_location_claim`)

- Accepts `duration_semantics` parameter inferred from the claim's temporal phrase by `_infer_duration_semantics()`.
- Four duration tiers:

| Semantic | Trigger phrases | Threshold |
|----------|----------------|-----------|
| `any_time` | "passed through", "went to", "visited", "entered", "came from", "stopped by" | >= 1 matched tick |
| `most_time` | "mostly", "spent most of" | >= 50% of valid ticks |
| `entire_time` | "the whole time", "entire round", "never left", "stayed in" | all valid ticks must match |
| `unknown_fallback` | everything else (incl. bare "this round") | >= 50% (backward compatible) |

- `entire_time` excludes ticks where the player is dead or has no timeline data.
- Evidence includes `valid_ticks`, `excluded_ticks`, `exclusion_reasons`, `match_rate`, and per-tick `observed_rooms`.

#### Sighting verifier (`verify_sighting_claim`)

- Uses `can_see()` which reimplements the engine's `VisionSystem.compute_visibility()` logic from timeline data:
  - Viewer in a room → can see non-transit players in the same room
  - Viewer in transit A→B → can see other transit players on the same corridor (same or opposite direction)
- Records `visibility_source` in evidence: `"engine_visibility"` when `game_map` is available, `"same_room_fallback"` otherwise.
- Evidence includes per-tick `subject_rooms`, `target_rooms`, `co_located_in_claimed_room_ticks`, `co_located_wrong_room_ticks`.

#### Activity verifier (`verify_activity_claim`)

Now supports 5 activity categories (was 2):

| Activity | Aliases | Verification rule |
|----------|---------|-------------------|
| `task` / `tasking` | `doing_task` | `task_progress` or `task_completed` events for subject in window |
| `traveling` / `moving` | — | Subject in transit or `move()` action at any tick |
| `waiting` / `staying` | `idling` | Subject stayed in <= 1 room (true); mostly one room >= 80% (near_miss); otherwise false |
| `reporting body` | `found body`, `reporting` | `body_reported` event with caller == subject at meeting_tick |
| `calling meeting` | `emergency meeting`, `called meeting` | `meeting_called` event with caller == subject at meeting_tick |

Unsupported activities return `unverifiable` with a list of supported activities in the reason.

#### Defense verifier

- Stays `unverifiable` — no automatic subclaim decomposition.
- Now returns a clear reason: `"Defense claims are not automatically decomposable; no location/alibi subclaim was extracted for verification."`
- Verifier name recorded as `"verify_defense_claim"`.

#### Accusation verifier

- Converted to return `VerificationResult` with evidence `{"target_id": ..., "target_is_duck": bool}`.
- Semantic unchanged.

### 4. New helper functions

| Function | Purpose |
|----------|---------|
| `_infer_duration_semantics(temporal)` | Rule-based inference of location duration tier from temporal phrase |
| `_event_actor_id(event)` | Extract the acting player ID from any event type |
| `can_see(subject, target, tick, timeline, game_map)` | Reimplement engine visibility rules from timeline data |
| `_temporal_resolution_source(meeting_tick)` | Label how the temporal window was resolved |
| `_build_audit_entry(...)` | Assemble per-claim audit record |

### 5. Tests added (25 new, 0 regressions)

| Test class | Tests | What it covers |
|-----------|-------|---------------|
| `TestDetermineRoundRange` | 7 | Temporal window fix (meeting_tick=7→[0,6], meeting_tick=17→[0,16], multi-meeting, keyword clamping) |
| `TestDurationSemantics` | 7 | `_infer_duration_semantics()` phrases, any_time/entire_time/most_time/unknown verifier behavior, dead-tick exclusion |
| `TestCanSee` | 5 | Same-room stationary, stationary-vs-transit, different rooms, same-direction corridor, opposite-direction corridor |
| `TestVerifyActivityNewTypes` | 5 | waiting/staying true/false, reporting body true/false, calling meeting false |
| `TestVerificationResultEvidence` | 3 | Evidence structure, visibility_source, mechanically-derived reason |
| `TestDefenseVerifier` | 1 | Defense returns unverifiable with decomposability reason |
| `TestAuditOutput` | 2 | Audit entry schema, temporal window reflects preceding free-roam at tick 17 |
| `TestBackwardCompatibility` | 3 | `Tier3Metrics.to_dict()` keys unchanged, `tier3_audit_path` in `EvaluationResult.to_dict()`, absent when None |

Existing test assertions updated from `assert result == "true"` to `assert result.verdict == "true"` (10 tests).

Full suite: **92 passed, 0 failed**.

## Backward compatibility

- `StatementVerificationPipeline.run()` still returns `Tier3Metrics` (unchanged signature).
- All `Tier3Metrics.to_dict()` keys are preserved. `tier3_audit_path` only appears in `evaluation.json` when audit is enabled.
- Tier 1 and Tier 2 output schema is byte-for-byte identical.
- `--save-tier3-audit` defaults to `False`.
- `game_reconstructor.py`: `meeting_boundaries` gains one new optional key (`preceding_free_roam_index`); `free_roam_segments` is an additive field. `get_round_boundaries()` returns identical values when `free_roam_segments` is populated.
- Old code calling verifier functions directly needs to check `.verdict` instead of comparing to a string — this only affects test code and internal callers.

## Validation

Run the validation script on a real game log:

```bash
uv run python scripts/validate_tier3_audit.py
```

Or manually:

```bash
# Run a game
uv run python scripts/run_game.py seed=3

# Evaluate with Tier 3 audit
uv run python scripts/evaluate_game.py \
  game_logs/homogeneous/gpt5.2/<timestamp>_seed3/game.jsonl \
  --tier3 --api-key YOUR_KEY --save-tier3-audit

# Inspect
cat game_logs/.../evaluation.json | python -m json.tool | grep -A5 tier3
cat game_logs/.../tier3_claims.jsonl | head -3
```
