# GGD-AI: VLM Multi-Agent Social Deduction Environment

A modular, extensible **Goose Goose Duck (鹅鸭杀)** multi-agent environment designed to benchmark **Vision-Language Model (VLM)** reasoning capabilities. Unlike Werewolf/Mafia-based benchmarks that only test LLM text reasoning, GGD-AI adds **spatial reasoning** through visual map observations, making it a more comprehensive test of VLM abilities.

## Why This Project?

Most existing social deduction agent benchmarks (Werewolf, Mafia, Avalon) are text-only — agents read and write natural language. This limits testing to LLM capabilities alone.

GGD-AI introduces a **spatial dimension**: agents navigate a discrete map, have limited local vision with fog of war, and receive rendered map images as input. This means VLM agents must:

1. **Read and interpret visual maps** — understand room layouts, player positions, task markers
2. **Reason spatially** — plan movement, track where other players were seen
3. **Deduce socially** — identify impostors through discussion and voting
4. **Act strategically** — balance task completion with survival and information gathering

---

## Quick Start

### Installation

```bash
# Clone and enter the project
cd GGD-AI

# Create a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install the package (editable mode with dev tools)
pip install -e ".[dev]"
```

### Run a Game

```bash
# Basic game with random agents (text output only)
python scripts/run_game.py

# With a fixed seed for reproducibility
python scripts/run_game.py --seed 42

# Save per-player rendered map images (global + local view per tick)
python scripts/run_game.py --save-renders --seed 42

# Save god-view renders (omniscient observer, all players visible)
python scripts/run_game.py --god-view --seed 42

# Everything at once
python scripts/run_game.py --save-renders --god-view --seed 42
```

### CLI Options

| Flag | Description |
|------|-------------|
| `--config PATH` | Path to game config YAML (default: `configs/default_game.yaml`) |
| `--render` | Enable rendering pipeline (images sent to VLM agents, not saved to disk) |
| `--save-renders` | Save per-player global + local view images to `renders/` |
| `--god-view` | Save god-view frames to `renders/god_view/` |
| `--seed N` | Fixed random seed for reproducible games |

---

## Understanding the Game

### Roles

- **Goose (鹅)** — Crew members. Complete tasks to win. Can report bodies and call emergency meetings.
- **Duck (鸭)** — Impostors. Kill Geese to gain voting majority. Blend in by pretending to do tasks.

### Win Conditions

| Team | How to Win |
|------|-----------|
| Goose | Complete all tasks **OR** eject all Ducks via voting |
| Duck | Kill enough Geese to reach voting majority (Ducks ≥ Geese alive) |
| Either | If max ticks reached, Geese win by default |

### Game Phases

```
FREE_ROAM ──→ MEETING_CALLED ──→ DISCUSSION ──→ VOTING ──→ EJECTION ──→ FREE_ROAM
    │                                                                        │
    └─── (body report or emergency bell) ──→ ────────────────────────────────┘
    │
    └─── (win condition met) ──→ GAME_OVER
```

1. **Free Roam** — Each tick, every alive player chooses an action:
   - `move(room_name)` — walk to an adjacent room
   - `do_task()` — work on a task in the current room (takes multiple ticks)
   - `report_body()` — report a dead body (triggers meeting)
   - `call_meeting()` — press the emergency button (only in cafeteria)
   - `kill(target_id)` — *Duck only* — kill a player in the same room
   - `wait()` — do nothing

2. **Discussion** — All alive players speak in turn (multiple rounds). Communication is natural language.

3. **Voting** — Each player votes to eject someone or skips. Majority wins; ties skip.

4. **Ejection** — The ejected player is eliminated. Their role is revealed. Game resumes.

### Map

The game uses a **discrete graph-based map** — rooms connected by corridors. Players can only move to adjacent rooms (one hop per tick).

Default map (`configs/maps/simple_ship.yaml`):

```
              cafeteria (emergency button)
             /     |     \
      engine_room  medbay  electrical
             \     |     /
              navigation
```

Each room can have **task locations** where Geese perform tasks. Tasks require staying in the room for a set number of ticks.

---

## Rendering & Visualization

GGD-AI renders three types of images, all using **pixel-art style character sprites**:

### 1. Per-Player Global Map (fog of war)

Each agent sees a global map with:
- **Fog of war** — unvisited/far rooms are dimmed; recently visited rooms stay revealed for a configurable number of ticks
- **Visible players** shown as pixel sprites in the rooms they occupy
- **Task markers** (T = incomplete, V = complete) on rooms with tasks
- **Body markers** — dead sprite where a body was found
- **HUD** — current tick, phase, task progress, alive count
- **Legend** — player color reference

Saved to: `renders/tick{NNN}_{player_id}_global.png`

### 2. Per-Player Local View (zoomed)

A zoomed-in view centered on the player's current room and immediate neighbors. Same info as the global map but at 2x scale for better detail. Useful for VLM agents to see fine details in their immediate area.

Saved to: `renders/tick{NNN}_{player_id}_local.png`

### 3. God View (omniscient observer)

An **all-seeing** overhead view designed for human observers and debugging:
- **No fog of war** — all rooms and corridors visible
- **All players** shown with pixel sprites, regardless of visibility
- **Vision halos** — semi-transparent colored overlay showing each player's current vision range
- **Role labels** — Goose (green) / Duck (red) shown below each character
- **Action annotations** — the last action each player took, color-coded:
  - Gray: movement
  - Green: task progress
  - Red: kill
- **Right panel** with:
  - **Player roster** — name, role, current room, alive/dead status
  - **Event log** — scrolling timeline of all game events, color-coded by type

Saved to: `renders/god_view/god_tick{NNN}.png`

### Viewing Renders as an Animation

After a game run with `--god-view` or `--save-renders`, you can stitch the frames into a video or GIF to watch the game unfold:

```bash
# Using ffmpeg to create an MP4 from god-view frames
ffmpeg -framerate 4 -i renders/god_view/frame_%04d.png -c:v libx264 -pix_fmt yuv420p god_view.mp4

# Or create an animated GIF
ffmpeg -framerate 3 -i renders/god_view/frame_%04d.png -vf "scale=1024:-1" god_view.gif

# Browse frames manually
eog renders/god_view/   # GNOME image viewer
feh renders/god_view/   # lightweight viewer (← → to navigate)
```

---

## Game Logs

Every game run automatically saves a structured JSONL log file to `game_logs/`.

### Log Format

Each line is a JSON object:

```json
{"timestamp": 1772148671.23, "event_type": "player_moved", "tick": 5, "data": {"player_id": "player_0", "from": "cafeteria", "to": "medbay"}}
{"timestamp": 1772148671.45, "event_type": "player_killed", "tick": 22, "data": {"killer_id": "player_5", "target_id": "player_3", "room": "engine_room"}}
{"timestamp": 1772148671.67, "event_type": "task_completed", "tick": 18, "data": {"player_id": "player_2", "task_name": "Calibrate Distributor", "room": "electrical"}}
```

### Event Types

| Event | Key Data Fields |
|-------|----------------|
| `game_started` | `players` list |
| `tick_start` / `tick_end` | `tick` number |
| `player_moved` | `player_id`, `from`, `to` |
| `player_killed` | `killer_id`, `target_id`, `room` |
| `body_reported` | `reporter_id`, `body_id`, `room`, `reason` |
| `meeting_called` | `caller_id`, `reason` |
| `discussion_message` | `player_id`, `message` |
| `vote_cast` | `voter_id`, `target_id` |
| `player_ejected` | `player_id`, `name`, `role`, `team` |
| `vote_skipped` | `reason` |
| `task_progress` | `player_id`, `task_name`, `ticks_done` |
| `task_completed` | `player_id`, `task_name`, `room` |
| `phase_changed` | `from`, `to` |
| `game_over` | `winner`, `reason` |

### Analyzing Logs

```python
import json

with open("game_logs/game_1772148671.jsonl") as f:
    events = [json.loads(line) for line in f]

# Filter for kills
kills = [e for e in events if e["event_type"] == "player_killed"]
for k in kills:
    print(f"Tick {k['tick']}: {k['data']['killer_id']} killed {k['data']['target_id']} in {k['data']['room']}")

# Get all discussion messages
messages = [e for e in events if e["event_type"] == "discussion_message"]
for m in messages:
    print(f"  {m['data']['player_id']}: {m['data']['message']}")

# Game outcome
game_over = [e for e in events if e["event_type"] == "game_over"][0]
print(f"Winner: {game_over['data']['winner']} — {game_over['data']['reason']}")
```

---

## Configuration

### Game Settings (`configs/default_game.yaml`)

```yaml
game:
  num_players: 6          # total players
  num_ducks: 1            # number of impostors
  max_ticks: 200          # max ticks before forced game over
  start_room: cafeteria   # where everyone starts
  map: configs/maps/simple_ship.yaml

tasks:
  ticks_per_task: 3       # ticks needed to complete each task
  tasks_per_player: 3     # tasks assigned to each Goose

kill:
  cooldown_ticks: 10      # ticks between Duck kills
  initial_cooldown: 15    # ticks before first kill allowed

meeting:
  max_discussion_rounds: 2
  emergency_meetings_per_player: 1

vision:
  visibility_range: 1     # rooms within N graph hops are visible
  fog_memory_ticks: 20    # how long a room stays revealed after visiting
```

### Map Definition (`configs/maps/simple_ship.yaml`)

Maps are defined as room graphs with coordinates for rendering:

```yaml
rooms:
  cafeteria:
    x: 5      # grid position for rendering
    y: 1
    size: 3   # visual size of the room
  engine_room:
    x: 1
    y: 5
    size: 2

corridors:
  - [cafeteria, engine_room]
  - [cafeteria, medbay]

task_locations:
  - room: engine_room
    name: "Fix Wiring"

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
│   │   └── event_bus.py       # Pub/sub event system for decoupled communication
│   ├── map/
│   │   ├── game_map.py        # Discrete graph-based map (rooms + corridors)
│   │   └── pathfinding.py     # BFS shortest path utilities
│   ├── roles/
│   │   ├── base_role.py       # Abstract role with abilities interface
│   │   ├── goose.py           # Goose role (crew)
│   │   └── duck.py            # Duck role (impostor)
│   ├── systems/
│   │   ├── vision.py          # Fog of war, local visibility computation
│   │   ├── task.py            # Task assignment and tick-based progress
│   │   ├── kill.py            # Kill mechanics and cooldowns
│   │   ├── meeting.py         # Body reports and emergency meetings
│   │   └── voting.py          # Vote tallying and ejection
│   ├── agents/
│   │   ├── base_agent.py      # Abstract agent interface
│   │   ├── vlm_agent.py       # VLM agent using LiteLLM (Phase 3)
│   │   └── prompt_builder.py  # Prompt construction for VLM agents
│   ├── rendering/
│   │   ├── map_renderer.py    # Pillow-based renderer (global, local, god view)
│   │   ├── sprites.py         # Procedural pixel-art character generator
│   │   └── colors.py          # Color palette and size constants
│   └── utils/
│       ├── config.py          # YAML config loader
│       └── logger.py          # Structured JSONL game logger
├── configs/
│   ├── default_game.yaml      # Default game settings
│   └── maps/
│       └── simple_ship.yaml   # 5-room ship map
├── scripts/
│   └── run_game.py            # CLI entry point with RandomAgent for testing
├── pyproject.toml
└── README.md
```

### Key Design Principles

- **Event-driven** — All game actions emit events via the `EventBus`. Systems, loggers, and renderers subscribe independently. Adding new tracking or analysis requires zero changes to game logic.
- **Agent-agnostic** — The `BaseAgent` interface (`choose_action`, `speak`, `vote`) works with any backend: random, rule-based, LLM, or VLM.
- **Configurable** — Game parameters, map layout, and vision settings are all externalized in YAML.
- **Extensible roles** — New roles (e.g., Vulture, Dodo, Pelican) are added by subclassing `BaseRole` with custom abilities.

---

## Current Status

| Phase | Status | Description |
|-------|--------|-------------|
| Phase 1: Core Engine | Done | Game loop, state machine, events, roles, all game systems |
| Phase 2: Rendering | Done | Pixel-art sprites, global/local/god-view renders |
| Phase 3: VLM Agent | Next | Integrate real VLM models as agent brains via LiteLLM |
