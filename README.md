# QUACK🦆: Questioning, Understanding, and Assessing Collaborative Knowledge

### A Multimodal Social Deduction Benchmark for Vision-Language Models

Social deduction games are compelling testbeds for evaluating agents' theory of mind, deception, and social reasoning. Yet most existing benchmarks are *text-only*, preventing grounded verification of agents' claims against their actual behavior in partially observed environments.

**QUACK** is the first *multimodal* social deduction benchmark designed for Vision-Language Models, built on a fully open-source engine for multimodal social deduction research. Agents navigate configurable graph-based map layouts with weighted corridors, operate under strict partial observability with same-room visibility, complete multi-tick location-bound tasks, and participate in emergency meetings with multi-round free-form discussion and voting. Each decision step provides a global map view, a local perceptual view, and structured textual state, requiring grounded multimodal reasoning over long-horizon episodes.

Beyond environment design, QUACK introduces a structured evaluation protocol that measures task performance, social coordination, adversarial robustness, and behavioral linguistic consistency. We develop an automatic Statement Verification Pipeline that extracts spatial and behavioral claims from meeting utterances and validates them against engine-level ground-truth logs, enabling scalable auditing of deception, belief consistency, and action-speech alignment under partial observability.

<video width="320" height="240" controls>
  <source src="https://github.com/AAAAA-Academia-Attractions/QUACK/blob/main/assets/video.mp4" type="video/mp4">
</video>

---

## Why This Project?

Most existing social deduction agent benchmarks (Werewolf, Mafia, Avalon) are text-only — agents read and write natural language. This limits testing to LLM capabilities alone.

QUACK introduces a **spatial dimension**: agents navigate a discrete map, have limited local vision, and receive rendered map images as input. This means VLM agents must:

1. **Read and interpret visual maps** — understand room layouts, task markers
2. **Reason spatially** — plan movement routes based on weighted corridors, track encounters
3. **Deduce socially** — identify impostors through discussion and voting
4. **Act strategically** — balance task completion with survival and information gathering

---

## Quick Start

### Installation

```bash
cd QUACK

python3 -m venv .venv
source .venv/bin/activate

pip install -e ".[dev]"
```

### Run a Game (Random Agents — no API key needed)

```bash
# Basic game with random agents (no api_key.txt required)
python scripts/run_game.py

# With a fixed seed for reproducibility
python scripts/run_game.py seed=42

# Disable video generation (faster)
python scripts/run_game.py video=false seed=42
```

### Run a Game (VLM Agents)

```bash
# Create api_key.txt with your API key first
echo "sk-your-key-here" > api_key.txt

# Run with GPT-5.2 (default model)
python scripts/run_game.py seed=42

# Run with Claude Opus 4.6
python scripts/run_game.py model=claude_opus4.6 seed=42

# Run with Gemini 3.1 Pro (uses streaming automatically)
python scripts/run_game.py model=gemini3.1pro seed=42

# VLM agents with Simplified Chinese speech (简体中文)
python scripts/run_game.py speak_chinese=true seed=42

# Custom API endpoint
python scripts/run_game.py base_url=https://endpoint.wendalog.com
```

### Heterogeneous Experiments

```bash
# GPT-5.2 geese vs Claude Opus 4.6 duck
python scripts/run_game.py experiment=heterogeneous model=gpt5.2 experiment.duck_model=claude_opus4.6 seed=42

# Claude geese vs Grok duck
python scripts/run_game.py experiment=heterogeneous model=claude_opus4.6 experiment.duck_model=grok4 seed=42
```

### Batch Runs

Three shell scripts automate large-scale experiments. All support `-h` for full usage.

#### Homogeneous Batch (`batch_homogeneous.sh`)

```bash
# All 5 models × 50 games each (default)
./scripts/batch_homogeneous.sh

# Single model, 10 games
./scripts/batch_homogeneous.sh -m gpt5.2 -n 10

# Two models, 5 games each, starting from seed 11
./scripts/batch_homogeneous.sh -m gpt5.2,claude_opus4.6 -n 5 -s 11

# Skip video generation for faster runs
./scripts/batch_homogeneous.sh -m gpt5.2 -n 10 -- video=false
```

#### Heterogeneous Batch (`batch_heterogeneous.sh`)

```bash
# All cross-model pairs (20 pairs) × 50 games each
./scripts/batch_heterogeneous.sh

# Specific goose/duck pair, 10 games
./scripts/batch_heterogeneous.sh -g gpt5.2 -d claude_opus4.6 -n 10

# GPT-5.2 geese vs every other model as duck, 5 games each
./scripts/batch_heterogeneous.sh -g gpt5.2 -d all -n 5
```

#### Full Experiment Suite (`batch_full_experiment.sh`)

```bash
# Full matrix: 6 homogeneous + 30 heterogeneous = 36 conditions × 50 games = 1800 games
./scripts/batch_full_experiment.sh

# Quick test run: 36 conditions × 5 games = 180 games
./scripts/batch_full_experiment.sh -n 5

# Run everything + auto-evaluate at the end
./scripts/batch_full_experiment.sh -n 10 --eval
```

#### Manual loop (alternative)

```bash
# Run 50 games with Gemini 3.1 Pro
for seed in $(seq 1 50); do
    python scripts/run_game.py model=gemini3.1pro seed=$seed
done

# Run 50 heterogeneous games
for seed in $(seq 1 50); do
    python scripts/run_game.py experiment=heterogeneous model=gpt5.2 experiment.duck_model=claude_opus4.6 seed=$seed
done
```

### Replay a Game Log

```bash
# Regenerate render frames from a saved game log
python scripts/replay_game.py game_logs/homogeneous/gpt5.2/20260308_143022_seed42/game.jsonl --output renders/replay/

# Generate frames + assemble into video
python scripts/replay_game.py game_logs/homogeneous/gpt5.2/20260308_143022_seed42/game.jsonl -o renders/replay/ --video replay.mp4 --fps 3
```

### Generate Videos from Existing Runs

```bash
# Generate video.mp4 for all runs that don't have one yet (1 fps)
./scripts/generate_videos.sh

# Only for a specific model
./scripts/generate_videos.sh game_logs/homogeneous/gpt5.2/

# Custom frame rate
./scripts/generate_videos.sh -f 2

# Force-regenerate all videos (even if video.mp4 already exists)
./scripts/generate_videos.sh --force
```

### Evaluate Games

```bash
# Evaluate a single game (Tier 1 + Tier 2; auto-saves evaluation.json alongside game.jsonl)
python scripts/evaluate_game.py game_logs/homogeneous/gpt5.2/20260308_143022_seed42/game.jsonl

# Include Tier 3 statement verification (requires LLM API key)
python scripts/evaluate_game.py game_logs/homogeneous/gpt5.2/20260308_143022_seed42/game.jsonl --tier3 --api-key YOUR_KEY

# Evaluate all GPT-5.2 homogeneous games
python scripts/evaluate_batch.py game_logs/homogeneous/gpt5.2/

# Evaluate all homogeneous models at once
python scripts/evaluate_batch.py game_logs/homogeneous/

# Evaluate a specific heterogeneous condition
python scripts/evaluate_batch.py game_logs/heterogeneous/geese_gpt5.2_duck_claude_opus4.6/

# Evaluate everything
python scripts/evaluate_batch.py game_logs/ --tier3 --api-key YOUR_KEY
```

---

## Configuration (Hydra)

QUACK uses [Hydra](https://hydra.cc/) for hierarchical configuration management. All settings are composable YAML files under `configs/`:

```
configs/
├── config.yaml              # Main entry point (defaults + runtime options)
├── game/
│   └── default.yaml          # Game rules (num_players, max_ticks, etc.)
├── map/
│   └── simple_ship.yaml      # Map definition (rooms, corridors, tasks)
├── model/
│   ├── gpt5.2.yaml           # GPT-5.2 (default)
│   ├── gpt5.4.yaml           # GPT-5.4
│   ├── gemini3.1pro.yaml     # Gemini 3.1 Pro (streaming)
│   ├── claude_opus4.6.yaml   # Claude Opus 4.6
│   ├── grok4.yaml            # Grok 4
│   └── kimi2.5.yaml          # Kimi K2.5
└── experiment/
    ├── homogeneous.yaml      # All players use the same model
    └── heterogeneous.yaml    # Geese use one model, duck uses another
```

Override any setting on the command line using Hydra's `key=value` syntax:

```bash
# Override seed and model
python scripts/run_game.py model=claude_opus4.6 seed=42

# Override game settings
python scripts/run_game.py game.max_ticks=100 game.num_ducks=2

# Override nested settings
python scripts/run_game.py game.kill.cooldown_ticks=3 game.meeting.max_discussion_rounds=3

# Disable video and god view
python scripts/run_game.py video=false god_view=false
```

---

## Supported Models

| Config Name | Display Name | API Model ID | Streaming | Notes |
|---|---|---|---|---|
| `gpt5.2` | GPT-5.2 | `gpt-5.2` | No | Default model |
| `gpt5.4` | GPT-5.4 | `gpt-5.4` | No | |
| `gemini3.1pro` | Gemini 3.1 Pro | `gemini-3.1-pro-preview` | **Yes** | Requires streaming to avoid timeout; do NOT set max_tokens |
| `claude_opus4.6` | Claude Opus 4.6 | `claude-opus-4-6` | No | |
| `grok4` | Grok 4 | `grok-4` | No | |
| `kimi2.5` | Kimi K2.5 | `Kimi-K2.5` | No | |

All models use the same API key and base URL (`https://endpoint.greatrouter.com` by default).

### Adding a New Model

Create a YAML file at `configs/model/<name>.yaml`:

```yaml
name: "my_model"
display_name: "My Model"
model_id: "my-model-api-id"
temperature: 0.7
requires_stream: false
```

Then run: `python scripts/run_game.py model=my_model`

---

## Output Structure

Each experiment run produces a self-contained directory with everything needed for analysis and replay:

```
game_logs/
├── homogeneous/
│   ├── gpt5.2/
│   │   ├── 20260308_143022_seed42/
│   │   │   ├── game.jsonl           # Structured event log
│   │   │   ├── config.yaml          # Frozen Hydra config snapshot
│   │   │   ├── evaluation.json      # Evaluation results (after running evaluate)
│   │   │   ├── renders/
│   │   │   │   └── god_view/
│   │   │   │       ├── frame_0001.png
│   │   │   │       ├── frame_0002.png
│   │   │   │       └── ...
│   │   │   └── video.mp4            # Auto-generated replay video
│   │   ├── 20260308_143522_seed43/
│   │   │   └── ...
│   │   └── ...
│   ├── gpt5.4/
│   ├── gemini3.1pro/
│   ├── claude_opus4.6/
│   ├── grok4/
│   └── kimi2.5/
├── heterogeneous/
│   ├── geese_gpt5.2_duck_claude_opus4.6/
│   │   └── 20260308_150000_seed42/
│   │       └── ...
│   └── ...
└── evaluation/                # Aggregated results (from batch evaluator)
    ├── homogeneous_gpt5.2.json
    ├── heterogeneous_geese_gpt5.2_duck_claude_opus4.6.json
    └── summary.json
```

### Naming Convention

- **Homogeneous:** `game_logs/homogeneous/{model_name}/{timestamp}_seed{N}/`
- **Heterogeneous:** `game_logs/heterogeneous/geese_{goose_model}_duck_{duck_model}/{timestamp}_seed{N}/`
- **Random seed:** `{timestamp}_random` when no seed is specified.

---

## Understanding the Game

### Roles

- **Goose** — Crew members. Complete tasks to win. Can report bodies and call emergency meetings.
- **Duck** — Impostors. Kill Geese to gain voting majority. Blend in by pretending to do tasks. Can report bodies strategically.

### Win Conditions

| Team | How to Win |
|------|-----------|
| Goose | Complete all tasks **OR** eject all Ducks via voting |
| Duck | Kill enough Geese to reach voting majority (Ducks >= Geese alive) |
| Either | If max ticks reached, Geese win by default |

### Game Phases

```
FREE_ROAM ──→ MEETING_CALLED ──→ DISCUSSION ──→ VOTING ──→ EJECTION ──→ FREE_ROAM
    │              (body report or                                           │
    │               emergency bell)                                          │
    └────────────────────────────────────────────────────────────────────────┘
    │
    └─── (win condition met) ──→ GAME_OVER
```

1. **Free Roam** — Each tick, every alive player chooses an action:
   - `move(room_name)` — walk to an adjacent room (travel time varies by corridor weight)
   - `do_task()` — work on a task in the current room (takes multiple ticks)
   - `report()` — report a dead body in the room (triggers meeting)
   - `call_meeting()` — press the emergency button (cafeteria only, limited uses)
   - `kill(target_id)` — *Duck only* — kill a player in the same room
   - `wait()` — do nothing
   - **Optional chat** — with any action, an agent may append `| say(message)` to speak to players in the **same room** during Free Roam (e.g. `move(weapons) | say(I saw a body in storage)`).

2. **Discussion** — The player who reported the body or pressed the emergency button speaks **first**. Remaining players speak in random order. Up to 2 rounds (each player speaks twice max). Body location is only revealed by the reporter's speech — Ducks may lie about it; the God view shows the actual locations so observers can spot lies.

3. **Voting** — Each player votes to eject someone or skips. Majority wins; ties skip.

4. **Ejection** — The ejected player is eliminated. All living players are randomly respawned to new rooms. All bodies are cleared.

### Key Mechanics

- **Caller speaks first**: On body report or emergency meeting, the reporter/caller speaks first. Other players follow in random order.
- **Body location from reporter only**: The meeting reason does not reveal body location — only the first speaker (the reporter) describes it. Ducks can lie about location; God view displays actual locations for observers.
- **Free-roam chat**: During Free Roam, agents may attach `| say(message)` to any action to broadcast a short message to players in the **same room only**. Messages are not heard by players in other rooms or in corridors.
- **Weighted corridors**: Moving between rooms takes a variable number of ticks (1-3). Agents must plan routes efficiently.
- **Random spawns**: Players start in random rooms and are re-randomized after each meeting.
- **Emergency bell limit**: The total number of emergency meetings (bell pulls) per game equals the number of Ducks. Body reports are unlimited.
- **Kill cooldown**: Ducks must wait a cooldown (default: 5 ticks) between kills, with an initial delay (default: 5 ticks) before the first kill.
- **Same-room vision only**: Players can only see other players in the same room. Players in corridors can see others traveling the same corridor. No adjacent-room vision.

### Map

The game uses a **10-room ship map** with weighted corridors:

```
    oxygen ──(2)── cafeteria ──(2)── weapons
      │               │    ╲           │
     (1)             (1)    (2)       (1)
      │               │       ╲        │
  upper_engine ─(2)─ medbay ─(1)─ electrical ─(2)─ security
      │               │                              │
     (2)             (2)                             (2)
      │               │                              │
  lower_engine ─(2)─ storage ─────(3)────── navigation
```

Numbers in parentheses = travel ticks. Each room has themed pixel-art decorations (cafeteria has tables, medbay has beds, etc.) and unique task locations.

---

## VLM Agent Architecture

Each VLM agent (powered by a configurable model via OpenAI-compatible API) has:

### Vision Input (2 images per tick)

1. **Global map** — Shows the full ship layout with all rooms and corridors. The agent's task locations are marked with their color. **No other players are visible** on this map — only the room structure and the agent's own position.

2. **Local view** — A zoomed-in view of the agent's current room or corridor position. Shows players and bodies the agent can actually see right now (same-room only when in a room; same-corridor only when in transit).

### Memory System

Each agent maintains structured memory across the game:
- **Tick history**: room or corridor position, action taken, players seen, bodies found, free-roam chats heard
- **Encounter log**: who was seen, where, when
- **Meeting history**: what was discussed, who was ejected
- **Route description**: path taken since last meeting (for discussion)

### Strategy Prompts

Agents receive role-specific strategy guides embedded in their system prompt:

- **Goose strategy**: Task prioritization, buddy system, early vs late speaker tactics, evidence-based voting
- **Duck strategy**: Target isolation, kill timing, alibi building, teammate protection, strategic body reporting, discussion deflection

### Streaming Support

Some models (e.g. Gemini 3.1 Pro) require streaming to avoid timeouts. This is configured per-model via `requires_stream: true` in the model config. The VLM agent automatically uses streaming when configured.

### Rate Limiting

API calls are globally rate-limited (1s minimum between calls) with automatic retry and exponential backoff for 429 errors. OpenAI client retry logs are suppressed.

---

## Rendering & Visualization

QUACK renders using **pixel-art style character sprites** with themed room interiors.

### Per-Player Global Map

Each agent sees a global map with:
- All rooms and corridors visible (full ship layout)
- Agent's own task locations marked with their color
- No other players shown — agents rely on local view for spatial awareness
- HUD with tick, phase, task progress, alive count

### Per-Player Local View

A zoomed view showing only the agent's current room:
- Players and bodies in the same room
- Adjacent room connections
- Used by VLM agents for spatial decision-making

### God View (Omniscient Observer)

An all-seeing overhead view for human observers and debugging:
- **All players** shown with pixel sprites and role labels (Goose/Duck)
- **Vision halos** — colored overlay showing each player's current vision
- **Action annotations** — last action per player, color-coded (gray=move, green=task, red=kill)
- **Right panel** — player roster, event log (includes kills, meetings, and free-roam chat lines)
- **Per-player POV row** — single horizontal row of every player's first-person local view below the main map (keeps video landscape)
- **Meeting frames** (1280x720) — dedicated frames for meeting calls, speeches, and vote results:
  - Two-panel layout: past speeches on left, current speaker's full message on right (readable fonts)
  - **Actual body locations** banner during discussion — shows the truth so you can see if the reporter (e.g. a Duck) is lying
- **Free-roam chat bubbles** — when players use `say(...)` during Free Roam, their latest message in that tick is rendered as a small text bubble under their character.

### Automatic Video Generation

When `video=true` (default) and `god_view=true` (default), the game automatically stitches god-view frames into an MP4 video using ffmpeg. If ffmpeg is not installed, a warning is logged and the video step is skipped (no crash).

```bash
# Manual stitching (if needed)
ffmpeg -framerate 3 -i renders/god_view/frame_%04d.png -c:v libx264 -pix_fmt yuv420p \
  -vf "pad=ceil(iw/2)*2:ceil(ih/2)*2" god_view.mp4

# Or use the replay script
python scripts/replay_game.py game_logs/homogeneous/gpt5.2/20260308_143022_seed42/game.jsonl --video replay.mp4 --fps 3
```

---

## Game Logs

Every game run saves a structured JSONL log to its experiment directory.

### Log Format

Each line is a JSON object:

```json
{"timestamp": 1772148671.23, "event_type": "player_moved", "tick": 5, "data": {"player_id": "player_0", "from": "cafeteria", "to": "medbay"}}
```

The `game_started` event contains the full initial state (roles, rooms, tasks) enabling complete game replay:

```json
{"event_type": "game_started", "tick": 0, "data": {"players": [...], "config": {...}, "initial_state": {"player_0": {"name": "Alice", "role": "Goose", "team": "goose", "room": "medbay", "tasks": [...]}, ...}}}
```

### Event Types

| Event | Key Data Fields |
|-------|----------------|
| `game_started` | `players`, `config`, `initial_state` |
| `tick_start` / `tick_end` | `tick` |
| `player_moved` | `player_id`, `from`, `to`, `ticks_remaining` |
| `player_killed` | `killer_id`, `target_id`, `room` |
| `body_reported` | `caller`, `reason`, `bodies` (actual room/victim for replay) |
| `meeting_called` | `caller`, `reason` |
| `discussion_message` | `player_id`, `message` |
| `vote_cast` | `voter`, `target` |
| `player_ejected` | `player_id`, `name`, `role`, `team` |
| `vote_skipped` | `reason` |
| `task_progress` | `player_id`, `task_name`, `ticks_done` |
| `task_completed` | `player_id`, `task_name`, `room` |
| `free_roam_chat` | `player_id`, `name`, `room`, `message` |
| `phase_changed` | `phase` |
| `game_over` | `winner`, `reason` |

---

## Evaluation Pipeline

QUACK includes a fully automated evaluation pipeline that reads game logs and computes metrics across three tiers. Tier 1 and Tier 2 run purely from log data; Tier 3 uses an LLM to extract and verify natural language claims.

### Tier 1 — Game-Level Metrics

Computed directly from engine events. No reconstruction required.

| Metric | Description |
|--------|-------------|
| Winner / win reason | `goose`, `duck`, or `timeout` with reason |
| Game duration | Total ticks |
| Task completion rate | Goose tasks completed / total assigned |
| Kill count & timing | Total kills, first kill tick, avg inter-kill interval |
| Meeting counts | Body reports vs emergency meetings |
| Ejection accuracy | Fraction of ejections that removed a Duck |
| Final survival | Alive counts by role |

### Tier 2 — Behavioral Metrics

Requires tick-by-tick game state reconstruction. The `GameReconstructor` replays all events to build a `GameTimeline` that tracks every player's room, transit state, alive status, and action at every tick.

| Metric | Description |
|--------|-------------|
| Goose voting accuracy | Fraction of goose votes targeting a Duck (excluding skips) |
| Goose skip rate | Fraction of goose votes that were skip/null |
| Report latency | Avg ticks between a body appearing in a goose's room and the report |
| Task efficiency | Fraction of goose free-roam ticks spent doing tasks or moving toward task rooms |
| Spatial coverage | Avg distinct rooms visited per goose / per duck |
| Post-kill displacement | Hop distance between kill room and killer's room 3 ticks later |
| Self-report rate | Fraction of kills where the duck reported its own body |
| Cooldown utilization | Fraction of kill opportunities (cooldown=0, goose in room) not taken |

### Tier 3 — Statement Verification

The most novel component. For each meeting discussion message:

1. **Claim extraction** — An LLM parses each statement into structured claims (location, sighting, activity, accusation, defense) with temporal references and normalized room names.
2. **Ground-truth verification** — Each claim is checked against the `GameTimeline`. Location claims require >= 50% tick presence; sighting claims require co-location at any tick; activity claims check for matching task/movement events.
3. **Metric computation** — Aggregates verdicts into truthfulness, deception, and detection rates.

| Metric | Description |
|--------|-------------|
| Goose truthfulness | Fraction of goose verifiable claims that are true |
| Spatial hallucination rate | Fraction of goose claims that are false (VLM confabulation) |
| Duck deception rate | Fraction of duck verifiable claims that are false |
| Deception sophistication | Among duck lies, fraction that are near-misses (briefly visited the room) |
| Accusation accuracy | Fraction of accusations targeting an actual Duck |
| Lie detection rate | Fraction of meetings where duck lied and was subsequently voted for |
| Per-player breakdown | Claim counts and verdicts per player |

### Batch Evaluation

The batch evaluator recursively discovers game logs, groups results by experiment condition, and computes per-condition and overall aggregated metrics (mean +/- std):

```bash
python scripts/evaluate_batch.py game_logs/ --output batch_results.json
```

Results are saved as:
- **Per-game**: `evaluation.json` alongside each `game.jsonl`
- **Per-condition**: `game_logs/evaluation/{condition}.json`
- **Overall**: `game_logs/evaluation/summary.json`

### Programmatic Usage

```python
from quack.evaluation import GameEvaluator, BatchEvaluator

# Single game
evaluator = GameEvaluator()
result = evaluator.evaluate("game_logs/homogeneous/gpt5.2/20260308_143022_seed42/game.jsonl")
print(result.tier1.winner)          # "goose"
print(result.tier2.task_efficiency)  # 0.45

# With Tier 3
result = evaluator.evaluate(
    "game_logs/homogeneous/gpt5.2/20260308_143022_seed42/game.jsonl",
    run_tier3=True,
    llm_api_key="sk-...",
    llm_model="gpt-5.2",
)
print(result.tier3.goose_truthfulness)  # 0.89

# Batch
batch = BatchEvaluator().evaluate_batch("game_logs/")
print(batch.aggregated["tier1"]["task_completion_rate"])  # {"mean": 0.14, "std": 0.24, "n": 21}
```

---

## Project Architecture

```
QUACK/
├── quack/
│   ├── engine/
│   │   ├── game_engine.py     # Main game loop, phase management, action dispatch
│   │   ├── game_state.py      # Core data structures (Player, GameState, Body, etc.)
│   │   └── event_bus.py       # Pub/sub event system
│   ├── map/
│   │   ├── game_map.py        # Discrete graph-based map with weighted corridors
│   │   └── pathfinding.py     # Dijkstra shortest path
│   ├── roles/
│   │   ├── base_role.py       # Abstract role with abilities
│   │   ├── goose.py           # Goose role (crew)
│   │   └── duck.py            # Duck role (impostor)
│   ├── systems/
│   │   ├── vision.py          # Same-room visibility, corridor vision
│   │   ├── task.py            # Task assignment and progress
│   │   ├── kill.py            # Kill mechanics and cooldowns
│   │   ├── meeting.py         # Body reports and emergency meetings
│   │   └── voting.py          # Vote tallying and ejection
│   ├── agents/
│   │   ├── base_agent.py      # Abstract agent interface
│   │   ├── vlm_agent.py       # VLM agent (OpenAI SDK, multi-model, streaming, memory)
│   │   ├── prompt_builder.py  # System prompts with role-specific strategy guides
│   │   └── memory.py          # Per-agent structured memory system
│   ├── evaluation/
│   │   ├── log_parser.py              # Parse JSONL logs into structured event lists
│   │   ├── game_reconstructor.py      # Tick-by-tick state reconstruction (GameTimeline)
│   │   ├── tier1_game_metrics.py      # Game-level metrics (outcomes, tasks, kills, meetings)
│   │   ├── tier2_behavioral.py        # Behavioral metrics (spatial, voting, task efficiency)
│   │   ├── tier3_statement_verification.py  # LLM claim extraction + ground-truth verification
│   │   ├── evaluator.py              # Orchestrator (GameEvaluator, BatchEvaluator)
│   │   └── report.py                 # Human-readable + JSON report generation
│   ├── rendering/
│   │   ├── map_renderer.py    # Global, local, god view + meeting frame renderer
│   │   ├── sprites.py         # Procedural pixel-art character sprites
│   │   ├── room_decor.py      # Themed pixel-art room decorations
│   │   └── colors.py          # Color palette and constants
│   └── utils/
│       ├── config.py          # YAML config loader
│       └── logger.py          # Structured JSONL game logger
├── configs/
│   ├── config.yaml            # Hydra main config (defaults + runtime overrides)
│   ├── game/
│   │   └── default.yaml       # Game rules (num_players, max_ticks, tasks, kill, etc.)
│   ├── map/
│   │   └── simple_ship.yaml   # 10-room ship map with weighted corridors
│   ├── model/
│   │   ├── gpt5.2.yaml        # GPT-5.2 (default)
│   │   ├── gpt5.4.yaml        # GPT-5.4
│   │   ├── gemini3.1pro.yaml  # Gemini 3.1 Pro (streaming)
│   │   ├── claude_opus4.6.yaml# Claude Opus 4.6
│   │   ├── grok4.yaml         # Grok 4
│   │   └── kimi2.5.yaml       # Kimi K2.5
│   ├── experiment/
│   │   ├── homogeneous.yaml   # All players same model
│   │   └── heterogeneous.yaml # Different models for geese vs duck
│   └── maps/
│       └── simple_ship.yaml   # Legacy map path (kept for backward compat)
├── scripts/
│   ├── run_game.py            # Hydra CLI entry point (multi-model, auto video)
│   ├── replay_game.py         # Replay game logs and generate renders/video
│   ├── evaluate_game.py       # Evaluate a single game log (all tiers)
│   ├── evaluate_batch.py      # Recursive batch evaluate with per-condition aggregation
│   ├── batch_homogeneous.sh   # Batch runner for homogeneous experiments
│   ├── batch_heterogeneous.sh # Batch runner for cross-model experiments
│   ├── batch_full_experiment.sh # One-command full experiment suite
│   └── generate_videos.sh    # Batch generate video.mp4 from god-view frames
├── tests/
│   └── test_evaluation/       # Unit tests for the evaluation pipeline
├── game_logs/                 # Experiment output (structured by model/condition)
├── api_key.txt                # API key for VLM endpoint (not committed)
├── pyproject.toml
└── README.md
```
