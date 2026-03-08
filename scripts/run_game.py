"""Entry point to configure and run a full Goose Goose Duck game."""

from __future__ import annotations

import argparse
import asyncio
import logging
import random
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quack.agents.base_agent import BaseAgent
from quack.engine.game_engine import GameEngine
from quack.utils.logger import GameLogger


class RandomAgent(BaseAgent):
    """Simple random agent for testing the game loop without VLM calls."""

    async def choose_action(self, observation: dict[str, Any], phase: str) -> str:
        actions = observation.get("available_actions", ["wait()"])
        action = random.choice(actions)
        return action.split("#")[0].strip()

    async def speak(self, observation: dict[str, Any]) -> str:
        current_room = observation.get("current_room", "somewhere")
        visible = observation.get("visible_players", [])

        phrases = [
            f"I was in {current_room} doing my tasks.",
            "I didn't see anything suspicious.",
            "I think we should skip this vote.",
            "Has anyone seen anything?",
        ]
        if visible:
            target = random.choice(visible)
            phrases.append(f"I saw {target['name']} acting suspicious near {target['room']}.")

        return random.choice(phrases)

    async def vote(self, observation: dict[str, Any]) -> str | None:
        votable = observation.get("votable_players", [])
        if random.random() < 0.3 or not votable:
            return None
        return random.choice(votable)["id"]


PLAYER_NAMES = [
    "Alice", "Bob", "Charlie", "Diana", "Eve", "Frank",
    "Grace", "Hank", "Ivy", "Jack",
]


def create_random_agents(num_players: int) -> dict[str, BaseAgent]:
    agents: dict[str, BaseAgent] = {}
    for i in range(num_players):
        pid = f"player_{i}"
        name = PLAYER_NAMES[i % len(PLAYER_NAMES)]
        agents[pid] = RandomAgent(player_id=pid, name=name)
    return agents


def create_vlm_agents(
    num_players: int, api_key: str, base_url: str, model: str,
    speak_chinese: bool = False,
) -> dict[str, BaseAgent]:
    from quack.agents.vlm_agent import VLMAgent

    agents: dict[str, BaseAgent] = {}
    for i in range(num_players):
        pid = f"player_{i}"
        name = PLAYER_NAMES[i % len(PLAYER_NAMES)]
        agents[pid] = VLMAgent(
            player_id=pid,
            name=name,
            api_key=api_key,
            base_url=base_url,
            model=model,
            speak_chinese=speak_chinese,
        )
    return agents


async def run_game(
    config_path: str,
    render: bool = False,
    save_renders: bool = False,
    god_view: bool = False,
    seed: int | None = None,
    vlm: bool = False,
    api_key: str = "",
    base_url: str = "https://endpoint.greatrouter.com",
    model: str = "gpt-5.2",
    speak_chinese: bool = False,
) -> None:
    if seed is not None:
        random.seed(seed)

    engine = GameEngine.from_config(config_path)

    game_logger = GameLogger()
    engine.event_bus.subscribe_all(game_logger.handle_event)

    if render:
        engine.enable_rendering()

    num_players = engine.config.get("game", {}).get("num_players", 6)

    if vlm:
        print(f"Creating {num_players} VLM agents (model: {model})...")
        agents = create_vlm_agents(num_players, api_key, base_url, model, speak_chinese)
    else:
        agents = create_random_agents(num_players)

    engine.register_agents(agents)

    # setup_game now handles on_game_start for all agents
    await engine.setup_game()

    print(f"Game started with {num_players} players")
    print(f"Roles: { {pid: f'{p.name} ({p.role_name}/{p.team.value})' for pid, p in engine.state.players.items()} }")
    print(f"Log: {game_logger.log_path}")
    if vlm:
        # Show duck teammates for debugging
        for pid, p in engine.state.players.items():
            if p.team.value == "duck":
                agent = agents[pid]
                if hasattr(agent, "_teammates"):
                    print(f"  Duck {p.name} knows teammates: {agent._teammates}")
    print("-" * 60)

    god_frame_counter = [0]

    def _next_god_frame() -> int:
        god_frame_counter[0] += 1
        return god_frame_counter[0]

    while engine.state.phase.value != "game_over":
        prev_phase = engine.state.phase

        if engine.state.phase.value == "free_roam":
            await engine._run_free_roam_tick()
            if save_renders and engine.renderer:
                _save_renders(engine)
            if god_view and engine.renderer:
                _save_god_view_frame(engine, _next_god_frame())

            if vlm:
                tick = engine.state.current_tick
                if tick % 5 == 0:
                    print(f"  Tick {tick}...")
                # Print any free-roam chat messages spoken this tick
                for msgs in engine.state.room_messages.values():
                    for msg in msgs:
                        if msg.get("tick") == tick:
                            room = msg.get("room", "?")
                            name = msg.get("name", "?")
                            text = msg.get("message", "")
                            print(f"  [CHAT][{room}] {name}: {text}")

        elif engine.state.phase.value == "discussion":
            if (god_view and engine.renderer
                    and engine.state.current_speaker_idx == 0
                    and engine.state.discussion_round == 0
                    and len(engine.state.discussion_messages) == 0):
                meeting_img = engine.renderer.render_meeting_called(
                    engine.state,
                    engine.state.meeting_reason or "",
                    engine.state.current_tick,
                )
                _save_meeting_frame(meeting_img, _next_god_frame())

            await engine._run_discussion()

            if god_view and engine.renderer and engine.state.discussion_messages:
                last_msg = engine.state.discussion_messages[-1]
                speech_img = engine.renderer.render_speech(
                    engine.state,
                    last_msg["player_id"],
                    last_msg["message"],
                    engine.state.discussion_messages,
                    engine.state.current_tick,
                )
                _save_meeting_frame(speech_img, _next_god_frame())

            # Print speech in real-time for VLM games
            if vlm and engine.state.discussion_messages:
                last_msg = engine.state.discussion_messages[-1]
                speaker_name = engine.state.players[last_msg["player_id"]].name
                print(f"  [{speaker_name}]: {last_msg['message']}")

        elif engine.state.phase.value == "voting":
            await engine._run_voting()

            if god_view and engine.renderer:
                ejected_id = None
                for p in engine.state.players.values():
                    if not p.is_alive and any(
                        t == p.player_id for t in engine.state.votes.values()
                    ):
                        ejected_id = p.player_id
                        break
                vote_img = engine.renderer.render_vote_result(
                    engine.state,
                    engine.state.votes,
                    ejected_id,
                    engine.state.current_tick,
                )
                _save_meeting_frame(vote_img, _next_god_frame())

        elif engine.state.phase.value == "ejection":
            engine._post_ejection()

        engine._check_win_conditions()

        if engine.state.phase != prev_phase:
            print(f"  Phase: {prev_phase.value} -> {engine.state.phase.value}")

    print("-" * 60)
    winner = engine.state.winner
    print(f"Game Over! Winner: {winner.value if winner else 'None'}")
    print(f"Reason: {engine.state.win_reason}")
    print(f"Ticks: {engine.state.current_tick}")
    print(f"Log saved to: {game_logger.log_path}")
    print(f"Events recorded: {len(game_logger.get_entries())}")


def _save_god_view_frame(engine: GameEngine, frame_num: int) -> None:
    renders_dir = Path("renders/god_view")
    renders_dir.mkdir(parents=True, exist_ok=True)
    god_img = engine.render_god_view()
    if god_img:
        god_img.save(renders_dir / f"frame_{frame_num:04d}.png")


def _save_meeting_frame(img: object, frame_num: int) -> None:
    renders_dir = Path("renders/god_view")
    renders_dir.mkdir(parents=True, exist_ok=True)
    if img and hasattr(img, "save"):
        img.save(renders_dir / f"frame_{frame_num:04d}.png")


def _save_renders(engine: GameEngine) -> None:
    renders_dir = Path("renders")
    renders_dir.mkdir(exist_ok=True)

    renderer = engine.renderer
    if renderer is None:
        return

    for pid, player in engine.state.players.items():
        if not player.is_alive:
            continue
        vis = engine.vision_system.compute_visibility(player, engine.state)
        fog_revealed = engine.vision_system.get_fog_revealed_rooms(
            pid, engine.state.current_tick,
        )
        all_revealed = fog_revealed | vis.visible_rooms

        global_img = renderer.render_global_map(
            state=engine.state,
            revealed_rooms=all_revealed,
            viewer_room=player.current_room,
            visible_players=vis.visible_players,
            visible_bodies=vis.visible_bodies,
            viewer_id=pid,
            tick=engine.state.current_tick,
        )
        local_img = renderer.render_local_view(
            state=engine.state,
            player=player,
            visible_rooms=vis.visible_rooms,
            visible_players=vis.visible_players,
            visible_bodies=vis.visible_bodies,
        )

        tick = engine.state.current_tick
        global_img.save(renders_dir / f"tick{tick:03d}_{pid}_global.png")
        local_img.save(renders_dir / f"tick{tick:03d}_{pid}_local.png")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a Goose Goose Duck AI game")
    parser.add_argument(
        "--config",
        default="configs/default_game.yaml",
        help="Path to game config YAML",
    )
    parser.add_argument(
        "--render",
        action="store_true",
        help="Enable rendering (images sent to VLM agents)",
    )
    parser.add_argument(
        "--save-renders",
        action="store_true",
        help="Save rendered map images to renders/ directory each tick",
    )
    parser.add_argument(
        "--god-view",
        action="store_true",
        help="Save god-view renders (omniscient observer) to renders/god_view/",
    )
    parser.add_argument(
        "--vlm",
        action="store_true",
        help="Use VLM agents (gpt-5.2) instead of random agents",
    )
    parser.add_argument(
        "--api-key",
        default="",
        help="API key for VLM (reads from api_key.txt if not provided)",
    )
    parser.add_argument(
        "--base-url",
        default="https://endpoint.greatrouter.com",
        help="Base URL for the VLM API endpoint",
    )
    parser.add_argument(
        "--model",
        default="gpt-5.2",
        help="Model name for VLM agents",
    )
    parser.add_argument(
        "--chinese",
        action="store_true",
        help="Make all agent speeches in Chinese (中文)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Random seed for reproducibility",
    )
    args = parser.parse_args()

    # Auto-load API key from api_key.txt if not provided
    api_key = args.api_key
    if args.vlm and not api_key:
        key_path = Path(__file__).resolve().parent.parent / "api_key.txt"
        if key_path.exists():
            api_key = key_path.read_text().strip()
            print(f"Loaded API key from {key_path}")
        else:
            print("ERROR: --vlm requires an API key. Provide --api-key or create api_key.txt")
            sys.exit(1)

    if args.vlm:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        )

    asyncio.run(run_game(
        args.config,
        render=args.render or args.save_renders or args.god_view or args.vlm,
        save_renders=args.save_renders,
        god_view=args.god_view,
        seed=args.seed,
        vlm=args.vlm,
        api_key=api_key,
        base_url=args.base_url,
        model=args.model,
        speak_chinese=args.chinese,
    ))


if __name__ == "__main__":
    main()
