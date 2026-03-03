# GGD-AI: VLM Multi-Agent Social Deduction Environment

A modular, extensible **Goose Goose Duck (鹅鸭杀)** multi-agent environment designed to benchmark **Vision-Language Model (VLM)** reasoning capabilities. Unlike Werewolf/Mafia-based benchmarks that only test LLM text reasoning, GGD-AI adds **spatial reasoning** through visual map observations, making it a more comprehensive test of VLM abilities.

## Why This Project?

Most existing social deduction agent benchmarks (Werewolf, Mafia, Avalon) are text-only — agents read and write natural language. This limits testing to LLM capabilities alone.

GGD-AI introduces a **spatial dimension**: agents navigate a discrete map, have limited local vision, and receive rendered map images as input. This means VLM agents must:

1. **Read and interpret visual maps** — understand room layouts, task markers
2. **Reason spatially** — plan movement routes based on weighted corridors, track encounters
3. **Deduce socially** — identify impostors through discussion and voting
4. **Act strategically** — balance task completion with survival and information gathering

---

## Quick Start

### Installation

```bash
cd GGD-AI

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

GGD-AI renders using **pixel-art style character sprites** with themed room interiors.

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

## Project Architecture

```
GGD-AI/
├── ggd_ai/
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
│   └── replay_game.py         # Replay game logs and generate renders/video
├── api_key.txt                # API key for VLM endpoint (not committed)
├── pyproject.toml
└── README.md
```

---

## Current Status

| Phase | Status | Description |
|-------|--------|-------------|
| Phase 1: Core Engine | Done | Game loop, state machine, events, roles, all systems |
| Phase 2: Rendering | Done | Pixel sprites, themed rooms, global/local/god view, meeting frames |
| Phase 3: VLM Agent | Done | gpt-5.2 agents with memory, strategy prompts, rate limiting, Chinese mode |
| Replay System | Done | Reconstruct renders from game logs, video export |
