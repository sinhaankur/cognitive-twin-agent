"""Deterministic intent matching: clear commands map to skills; nuanced talk doesn't."""

from __future__ import annotations

from cognitive_twin.agent import intents


AVAIL = {"book_amenity", "check_amenity_availability", "my_day", "list_projects",
         "greeting", "now_playing", "places_today"}


def test_amenity_commands_match():
    assert intents.match("book an amenity for me", AVAIL) == ("book_amenity", {})
    assert intents.match("we have to book amenities", AVAIL) == ("book_amenity", {})


def test_other_clear_commands_match():
    assert intents.match("what is on my day", AVAIL)[0] == "my_day"
    assert intents.match("what am I building", AVAIL)[0] == "list_projects"
    assert intents.match("good morning", AVAIL)[0] == "greeting"


def test_casual_talk_does_not_match():
    # nuanced / emotional / open messages must fall through to the model
    assert intents.match("just chatting about life", AVAIL) is None
    assert intents.match("i feel a bit low today", AVAIL) is None
    assert intents.match("what do you think love means?", AVAIL) is None


def test_unavailable_skill_does_not_fire():
    # if the skill isn't registered, don't claim to match it
    assert intents.match("book an amenity", set()) is None


def test_long_message_falls_through():
    # a long, nuanced message is the model's job, not a keyword grab
    assert intents.match("book an amenity " + "and also " * 40, AVAIL) is None
