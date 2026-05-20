"""Tests for AgentMemory witness fields (departures / arrivals)."""

from __future__ import annotations

from quack.agents.memory import AgentMemory
from quack.agents.prompt_builder import (build_action_prompt,
                                         build_discussion_prompt,
                                         build_vote_prompt)


def test_record_tick_stores_witness_lists() -> None:
    mem = AgentMemory("Alice")
    mem.record_tick(
        tick=4,
        room="medbay",
        action="wait()",
        players_seen=["Bob"],
        bodies_seen=[],
        departures=[{"name": "Bob", "to_room": "electrical", "multi_tick": True}],
        arrivals=[{"name": "Carol", "from_room": "cafeteria"}],
    )

    last = mem.tick_history[-1]
    assert last.departures == [
        {"name": "Bob", "to_room": "electrical", "multi_tick": True}
    ]
    assert last.arrivals == [{"name": "Carol", "from_room": "cafeteria"}]


def test_build_movement_summary_mentions_witnessed_traffic() -> None:
    mem = AgentMemory("Alice")
    mem.record_tick(
        tick=8,
        room="medbay",
        action="do_task()",
        players_seen=["Carol"],
        bodies_seen=[],
        departures=[{"name": "Bob", "to_room": "electrical", "multi_tick": True}],
        arrivals=[{"name": "Carol", "from_room": "cafeteria"}],
    )

    summary = mem.build_movement_summary()
    assert "witnessed" in summary
    assert "Bob -> electrical" in summary
    assert "Carol arrived from cafeteria" in summary


def test_build_witness_summary_chronological_lines() -> None:
    mem = AgentMemory("Alice")
    mem.record_tick(tick=5, room="medbay", action="wait()",
                    players_seen=[], bodies_seen=[],
                    departures=[{"name": "Bob", "to_room": "electrical", "multi_tick": False}])
    mem.record_tick(tick=7, room="medbay", action="wait()",
                    players_seen=[], bodies_seen=[],
                    arrivals=[{"name": "Carol", "from_room": "cafeteria"}])

    text = mem.build_witness_summary()
    assert "T5" in text and "Bob" in text and "left medbay -> electrical" in text
    assert "T7" in text and "Carol entered medbay from cafeteria" in text


def test_build_witness_summary_clears_at_meeting_boundary() -> None:
    mem = AgentMemory("Alice")
    mem.record_tick(tick=3, room="medbay", action="wait()",
                    players_seen=[], bodies_seen=[],
                    departures=[{"name": "Bob", "to_room": "electrical", "multi_tick": False}])
    mem.start_meeting(tick=5, reason="body", dead_players=["Bob"])
    mem.record_vote_result("ejected", "Bob")
    mem.record_tick(tick=7, room="cafeteria", action="wait()",
                    players_seen=[], bodies_seen=[],
                    arrivals=[{"name": "Carol", "from_room": "storage"}])

    text = mem.build_witness_summary()
    # Pre-meeting witness should be excluded; only post-meeting one remains.
    assert "Bob" not in text
    assert "Carol entered cafeteria from storage" in text


def test_action_prompt_includes_movement_block_when_present() -> None:
    obs = {
        "current_room": "medbay",
        "in_transit": False,
        "adjacent_rooms_detail": [{"room": "electrical", "travel_ticks": 1}],
        "visible_players": [],
        "tasks": [],
        "available_actions": ["wait()"],
        "transit_observations": {
            "departures": [
                {"name": "Bob", "to_room": "electrical", "multi_tick": True}
            ],
            "arrivals": [{"name": "Carol", "from_room": "cafeteria"}],
        },
    }
    prompt = build_action_prompt(obs)
    assert "=== MOVEMENT AROUND YOU (this tick) ===" in prompt
    assert "Bob LEFT toward electrical" in prompt
    assert "(multi-tick)" in prompt
    assert "Carol ARRIVED from cafeteria" in prompt


def test_action_prompt_omits_movement_block_when_empty() -> None:
    obs = {
        "current_room": "medbay",
        "in_transit": False,
        "adjacent_rooms_detail": [],
        "visible_players": [],
        "tasks": [],
        "available_actions": ["wait()"],
        "transit_observations": {"departures": [], "arrivals": []},
    }
    prompt = build_action_prompt(obs)
    assert "MOVEMENT AROUND YOU" not in prompt


def test_corridor_co_direction_renders_in_prompt() -> None:
    obs = {
        "current_room": "cafeteria",
        "in_transit": True,
        "moving_to": "medbay",
        "adjacent_rooms_detail": [],
        "visible_players": [
            {"id": "p1", "name": "Bob", "room": "cafeteria",
             "in_transit": True, "moving_to": "medbay", "co_direction": "same"},
            {"id": "p2", "name": "Carol", "room": "medbay",
             "in_transit": True, "moving_to": "cafeteria", "co_direction": "opposite"},
        ],
        "tasks": [],
        "available_actions": ["wait()"],
        "transit_observations": {"departures": [], "arrivals": []},
    }
    prompt = build_action_prompt(obs)
    assert "Bob (corridor, going SAME way as you)" in prompt
    assert "Carol (corridor, going OPPOSITE way from you)" in prompt


def test_discussion_prompt_includes_witness_summary() -> None:
    mem = AgentMemory("Alice")
    mem.record_tick(tick=5, room="medbay", action="wait()",
                    players_seen=[], bodies_seen=[],
                    departures=[{"name": "Bob", "to_room": "electrical", "multi_tick": False}])
    obs = {
        "meeting_reason": "body found",
        "discussion_history": [],
        "dead_players": [],
        "speaker_order": ["Alice"],
        "my_position": 0,
    }
    prompt = build_discussion_prompt(obs, mem)
    assert "Witnessed movements" in prompt
    assert "left medbay -> electrical" in prompt


def test_vote_prompt_includes_witness_summary() -> None:
    mem = AgentMemory("Alice")
    mem.record_tick(tick=5, room="medbay", action="wait()",
                    players_seen=[], bodies_seen=[],
                    departures=[{"name": "Bob", "to_room": "electrical", "multi_tick": False}])
    obs = {
        "discussion_history": [],
        "dead_players": [],
        "votable_players": [{"id": "p1", "name": "Bob"}],
    }
    prompt = build_vote_prompt(obs, mem)
    assert "Your witnessed movements this round" in prompt
    assert "Bob left medbay -> electrical" in prompt
