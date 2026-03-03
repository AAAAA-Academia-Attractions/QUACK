"""VLM-powered agent using OpenAI SDK with gpt-5.2 for Goose Goose Duck."""

from __future__ import annotations

import asyncio
import logging
import re
import time
from typing import Any

from PIL import Image

from ggd_ai.agents.base_agent import BaseAgent
from ggd_ai.agents.memory import AgentMemory
from ggd_ai.agents.prompt_builder import (build_action_prompt,
                                          build_discussion_prompt,
                                          build_system_prompt,
                                          build_vlm_messages,
                                          build_vote_prompt)

logger = logging.getLogger(__name__)

# Suppress noisy retry logs from the OpenAI client
logging.getLogger("openai._base_client").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)


class VLMAgent(BaseAgent):
    """Agent driven by a Vision-Language Model via OpenAI-compatible API.

    Uses the openai SDK pointing at a custom endpoint with gpt-5.2.
    Maintains per-game memory for strategic context.
    A class-level rate limiter ensures minimum spacing between API calls
    across all VLMAgent instances to avoid 429 errors.
    """

    # Shared across all instances to throttle API calls globally
    _last_call_time: float = 0.0
    _min_call_interval: float = 1.0  # minimum seconds between API calls

    def __init__(
        self,
        player_id: str,
        name: str,
        api_key: str,
        base_url: str = "https://endpoint.greatrouter.com",
        model: str = "gpt-5.2",
        temperature: float = 0.7,
        speak_chinese: bool = False,
    ):
        super().__init__(player_id, name)
        self.model = model
        self.temperature = temperature
        self.api_key = api_key
        self.base_url = base_url
        self.speak_chinese = speak_chinese

        self._system_prompt = ""
        self.memory = AgentMemory(name)

        self._global_map_image: Image.Image | None = None
        self._local_view_image: Image.Image | None = None

        self._teammates: list[str] = []
        self._role_name = ""
        self._team = ""

        self._client = None

    def _get_client(self):
        if self._client is None:
            from openai import OpenAI
            self._client = OpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
                max_retries=3,
                timeout=60.0,
            )
        return self._client

    async def on_game_start(
        self,
        role_name: str,
        team: str,
        objective: str,
        *,
        total_geese: int = 0,
        total_ducks: int = 0,
        teammates: list[str] | None = None,
        all_players: list[str] | None = None,
    ) -> None:
        self._role_name = role_name
        self._team = team
        self._teammates = teammates or []
        self._system_prompt = build_system_prompt(
            self.name,
            role_name,
            team,
            objective,
            total_geese=total_geese,
            total_ducks=total_ducks,
            teammates=teammates,
            all_players=all_players,
            speak_chinese=self.speak_chinese,
        )
        self.memory = AgentMemory(self.name)

    def set_images(
        self,
        global_map: Image.Image | None = None,
        local_view: Image.Image | None = None,
    ) -> None:
        self._global_map_image = global_map
        self._local_view_image = local_view

    async def choose_action(self, observation: dict[str, Any], phase: str) -> str:
        self._record_observation(observation)

        user_text = build_action_prompt(observation, self.memory)
        images = self._collect_images()
        messages = build_vlm_messages(self._system_prompt, user_text, images)

        response = await self._call_vlm(messages)
        action = self._parse_action(response, observation.get("available_actions", []))

        self.memory.tick_history[-1].action = action
        logger.info("[%s] action=%s (raw: %s)", self.name, action, response[:100])
        return action

    async def speak(self, observation: dict[str, Any]) -> str:
        user_text = build_discussion_prompt(observation, self.memory)
        images = self._collect_images()
        messages = build_vlm_messages(self._system_prompt, user_text, images)

        response = await self._call_vlm(messages)
        speech = response.strip()

        self.memory.record_my_speech(speech)
        logger.info("[%s] speech: %s", self.name, speech[:200])
        return speech

    async def vote(self, observation: dict[str, Any]) -> str | None:
        user_text = build_vote_prompt(observation, self.memory)
        images = self._collect_images()
        messages = build_vlm_messages(self._system_prompt, user_text, images)

        response = await self._call_vlm(messages)
        result = self._parse_vote(response, observation.get("votable_players", []))
        logger.info("[%s] vote=%s (raw: %s)", self.name, result, response[:100])
        return result

    def _record_observation(self, observation: dict[str, Any]) -> None:
        """Record tick observation into memory."""
        players_seen = [p["name"] for p in observation.get("visible_players", [])]
        bodies_seen = [b["name"] for b in observation.get("visible_bodies", [])]
        self.memory.record_tick(
            tick=observation.get("tick", 0),
            room=observation.get("current_room", "?"),
            action="",
            players_seen=players_seen,
            bodies_seen=bodies_seen,
            in_transit=observation.get("in_transit", False),
            moving_to=observation.get("moving_to", ""),
        )

    def _collect_images(self) -> list[Image.Image]:
        imgs: list[Image.Image] = []
        if self._global_map_image:
            imgs.append(self._global_map_image)
        if self._local_view_image:
            imgs.append(self._local_view_image)
        return imgs

    async def _call_vlm(self, messages: list[dict[str, Any]]) -> str:
        """Call the VLM API with global rate limiting and retry."""
        # Rate limiting: ensure minimum interval between calls across all agents
        now = time.monotonic()
        wait = VLMAgent._min_call_interval - (now - VLMAgent._last_call_time)
        if wait > 0:
            await asyncio.sleep(wait)
        VLMAgent._last_call_time = time.monotonic()

        client = self._get_client()
        oai_messages = self._convert_messages(messages)

        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = client.chat.completions.create(
                    model=self.model,
                    messages=oai_messages,
                    temperature=self.temperature,
                )
                content = response.choices[0].message.content or ""
                return content
            except Exception as e:
                err_str = str(e).lower()
                is_rate_limit = "rate" in err_str or "429" in err_str or "retry" in err_str
                if is_rate_limit and attempt < max_retries - 1:
                    backoff = 2 ** (attempt + 1)
                    logger.warning(
                        "[%s] Rate limited, backing off %ds (attempt %d/%d)",
                        self.name, backoff, attempt + 1, max_retries,
                    )
                    await asyncio.sleep(backoff)
                    VLMAgent._last_call_time = time.monotonic()
                    continue
                logger.exception("[%s] VLM API call failed (attempt %d/%d)", self.name, attempt + 1, max_retries)
                return ""
        return ""

    def _convert_messages(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Convert internal message format to OpenAI SDK format."""
        converted = []
        for msg in messages:
            role = msg["role"]
            content = msg["content"]

            if isinstance(content, str):
                converted.append({"role": role, "content": content})
            elif isinstance(content, list):
                converted.append({"role": role, "content": content})
            else:
                converted.append(msg)
        return converted

    def _parse_action(self, response: str, available_actions: list[str]) -> str:
        """Extract a valid action from VLM response, with intelligent fallback."""
        response_clean = response.strip()

        for action in available_actions:
            action_clean = action.split("#")[0].strip()
            if action_clean in response_clean:
                return action_clean

        response_lower = response_clean.lower()
        for action in available_actions:
            action_clean = action.split("#")[0].strip()
            if action_clean.lower() in response_lower:
                return action_clean

        match = re.search(
            r'(move|do_task|kill|report|call_meeting|wait)\([^)]*\)',
            response_clean,
            re.IGNORECASE,
        )
        if match:
            extracted = match.group(0)
            for action in available_actions:
                action_clean = action.split("#")[0].strip()
                if action_clean.lower() == extracted.lower():
                    return action_clean

        for action in available_actions:
            action_base = action.split("(")[0].strip().lower()
            if action_base in response_lower and action_base != "wait":
                return action.split("#")[0].strip()

        return "wait()"

    def _parse_vote(self, response: str, votable_players: list[dict[str, Any]]) -> str | None:
        response_lower = response.strip().lower()

        if "skip" in response_lower or "abstain" in response_lower:
            return None

        for p in votable_players:
            if p["name"].lower() in response_lower:
                return p["id"]

        for p in votable_players:
            if p["id"].lower() in response_lower:
                return p["id"]

        return None
