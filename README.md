# QUACK: Questioning, Understanding, and Assessing Collaborative Knowledge

### A Multimodal Social Deduction Benchmark for Vision-Language Models

Social deduction games are compelling testbeds for evaluating agents' theory of mind, deception, and social reasoning. Yet most existing benchmarks are *text-only*, preventing grounded verification of agents' claims against their actual behavior in partially observed environments.

**QUACK** is the first *multimodal* social deduction benchmark designed for Vision-Language Models, built on a fully open-source engine for multimodal social deduction research. Agents navigate configurable graph-based map layouts with weighted corridors, operate under strict partial observability with same-room visibility, complete multi-tick location-bound tasks, and participate in emergency meetings with multi-round free-form discussion and voting. Each decision step provides a global map view, a local perceptual view, and structured textual state, requiring grounded multimodal reasoning over long-horizon episodes.

Beyond environment design, QUACK introduces a structured evaluation protocol that measures task performance, social coordination, adversarial robustness, and behavioral linguistic consistency. We develop an automatic Statement Verification Pipeline that extracts spatial and behavioral claims from meeting utterances and validates them against engine-level ground-truth logs, enabling scalable auditing of deception, belief consistency, and action-speech alignment under partial observability.

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

### Run a Game (Random Agents)

```bash
# Basic game with random agents
python scripts/run_game.py

# With a fixed seed for reproducibility
python scripts/run_game.py --seed 42

# Save god-view frames (omniscient observer)
python scripts/run_game.py --god-view --seed 42

# Save per-player rendered images each tick
python scripts/run_game.py --save-renders --seed 42
```

### Run a Game (VLM Agents)

```bash
# Create api_key.txt with your API key first
echo "sk-your-key-here" > api_key.txt

# Run with VLM agents (gpt-5.2 via OpenAI-compatible endpoint)
python scripts/run_game.py --vlm --god-view --seed 42

# VLM agents with Simplified Chinese speech (简体中文)
python scripts/run_game.py --vlm --chinese --god-view --seed 42

# Test Chinese font rendering (check renders/test_chinese*.png)
python scripts/test_chinese_font.py

# Custom model and endpoint
python scripts/run_game.py --vlm --model gpt-5.2 --base-url https://endpoint.greatrouter.com
```

### Replay a Game Log

```bash
# Regenerate render frames from a saved game log
python scripts/replay_game.py game_logs/game_XXXXX.jsonl --output renders/replay/

# Generate frames + assemble into video
python scripts/replay_game.py game_logs/game_XXXXX.jsonl -o renders/replay/ --video replay.mp4 --fps 3
```

### Evaluate a Game

```bash
# Evaluate a single game log (Tier 1 + Tier 2)
python scripts/evaluate_game.py game_logs/game_XXXXX.jsonl

# Save results as JSON
python scripts/evaluate_game.py game_logs/game_XXXXX.jsonl --output results.json

# Include Tier 3 statement verification (requires LLM API key)
python scripts/evaluate_game.py game_logs/game_XXXXX.jsonl --tier3 --api-key YOUR_KEY

# Batch evaluate all logs in a directory
python scripts/evaluate_batch.py game_logs/ --output batch_results.json
```

### CLI Options

#### `run_game.py`

| Flag | Description |
|------|-------------|
| `--config PATH` | Path to game config YAML (default: `configs/default_game.yaml`) |
| `--render` | Enable rendering pipeline (images sent to VLM agents, not saved) |
| `--save-renders` | Save per-player global + local view images to `renders/` |
| `--god-view` | Save god-view frames to `renders/god_view/` |
| `--vlm` | Use VLM agents instead of random agents |
| `--chinese` | Agent speeches in Simplified Chinese (简体中文); requires CJK font for rendering |
| `--api-key KEY` | API key for VLM (auto-reads from `api_key.txt` if not provided) |
| `--base-url URL` | Base URL for VLM API endpoint |
| `--model NAME` | Model name for VLM agents (default: `gpt-5.2`) |
| `--seed N` | Fixed random seed for reproducible games |

#### `replay_game.py`

| Flag | Description |
|------|-------------|
| `log_path` | Path to game log JSONL file (positional argument) |
| `--output`, `-o` | Output directory for frames (default: `renders/replay/`) |
| `--video`, `-v` | Output video path (e.g. `replay.mp4`); requires ffmpeg |
| `--fps` | Frames per second for video (default: 2) |

#### `evaluate_game.py`

| Flag | Description |
|------|-------------|
| `log_path` | Path to game log JSONL file (positional argument) |
| `--tier3` | Run Tier 3 statement verification (requires LLM API key) |
| `--api-key KEY` | API key for Tier 3 LLM (auto-reads from `api_key.txt` if not provided) |
| `--base-url URL` | Base URL for the LLM API endpoint |
| `--model NAME` | LLM model for claim extraction (default: `gpt-4o-mini`) |
| `--map-config PATH` | Path to map config YAML (default: `configs/maps/simple_ship.yaml`) |
| `--output`, `-o` | Save results as JSON to this path |
| `--verbose`, `-v` | Enable verbose logging |

#### `evaluate_batch.py`

| Flag | Description |
|------|-------------|
| `log_dir` | Directory containing game log JSONL files (positional argument) |
| `--tier3` | Run Tier 3 statement verification (requires LLM API key) |
| `--api-key KEY` | API key for Tier 3 LLM |
| `--base-url URL` | Base URL for the LLM API endpoint |
| `--model NAME` | LLM model for claim extraction (default: `gpt-4o-mini`) |
| `--map-config PATH` | Path to map config YAML |
| `--output`, `-o` | Save aggregated results as JSON to this path |
| `--verbose`, `-v` | Enable verbose logging |

---

## Understanding the Game

### Roles

- **Goose (鹅)** — Crew members. Complete tasks to win. Can report bodies and call emergency meetings.
- **Duck (鸭)** — Impostors. Kill Geese to gain voting majority. Blend in by pretending to do tasks. Can report bodies strategically.

### Win Conditions

| Team | How to Win |
|------|-----------|
| Goose | Complete all tasks **OR** eject all Ducks via voting |
| Duck | Kill enough Geese to reach voting majority (Ducks ≥ Geese alive) |
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
- **Weighted corridors**: Moving between rooms takes a variable number of ticks (1–3). Agents must plan routes efficiently.
- **Random spawns**: Players start in random rooms and are re-randomized after each meeting.
- **Emergency bell limit**: The total number of emergency meetings (bell pulls) per game equals the number of Ducks. Body reports are unlimited.
- **Kill cooldown**: Ducks must wait a cooldown (default: 3 ticks) between kills, with an initial delay (default: 5 ticks) before the first kill.
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

Each VLM agent (powered by gpt-5.2 via OpenAI-compatible API) has:

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
- **Meeting frames** (1280×720) — dedicated frames for meeting calls, speeches, and vote results:
  - Two-panel layout: past speeches on left, current speaker's full message on right (readable fonts)
  - **Actual body locations** banner during discussion — shows the truth so you can see if the reporter (e.g. a Duck) is lying
- **Free-roam chat bubbles** — when players use `say(...)` during Free Roam, their latest message in that tick is rendered as a small text bubble under their character.

### Viewing as Video

```bash
# Stitch god-view frames into video
ffmpeg -framerate 3 -i renders/god_view/frame_%04d.png -c:v libx264 -pix_fmt yuv420p \
  -vf "pad=ceil(iw/2)*2:ceil(ih/2)*2" god_view.mp4

# Or use the replay script (handles frame generation + video in one step)
python scripts/replay_game.py game_logs/game_XXXXX.jsonl --video replay.mp4 --fps 3
```

---

## Game Logs

Every game run saves a structured JSONL log to `game_logs/`.

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

## Configuration

### Game Settings (`configs/default_game.yaml`)

```yaml
game:
  num_players: 6
  num_ducks: 1
  max_ticks: 200
  map: configs/maps/simple_ship.yaml

tasks:
  ticks_per_task: 3       # ticks to complete each task
  tasks_per_player: 3     # tasks assigned to each Goose

kill:
  cooldown_ticks: 3       # ticks between Duck kills
  initial_cooldown: 5     # ticks before first kill allowed

meeting:
  max_discussion_rounds: 2  # each player speaks up to 2 times per meeting

vision:
  visibility_range: 0     # 0 = current room only
  fog_memory_ticks: 0     # 0 = instantaneous vision, no memory
```

### Map Definition (`configs/maps/simple_ship.yaml`)

```yaml
rooms:
  cafeteria:
    x: 7
    y: 1
    size: 3
  medbay:
    x: 5
    y: 5
    size: 2

corridors:
  - [cafeteria, medbay, 1]         # weight = 1 tick
  - [cafeteria, engine_room, 3]    # weight = 3 ticks

task_locations:
  - room: medbay
    name: "Submit Scan"

emergency_button: cafeteria
```

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
2. **Ground-truth verification** — Each claim is checked against the `GameTimeline`. Location claims require ≥50% tick presence; sighting claims require co-location at any tick; activity claims check for matching task/movement events.
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

### Example Output

```
=== QUACK Evaluation: game_1772940357 ===

TIER 1 — Game-Level Metrics
  Winner: Duck (Ducks have voting majority)
  Duration: 194 ticks
  Tasks completed: 9/25 (36.0%)
  Kills: 4 (first kill at tick 8)
  Meetings: 2 (1 body reports, 1 emergency)
  Ejections: 0 correct, 0 wrong, 2 skipped

TIER 2 — Behavioral Metrics
  Goose voting accuracy: 50.0%
  Goose skip rate: 66.7%
  Task efficiency: 37.6%
  Avg rooms visited (goose): 7.0
  Post-kill displacement: avg 0.8 rooms
  Self-report rate: 2 (50.0%)
  Cooldown utilization: 100.0%

TIER 3 — Statement Verification
  Claims extracted: 47 (38 verifiable)
  Goose truthfulness: 89.3% (spatial hallucination: 10.7%)
  Duck truthfulness: 42.9% (deception rate: 57.1%)
  Deception sophistication: 75.0% (near-miss alibis)
  Accusation accuracy: 33.3%
```

### Batch Evaluation

The batch evaluator processes all `.jsonl` logs in a directory and aggregates metrics with mean ± std:

```bash
python scripts/evaluate_batch.py game_logs/ --output batch_results.json
```

Both single-game and batch results are saved as structured JSON for downstream analysis.

### Programmatic Usage

```python
from quack.evaluation import GameEvaluator, BatchEvaluator

# Single game
evaluator = GameEvaluator()
result = evaluator.evaluate("game_logs/game_XXXXX.jsonl")
print(result.tier1.winner)          # "goose"
print(result.tier2.task_efficiency)  # 0.45

# With Tier 3
result = evaluator.evaluate(
    "game_logs/game_XXXXX.jsonl",
    run_tier3=True,
    llm_api_key="sk-...",
    llm_model="gpt-4o-mini",
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
│   │   ├── vlm_agent.py       # VLM agent (OpenAI SDK, gpt-5.2, memory, rate limiting)
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
│   ├── default_game.yaml      # Default game settings
│   └── maps/
│       └── simple_ship.yaml   # 10-room ship map with weighted corridors
├── scripts/
│   ├── run_game.py            # CLI entry point (random or VLM agents)
│   ├── replay_game.py         # Replay game logs and generate renders/video
│   ├── evaluate_game.py       # Evaluate a single game log (all tiers)
│   └── evaluate_batch.py      # Batch evaluate all logs in a directory
├── tests/
│   └── test_evaluation/       # Unit tests for the evaluation pipeline
├── api_key.txt                # API key for VLM endpoint (not committed)
├── pyproject.toml
└── README.md
```
