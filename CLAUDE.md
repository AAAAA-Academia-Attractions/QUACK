# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install (editable + dev deps)
pip install -e ".[dev]"

# Run a game with random agents (no API key needed)
python scripts/run_game.py

# Run with specific model and seed
python scripts/run_game.py model=claude_opus4.6 seed=42

# Run heterogeneous experiment
python scripts/run_game.py experiment=heterogeneous model=gpt5.2 experiment.duck_model=claude_opus4.6 seed=42

# Override game rules
python scripts/run_game.py game.max_ticks=100 game.num_ducks=2

# Run all tests
python -m pytest

# Run a single test
python -m pytest tests/test_evaluation/test_tier1.py::TestTier1Metrics::test_winner -v

# Lint
ruff check .

# Replay a game log
python scripts/replay_game.py game_logs/homogeneous/gpt5.2/<timestamp>/game.jsonl --video replay.mp4

# Evaluate a game
python scripts/evaluate_game.py game_logs/homogeneous/gpt5.2/<timestamp>/game.jsonl

# Batch evaluate (with Tier 3)
python scripts/evaluate_batch.py game_logs/ --tier3 --api-key YOUR_KEY

# Batch experiments
./scripts/batch_homogeneous.sh -m gpt5.2 -n 10
./scripts/batch_heterogeneous.sh -g gpt5.2 -d claude_opus4.6 -n 10
./scripts/batch_full_experiment.sh -n 5
```

## Architecture

### High-level structure

QUACK is a **social deduction game engine** (Goose Goose Duck / Among Us-like) designed as a benchmark for Vision-Language Models. The game runs in discrete ticks with Free Roam and Meeting phases.

```
quack/
├── engine/          # Game loop (GameEngine), state (GameState), event bus (EventBus)
├── map/             # Graph-based map (GameMap) with weighted corridors + Dijkstra pathfinding
├── roles/           # Goose (crew) and Duck (impostor) with role-specific abilities
├── systems/         # Composable game systems: vision, task, kill, meeting, voting
├── agents/          # Agent interface + VLM agent (OpenAI SDK, memory, prompt builder)
├── evaluation/      # Tier 1-3 evaluation pipeline (log parser, reconstructor, metrics)
├── rendering/       # Pillow-based pixel-art renderer (global, local, god view, meeting frames)
└── utils/           # Config loader, JSONL logger
```

### Key design patterns

- **Event-driven**: `EventBus` pub/sub decouples systems from the engine. Systems emit events; the logger subscribes to all events for structured JSONL logging.
- **Hook-based systems**: Each game system (kill, meeting, voting, task, vision) is a standalone class injected into `GameEngine`, taking `EventBus` as a dependency.
- **Strategy pattern for roles**: `BaseRole` abstract class; `Goose` and `Duck` override `get_extra_actions()` (e.g., Duck gets `kill()` action).
- **Agent interface**: `BaseAgent` ABC with `choose_action()` / `speak()` / `vote()` / `on_game_start()`. `RandomAgent` for testing without API keys; `VLMAgent` for VLM-powered play.
- **VLM agent pipeline**: Per tick, the engine renders 2 images (global map + local view), builds a text observation, then the agent constructs a multimodal prompt and calls the VLM API.
- **Configuration**: Hydra with composable `configs/` YAML files. Override any nested key via CLI (`game.kill.cooldown_ticks=3`).

### Agent memory system

Each `VLMAgent` has an `AgentMemory` instance tracking tick history, player encounters, meeting speeches, and route descriptions. Memory is serialized into natural language for prompt inclusion. The engine pushes data to all agents' memories during meetings via `hasattr(ag, "memory")` checks.

### Evaluation pipeline

Three-tier evaluation reads JSONL game logs:
1. **Tier 1** — Direct engine metrics (winner, kills, tasks, ejections)
2. **Tier 2** — Behavioral metrics from tick-by-tick `GameTimeline` reconstruction (voting accuracy, task efficiency, spatial coverage, deception metrics)
3. **Tier 3** — LLM-based statement verification: extracts spatial/behavioral claims from meeting speeches and validates against ground-truth timeline

Tests use `build_minimal_game_events()` in `conftest.py` to construct synthetic event logs for unit testing.

### Rendering

Pillow-based with procedural pixel-art sprites. Three view types:
- **Global map**: Full ship layout with fog of war, only shows viewer's position
- **Local view**: Zoomed view of current room with visible players/bodies
- **God view**: Omniscient overhead view with vision halos, action annotations, chat bubbles, event log panel, and per-player POV row. Frames are stitched into MP4 via ffmpeg.

### Adding a new model

Create `configs/model/<name>.yaml` with `name`, `display_name`, `model_id`, `temperature`, `requires_stream`. Run with `python scripts/run_game.py model=<name>`.

### Output structure

```
game_logs/{homogeneous|heterogeneous}/{condition}/{timestamp}_seed{N}/
├── game.jsonl       # Structured event log (JSONL, one event per line)
├── config.yaml      # Frozen Hydra config
├── evaluation.json  # Evaluation results (after running evaluate)
├── renders/god_view/frame_*.png
└── video.mp4        # Auto-generated replay video
```
