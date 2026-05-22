# CHANGES

## God-view rendering (`feat/render`)

**Branch:** `feat/render`  
**Base:** `main`  
**Commits:** `02e8586` fix the render logic for moving between rooms · `e309859` refine the render

```text
 quack/rendering/colors.py                   |  38 +-
 quack/rendering/map_renderer.py             | 808 +++++++++++++++++-----------
 quack/rendering/room_decor.py               | 162 ++++--
 scripts/verify_transit_render.py            | 159 ++++++   (new)
 tests/test_rendering/test_transit_visual.py | 254 +++++++++   (new)
 5 files changed, 1013 insertions(+), 394 deletions(-)
```

**Scope:** render-only. Touches `quack/rendering/*`, replay/live god-view PNG output, and new tests/scripts. No changes to `quack/engine/`, JSONL schema, agents, or evaluation on this branch.

---

## Summary vs `main`

On `main`, god-view PNGs are drawn from **raw engine state at tick *N* end**:

- God map scale is hardcoded (`scale = 1.2`).
- In-transit sprites use `progress = (weight − move_ticks_remaining) / weight` inline in `_god_draw_all_players`, but `_advance_transit()` for tick *N+1* has **not** run yet at frame capture time.
- The POV strip calls `compute_visibility()` on that same raw state.

This branch adds a **display snapshot** (one in-memory `_advance_transit()` pass before drawing complete free-roam frames), centralizes corridor math in `_visual_transit()`, aligns POV fog with the snapshot, and upgrades resolution / schematic styling / room decor / dead POV treatment.

---

## Jump / teleport rendering fixes

These are the user-visible “jump” bugs this branch addresses. All fixes are render-only.

### 1. Corridor hop (multi-tick move looks like a room teleport)

**Symptom:** On weight-*W* corridors, consecutive god-view frames show a player in the **origin room** (or nowhere on the corridor), then suddenly in the **destination room**, with no intermediate corridor step — e.g. Frank `storage → medbay → cafeteria` appearing to jump each hop.

**Cause on `main`:** Frames are captured at tick *N* end while `move_ticks_remaining` still reflects pre–tick *N+1* state. A player with `remaining == 1` is drawn on the corridor (or at origin), then after the real `_advance_transit()` at tick *N+1* start they appear in the destination — one visual “teleport” per hop.

**Fix:** `_snapshot_next_tick_start()` applies one `_advance_transit()` in memory before drawing complete free-roam frames. `_visual_transit()` + `_transit_corridor_xy()` draw corridor progress on the **post-snapshot** fields:

```text
elapsed  = weight - move_ticks_remaining
progress = elapsed / weight   (clamped 0.25 … 0.75)
```

Arrivals committed by the snapshot are drawn in `current_room` (no corridor sprite).

**Before / after (weight 2):**

```text
main:   tick N end → origin/corridor  |  tick N+1 end → destination   (looks like a jump)
branch: tick N end → corridor step   |  tick N+1 end → next step or destination
```

### 2. POV black void (caption vs image mismatch)

**Symptom:** Panel/caption shows destination room (e.g. `storage`) while the personal POV shows a gray corridor stub on empty background — map and label disagree.

**Cause on `main`:** POV crop centers on destination (via in-transit display logic) but `compute_visibility()` uses engine `current_room` (still origin) with `visibility_range == 0`, so the room interior is never drawn.

**Fix:** God-view POV strip uses the same `display_state` as the map; `compute_visibility()` runs on snapshot players so crop center and `visible_rooms` match.

### 3. Wrong advance after respawn or meeting interrupt

**Symptom:** Applying the display snapshot on respawn or partial-tick frames would shift positions again (on top of random post-meeting teleport) or advance transit when the tick never completed.

**Fix:** `_use_next_tick_snapshot()` returns `False` when:

- `phase_override in ("Spawn", "Respawn (post-meeting)")`
- `state.phase` is neither `FREE_ROAM` nor `GAME_OVER` (body report / meeting mid-tick → `DISCUSSION`; no `tick_end`)

Raw engine state is drawn for those frames. (Dedicated spawn/respawn frames themselves come from `main`; this branch only ensures snapshot is **not** applied to them.)

### 4. Last frame on max ticks (live game only)

**Symptom:** On timeout, the final god-view frame can show a player still in transit / wrong corridor step while every other tick-end frame looked correct.

**Cause:** `_run_free_roam_tick()` sets `phase = GAME_OVER` immediately after emitting `tick_end` when `current_tick >= max_ticks`. `run_game.py` then saves the god-view frame with `GAME_OVER` phase, so an earlier version of `_use_next_tick_snapshot()` (which required `FREE_ROAM`) skipped the display snapshot. Replay is unaffected: `tick_end` is rendered before the separate `game_over` event applies.

**Fix:** `_use_next_tick_snapshot()` also returns `True` for `GamePhase.GAME_OVER` (still excluding spawn/respawn overrides). Only the post–complete-tick frame is saved in that phase; meeting interrupts and vote-end wins never save another god-view PNG.

---

## Files changed

| File | Purpose |
|------|---------|
| `quack/rendering/map_renderer.py` | Display snapshot, `_VisualTransit`, god/local refactor, layout/fonts, dead POV gray-out |
| `quack/rendering/colors.py` | Schematic palette, scale constants, `DEAD_POV_*` |
| `quack/rendering/room_decor.py` | Proportional decor, `_w()` strokes, cafeteria/storage layouts |
| `tests/test_rendering/test_transit_visual.py` | **New** — 11 tests (transit, snapshot, POV, snapshot guards, max-ticks) |
| `scripts/verify_transit_render.py` | **New** — manual seed11 Frank ticks 25–27 spot-check |

---

## Implementation details

### Display snapshot

| Helper | Behavior |
|--------|----------|
| `_snapshot_next_tick_start(state)` | Shallow copy; decrement `move_ticks_remaining`; on zero set `current_room = moving_to`, clear transit (same as `GameEngine._advance_transit`) |
| `_use_next_tick_snapshot(state, phase_override)` | Gate: complete free-roam tick ends; includes `GAME_OVER` after max-ticks timeout |

`render_god_view()` sets `display_state`, then draws map, panel, and POV from it. HUD tick number, event log, and chat bubbles still reflect logged tick *N*.

### Transit drawing

- `_VisualTransit` — renderer-only corridor placement tuple
- `_player_display_room()` — room name or `"origin → dest"` on corridor
- `_god_draw_all_players()` — uses `_transit_corridor_xy()` instead of duplicated inline progress math

### POV strip

- Built from `display_state` players
- Dead agents: `_gray_local_view()` (grayscale), muted title (`DEAD_POV_TITLE_BG` / `DEAD_POV_TITLE_TEXT`), dead sprite without YOU ring
- Live `_render_for_player` local views unchanged (raw engine state)

### Layout & style (`colors.py`)

| Constant | Value |
|----------|-------|
| `GOD_VIEW_SCALE` | 1.55 |
| `GOD_SPRITE_SCALE` | 3 |
| `GOD_VIEW_PANEL_W` | 440 |
| `GOD_VIEW_HUD_H` | 72 |
| `GOD_VIEW_POV_LABEL_H` | 52 |
| `LOCAL_VIEW_SCALE` | 2.2 |
| `LOCAL_VIEW_SPRITE_SCALE` | 4 |
| `LOCAL_VIEW_CROP_HALF` | 290 |
| `LOCAL_VIEW_TITLE_H` | 58 |

Room title bars, nameplates, weight badges; `_WINDOWS_FONT_PATHS`; helpers `_draw_room_title_bar`, `_draw_nameplate`, `_draw_weight_badge`, `_draw_agent_marker`.

### Room decor

- `decor_scale = clamp(inner / 115, 0.55, 2.8)` from room interior size
- Cafeteria tables: `w // 4`
- Storage: `_draw_crate` + warehouse layout (back row, side stacks, clear aisle)

---

## Tests & verification

```bash
python -m pytest tests/test_rendering/test_transit_visual.py -q   # 11 tests
python -m pytest tests/test_rendering/ -q                         # 16 (incl. witness arrows)
python scripts/verify_transit_render.py
python scripts/replay_game.py path/to/game.jsonl --output out/dir/
```

**Live game:** `run_game.py` uses the same `engine.render_god_view()` path as replay; snapshot rules above apply to PNGs under `renders/god_view/`. Agent `_render_for_player` local views still use raw engine state mid-tick.

**`test_transit_visual.py`:**

- `_visual_transit` corridor progress (weight 2 and 3)
- `_snapshot_next_tick_start` commits weight-2 arrival
- God-view corridor vs room placement (Frank storage → medbay → cafeteria)
- POV visibility after snapshot (`visibility_range=0`, two players same room)
- Snapshot disabled for `Respawn (post-meeting)` and `GamePhase.DISCUSSION`
- Snapshot enabled for `GamePhase.GAME_OVER` (max-ticks last frame)
- Dead POV grayscale treatment

---

## Backward compatibility

- Engine and `game.jsonl` unchanged; old logs replay with new PNG output only
- `render_god_view(..., phase_override=...)` API unchanged
- Witness-arrow tests still pass
- Composes with spawn / respawn / meeting frames already on `main`

---

## Out of scope (not changed on this branch)

- `quack/engine/game_engine.py`
- Post-meeting `PLAYERS_RESPAWNED` event / respawn frame (already on `main`)
- Agent observations, Tier 1/2/3 evaluation
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

### Follow-up fix: drop `temperature` / `max_tokens` from API calls

After running `python scripts/run_game.py seed=42` end-to-end against the live greatrouter endpoint, every VLM call returned:

```
openai.BadRequestError: Unsupported value: 'temperature' does not support 0.7 with this model.
Only the default (1) value is supported.
```

`gpt-5.5`, `claude-opus-4-7`, and `gemini-3.1-pro-preview` on greatrouter all reject any custom `temperature`. Gemini additionally returns empty bodies when `max_tokens` is set. Neither of these two parameters appear in the reference snippets the user shared. Both are now omitted unconditionally:

| File | Δ | Purpose |
|------|---|---------|
| `quack/agents/vlm_agent.py` | +20 −13 | `temperature: float \| None = None`. New `_build_create_kwargs()` helper assembles the `client.chat.completions.create` payload and only includes `temperature` when explicitly set (non-None). Both the sync and streaming paths now route through this helper. |
| `quack/evaluation/tier3_statement_verification.py` | +4 −6 | `_extract_claims_sync()` removed `temperature=0.0` and `max_tokens=2000` from both `litellm.completion(...)` branches. |
| `scripts/run_game.py` | +2 −2 | `temperature=cfg.model.get("temperature", None)` in both `create_agents_from_config` and `reassign_duck_agents` so a missing/null YAML field is forwarded as `None` rather than raising. |
| `configs/model/gpt5.5.yaml` | +3 −1 | `temperature: null` with an inline comment explaining the constraint. |
| `configs/model/claude_opus4.7.yaml` | +3 −1 | `temperature: null` with the same comment. |
| `configs/model/gemini3.1pro.yaml` | +3 −1 | `temperature: null`, plus the existing `max_tokens` warning is preserved as a comment. |

Backward compatibility: callers that explicitly construct `VLMAgent(temperature=0.7)` (e.g. against a self-hosted endpoint that *does* accept custom temperature) still get the parameter forwarded. The new behavior only changes how a `None` (or omitted) value is handled — previously the SDK would receive a default of `0.7`, now the kwarg is dropped entirely.

After the fix, `python scripts/run_game.py seed=42` runs against the live endpoint with no `BadRequestError`. All 125 tests continue to pass.

### Follow-up fix: actually retry on transient upstream errors

Live runs showed two new transient failure modes that the old retry policy did **not** catch (it only matched `"rate" | "429" | "retry"` substrings):

1. `openai.APIStatusError: ... upstreamException - {"code":"quota_exceeded"} ... Model configuration error`  
   — greatrouter occasionally returns a wrapped quota-exceeded payload from its upstream provider even when the per-user account has quota.
2. `httpx.ReadTimeout: The read operation timed out`  
   — the streaming path (Gemini) sometimes stalls mid-response.

In both cases the *next* tick's call succeeded on its own, so they are clearly transient — but the agent had already silently fallen back to `wait()` (action) or `""` (speech / vote) for the failed tick. The log line `attempt 1/3` was misleading because the code never actually retried.

**Fix:**

- `quack/agents/vlm_agent.py`
  - New module-level `_is_retryable_error(exc)` that returns `True` for typed `openai.RateLimitError` / `APITimeoutError` / `APIConnectionError` / `InternalServerError` and `httpx.TimeoutException` / `NetworkError` / `RemoteProtocolError`, plus a substring fallback covering `quota_exceeded`, `upstreamException`, `5xx`, `timed out`, `connection reset`, etc. Permanent client errors (`BadRequestError`, auth, model-not-found, …) are intentionally not retried.
  - `_call_vlm()` now calls `_is_retryable_error()` to decide whether to retry. `max_retries` raised from 3 → 4. Backoff is capped exponential (`min(30, 2 ** (attempt+1))`) plus 0–0.75s random jitter to avoid thundering herd across the 6 concurrent agents.
  - Retryable failures are logged at `WARNING` with `type(e).__name__` and a 240-char message snippet; the full traceback is only emitted with `logger.exception` when retries are truly exhausted or the error is permanent. Terminal output for a normal run with a couple of upstream blips no longer carries 30-line stack traces per attempt.
- `tests/test_agents/test_vlm_retry.py` (new, 19 tests)
  - Substring matching for every observed transient pattern (`upstreamException`, `quota_exceeded`, `429`, `503`, `502`, `500`, `timed out`, `Connection reset`, `RemoteProtocolError`, …).
  - Negative cases for permanent errors (`Unsupported value`, `Invalid request`, `Authentication failed`, `model ... does not exist`, `Permission denied`).
  - Typed-exception coverage: `openai.RateLimitError`, `openai.InternalServerError`, `httpx.ReadTimeout`, `httpx.RemoteProtocolError` (skipped automatically if the SDK is missing).

After the fix:

```bash
python -m pytest -q
# 144 passed (was 125 — 19 new retry-policy tests, 0 regressions)
```

Behavioral effect on a live run: when greatrouter returns `quota_exceeded` or the stream times out, the agent now sleeps a couple of seconds and retries (up to 4 attempts) instead of immediately defaulting to `wait()` / empty speech. The terminal noise per failure drops from a multi-line traceback to a single `WARNING` line; only a true give-up emits the full traceback.

### Renderer fix: "teleporting" characters, missing spawn frame, frame-vs-tick mismatch

Watching the god-view video, the user noticed three closely-related visual bugs:

1. **Characters appear to teleport between adjacent frames** (the user's specific example: Frank shows up in `weapons` in one frame and `medbay` in the very next frame, even though those rooms are not adjacent).
2. **Render "tick" doesn't line up with the engine tick.** During a meeting, ~7 frames in a row all share the same `state.current_tick` in the HUD, then the next free-roam frame jumps the label.
3. **Tick 0 — the actual spawn state — is never rendered.** The video opens at tick 1, after every agent has already taken its first action, so the viewer never sees the starting positions.

I traced every frame produced by `run_game.py` and `replay_game.py` against `quack/engine/game_engine.py`. The game-logic side is fine; the engine is fully consistent (single-tick moves only go to adjacent rooms; multi-tick moves correctly leave `current_room` at the origin while in transit; `_god_draw_all_players` already draws in-transit players along the corridor). The teleport is *not* a kinematics bug — it is the deliberate **post-ejection respawn** in `_post_ejection`, which randomly re-rooms every alive player after a meeting. Before this fix the respawn was completely invisible to the viewer because:

```
... last free-roam god-view (players at pre-meeting positions)
    meeting-called frame (1280×720, no map)
    speech frames     (1280×720, no map)
    vote-result frame (1280×720, no map)
    _post_ejection() runs — silently mutates positions, no event, no frame
    next free-roam god-view (players already at new random rooms)
```

So in the video the two adjacent **god-view** frames showed players at completely unrelated rooms, while nothing in the HUD or logs explained it.

**Fix — engine:**

- `quack/engine/event_bus.py`: new `EventType.PLAYERS_RESPAWNED` ("players_respawned").
- `quack/engine/game_engine.py::_post_ejection` now snapshots the random respawn into a `respawn_map: dict[player_id, room]` and emits `PLAYERS_RESPAWNED` with that map (and tick = the meeting tick). The respawn is now in the JSONL log and downstream tools can reconstruct it exactly. The game still ends the same way when win-conditions trigger (no respawn event in that branch).
- `quack/engine/game_engine.py::render_god_view` accepts two new optional HUD args, `frame_idx` and `phase_override`, so individual frames can show *which* frame number they are within the same tick and *what they are showing* (e.g. `Spawn`, `Respawn (post-meeting)`) rather than only the engine phase.
- `quack/rendering/map_renderer.py::render_god_view` consumes those args and now draws the HUD as:

  ```
  GOD VIEW  |  Frame 0018  |  Tick: 2  |  Phase: Respawn (post-meeting)
  ```

  Previously it could only show `Tick: N | Phase: <engine phase>`, so the seven-frame meeting at tick 8 all looked indistinguishable.

**Fix — `scripts/run_game.py`:**

- Before the main loop, an explicit **spawn frame** is now rendered from the post-`setup_game` state, labelled `Phase: Spawn`. This is the missing tick-0 frame.
- In the `"ejection"` branch, after `engine._post_ejection()` finishes and the phase has flipped back to `free_roam`, a dedicated **respawn frame** is rendered with `Phase: Respawn (post-meeting)`. This is the previously-missing visualization of the random repositioning.
- `_save_god_view_frame` was extended to forward `frame_idx` (now baked into every god-view frame) and `phase_override`.

**Fix — `scripts/replay_game.py`:**

- Renders the same spawn frame from the `game_started` event's `initial_state` before iterating events.
- Handles the new `players_respawned` event: updates each surviving player's `current_room`, clears transit fields, snaps `state.phase` back to `FREE_ROAM`, and emits a dedicated respawn god-view frame so the replay video matches the live video frame-for-frame.
- When applying a multi-tick `player_moved` event, `current_room` is now explicitly set to `from_room`. This closes a subtle replay bug: after a respawn the player's actual room had changed in the engine, but the replay's `current_room` was stale (the engine doesn't update `current_room` while in transit). Without the sync, the replay rendered the corridor segment from the *pre-meeting* room to the new destination — visually wrong for the first move after every meeting. Now the corridor always starts at the logged `from`.
- Renders a god-view frame on `body_reported` / `meeting_called` to mirror the live behaviour where `run_game.py` saves a god-view after `_run_free_roam_tick` even when that tick was interrupted by a report. Without this the replay was missing one god-view per meeting.

**Backward compatibility:**

- Old logs (no `players_respawned` events) still replay; they just don't get the dedicated respawn frame. The `current_room` ← `from_room` sync in the multi-tick branch makes the *first move after a meeting* render correctly in old logs as well, because the logged `from` field of that move is already the post-respawn room.
- `render_god_view`'s new HUD args are optional; existing callers that don't pass them get the pre-change HUD format unchanged.

**Validation:**

- Smoke run (`seed=1`, random agents, 25 ticks, 2 meetings, both with respawns) produces 54 frames including:
  - `Frame 0001 | Tick: 0 | Phase: Spawn`
  - regular tick-end god-views
  - meeting / speech / vote frames at 1280×720 (unchanged)
  - `Frame 0018 | Tick: 2 | Phase: Respawn (post-meeting)` and `Frame ... | Tick: 14 | Phase: Respawn (post-meeting)`
- `python scripts/replay_game.py` on the new log generates 54 frames (exact parity with live); on a pre-fix log it generates 45 frames (no missing-key crash, just no respawn frames).
- `python -m pytest -q` — 144 passed (no regressions).

**What the user will now see in the video for the original report:** instead of two god-view frames where Frank seems to jump from `weapons` to `medbay`, the sequence is now `... weapons (free roam) → meeting-called → speeches → vote-result → Respawn (post-meeting) → medbay (free roam) ...`, with the respawn frame's HUD explicitly labelled so the random repositioning is visible and self-explanatory.

### Engine fix: weight-W corridor must consume W game ticks (off-by-one in `_do_move`)

While reviewing a fresh `gpt5.5/20260520_203835_seed42` log the user spotted a second, deeper teleport — this one in the engine itself, not the renderer. Frank's log fragment:

```
tick 5: player_5 moved upper_engine -> oxygen          (instant, weight=1)
tick 6: player_5 moved oxygen -> cafeteria  ticks_remaining: 1
tick 7: player_5 moved cafeteria -> electrical  ticks_remaining: 1
tick 8: player_5 killed player_1 in electrical
```

`oxygen ↔ cafeteria` is weight 2 in `configs/maps/simple_ship.yaml`, and `cafeteria ↔ electrical` is also weight 2 — so the legal travel time for `oxygen → cafeteria → electrical` is **4 game ticks**, not 2. The engine was letting Frank traverse both corridors in **two ticks** (one action per tick), which then enabled the tick-8 kill in `electrical` that the goose timeline-arithmetic could not explain.

**Root cause** — one-line off-by-one in `quack/engine/game_engine.py::_do_move`:

```python
player.move_ticks_remaining = weight - 1
```

The intent of the surrounding pipeline is:

1. `_run_free_roam_tick` increments `current_tick`, then calls `_advance_transit` at the **start** of every tick. `_advance_transit` decrements `move_ticks_remaining` and, when it hits zero, marks the player arrived.
2. After `_advance_transit`, the player gets an action turn — but only if `is_in_transit` is false.

With `move_ticks_remaining = weight - 1`, a weight-2 corridor was set to `1` on tick N, then immediately decremented to `0` at the start of tick N+1, so the player arrived **and** could act on the same tick N+1. Effective travel time = **1** game tick regardless of corridor weight ≥ 2. Weight-3 corridors took only 2 ticks, weight-4 only 3, etc.

**Fix** — set `move_ticks_remaining = weight` instead:

```python
# A weight-W corridor must consume W game ticks total: the action tick where
# _do_move runs (now) plus W-1 subsequent ticks where the player is skipped
# because is_in_transit is True. _advance_transit decrements
# move_ticks_remaining at the START of every following tick before the player
# gets an action turn — so the player is in transit for ticks N+1 .. N+(W-1)
# and arrives at the start of tick N+W where they can act again.
player.move_ticks_remaining = weight
```

The accompanying `# {w} ticks travel time` annotation in `_get_available_actions` is now accurate (previously it claimed weight-2 was "2 ticks travel time" while the engine only spent 1).

**Verified trace** for the user's exact scenario (`oxygen → cafeteria → electrical`, both weight 2), with the fix:

```
tick 1: TRANSIT oxygen->cafeteria (2t left)     # issued move
tick 2: TRANSIT oxygen->cafeteria (1t left)     # skipped action
tick 3: TRANSIT cafeteria->electrical (2t left) # arrived at cafeteria, issued next move
tick 4: TRANSIT cafeteria->electrical (1t left) # skipped action
tick 5: AT electrical                           # arrived, can act
```

Total elapsed = 4 ticks ( = 2 + 2 = sum of weights). Bob's "Frank just came from cafeteria → therefore he was in cafeteria last tick" deductions are now physically possible to reason about.

**Tests updated:**

- `tests/test_systems/test_engine_witness.py::test_engine_emits_multi_tick_arrival_in_completion_tick` — the original test ran `_run_free_roam_tick` twice and asserted "Bob arrived on tick 2", which only held under the buggy off-by-one semantics. Rewrote it as a 3-tick trace: tick 1 starts the move (remaining = 2), tick 2 is in-transit (remaining = 1, no arrival event), tick 3 emits the arrival when `_advance_transit` decrements 1 → 0. Adds explicit `is_in_transit` / `move_ticks_remaining` assertions at every step.
- `tests/test_evaluation/test_game_reconstructor.py::test_multi_tick_travel` — was using `ticks_remaining=1` for a weight-2 corridor (consistent with the old engine output) and asserting arrival at tick 2. Updated the synthetic event to `ticks_remaining=2` and asserts in-transit at both tick 1 and tick 2, arrival at tick 3 — which matches both the new engine logging and the reconstructor's `tick + ticks_remaining` arrival formula.

**Backward compatibility:** the `GameReconstructor` and `replay_game.apply_event` both trust the logged `ticks_remaining`, so pre-fix logs (with `ticks_remaining = weight - 1`) still replay against the original buggy timing they actually ran with — no rewriting needed. The fix only affects logs produced **after** the change.

**Validation:**

- `python -m pytest -q` → 144 passed, 0 failures.
- Direct engine reproduction (single-player scripted agent) confirms `oxygen → cafeteria → electrical` now takes 4 ticks end-to-end.
- Fresh `seed=42 game.max_ticks=10` run shows every multi-tick `player_moved` event in the log now carries `"ticks_remaining": 2` for weight-2 corridors (previously `"ticks_remaining": 1`).
- Replaying both the user's pre-fix `gpt5.5/20260520_203835_seed42/game.jsonl` and a fresh post-fix log both succeed without crashes (the reconstructor's tick-based `ticks_remaining` decrement gracefully handles both the old `1` and the new `2`).

---

## God-View Replay Fix: in-Transit Players Frozen at Origin

**Date:** 2026-05-20

**Reported issue (user):** "I notice some player actions from the log are not correctly appearing on the rightmost side of the god view." Looking at `game_logs/homogeneous/gpt5.5/20260520_212746_seed42/game.jsonl`, the event log on the right panel correctly listed lines like `[T7] Bob moved security -> electrical` and `[T8] Eve moved weapons -> cafeteria`, but the **player roster** (also on the right panel) and the **map sprites** kept showing those players at their *origin* room (`security`, `weapons`) instead of their *destination* room — making it look like those logged actions had no effect.

### Root cause

The live engine's `_run_free_roam_tick` calls `_advance_transit()` at the **start of every tick**. This decrements `move_ticks_remaining` for every in-transit player and, when it hits zero, completes the arrival by setting `current_room = moving_to` and clearing the transit state.

`scripts/replay_game.py` *defined* an equivalent `advance_in_transit(state)` helper but **never called it**. As a result, every multi-tick `player_moved` event in `apply_event` correctly set `move_ticks_remaining = ticks_remaining` and `current_room = from_room`, but no subsequent tick ever decremented or completed the move. Multi-tick travelers stayed pinned to their `from_room` for the entire rest of the replay.

Concrete diff between live engine and replay for this log at end of tick 9:

| Player | Live engine | Replay (pre-fix) | Replay (post-fix) |
| --- | --- | --- | --- |
| Bob (T7 `security → electrical`, w=2) | `electrical` | `security` (frozen, 2t left) | `electrical` |
| Eve (T8 `weapons → cafeteria`, w=2) | in transit `weapons`, 1t left | `weapons`, 2t left (never decremented) | in transit `weapons`, 1t left |
| Frank (T9 `cafeteria → weapons`, w=2) | in transit `cafeteria`, 2t left | `cafeteria`, 2t left (correct, just departed) | `cafeteria`, 2t left |

So at the body-reported frame at T10 the old replay showed Bob at security and Eve at weapons; the live god-view had them at electrical and cafeteria respectively. Frank's "just departed" case happened to look right because no tick boundary had elapsed yet between his departure and the render.

### Files changed

- `scripts/replay_game.py` — call `advance_in_transit(state)` inside `apply_event` for the `tick_start` branch, after kill-cooldown decrement and after merging `pending_arrivals` for the current tick. This exactly mirrors `GameEngine._advance_transit()` being invoked at the top of every `_run_free_roam_tick`. Added an explanatory comment so future readers don't drop the call again.

### Why this is the right place

- The engine's order at tick N is: emit `tick_start` → `tick_cooldowns` → `_advance_transit` → player actions. The replay's `apply_event(tick_start)` already handled the first two, so adding `advance_in_transit` at the end of that branch preserves the same order before any of the tick's downstream `player_moved` / `task_progress` / `body_reported` events get applied.
- `pending_arrivals` is still merged into `state.tick_movements` (so witness-arrow rendering of arrivals is unchanged). The fix only adds the missing `current_room` mutation for arriving players — `pending_arrivals` and `advance_in_transit` are complementary, not redundant.
- A player who finishes transit at tick N can now act on tick N just like the live engine allows (Bob arrives at electrical at T9 start and immediately progresses his task that same tick — confirmed against the log).

### Verification

- Reconstructed state for `gpt5.5/20260520_212746_seed42/game.jsonl` at end of tick 9 now exactly matches the live engine for every player (Bob at electrical, Eve in transit with 1t left, Diana at medbay, etc.).
- Re-rendered `renders_new/` + `video_new.mp4` for the same log. The frame-11 (body-reported) god view now draws Bob in `electrical`, Eve in `cafeteria` (just arrived, with the body she reported), Frank in `cafeteria` (transit cancelled by the meeting) — matching the in-game ground truth.
- The event-log panel content was always correct (all 37 entries appear, no events are filtered out); only the roster and sprite positions were stale, and both are now consistent with the event log.
- `python -m pytest -q` → 144 passed, 0 failures.

### Backward compatibility

The fix is purely on the replay side and changes no on-disk log format. All historical `game.jsonl` files will now replay with the **correct** post-transit positions; previously they replayed with frozen-at-origin positions for any player who initiated a multi-tick move.

---

## Batch Default: 50 → 30 Games Per Condition

**Date:** 2026-05-20

**Request (user):** lower the default seed count for all batch experiment scripts from 50 to 30 so the full experiment matrix completes in a more reasonable amount of compute (270 instead of 450 games end-to-end).

### Files changed

- `scripts/batch_homogeneous.sh` — `NUM_GAMES=50` → `NUM_GAMES=30`; help-text examples and usage comment updated to reflect "× 30 seeds".
- `scripts/batch_heterogeneous.sh` — `NUM_GAMES=50` → `NUM_GAMES=30`; usage comment and example updated to "× 30 seeds".
- `scripts/batch_full_experiment.sh` — `NUM_GAMES=50` → `NUM_GAMES=30`; header comment and the "9 × 50 = 450 games" example updated to "9 × 30 = 270 games".
- `README.md` — every Quickstart / batch section example that referenced 50 games / `seq 1 50` is now 30 games / `seq 1 30`. The full-experiment line now reads "9 conditions × 30 games = 270 games".

### Behavior

- All three scripts still accept `-n NUM` to override. Anyone who wants the old 50-game runs can pass `-n 50` explicitly; nothing in the runner logic changed except the default.
- `bash -n` syntax check on all three scripts passes; `python -m pytest -q` still 144 passed (no test changes).

---

## Claude Opus 4.7: Switch to Official Anthropic API

**Date:** 2026-05-20

**Reported issue (user):** Claude Opus 4.7 calls through the greatrouter proxy were heavily rate-limited and very slow — too slow to run a 30-game homogeneous batch. Decision: keep GPT-5.5 and Gemini 3.1 Pro Preview on greatrouter (they work fine there), but route Claude Opus 4.7 directly to `api.anthropic.com` using a dedicated Anthropic key.

### Design

`VLMAgent` is now **provider-aware**. A new `provider` field on each model YAML (default `"openai"`) selects between:

| Provider | SDK | Endpoint | Key source |
|---|---|---|---|
| `openai` | `openai` Python SDK (OpenAI-compatible) | `cfg.base_url` (greatrouter by default) | `api_key.txt` / `$QUACK_API_KEY` |
| `anthropic` | `anthropic` Python SDK | `api.anthropic.com` (SDK default) | `claude_key.txt` / `$ANTHROPIC_API_KEY` |

Everything else in the agent — prompt building, vision images, retry policy, memory — is identical across providers. The provider switch only changes (1) which SDK client is constructed, (2) which API key is supplied, and (3) how the OpenAI-style internal message format is rewritten on the way to the wire.

### Files changed

- `configs/model/claude_opus4.7.yaml` — added `provider: "anthropic"` and `max_tokens: 4096` (Anthropic's Messages API requires `max_tokens` on every call). Header comment now explains why we bypass greatrouter for Opus.
- `quack/agents/vlm_agent.py`:
  - Constructor: new `provider: str = "openai"` and `max_tokens: int | None = None` parameters.
  - `_get_client()`: branches on `self.provider`. Anthropic path builds `anthropic.Anthropic(api_key=..., max_retries=3, timeout=60.0)`. OpenAI path is unchanged.
  - `_call_vlm_sync()` / `_call_vlm_stream()`: dispatch to the new `_call_anthropic_sync` for `provider="anthropic"`. The streaming branch falls back to non-streaming for Anthropic (no Claude model currently sets `requires_stream=True`).
  - New `_call_anthropic_sync()`: builds `client.messages.create(model=, max_tokens=, system=, messages=, [temperature=])` kwargs, then concatenates text from the response's content blocks.
  - New `_to_anthropic_messages()` static helper — the single conversion point from OpenAI-format to Anthropic-format messages. Pulls every `system` role out into a single top-level `system=` string, and rewrites each OpenAI `image_url` part (`data:image/png;base64,...` URL) into Anthropic's typed `image` block (`{type: image, source: {type: base64, media_type, data}}`). Text parts pass through unchanged, and already-typed `image` blocks pass through too. Multiple `system` messages are joined with `\n\n`.
  - `_is_retryable_error()`: now also recognizes `anthropic.RateLimitError`, `anthropic.APITimeoutError`, `anthropic.APIConnectionError`, and `anthropic.InternalServerError` so the existing capped-exponential-backoff retry loop applies to Claude calls too.
- `scripts/run_game.py`:
  - New helper `_resolve_provider_key(model_cfg, openai_key, anthropic_key)` — picks the matching key based on the model's `provider` field, with `openai` as the fallback for legacy configs that don't set it.
  - `create_agents_from_config()` and `reassign_duck_agents()` now accept an `anthropic_api_key` kwarg and forward `provider` + `max_tokens` from the model YAML to every `VLMAgent` they construct. Heterogeneous mode picks the key per-model (e.g. a GPT-5.5 goose + Claude-Opus duck game uses both keys in the same run).
  - `run_game()` accepts `anthropic_api_key` and considers the run "VLM-enabled" if *either* key is present.
  - `main()` loads the Anthropic key from `$ANTHROPIC_API_KEY` first, then `claude_key.txt` at the project root, mirroring the existing `api_key.txt` flow.
- `pyproject.toml` — added explicit `openai>=1.40` and `anthropic>=0.39` dependencies. (Previously `openai` was a transitive dep of `litellm`; now both providers are first-class.)
- `.gitignore` — `claude_key.txt` is now ignored alongside `api_key.txt`.
- `README.md`:
  - Quickstart now mentions both `api_key.txt` and `claude_key.txt`.
  - "Supported Models" table gains a **Provider** and **Endpoint** column.
  - "Adding a New Model" snippet shows the `provider:` and (Anthropic-only) `max_tokens:` fields.
  - Layout diagram lists `claude_key.txt` next to `api_key.txt`.
  - Agent-architecture paragraph clarifies that Claude is on the official Anthropic API, not greatrouter.

### Tests

- New `tests/test_agents/test_vlm_anthropic.py` (9 tests) pins:
  - System-role messages get pulled out into the top-level `system` parameter; multiple system messages join with `\n\n`; list-form system content concatenates text parts.
  - Plain string user content passes through unchanged.
  - `data:image/png;base64,<b64>` URLs convert to Anthropic `image` blocks with `source.type=base64`, the matching `media_type`, and the raw base64 payload (stripped of the `data:` prefix).
  - `image/jpeg` URLs preserve their media type.
  - Already-typed `image` blocks pass through unchanged.
  - `_is_retryable_error` returns True for `anthropic.RateLimitError` and `anthropic.InternalServerError` instances.
- Existing `tests/test_agents/test_vlm_retry.py` keeps passing — the retry predicate stays a superset of the original behavior.
- Mock-client smoke test confirmed end-to-end that calling `_call_anthropic_sync` with a typical OpenAI-format message list calls `client.messages.create(model="claude-opus-4-7", max_tokens=2048, system="You are Alice.", messages=[{role:"user", content:[{type:"image", source:{type:"base64", media_type:"image/png", data:"XYZ="}}, {type:"text", text:"What do you see?"}]}])`.

### Validation

- `python -m pytest -q` → **153 passed** (was 144; 9 new Anthropic-conversion tests).
- `ruff check quack/agents/vlm_agent.py scripts/run_game.py tests/test_agents/test_vlm_anthropic.py` → clean.
- Config-routing check: `_resolve_provider_key` correctly picks `anth-key` for `claude_opus4.7.yaml` and `oai-key` for `gpt5.5.yaml` / `gemini3.1pro.yaml`.

### Backward compatibility

- Model configs without a `provider:` field default to `"openai"`, so any third-party / private model configs that pre-date this change continue to work.
- `max_tokens` is only forwarded when the model config sets it, so the existing Gemini-streaming requirement ("do NOT set `max_tokens`") is unaffected.
- No on-disk log format changed; old `game.jsonl` files replay identically.

## 2026-05-22 (Tier 3: Per-Claim Audit Log with Raw Engine Events)

### Motivation

`evaluation.json` keeps only the final aggregate Tier 3 metrics
(`goose_truthfulness`, `duck_near_miss_claims`, `deception_sophistication`,
…). For any specific verdict it produces, you couldn't tell **(a)** which
claim was extracted, **(b)** which raw `game.jsonl` events it was compared
against, or **(c)** why it landed in the bucket it did. Reviewers wanting
to spot-check a `near_miss` verdict had to re-derive the ground truth by
hand from the engine log.

This change writes a per-claim audit log alongside `evaluation.json` so
every aggregated number can be traced back to specific log lines.

### What changed

- **New file** `tier3_claims.jsonl` is written next to `evaluation.json`
  whenever Tier 3 runs (one JSON object per claim, JSONL). Each entry
  contains:
  - `meeting` — meeting index / tick / type / caller
  - `temporal_window` — `[start_tick, end_tick]` the verifier inspected,
    plus how the window was resolved (`preceding_free_roam`,
    `round_boundary_fallback`, `game_start_clamp`, …)
  - `speaker` — speaker id / name / team (goose/duck) / alive_at_meeting
  - `utterance` — the raw discussion message the LLM extracted from
  - `structured_claim` — claim type / subject / target / room /
    activity / temporal_ref / duration_semantics / confidence
  - `verification` — final `verdict` (`true` / `false` / `near_miss` /
    `wrong_room` / `unverifiable`), `verifier_name`, free-form `reason`,
    and a derived `evidence` block (e.g. `match_rate`, `observed_rooms`,
    `ticks_checked`)
  - **`ground_truth_events`** — *new*. The raw event dicts copied
    verbatim from `game.jsonl`, filtered to events that (i) fall inside
    `temporal_window` and (ii) involve the claim's subject / target /
    speaker. This is the "对照的 game engine log event" piece — you can
    open `tier3_claims.jsonl`, find a claim, and see the exact log lines
    the verdict was compared against without having to re-read the
    whole `game.jsonl`.

### Code changes

- `quack/evaluation/tier3_statement_verification.py`:
  - New `StatementVerificationPipeline._filter_relevant_events(actor_ids,
    start_tick, end_tick, event_types=None, max_events=200)` helper.
    Returns the raw `game.jsonl` events of relevant types
    (`player_moved`, `player_killed`, `task_progress`, `task_completed`,
    `body_reported`, `meeting_called`, `free_roam_chat`,
    `player_ejected`, `players_respawned`) where any of the supplied
    actor ids appears as `player_id` / `killer_id` / `target_id` /
    `caller` / `voter` / `target`. Empty `actor_ids` returns `[]` so
    audits don't balloon when entity resolution fails.
  - `_build_audit_entry()` now collects `subject_id`, `target_id`,
    and — for `accusation` / `defense` claims — the speaker, then attaches
    the filtered raw events under a new top-level `ground_truth_events`
    field on every audit record.
- `quack/evaluation/evaluator.py`:
  - `GameEvaluator.evaluate(..., save_tier3_audit=True)` — default flipped
    from `False` to `True`. The audit file is free once you've paid for
    the LLM calls, so it's now produced automatically with every Tier 3
    run.
  - `BatchEvaluator.evaluate_batch(..., save_tier3_audit=True)` — new
    kwarg, forwarded to each per-game `evaluate()`.
- `scripts/evaluate_game.py` and `scripts/evaluate_batch.py`:
  - `--save-tier3-audit` is now the default behavior (kept as a no-op
    alias for backwards compat).
  - New `--no-tier3-audit` flag to opt out for users who only want the
    aggregate metrics file.

### Tests

- New class `TestAuditGroundTruthEvents` in
  `tests/test_evaluation/test_claim_verification.py` (6 tests) pins:
  - Every audit entry has the `ground_truth_events` list field.
  - All cited events fall inside the audit's declared `temporal_window`.
  - Every cited event references the claim's subject (or target) in one
    of the standard actor keys (`player_id` / `killer_id` / `target_id`
    / `caller` / `voter` / `target`).
  - Cited events are verbatim log entries (carry `event_type`, `tick`,
    `data`), not summarized / transformed.
  - `_filter_relevant_events` returns `[]` when given an empty actor set
    (so audits don't balloon when entity resolution fails).
  - `_filter_relevant_events` respects the tick window.

### Validation

- `python -m pytest tests/test_evaluation -q` → **98 passed** (was 92;
  +6 new audit tests).
- `python -m pytest tests/test_evaluation/test_claim_verification.py -q`
  → **54 passed**.
- Offline smoke test on a real game log
  (`game_logs/homogeneous/gpt5.5/20260520_230743_seed1/game.jsonl`):
  generated audit for a synthetic "Alice was in medbay" location claim →
  verdict `false`, 26 raw `game.jsonl` events surfaced under
  `ground_truth_events`, all involving Alice (`player_0`), all within the
  declared window `[0, 21]`.

### Backward compatibility

- `evaluation.json` schema is unchanged; the new file is purely
  additive.
- `--save-tier3-audit` (the old opt-in flag) still works — it now just
  matches the default. Existing scripts that explicitly pass it are
  unaffected. Pass `--no-tier3-audit` to restore the pre-change
  "metrics-only" behavior.
- `EvaluationResult.tier3_audit_path` was already in `evaluator.py`
  before this change; only the default of `save_tier3_audit` flipped,
  so any code reading `result.tier3_audit_path` keeps working.
