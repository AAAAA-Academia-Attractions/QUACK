# CHANGES

## Tier 3 statement verification (`fix/tier3-temporal-window`)

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

---

## Agent & observation fixes

Branch: `fix/tick-agent-memory`  
Base: `main`  
Commits:
- `93d7939` — add tick in agent observation
- `3928ceb` — fix free-roam `say()` forwarding to game engine

### Summary

Two fixes for VLM agent play during free roam:

1. **Include `tick` in observations** — `VisionSystem.build_observation()` now sets `"tick": state.current_tick`, so agent memory (movement summary, encounters, route since last meeting) uses real tick numbers instead of always `0`.
2. **Forward free-roam `| say(...)` to the game engine** — `VLMAgent` previously dropped chat when `_parse_action()` returned only `move(medbay)`; the model’s `| say(message)` never reached `GameEngine`. Other players in the same room can now hear free-roam chat via `room_messages` / `FREE_ROAM_CHAT`.

Tier 1 / Tier 2 / Tier 3 evaluation are unchanged (they read `game.jsonl` events; free-roam chat was already logged when the engine received it).

### Files changed

| File | Purpose |
|------|---------|
| `quack/systems/vision.py` | Add `"tick"` to `build_observation()` |
| `quack/agents/action_format.py` | **New** — `extract_say_clause()`, `combine_action_and_say()` |
| `quack/agents/vlm_agent.py` | Return `combine_action_and_say(action, response)` from `choose_action()` |
| `tests/test_systems/test_vision.py` | **New** — observation includes current tick |
| `tests/test_agents/test_vlm_say.py` | **New** — say extraction and combine behavior |

### Detailed changes

#### 1. Observation `tick`

**Problem:** `VLMAgent._record_observation()` used `observation.get("tick", 0)`, but `build_observation()` never set `tick`. Every `TickMemory` entry was stored at tick `0`, breaking `build_movement_summary()`, `build_encounter_summary()`, and `get_route_description()` (filter `t.tick > last_meeting_tick`).

**Fix:** Add `"tick": state.current_tick` to the dict returned by `build_observation()`.

#### 2. Free-roam `say()` forwarding

**Problem:** Prompts instruct models to return `move(medbay) | say(I saw something)`. `VLMAgent.choose_action()` called `_parse_action()`, which only returns strings from `available_actions` (e.g. `move(medbay)`). `GameEngine` splits `raw_action` on `|` to emit `FREE_ROAM_CHAT`; without `| say(...)` in the return value, chat was silently dropped (move still ran).

**Fix:**

- `extract_say_clause(response)` — find `say(...)` in the raw model text (any `|`-separated segment, or a lone `say(...)` line); normalize to `say(message)` (handles `Say(...)` casing).
- `combine_action_and_say(action, response)` — return `f"{action} | {say_clause}"` when present.
- `choose_action()` returns the combined string; memory and logs record action + chat.

**Example:**

```text
Model response:  move(medbay) | say(I saw Bob)
Returned to engine: move(medbay) | say(I saw Bob)
Engine:            move executes + FREE_ROAM_CHAT for same-room players
```

### Tests

```bash
python -m pytest tests/test_systems/test_vision.py tests/test_agents/test_vlm_say.py -q
```

7 tests (1 vision + 6 say).

### Backward compatibility

- `RandomAgent` unchanged (already strips `#`; does not use `say`).
- `GameEngine` free-roam chat parsing unchanged; VLM now supplies the format it expects.
- Re-run games for new agent memory / free-roam chat behavior; existing `game.jsonl` files are not retroactively fixed.

---

## Witness vision: agents see who leaves / enters their room

Branch: `fix/agent_vision`  
Base: `fix/tick-agent-memory`  
Commit: `7e67170 Add witness vision: agents now see who leaves/enters their room`

### Summary

Closes the perception gap where a stationary agent saw same-room roommates simply **disappear** when they moved (and **appear** with no origin info when they entered). After this change:

1. **Stationary witnesses** see departures from their room (with destination) and arrivals into their room (with origin) every tick.
2. **Corridor co-travelers** carry direction info (`co_direction: "same" | "opposite"`).
3. Witness info reaches the VLM through **three correlated surfaces**: the text observation, the local-view image (single-tick arrows at room doorways), and `AgentMemory` (which is reused in discussion and vote prompts).
4. Visibility range, the JSONL event schema, and Tier 1 / Tier 2 / Tier 3 evaluation are unchanged.

The same filter (`VisionSystem.get_witnessed_movements`) feeds both the image arrows and the text observation, so the two surfaces cannot disagree.

### Files changed

| File | Δ | Purpose |
|------|---|---------|
| `quack/engine/game_state.py` | +6 | Add `tick_movements: list[dict]` per-tick witness event log |
| `quack/engine/game_engine.py` | +54 −10 | Clear at tick start; emit `departed` / `arrived` from `_do_move` and `_advance_transit`; wire `witnessed_events` through `_render_for_player` |
| `quack/systems/vision.py` | +78 −10 | New `get_witnessed_movements(player, state)`; `build_observation` adds `transit_observations`; corridor co-travelers annotated with `in_transit`, `moving_to`, `co_direction` |
| `quack/rendering/map_renderer.py` | +98 | `render_local_view` accepts `witnessed_events`; new `_draw_witness_arrows_local` draws single-tick arrows at room doorways; god-view per-player POV stack uses the same helper |
| `quack/agents/prompt_builder.py` | +40 −4 | New `=== MOVEMENT AROUND YOU (this tick) ===` block in `build_action_prompt`; corridor co-direction phrasing; witness summary section in `build_discussion_prompt` and `build_vote_prompt` |
| `quack/agents/memory.py` | +49 | `TickMemory` gains `departures` / `arrivals`; `build_movement_summary` mentions witnessed traffic; new `build_witness_summary(since_tick=None)` produces chronological lines scoped to "since last meeting" |
| `quack/agents/vlm_agent.py` | +5 | `_record_observation` copies `transit_observations.departures` / `arrivals` into the latest `TickMemory` |
| `scripts/replay_game.py` | +61 −7 | Rebuild `tick_movements` per tick from logged `player_moved` events with a `pending_arrivals: {tick: [event]}` queue for multi-tick completions |
| `tests/test_systems/test_vision.py` | +172 | 7 new tests (multi-tick / instant departures and arrivals, self-event exclusion, transit viewer co-direction, room-filter) |
| `tests/test_systems/test_engine_witness.py` | +231 (new) | 6 integration tests covering engine emission for instant + multi-tick moves, per-tick clear, acted-first edge case, and replay reconstruction parity |
| `tests/test_agents/test_witness_memory.py` | +147 (new) | 9 tests covering `TickMemory` storage, `build_movement_summary` / `build_witness_summary` formatting, meeting-boundary scoping, and prompt rendering for action / discussion / vote |
| `tests/test_rendering/test_witness_arrows.py` | +148 (new) | 5 tests: empty events = byte-identical image (regression guard), non-empty events alter pixels, irrelevant corridors are ignored, transit viewers skip arrows, image arrow set matches observation filter |

### Detailed changes

#### 1. Engine instrumentation — `state.tick_movements`

**New: `GameState.tick_movements`** (`game_state.py`) — cleared at the top of every `_run_free_roam_tick`. Each entry:

```python
{
    "type": "departed" | "arrived",
    "player_id": str,
    "from_room": str,
    "to_room": str,
    "multi_tick": bool,
    "tick": int,
}
```

Where events are produced:

- `_do_move` weight 1 (instant): appends one `departed` AND one `arrived` event.
- `_do_move` weight > 1 (multi-tick start): appends one `departed` event.
- `_advance_transit` (multi-tick completion): appends one `arrived` event. This fires BEFORE any agent's observation is built this tick, so every stationary witness in the destination room sees the arrival.

This is authoritative state in the engine and does not depend on agent processing order.

#### 2. Vision filtering — `get_witnessed_movements`

**New helper** (`vision.py`):

```python
def get_witnessed_movements(self, player: Player, state: GameState) -> list[dict]:
    if player.is_in_transit:
        return []
    room = player.current_room
    return [
        ev for ev in state.tick_movements
        if ev["player_id"] != player.player_id and (
            (ev["type"] == "departed" and ev["from_room"] == room) or
            (ev["type"] == "arrived" and ev["to_room"] == room)
        )
    ]
```

Used in two places to guarantee the image and text observation agree:

1. `GameEngine._render_for_player` — passes the result as `witnessed_events` to `renderer.render_local_view`.
2. `VisionSystem.build_observation` — used to populate `transit_observations`.

#### 3. Observation schema

`build_observation()` adds:

```python
"transit_observations": {
    "departures": [{"id", "name", "to_room", "multi_tick"}, ...],
    "arrivals":   [{"id", "name", "from_room"}, ...],
}
```

For transit viewers, `visible_players` entries are augmented with:

```python
"in_transit": True,
"moving_to": <other player's destination>,
"co_direction": "same" | "opposite",
```

Stationary viewers' `visible_players` entries are unchanged (backward compatible).

#### 4. Prompt rendering

**`build_action_prompt`** renders a new block when `transit_observations` is non-empty:

```text
=== MOVEMENT AROUND YOU (this tick) ===
  Bob LEFT toward electrical (multi-tick)
  Alice ARRIVED from cafeteria
```

Corridor viewers see direction in `visible_players`:

```text
Visible players: Bob (corridor, going SAME way as you), Carol (corridor, going OPPOSITE way from you)
```

**`build_discussion_prompt`** and **`build_vote_prompt`** include `memory.build_witness_summary()` so meeting speakers can cite concrete witness evidence.

#### 5. Memory

- `TickMemory.departures` / `arrivals` store the witness payload verbatim.
- `build_movement_summary` lines now append `witnessed [Bob -> electrical; Carol arrived from cafeteria]`.
- New `build_witness_summary(since_tick=None)` returns lines like:
  ```text
    T8: Bob left medbay -> electrical
    T12: Carol entered medbay from cafeteria
  ```
  Defaults to "since last meeting" (uses `meeting_history[-1].tick`), which keeps speeches focused on the current round.

#### 6. Renderer

**New: `_draw_witness_arrows_local(draw, scale, viewer, witnessed_events)`** (`map_renderer.py`):

- Called from `render_local_view` after `_draw_players_local` and before `_draw_viewer_local`.
- For each event involving `viewer.current_room`:
  - Computes the corridor line segment between `_room_center(viewer_room)` and `_room_center(neighbor_room)`.
  - Anchors the arrow at ~30% along the segment (just past the room boundary).
  - Outward triangle + label `Bob -> electrical` for departures; inward triangle + label `Alice <- cafeteria` for arrivals.
  - Uses `_get_player_color(pid)` for the arrow color and a small color swatch.
  - Multiple events on the same corridor stack vertically with small offsets.
- Transit viewers and empty event lists are no-ops — same pixels as before this change (regression-safe).

`render_global_map` is NOT modified; it still shows only the viewer's own dot.

#### 7. Replay parity

`scripts/replay_game.py` rebuilds `tick_movements` from the same `player_moved` events already in `game.jsonl`:

- `apply_event` accepts a new optional `pending_arrivals: dict[int, list[dict]]` map.
- On `tick_start`: clear `state.tick_movements`, then drain `pending_arrivals[current_tick]` into it.
- On `player_moved` with `ticks_remaining == 0` (instant): append `departed` + `arrived` to current tick.
- On `player_moved` with `ticks_remaining > 0` (multi-tick start): append `departed` to current tick; queue an `arrived` event into `pending_arrivals[tick + ticks_remaining]`.

No new JSONL event types are added.

### Backward compatibility

- All new keys are additive. Existing `visible_players` entries still carry `id`, `name`, `room`.
- `render_local_view` with `witnessed_events=None` (the default) and no events produces byte-identical output to the pre-change implementation (covered by a regression test).
- `RandomAgent` ignores the new observation keys; existing test fixtures still pass.
- Tier 1 / Tier 2 / Tier 3 evaluation logic is unchanged. `GameReconstructor` and `tier3_statement_verification` continue to read `player_moved` events; `tick_movements` is transient runtime state.
- Old `game.jsonl` logs replay correctly because `pending_arrivals` is rebuilt from existing event fields.

### Tests

```bash
python -m pytest -q
# 125 passed in 0.13s
```

- 26 new tests across 4 files; 0 regressions on the 99 pre-existing tests.
- End-to-end smoke test: `python scripts/run_game.py video=false god_view=false seed=42` runs to completion; `python scripts/replay_game.py game_logs/.../game.jsonl --output /tmp/...` renders all frames including witness arrows without error.

---

## Supported-model refresh + project repositioning

Branch: `feat/model-refresh`  
Base: `main`

### Summary

Three coordinated, non-functional changes:

1. **Narrow the supported VLMs to three** — `gpt5.5`, `claude_opus4.7`, and `gemini3.1pro` (all served through the greatrouter OpenAI-compatible proxy). Drop the five legacy model configs (`gpt5.2`, `gpt5.4`, `claude_opus4.6`, `grok4`, `kimi2.5`) and remove their references throughout the engine, scripts, evaluator, and documentation.
2. **Update the default model** from `gpt5.2` → `gpt5.5` across the engine, the heterogeneous duck role, the evaluator Tier 3 defaults, and the agent class default.
3. **Reposition QUACK from "benchmark" to "open-source environment and evaluation framework"** in `README.md`, updating the title to match the paper (`Questioning, Understanding, and Auditing Collaborative Knowledge in Multimodal Social Deduction Agents`) and aligning the abstract, motivation, and Tier-3 description with the four failure modes audited (spatial hallucination, unsupported accusation, deception collapse, language-action inconsistency).

No engine behavior, log schema, or evaluation tier output is altered by this change. All 125 existing tests pass unchanged.

### Files changed

| File | Δ | Purpose |
|------|---|---------|
| `configs/model/gpt5.5.yaml` | **new** | GPT-5.5 (`model_id: gpt-5.5`, `requires_stream: false`) — default model |
| `configs/model/claude_opus4.7.yaml` | **new** | Claude Opus 4.7 (`model_id: claude-opus-4-7`, `requires_stream: false`) |
| `configs/model/gemini3.1pro.yaml` | unchanged | Gemini 3.1 Pro Preview (`model_id: gemini-3.1-pro-preview`, `requires_stream: true`) |
| `configs/model/gpt5.2.yaml` | **deleted** | Replaced by `gpt5.5.yaml` |
| `configs/model/gpt5.4.yaml` | **deleted** | Out of scope |
| `configs/model/claude_opus4.6.yaml` | **deleted** | Replaced by `claude_opus4.7.yaml` |
| `configs/model/grok4.yaml` | **deleted** | Out of scope |
| `configs/model/kimi2.5.yaml` | **deleted** | Out of scope |
| `configs/config.yaml` | +1 −1 | Default `model: gpt5.5` |
| `configs/experiment/heterogeneous.yaml` | +1 −1 | Default `duck_model: gpt5.5` |
| `quack/agents/vlm_agent.py` | +1 −1 | Default `model` parameter `gpt-5.5` |
| `quack/evaluation/evaluator.py` | +2 −2 | Default `llm_model` for `GameEvaluator.evaluate` and `BatchEvaluator.evaluate_batch` is `gpt-5.5` |
| `quack/evaluation/tier3_statement_verification.py` | +1 −1 | Default `model` for `StatementVerificationPipeline.__init__` is `gpt-5.5` |
| `scripts/run_game.py` | +1 −1 | Docstring example refers to `claude_opus4.7` |
| `scripts/evaluate_game.py` | +3 −3 | `--model` default + help text + docstring example use `gpt-5.5` / `gpt5.5` |
| `scripts/evaluate_batch.py` | +4 −4 | `--model` default + help text + docstring examples use `gpt-5.5` / `gpt5.5` / `claude_opus4.7` |
| `scripts/validate_tier3_audit.py` | +1 −1 | Example `LOG` path now points under `homogeneous/gpt5.5/` |
| `scripts/batch_homogeneous.sh` | rewritten | `ALL_MODELS="gpt5.5 claude_opus4.7 gemini3.1pro"`, examples updated |
| `scripts/batch_heterogeneous.sh` | rewritten | `ALL_MODELS="gpt5.5 claude_opus4.7 gemini3.1pro"`, examples updated |
| `scripts/batch_full_experiment.sh` | +4 −4 | Help text reflects 3 homogeneous + 6 heterogeneous = 9 conditions × 50 = 450 games |
| `scripts/generate_videos.sh` | +4 −4 | Help/usage examples reference `gpt5.5` paths |
| `README.md` | full rewrite | New title (`Auditing` not `Assessing`), paper abstract verbatim as the lede, three-model table, framework positioning, all `gpt5.2`/`gpt5.4`/`grok4`/`kimi2.5`/`claude_opus4.6` examples replaced by `gpt5.5`/`claude_opus4.7`/`gemini3.1pro` |
| `CLAUDE.md` | +6 −6 | Command examples and architecture blurb updated to reflect the three-model set and the framework framing |
| `CHANGES.md` | +this section | This entry |

### Detailed changes

#### 1. Model registry

- **New configs (2):**
  - `configs/model/gpt5.5.yaml` — `name: gpt5.5`, `display_name: "GPT-5.5"`, `model_id: gpt-5.5`, `temperature: 0.7`, `requires_stream: false`.
  - `configs/model/claude_opus4.7.yaml` — `name: claude_opus4.7`, `display_name: "Claude Opus 4.7"`, `model_id: claude-opus-4-7`, `temperature: 0.7`, `requires_stream: false`.
- **Retained:** `configs/model/gemini3.1pro.yaml` (model_id `gemini-3.1-pro-preview`, `requires_stream: true` — required to avoid timeouts; `max_tokens` must remain unset).
- **Deleted (5):** `gpt5.2.yaml`, `gpt5.4.yaml`, `claude_opus4.6.yaml`, `grok4.yaml`, `kimi2.5.yaml`.

All three remaining models share `base_url: https://endpoint.greatrouter.com` (with `https://endpoint.wendalog.com` documented as a domestic backup) and a single `api_key.txt` file. The agent's `requires_stream` flag continues to drive between `client.chat.completions.create(stream=False)` and the streaming path that accumulates `chunk.choices[0].delta.content` — no code changes required.

#### 2. Default model migration (`gpt5.2` → `gpt5.5`)

- `configs/config.yaml`: `defaults.model` switched to `gpt5.5`.
- `configs/experiment/heterogeneous.yaml`: `duck_model: "gpt5.5"`.
- `quack/agents/vlm_agent.py`: `VLMAgent.__init__(..., model: str = "gpt-5.5", ...)`.
- `quack/evaluation/evaluator.py`: `GameEvaluator.evaluate(..., llm_model="gpt-5.5", ...)` and `BatchEvaluator.evaluate_batch(..., llm_model="gpt-5.5", ...)`.
- `quack/evaluation/tier3_statement_verification.py`: `StatementVerificationPipeline.__init__(..., model="gpt-5.5", ...)`.
- `scripts/evaluate_game.py` / `scripts/evaluate_batch.py`: `--model` argparse default `gpt-5.5` and help text updated accordingly.
- `scripts/validate_tier3_audit.py`: example `LOG` path moved from `homogeneous/gpt5.2/...` to `homogeneous/gpt5.5/...`.
- `scripts/run_game.py`: docstring example `model=claude_opus4.7`.

#### 3. Batch scripts

- `scripts/batch_homogeneous.sh` and `scripts/batch_heterogeneous.sh` have `ALL_MODELS="gpt5.5 claude_opus4.7 gemini3.1pro"`, and every help/example line now uses one of the three supported names.
- `scripts/batch_full_experiment.sh` documents the new matrix size: **3 homogeneous + 6 heterogeneous = 9 conditions** (down from 6 + 30 = 36). At 50 seeds/condition this becomes 450 games — matching the paper abstract.
- `scripts/generate_videos.sh` help/usage text uses `homogeneous/gpt5.5/` as the example path.

#### 4. Documentation

- `README.md` is rewritten end-to-end:
  - **Title** now reads `Questioning, Understanding, and Auditing Collaborative Knowledge` (was `Assessing`), matching the paper.
  - **Subtitle** now reads `A Multimodal Social Deduction Environment for Vision-Language Model Agents` (was `Benchmark`).
  - **Abstract** is taken from the paper verbatim and replaces the previous "benchmark for VLMs" framing. It explicitly names QUACK as "an open-source environment and evaluation framework" and lists the four failure modes (spatial hallucination, unsupported accusation, deception collapse, language-action inconsistency).
  - **Supported Models** section is reduced to a 3-row table covering `gpt5.5`, `claude_opus4.7`, and `gemini3.1pro`, with a note that all three share the same greatrouter endpoint and that the streaming behavior is controlled per-model via `requires_stream`.
  - **Quick Start, Heterogeneous, Batch Runs, Replay, Generate Videos, Evaluate, Output Structure, Configuration tree, Architecture tree** sections all have their example commands and directory listings updated to reference the three supported model names exclusively. Hetero pair count corrected from 20 to 6; full-matrix count corrected from 1250/1800 to 450.
  - **Tier 3 — Statement Verification** section now points out that the verifier surfaces the four named failure modes and that the location verifier uses duration-aware semantics (preserving the threshold tiers introduced in the Tier 3 fix earlier in this changelog).
- `CLAUDE.md`:
  - High-level structure paragraph rewords QUACK from "designed as a benchmark for Vision-Language Models" to "designed as an open-source environment and evaluation framework for auditing multimodal social reasoning in Vision-Language Model agents".
  - All `gpt5.2` / `claude_opus4.6` command examples replaced with `gpt5.5` / `claude_opus4.7`.

### Backward compatibility

- **Game engine:** no behavior change; no event-schema change; existing `game.jsonl` logs still parse and replay.
- **Evaluation:** Tier 1 / Tier 2 / Tier 3 metric keys and `EvaluationResult.to_dict()` shape unchanged. The default LLM used by Tier 3 differs (`gpt-5.2` → `gpt-5.5`), but `--model` overrides remain available everywhere.
- **Logs from deleted model configs** (e.g. existing `game_logs/homogeneous/gpt5.2/...`) still replay and evaluate correctly — the evaluator reads `game.jsonl` rather than model names. Only the helper *scripts* no longer enumerate those models in their `ALL_MODELS` lists.
- **VLMAgent API** is unchanged. Existing callers that pass an explicit `model=` argument are unaffected; only the default value changed.

### Validation

```bash
# Tests
python -m pytest -q
# 125 passed

# Smoke run with the new default model on random agents (no API key required)
python scripts/run_game.py seed=42 video=false god_view=false game.max_ticks=20
# Output: game_logs/homogeneous/gpt5.5/<timestamp>_seed42/{game.jsonl,config.yaml}

# Verify no stray references to removed models in code/docs/configs (CHANGES.md is historical and intentionally retained)
rg 'gpt5\.2|gpt5\.4|grok4|kimi2\.5|claude_opus4\.6|claude-opus-4-6|grok-4|Kimi-K2\.5|gpt-5\.2|gpt-5\.4' \
   --glob '!CHANGES.md' --glob '!game_logs/**' --glob '!run_game.log'
# (no matches)
```
