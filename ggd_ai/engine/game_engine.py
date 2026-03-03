"""Main game loop orchestrating Free Roam and Meeting phases."""

from __future__ import annotations

import logging
import random
from typing import TYPE_CHECKING, Any

from ggd_ai.engine.event_bus import EventBus, EventType, GameEvent
from ggd_ai.engine.game_state import GamePhase, GameState, Player, Team
from ggd_ai.map.game_map import GameMap
from ggd_ai.rendering.map_renderer import MapRenderer
from ggd_ai.roles.base_role import BaseRole
from ggd_ai.roles.duck import Duck
from ggd_ai.roles.goose import Goose
from ggd_ai.systems.kill import KillSystem
from ggd_ai.systems.meeting import MeetingSystem
from ggd_ai.systems.task import TaskSystem
from ggd_ai.systems.vision import VisionSystem
from ggd_ai.systems.voting import VotingSystem
from ggd_ai.utils.config import load_game_config, load_map_config

if TYPE_CHECKING:
    from ggd_ai.agents.base_agent import BaseAgent

logger = logging.getLogger(__name__)


class GameEngine:
    """Orchestrates the full game lifecycle.

    Usage:
        engine = GameEngine.from_config("configs/default_game.yaml")
        engine.register_agents(agents)
        result = await engine.run()
    """

    def __init__(
        self,
        game_map: GameMap,
        config: dict[str, Any],
    ):
        self.game_map = game_map
        self.config = config
        self.event_bus = EventBus()
        self.state = GameState()
        self.agents: dict[str, BaseAgent] = {}
        self.roles: dict[str, BaseRole] = {}

        game_cfg = config.get("game", {})
        task_cfg = config.get("tasks", {})
        kill_cfg = config.get("kill", {})
        meeting_cfg = config.get("meeting", {})
        vision_cfg = config.get("vision", {})

        self.state.max_ticks = game_cfg.get("max_ticks", 200)
        self.state.max_discussion_rounds = meeting_cfg.get("max_discussion_rounds", 2)
        self._num_players = game_cfg.get("num_players", 6)
        self._num_ducks = game_cfg.get("num_ducks", 1)

        self.vision_system = VisionSystem(
            game_map=game_map,
            visibility_range=vision_cfg.get("visibility_range", 1),
            fog_memory_ticks=vision_cfg.get("fog_memory_ticks", 20),
        )
        self.task_system = TaskSystem(
            game_map=game_map,
            event_bus=self.event_bus,
            ticks_per_task=task_cfg.get("ticks_per_task", 3),
            tasks_per_player=task_cfg.get("tasks_per_player", 3),
        )
        self.kill_system = KillSystem(
            event_bus=self.event_bus,
            cooldown_ticks=kill_cfg.get("cooldown_ticks", 10),
            initial_cooldown=kill_cfg.get("initial_cooldown", 15),
        )
        self.meeting_system = MeetingSystem(
            event_bus=self.event_bus,
            game_map=game_map,
            max_discussion_rounds=meeting_cfg.get("max_discussion_rounds", 2),
        )
        self.voting_system = VotingSystem(event_bus=self.event_bus)

        self.renderer: MapRenderer | None = None
        self._event_log: list[str] = []

    def enable_rendering(self) -> None:
        """Create and configure the map renderer."""
        self.renderer = MapRenderer(self.game_map)

    @property
    def event_log(self) -> list[str]:
        return self._event_log

    @classmethod
    def from_config(cls, config_path: str) -> GameEngine:
        config = load_game_config(config_path)
        map_path = config.get("game", {}).get("map", "configs/maps/simple_ship.yaml")
        map_config = load_map_config(map_path)
        game_map = GameMap.from_config(map_config)
        return cls(game_map=game_map, config=config)

    def register_agents(self, agents: dict[str, BaseAgent]) -> None:
        self.agents = agents

    def _pick_random_rooms(self, n: int, rooms: list[str]) -> list[str]:
        """Pick n rooms, spreading players across different rooms as much as possible."""
        if n <= len(rooms):
            return random.sample(rooms, n)
        result = list(rooms) * (n // len(rooms)) + random.sample(rooms, n % len(rooms))
        random.shuffle(result)
        return result

    # ---- Game Setup ----

    async def setup_game(self) -> None:
        player_ids = list(self.agents.keys())
        if len(player_ids) < self._num_players:
            raise ValueError(
                f"Need {self._num_players} agents, got {len(player_ids)}"
            )
        player_ids = player_ids[: self._num_players]

        duck_ids = set(random.sample(player_ids, self._num_ducks))

        all_rooms = self.game_map.room_names
        spawn_rooms = self._pick_random_rooms(len(player_ids), all_rooms)

        for i, pid in enumerate(player_ids):
            is_duck = pid in duck_ids
            role = Duck() if is_duck else Goose()
            self.roles[pid] = role

            spawn = spawn_rooms[i]
            player = Player(
                player_id=pid,
                name=self.agents[pid].name,
                role_name=role.name,
                team=role.team,
                is_alive=True,
                current_room=spawn,
                emergency_meetings_left=1,
            )
            player.visited_rooms.add(spawn)
            self.state.players[pid] = player

        # Global emergency meeting pool: total bells = number of ducks
        self.state.emergency_meetings_remaining = self._num_ducks

        self.task_system.assign_tasks(self.state)
        self.kill_system.initialize_cooldowns(self.state)

        for pid in player_ids:
            room = self.state.players[pid].current_room
            self.vision_system.update_visit(pid, room, 0)

        if self.renderer:
            self.renderer.assign_player_colors(player_ids)
            self.renderer.set_player_names(
                {pid: self.state.players[pid].name for pid in player_ids}
            )

        self.event_bus.subscribe_all(self._build_event_log_entry)

        self.state.phase = GamePhase.FREE_ROAM
        self.state.current_tick = 0

        # Notify all agents of their role and team composition
        total_geese = sum(1 for pid in player_ids if pid not in duck_ids)
        total_ducks = len(duck_ids)
        all_player_names = [self.state.players[pid].name for pid in player_ids]
        duck_names_by_id = {pid: self.state.players[pid].name for pid in duck_ids}

        for pid in player_ids:
            role = self.roles[pid]
            agent = self.agents[pid]

            teammates: list[str] | None = None
            if pid in duck_ids:
                teammates = [
                    name for did, name in duck_names_by_id.items() if did != pid
                ]

            await agent.on_game_start(
                role_name=role.name,
                team=role.team.value,
                objective=role.objective,
                total_geese=total_geese,
                total_ducks=total_ducks,
                teammates=teammates,
                all_players=all_player_names,
            )
            logger.info(
                "Agent %s assigned role %s (team: %s)",
                agent.name, role.name, role.team.value,
            )

        self.event_bus.emit(GameEvent(
            event_type=EventType.GAME_STARTED,
            data={
                "players": all_player_names,
                "config": {
                    "num_players": self._num_players,
                    "num_ducks": self._num_ducks,
                    "map": self.config.get("game", {}).get("map", "configs/maps/simple_ship.yaml"),
                },
                "initial_state": {
                    pid: {
                        "name": p.name,
                        "role": p.role_name,
                        "team": p.team.value,
                        "room": p.current_room,
                        "tasks": [
                            {"name": t.task_name, "room": t.room, "ticks_required": t.ticks_required}
                            for t in p.tasks
                        ],
                    }
                    for pid, p in self.state.players.items()
                },
            },
            tick=0,
        ))

    # ---- Main Loop ----

    async def run(self) -> dict[str, Any]:
        await self.setup_game()

        while self.state.phase != GamePhase.GAME_OVER:
            if self.state.phase == GamePhase.FREE_ROAM:
                await self._run_free_roam_tick()
            elif self.state.phase == GamePhase.DISCUSSION:
                await self._run_discussion()
            elif self.state.phase == GamePhase.VOTING:
                await self._run_voting()
            elif self.state.phase == GamePhase.EJECTION:
                self._post_ejection()

            self._check_win_conditions()

        self.event_bus.emit(GameEvent(
            event_type=EventType.GAME_OVER,
            data={
                "winner": self.state.winner.value if self.state.winner else None,
                "reason": self.state.win_reason,
            },
            tick=self.state.current_tick,
        ))

        return {
            "winner": self.state.winner.value if self.state.winner else None,
            "reason": self.state.win_reason,
            "ticks": self.state.current_tick,
            "state": self.state.to_dict(),
        }

    # ---- Free Roam ----

    async def _run_free_roam_tick(self) -> None:
        self.state.current_tick += 1
        # Reset per-tick free-roam chat messages.
        self.state.room_messages.clear()
        self.event_bus.emit(GameEvent(
            event_type=EventType.TICK_START,
            data={"tick": self.state.current_tick},
            tick=self.state.current_tick,
        ))

        self.kill_system.tick_cooldowns(self.state)

        # Advance in-transit players first
        self._advance_transit()

        action_order = list(self.state.alive_player_ids)
        random.shuffle(action_order)

        for pid in action_order:
            if self.state.phase != GamePhase.FREE_ROAM:
                break

            player = self.state.players[pid]
            if player.is_in_transit:
                if self.renderer:
                    self.renderer.last_actions[pid] = (
                        f"traveling -> {player.moving_to} ({player.move_ticks_remaining}t)"
                    )
                continue

            agent = self.agents[pid]

            self._render_for_player(player)

            observation = self.vision_system.build_observation(
                player, self.state, self.game_map,
            )
            available_actions = self._get_available_actions(player)
            observation["available_actions"] = available_actions

            raw_action = await agent.choose_action(observation, self.state.phase.value)

            # Parse optional free-roam chat: \"action | say(message)\".
            room_before = player.current_room
            say_message = ""
            action_str = raw_action
            if isinstance(raw_action, str):
                parts = raw_action.split("|", 1)
                action_str = parts[0].strip() or "wait()"
                if len(parts) > 1:
                    suffix = parts[1].strip()
                    lower = suffix.lower()
                    if lower.startswith("say(") and suffix.endswith(")"):
                        say_message = suffix[4:-1].strip()

            self._execute_action(player, action_str)

            # Record chat in the origin room so only players who were there can hear it.
            if say_message:
                msgs = self.state.room_messages.setdefault(room_before, [])
                entry = {
                    "player_id": player.player_id,
                    "name": player.name,
                    "room": room_before,
                    "message": say_message,
                    "tick": self.state.current_tick,
                }
                msgs.append(entry)
                self.event_bus.emit(GameEvent(
                    event_type=EventType.FREE_ROAM_CHAT,
                    data=entry,
                    tick=self.state.current_tick,
                ))

            if self.renderer:
                self.renderer.last_actions[pid] = action_str

        if self.state.phase == GamePhase.FREE_ROAM:
            self.event_bus.emit(GameEvent(
                event_type=EventType.TICK_END,
                data={"tick": self.state.current_tick},
                tick=self.state.current_tick,
            ))

            if self.state.current_tick >= self.state.max_ticks:
                self.state.phase = GamePhase.GAME_OVER
                self.state.winner = Team.GOOSE
                self.state.win_reason = "Time ran out — Geese survived"

    def _render_for_player(self, player: Player) -> None:
        """If rendering is enabled and the agent is a VLMAgent, render and attach images."""
        if not self.renderer:
            return
        agent = self.agents.get(player.player_id)
        if agent is None:
            return

        vis = self.vision_system.compute_visibility(player, self.state)

        # Global map: show ALL rooms (map layout), but NO other players.
        # Only the viewer's position and their own task markers are visible.
        all_rooms = set(self.game_map.room_names)
        global_img = self.renderer.render_global_map(
            state=self.state,
            revealed_rooms=all_rooms,
            viewer_room=player.current_room,
            visible_players=[],
            visible_bodies=[],
            viewer_id=player.player_id,
            tick=self.state.current_tick,
        )

        # Local view: only shows players/bodies in visible rooms
        local_img = self.renderer.render_local_view(
            state=self.state,
            player=player,
            visible_rooms=vis.visible_rooms,
            visible_players=vis.visible_players,
            visible_bodies=vis.visible_bodies,
        )

        if hasattr(agent, "set_images"):
            agent.set_images(global_map=global_img, local_view=local_img)

    def _get_available_actions(self, player: Player) -> list[str]:
        if player.is_in_transit:
            return [f"traveling -> {player.moving_to} ({player.move_ticks_remaining}t left)"]

        actions = ["wait()"]

        neighbors = self.game_map.get_neighbors(player.current_room)
        for n in neighbors:
            w = self.game_map.get_corridor_weight(player.current_room, n)
            if w > 1:
                actions.append(f"move({n})  # {w} ticks travel time")
            else:
                actions.append(f"move({n})")

        if player.get_current_task() is not None:
            task = player.get_current_task()
            actions.append(f"do_task()  # {task.task_name} [{task.ticks_done}/{task.ticks_required}]")

        if self.meeting_system.can_report_body(player, self.state):
            actions.append("report()")
        if self.meeting_system.can_call_emergency(player, self.state):
            actions.append("call_meeting()")

        role = self.roles.get(player.player_id)
        if role:
            actions.extend(role.get_extra_actions(player, self.state))

        return actions

    def _execute_action(self, player: Player, action: str) -> None:
        action = action.strip()

        if action.startswith("move("):
            target_room = action.split("(")[1].rstrip(")")
            self._do_move(player, target_room)
        elif action.startswith("do_task"):
            self.task_system.do_task(player, self.state)
        elif action.startswith("kill("):
            target_id = action.split("(")[1].rstrip(")")
            self.kill_system.execute_kill(player, target_id, self.state)
        elif action.startswith("report"):
            self.meeting_system.report_body(player, self.state)
        elif action.startswith("call_meeting"):
            self.meeting_system.call_emergency(player, self.state)
        # "wait()" or anything unrecognized => do nothing

    def _do_move(self, player: Player, target_room: str) -> None:
        if not self.game_map.are_adjacent(player.current_room, target_room):
            return
        weight = self.game_map.get_corridor_weight(player.current_room, target_room)
        if weight <= 1:
            # Instant move
            old_room = player.current_room
            player.current_room = target_room
            player.visited_rooms.add(target_room)
            self.vision_system.update_visit(
                player.player_id, target_room, self.state.current_tick,
            )
            self.event_bus.emit(GameEvent(
                event_type=EventType.PLAYER_MOVED,
                data={
                    "player_id": player.player_id,
                    "from": old_room,
                    "to": target_room,
                },
                tick=self.state.current_tick,
            ))
        else:
            # Multi-tick travel
            player.moving_from = player.current_room
            player.moving_to = target_room
            player.move_ticks_remaining = weight - 1  # 1 tick used this turn
            self.event_bus.emit(GameEvent(
                event_type=EventType.PLAYER_MOVED,
                data={
                    "player_id": player.player_id,
                    "from": player.current_room,
                    "to": target_room,
                    "ticks_remaining": player.move_ticks_remaining,
                },
                tick=self.state.current_tick,
            ))

    def _advance_transit(self) -> None:
        """Tick down in-transit players and complete arrival."""
        for player in self.state.alive_players:
            if not player.is_in_transit:
                continue
            player.move_ticks_remaining -= 1
            if player.move_ticks_remaining <= 0:
                player.current_room = player.moving_to
                player.visited_rooms.add(player.moving_to)
                self.vision_system.update_visit(
                    player.player_id, player.moving_to, self.state.current_tick,
                )
                player.moving_from = ""
                player.moving_to = ""
                player.move_ticks_remaining = 0

    # ---- Discussion ----

    async def _run_discussion(self) -> None:
        speaker_id = self.meeting_system.get_current_speaker(self.state)
        if speaker_id is None:
            self.voting_system.start_voting(self.state)
            return

        agent = self.agents[speaker_id]
        player = self.state.players[speaker_id]
        self._render_for_player(player)

        # On the first speaker, notify all VLM agents that a meeting started
        if self.state.current_speaker_idx == 0 and self.state.discussion_round == 0:
            dead_names = [d["name"] for d in self.state.dead_player_names]
            for pid, ag in self.agents.items():
                if hasattr(ag, "memory"):
                    ag.memory.start_meeting(
                        tick=self.state.current_tick,
                        reason=self.state.meeting_reason or "Unknown",
                        dead_players=dead_names,
                    )

        observation = self.vision_system.build_observation(
            player, self.state, self.game_map,
        )
        observation["meeting_reason"] = self.state.meeting_reason
        observation["discussion_history"] = self.state.discussion_messages
        observation["discussion_round"] = self.state.discussion_round
        observation["you_are_speaking"] = True
        observation["dead_players"] = [d["name"] for d in self.state.dead_player_names]

        speaker_order = self.state.discussion_order
        speaker_names = [
            self.state.players[sid].name
            for sid in speaker_order
            if sid in self.state.players
        ]
        observation["speaker_order"] = speaker_names
        observation["my_position"] = self.state.current_speaker_idx

        if (self.state.current_speaker_idx == 0 and self.state.discussion_round == 0
                and speaker_id == self.state.meeting_caller and self.state.bodies):
            observation["you_are_reporter"] = True
            room_to_victims: dict[str, list[str]] = {}
            for b in self.state.bodies:
                name = self.state.players[b.player_id].name
                room_to_victims.setdefault(b.room, []).append(name)
            observation["body_info"] = [
                {"room": room, "victims": names}
                for room, names in room_to_victims.items()
            ]
        else:
            observation["you_are_reporter"] = False
            observation["body_info"] = []

        message = await agent.speak(observation)
        self.meeting_system.add_discussion_message(speaker_id, message, self.state)

        # Record speech in all agents' memories
        speaker_name = player.name
        for pid, ag in self.agents.items():
            if hasattr(ag, "memory"):
                ag.memory.record_speech(speaker_name, message)

        next_speaker = self.meeting_system.advance_speaker(self.state)
        if next_speaker is None:
            self.voting_system.start_voting(self.state)

    # ---- Voting ----

    async def _run_voting(self) -> None:
        for pid in self.state.alive_player_ids:
            agent = self.agents[pid]
            player = self.state.players[pid]
            self._render_for_player(player)

            observation = self.vision_system.build_observation(
                player, self.state, self.game_map,
            )
            observation["discussion_history"] = self.state.discussion_messages
            observation["dead_players"] = [d["name"] for d in self.state.dead_player_names]
            observation["votable_players"] = [
                {"id": p.player_id, "name": p.name}
                for p in self.state.alive_players
                if p.player_id != pid
            ]

            vote_target = await agent.vote(observation)
            self.voting_system.cast_vote(pid, vote_target, self.state)

        ejection_result = self.voting_system.execute_ejection(self.state)

        # Record vote result in all agents' memories
        ejected_name = ""
        if ejection_result and ejection_result.get("ejected"):
            ej_pid = ejection_result["ejected"]
            if ej_pid in self.state.players:
                ejected_name = self.state.players[ej_pid].name
        result_str = ejection_result.get("summary", "No one ejected") if ejection_result else "No one ejected"
        for pid, ag in self.agents.items():
            if hasattr(ag, "memory"):
                ag.memory.record_vote_result(result_str, ejected_name)

    # ---- Post-Ejection ----

    def _post_ejection(self) -> None:
        self._check_win_conditions()
        if self.state.phase != GamePhase.GAME_OVER:
            # Clear all bodies from the map
            self.state.bodies.clear()

            # Randomize alive players to different rooms
            alive = self.state.alive_players
            all_rooms = self.game_map.room_names
            new_rooms = self._pick_random_rooms(len(alive), all_rooms)
            for player, room in zip(alive, new_rooms):
                player.current_room = room
                player.moving_from = ""
                player.moving_to = ""
                player.move_ticks_remaining = 0
                player.visited_rooms.add(room)
                self.vision_system.update_visit(
                    player.player_id, room, self.state.current_tick,
                )

            self.state.phase = GamePhase.FREE_ROAM
            self.event_bus.emit(GameEvent(
                event_type=EventType.PHASE_CHANGED,
                data={"phase": GamePhase.FREE_ROAM.value},
                tick=self.state.current_tick,
            ))

    # ---- Win Conditions ----

    def _check_win_conditions(self) -> None:
        if self.state.phase == GamePhase.GAME_OVER:
            return

        if self.state.alive_duck_count == 0:
            self.state.phase = GamePhase.GAME_OVER
            self.state.winner = Team.GOOSE
            self.state.win_reason = "All Ducks have been ejected"
            return

        if self.state.alive_duck_count >= self.state.alive_goose_count:
            self.state.phase = GamePhase.GAME_OVER
            self.state.winner = Team.DUCK
            self.state.win_reason = "Ducks have voting majority"
            return

        if self.state.all_goose_tasks_complete:
            self.state.phase = GamePhase.GAME_OVER
            self.state.winner = Team.GOOSE
            self.state.win_reason = "All Goose tasks completed"
            return

    # ---- Event Log ----

    def _build_event_log_entry(self, event: GameEvent) -> None:
        """Convert game events into human-readable log lines."""
        d = event.data
        t = event.event_type

        def _name(pid: str) -> str:
            return self.state.players[pid].name if pid in self.state.players else pid

        if t == EventType.PLAYER_MOVED:
            self._event_log.append(
                f"[T{event.tick}] {_name(d['player_id'])} moved {d['from']} -> {d['to']}")
        elif t == EventType.PLAYER_KILLED:
            self._event_log.append(
                f"[T{event.tick}] {_name(d['killer_id'])} KILLED {_name(d['target_id'])} in {d['room']}")
        elif t == EventType.BODY_REPORTED:
            self._event_log.append(f"[T{event.tick}] BODY REPORTED: {d['reason']}")
        elif t == EventType.MEETING_CALLED:
            self._event_log.append(f"[T{event.tick}] MEETING: {d['reason']}")
        elif t == EventType.TASK_COMPLETED:
            self._event_log.append(
                f"[T{event.tick}] {_name(d['player_id'])} completed '{d['task_name']}'")
        elif t == EventType.FREE_ROAM_CHAT:
            self._event_log.append(
                f"[T{event.tick}] CHAT in {d.get('room', '?')}: {_name(d.get('player_id', ''))} said \"{d.get('message', '')}\""
            )
        elif t == EventType.PLAYER_EJECTED:
            self._event_log.append(
                f"[T{event.tick}] {d['name']} EJECTED ({d['role']}/{d['team']})")
        elif t == EventType.VOTE_SKIPPED:
            self._event_log.append(f"[T{event.tick}] Vote skipped ({d['reason']})")
        elif t == EventType.GAME_OVER:
            winner = d.get('winner', '?')
            self._event_log.append(f"[T{event.tick}] GAME OVER — {winner} wins: {d.get('reason', '')}")

    # ---- God View ----

    def render_god_view(self) -> Any:
        """Render the god-view image (PIL.Image.Image) if renderer is enabled."""
        if not self.renderer:
            return None
        return self.renderer.render_god_view(
            state=self.state,
            vision_system=self.vision_system,
            event_log=self._event_log,
            tick=self.state.current_tick,
        )
