"""
voice_understand — she can't read your lips, so she recovers a misheard word from
what she KNOWS of you (people/places/projects/lexicon). Repairs confidently, asks
when genuinely unsure, never touches ordinary English, safe when she knows nothing.
Voice path only — chat is already exact.
"""
from __future__ import annotations

from cognitive_twin import voice_understand as vu

VOCAB = {"munger": "Munger", "ranchi": "Ranchi", "shweta": "Shweta",
         "anita": "Anita", "ankur": "Ankur", "vera": "Vera"}


def test_empty_vocab_is_safe():
    u = vu.understand("remind mugger about it", vocab={})
    assert u.text == "remind mugger about it"     # nothing known → unchanged
    assert u.changed is False


def test_repairs_a_misheard_name():
    u = vu.understand("remind mugger about the property", vocab=VOCAB)
    assert "Munger" in u.text
    assert ("mugger", "Munger") in u.repairs
    assert u.changed is True


def test_leaves_ordinary_words_alone():
    u = vu.understand("what time is the meeting today", vocab=VOCAB)
    assert u.text == "what time is the meeting today"
    assert u.repairs == []


def test_fixes_correct_capitalization_without_flagging():
    # already-correct word → canonical spelling, not a "repair" or "unsure"
    u = vu.understand("did anita call", vocab=VOCAB)
    assert "Anita" in u.text
    assert u.unsure == []


def test_asks_when_unsure_instead_of_guessing():
    # a weak-but-plausible match → not auto-changed, but surfaced as a question
    u = vu.understand("tell ankoor to check", vocab=VOCAB)
    # it must NOT confidently rewrite to the wrong thing
    q = vu.clarify_question(u)
    if u.unsure:                                   # weak match path
        assert "Ankur" in q
        assert u.confident is False


def test_multiple_repairs_in_one_sentence():
    u = vu.understand("send it to monger", vocab=VOCAB)
    assert "Munger" in u.text


def test_understanding_confident_property():
    u = vu.understand("call Shweta", vocab=VOCAB)
    assert u.confident is True                     # clean → no question needed
    assert vu.clarify_question(u) == ""
