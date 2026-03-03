"""Replay a game from its log file and generate render frames.

Usage:
    python scripts/replay_game.py game_logs/game_XXXXX.jsonl --output renders/replay/
    python scripts/replay_game.py game_logs/game_XXXXX.jsonl --output renders/replay/ --video replay.mp4

Reads the game log, reconstructs game state tick by tick, and saves
god-view frames + meeting frames that can be assembled into a video.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ggd_ai.engine.game_state import (Body, GamePhase, GameState, Player,
                                      TaskProgress, Team)
from ggd_ai.map.game_map import GameMap
from ggd_ai.rendering.map_renderer import MapRenderer
from ggd_ai.systems.vision import VisionSystem
from ggd_ai.utils.config import load_map_config


def load_events(log_path: str) -> list[dict[str, Any]]:
    events = []
    with open(log_path) as f:
        for line in f:
            line = line.strip()
            if line:
                events.append(json.loads(line))
    return events


def build_initial_state(
    game_started_event: dict[str, Any],
    game_map: GameMap,
) -> tuple[GameState, VisionSystem, dict[str, str]]:
    """Reconstruct the initial game state from the game_started event."""
    data = game_started_event["data"]
    initial = data.get("initial_state", {})

    state = GameState()
    state.phase = GamePhase.FREE_ROAM
    state.current_tick = 0

    player_names: dict[str, str] = {}

    for pid, info in initial.items():
        team = Team.DUCK if info["team"] == "duck" else Team.GOOSE
        tasks = [
            TaskProgress(
                task_name=t["name"],
                room=t["room"],
                ticks_required=t["ticks_required"],
            )
            for t in info.get("tasks", [])
        ]
        player = Player(
            player_id=pid,
            name=info["name"],
            role_name=info["role"],
            team=team,
            is_alive=True,
            current_room=info["room"],
            tasks=tasks,
        )
        player.visited_rooms.add(info["room"])
        state.players[pid] = player
        player_names[pid] = info["name"]

    vision = VisionSystem(game_map=game_map, visibility_range=0, fog_memory_ticks=0)
    for pid in state.players:
        vision.update_visit(pid, state.players[pid].current_room, 0)

    return state, vision, player_names


def apply_event(state: GameState, event: dict[str, Any], event_log: list[str]) -> None:
    """Apply a single event to mutate the game state."""
    et = event["event_type"]
    data = event["data"]
    tick = event.get("tick", 0)

    def _name(pid: str) -> str:
        return state.players[pid].name if pid in state.players else pid

    if et == "tick_start":
        state.current_tick = data.get("tick", tick)
        state.phase = GamePhase.FREE_ROAM
        # Reset per-tick free-roam chat and tick down kill cooldowns
        if hasattr(state, "room_messages"):
            state.room_messages.clear()
        for p in state.alive_players:
            if p.team == Team.DUCK and p.kill_cooldown > 0:
                p.kill_cooldown -= 1

    elif et == "player_moved":
        pid = data["player_id"]
        player = state.players.get(pid)
        if player and player.is_alive:
            ticks_remaining = data.get("ticks_remaining", 0)
            if ticks_remaining > 0:
                player.moving_from = data["from"]
                player.moving_to = data["to"]
                player.move_ticks_remaining = ticks_remaining
            else:
                player.current_room = data["to"]
                player.moving_from = ""
                player.moving_to = ""
                player.move_ticks_remaining = 0
                player.visited_rooms.add(data["to"])
        event_log.append(f"[T{tick}] {_name(pid)} moved {data['from']} -> {data['to']}")

    elif et == "player_killed":
        target = state.players.get(data["target_id"])
        if target:
            target.is_alive = False
            state.bodies.append(Body(
                player_id=data["target_id"],
                room=data["room"],
                killed_at_tick=tick,
            ))
        killer = state.players.get(data["killer_id"])
        if killer:
            killer.kill_cooldown = 3
        event_log.append(f"[T{tick}] {_name(data['killer_id'])} KILLED {_name(data['target_id'])}")

    elif et == "body_reported":
        state.phase = GamePhase.DISCUSSION
        state.meeting_reason = data.get("reason", "Body reported")
        state.discussion_messages = []
        state.discussion_round = 0
        # Cancel transit
        for p in state.alive_players:
            if p.is_in_transit:
                p.moving_from = ""
                p.moving_to = ""
                p.move_ticks_remaining = 0
        event_log.append(f"[T{tick}] BODY REPORTED: {data.get('reason', '')}")

    elif et == "meeting_called":
        state.phase = GamePhase.DISCUSSION
        state.meeting_reason = data.get("reason", "Emergency meeting")
        state.discussion_messages = []
        state.discussion_round = 0
        for p in state.alive_players:
            if p.is_in_transit:
                p.moving_from = ""
                p.moving_to = ""
                p.move_ticks_remaining = 0
        event_log.append(f"[T{tick}] MEETING: {data.get('reason', '')}")

    elif et == "free_roam_chat":
        # Rebuild room_messages so god-view chat bubbles work in replay.
        room = data.get("room", "")
        if hasattr(state, "room_messages") and room:
            msgs = state.room_messages.setdefault(room, [])
            msgs.append({
                "player_id": data.get("player_id", ""),
                "name": data.get("name", ""),
                "room": room,
                "message": data.get("message", ""),
                "tick": tick,
            })
        event_log.append(f"[T{tick}] CHAT in {data.get('room', '?')}: {data.get('name', '')} said \"{data.get('message', '')}\"")

    elif et == "discussion_message":
        state.discussion_messages.append({
            "player_id": data["player_id"],
            "name": _name(data["player_id"]),
            "message": data["message"],
        })

    elif et == "phase_changed":
        phase_str = data.get("phase", "")
        try:
            state.phase = GamePhase(phase_str)
        except ValueError:
            pass
        if phase_str == "voting":
            state.votes = {}

    elif et == "vote_cast":
        state.votes[data["voter"]] = data.get("target")

    elif et == "player_ejected":
        pid = data.get("player_id", "")
        player = state.players.get(pid)
        if player:
            player.is_alive = False
        event_log.append(f"[T{tick}] {data.get('name', pid)} EJECTED ({data.get('role', '')}/{data.get('team', '')})")

        # Post-ejection: clear bodies, respawn is implicit in next events
        state.bodies.clear()

    elif et == "vote_skipped":
        state.bodies.clear()
        event_log.append(f"[T{tick}] Vote skipped")

    elif et == "task_completed":
        pid = data.get("player_id", "")
        player = state.players.get(pid)
        if player:
            for t in player.tasks:
                if t.task_name == data.get("task_name") and not t.is_complete:
                    t.ticks_done = t.ticks_required
                    break
        event_log.append(f"[T{tick}] {_name(pid)} completed '{data.get('task_name', '')}'")

    elif et == "task_progress":
        pid = data.get("player_id", "")
        player = state.players.get(pid)
        if player:
            for t in player.tasks:
                if t.task_name == data.get("task_name") and not t.is_complete:
                    t.ticks_done = data.get("ticks_done", t.ticks_done)
                    break

    elif et == "game_over":
        state.phase = GamePhase.GAME_OVER
        winner_str = data.get("winner", "")
        if winner_str == "goose":
            state.winner = Team.GOOSE
        elif winner_str == "duck":
            state.winner = Team.DUCK
        state.win_reason = data.get("reason", "")
        event_log.append(f"[T{tick}] GAME OVER — {winner_str}: {state.win_reason}")


def advance_in_transit(state: GameState) -> None:
    """Tick down in-transit players."""
    for player in state.alive_players:
        if not player.is_in_transit:
            continue
        player.move_ticks_remaining -= 1
        if player.move_ticks_remaining <= 0:
            player.current_room = player.moving_to
            player.visited_rooms.add(player.moving_to)
            player.moving_from = ""
            player.moving_to = ""
            player.move_ticks_remaining = 0


def replay(
    log_path: str,
    output_dir: str,
    video_path: str | None = None,
) -> None:
    events = load_events(log_path)
    if not events:
        print("No events in log file.")
        return

    # Find game_started event
    start_event = None
    for ev in events:
        if ev["event_type"] == "game_started":
            start_event = ev
            break

    if start_event is None:
        print("No game_started event found.")
        return

    initial_data = start_event["data"]
    config_info = initial_data.get("config", {})
    map_path = config_info.get("map", "configs/maps/simple_ship.yaml")

    if not initial_data.get("initial_state"):
        print("ERROR: This log was generated before the replay feature.")
        print("The game_started event is missing 'initial_state' data.")
        print("Please re-run the game to generate a new log with full state.")
        return

    map_config = load_map_config(map_path)
    game_map = GameMap.from_config(map_config)

    state, vision, player_names = build_initial_state(start_event, game_map)
    renderer = MapRenderer(game_map)
    renderer.assign_player_colors(list(state.players.keys()))
    renderer.set_player_names(player_names)

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    event_log: list[str] = []
    frame_counter = 0

    def save_frame(img: object) -> None:
        nonlocal frame_counter
        frame_counter += 1
        if img and hasattr(img, "save"):
            img.save(out / f"frame_{frame_counter:04d}.png")

    print(f"Replaying {len(events)} events from {log_path}")
    print(f"Players: {list(player_names.values())}")
    print(f"Output: {output_dir}")
    print("-" * 60)

    last_tick = -1
    discussion_rendered_count = 0

    for ev in events:
        et = ev["event_type"]
        tick = ev.get("tick", 0)

        apply_event(state, ev, event_log)

        # Render god view after each tick_end
        if et == "tick_end":
            god_img = renderer.render_god_view(
                state=state,
                vision_system=vision,
                event_log=event_log,
                tick=tick,
            )
            save_frame(god_img)
            last_tick = tick

        # Render meeting called frame
        if et in ("body_reported", "meeting_called"):
            meeting_img = renderer.render_meeting_called(
                state,
                state.meeting_reason or "",
                tick,
            )
            save_frame(meeting_img)
            discussion_rendered_count = 0

        # Render each speech
        if et == "discussion_message":
            discussion_rendered_count += 1
            speech_img = renderer.render_speech(
                state,
                ev["data"]["player_id"],
                ev["data"]["message"],
                state.discussion_messages,
                tick,
            )
            save_frame(speech_img)

        # Render vote result after all votes are in and ejection/skip happens
        if et in ("player_ejected", "vote_skipped"):
            ejected_id = None
            if et == "player_ejected":
                ejected_id = ev["data"].get("player_id")
            vote_img = renderer.render_vote_result(
                state,
                state.votes,
                ejected_id,
                tick,
            )
            save_frame(vote_img)

    print("-" * 60)
    print(f"Replay complete. Generated {frame_counter} frames in {output_dir}")

    if video_path:
        _make_video(output_dir, video_path)


def _make_video(frames_dir: str, output_path: str, fps: int = 2) -> None:
    """Assemble frames into a video using ffmpeg."""
    pattern = str(Path(frames_dir) / "frame_%04d.png")
    cmd = [
        "ffmpeg", "-y",
        "-framerate", str(fps),
        "-i", pattern,
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2",
        output_path,
    ]
    print(f"Creating video: {output_path}")
    try:
        subprocess.run(cmd, check=True, capture_output=True)
        print(f"Video saved to {output_path}")
    except FileNotFoundError:
        print("ffmpeg not found. Install ffmpeg to generate videos.")
    except subprocess.CalledProcessError as e:
        print(f"ffmpeg failed: {e.stderr.decode()[:500]}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Replay a game log and generate render frames / video",
    )
    parser.add_argument(
        "log_path",
        help="Path to the game log JSONL file",
    )
    parser.add_argument(
        "--output", "-o",
        default="renders/replay",
        help="Output directory for rendered frames (default: renders/replay/)",
    )
    parser.add_argument(
        "--video", "-v",
        default=None,
        help="If provided, assemble frames into a video at this path (e.g. replay.mp4)",
    )
    parser.add_argument(
        "--fps",
        type=int,
        default=2,
        help="Frames per second for the video (default: 2)",
    )
    args = parser.parse_args()

    replay(args.log_path, args.output, args.video)


if __name__ == "__main__":
    main()
