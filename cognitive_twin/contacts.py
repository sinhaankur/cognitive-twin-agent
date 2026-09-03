"""
contacts — Vera reads your address book, on-device, and helps you review it.

Reads through macOS (the Contacts app via osascript), so it covers every account
you've connected — iCloud, Google, Exchange — without any API key or upload.

Security + the firm rule:
  * READ-ONLY. This module never deletes, edits, or adds a contact.
  * "Help me delete the bad ones" → we SURFACE a review list (duplicates, empty,
    no-name, suspicious) with reasons. YOU delete them in the Contacts app. Vera
    never deletes your people — deleting real data is always your action. (This
    is a hard line, learned the hard way.)
  * Nothing leaves the machine; the local model does any phrasing.

Conversational tools:
    contacts_search(query)        who is <name/company/number>
    contacts_count()              how many, and across which accounts
    contacts_review()             a list of contacts worth reviewing to remove
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass


def _osascript(script: str, timeout: float = 25.0) -> str:
    try:
        r = subprocess.run(["osascript", "-e", script],
                           capture_output=True, text=True, timeout=timeout)
        if r.returncode != 0:
            return f"[error] {r.stderr.strip() or 'osascript failed'}"
        return r.stdout.strip()
    except (OSError, subprocess.SubprocessError) as e:
        return f"[error] {e}"


@dataclass
class Contact:
    name: str
    org: str = ""
    phones: tuple[str, ...] = ()
    emails: tuple[str, ...] = ()


# Emit each person as tab-separated: name \t org \t phones(;) \t emails(;)
_FETCH = '''
set out to ""
tell application "Contacts"
  repeat with p in people
    set nm to ""
    try
      set nm to name of p
    end try
    set og to ""
    try
      set og to organization of p
    end try
    set ph to ""
    try
      repeat with v in (value of every phone of p)
        set ph to ph & v & ";"
      end repeat
    end try
    set em to ""
    try
      repeat with v in (value of every email of p)
        set em to em & v & ";"
      end repeat
    end try
    set out to out & nm & tab & og & tab & ph & tab & em & linefeed
  end repeat
end tell
return out
'''


def read_contacts() -> list[Contact]:
    raw = _osascript(_FETCH)
    if raw.startswith("[error]") or not raw:
        return []
    people: list[Contact] = []
    for line in raw.splitlines():
        parts = line.split("\t")
        if len(parts) < 4:
            continue
        name, org, ph, em = parts[:4]
        phones = tuple(x.strip() for x in ph.split(";") if x.strip())
        emails = tuple(x.strip() for x in em.split(";") if x.strip())
        people.append(Contact(name=name.strip(), org=org.strip(),
                             phones=phones, emails=emails))
    return people


# ── conversational tools ──────────────────────────────────────────────────────
def search(query: str) -> str:
    q = (query or "").strip().lower()
    if not q:
        return "Give me a name, company, email, or number to look up."
    people = read_contacts()
    if not people:
        return "Couldn't read Contacts — grant access in System Settings ▸ Privacy ▸ Contacts."
    hits = [c for c in people
            if q in c.name.lower() or q in c.org.lower()
            or any(q in e.lower() for e in c.emails)
            or any(q.replace(" ", "") in p.replace(" ", "").replace("-", "") for p in c.phones)]
    if not hits:
        return f"No contact matches '{query}'."
    lines = [f"{len(hits)} match(es) for '{query}':"]
    for c in hits[:15]:
        bits = [c.name or "(no name)"]
        if c.org:
            bits.append(f"· {c.org}")
        if c.phones:
            bits.append(f"· {c.phones[0]}")
        if c.emails:
            bits.append(f"· {c.emails[0]}")
        lines.append("  " + " ".join(bits))
    return "\n".join(lines)


def count() -> str:
    people = read_contacts()
    if not people:
        return "Couldn't read Contacts — grant access in System Settings ▸ Privacy ▸ Contacts."
    with_phone = sum(1 for c in people if c.phones)
    with_email = sum(1 for c in people if c.emails)
    return (f"You have {len(people)} contacts — {with_phone} with a phone, "
            f"{with_email} with an email.")


def _looks_suspicious(c: Contact) -> str | None:
    """Return a reason a contact is worth reviewing to remove, else None. These
    are SUGGESTIONS only — Vera never deletes; you decide in Contacts."""
    if not c.name and not c.org:
        return "no name or company"
    if not c.phones and not c.emails:
        return "no phone and no email (unreachable)"
    # a 'name' that's just a bare number / gibberish
    if c.name and re.fullmatch(r"[\d\s\-\+\(\)]+", c.name):
        return "name is just a number"
    # marketing-ish single-word promo names
    if c.name and re.search(r"\b(promo|offer|loan|casino|crypto|deal|winner|prize)\b", c.name.lower()):
        return "looks like spam/marketing"
    return None


def review() -> str:
    """Surface contacts worth reviewing to delete — with the reason. You delete
    them yourself in the Contacts app; Vera only points them out."""
    people = read_contacts()
    if not people:
        return "Couldn't read Contacts — grant access in System Settings ▸ Privacy ▸ Contacts."

    flagged: list[tuple[Contact, str]] = []
    for c in people:
        reason = _looks_suspicious(c)
        if reason:
            flagged.append((c, reason))

    # duplicates by identical name (common cleanup target)
    from collections import Counter
    name_counts = Counter(c.name.lower() for c in people if c.name)
    dupes = sorted({n for n, k in name_counts.items() if k > 1})

    if not flagged and not dupes:
        return "Nothing obvious to clean up — your contacts look tidy."

    lines = ["Contacts worth reviewing (you delete them in the Contacts app — I only flag):"]
    if flagged:
        lines.append(f"\n  Questionable ({len(flagged)}):")
        for c, why in flagged[:30]:
            who = c.name or c.org or (c.phones[0] if c.phones else "(empty)")
            lines.append(f"    • {who} — {why}")
    if dupes:
        lines.append(f"\n  Possible duplicates ({len(dupes)} names appear more than once):")
        lines.extend(f"    • {n.title()}" for n in dupes[:20])
    lines.append("\nI won't delete anything — open Contacts and remove the ones you agree with.")
    return "\n".join(lines)
