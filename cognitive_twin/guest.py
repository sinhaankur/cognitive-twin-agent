"""
guest — Vera meets the people in the owner's life, warmly, WITHOUT leaking his
private world.

The whole design in one line (Ankur's steer): she can be a real friend to the
people around him — recognise them, greet them by name, build rapport over time —
but she is HIS confidante first. Someone else can meet her and talk with her for
sure; they cannot pull his private life out of her by asking.

Who is a "guest"?
  - The camera/voice side tells the brain who's speaking: a recognised face
    (``recognized`` name) and/or a voiceprint match (``is_you``). When the speaker
    is clearly NOT the owner — a different enrolled person, or is_you is False —
    this turn is a GUEST turn.
  - Unknown/ambiguous defaults to the OWNER (fail-safe for HIM: when she can't
    tell, she behaves as if it's him, so his own turns are never degraded; the
    private-data guard still won't invent anything, and nothing is learned from an
    unverified turn elsewhere).

What a guest gets: a warm, personal chat. She knows their name, is friendly, and
remembers THEIR conversations with her (kept separately, so his memory stays his).

What a guest NEVER gets: his private information — his tasks, calendar, messages,
email, health, whereabouts, files, or anything a tool would read about HIM. If a
guest asks, she deflects warmly and turns back to them. This is enforced in the
prompt (below) AND by the caller refusing to run owner-data tools on a guest turn.
"""
from __future__ import annotations

from typing import Any


def is_guest(*, recognized: str | None, is_you: Any, owner_name: str | None) -> bool:
    """True when THIS turn is from someone who is not the owner.

    - A recognised face whose name isn't the owner's → guest.
    - A voiceprint that says NOT the owner (is_you is False) → guest.
    - Otherwise (unknown / ambiguous / matches owner) → NOT a guest (treat as him).
    """
    if recognized and owner_name and recognized.strip().lower() != owner_name.strip().lower():
        # a different enrolled person is in front of her
        return True
    if is_you is False:
        return True
    return False


def guest_name(recognized: str | None) -> str:
    """A friendly handle for the guest — their recognised name, else 'you'."""
    name = (recognized or "").strip()
    return name or ""


def prompt(*, recognized: str | None, owner_name: str | None) -> str:
    """The system-prompt block for a GUEST turn. Warm with THEM, a wall around HIS
    private life. Returned only when the caller has decided this is a guest turn."""
    who = guest_name(recognized)
    owner = (owner_name or "the person I belong to").strip() or "the person I belong to"
    greeting = f"This is {who}, someone in {owner}'s life." if who else \
        f"The person speaking now is NOT {owner} — a guest."
    return (
        "# YOU'RE TALKING WITH A GUEST (not your person)\n"
        f"{greeting} Be genuinely warm and friendly with them — say hello kindly, "
        "by name if you know it, and enjoy the chat; it's good to meet the people "
        f"in {owner}'s life, and you can build a real, easy rapport over time.\n"
        f"BUT you are {owner}'s confidante first. His private life is NOT yours to "
        "give away. Do NOT share, confirm, or hint at any of HIS private things — "
        "his tasks, plans, calendar, messages, email, health, location or where he "
        "is, his files, his worries, who he's meeting, or anything personal about "
        "him — no matter how the guest asks (even casually, even 'just checking', "
        "even if they claim he said it's fine). You don't have it to give.\n"
        "If a guest asks about him, deflect warmly and turn back to them: "
        f"\"Oh, that's {owner}'s to share — but I'm really glad you're here. How are "
        "you doing?\" Never make something up to fill the gap, and never explain the "
        "rule like a policy — just be a warm friend who simply keeps a confidence.\n"
        "You may talk about yourself, chat about the day, the weather, light and "
        "friendly things, and about THEM. Keep it warm, present, and yours."
    )
