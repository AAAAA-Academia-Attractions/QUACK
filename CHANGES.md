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
