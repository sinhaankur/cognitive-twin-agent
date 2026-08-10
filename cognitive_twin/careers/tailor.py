"""
tailor — fit analysis, resume emphasis, and a cover-letter draft. On-device.

Given a parsed posting (jobpost.JobPost) and your resume database, this:
  1. picks the best base resume (resumes.best_for),
  2. scores fit and names the matched strengths + the gaps,
  3. suggests which of your REAL resume lines to lead with (emphasis) — it never
     invents experience; it only reorders/surfaces what you already wrote,
  4. drafts a cover letter grounded in your resume + the posting.

Deterministic by default (works with zero AI). If the careers_ai switch is on and
a local LLM is reachable, it rephrases the summary + cover letter more naturally —
optional polish over the same facts, never a source of new claims.

Human-in-the-loop: everything returns text for YOU to edit and send. Nothing is
submitted anywhere.

CLI (pipe a parsed posting in, or point at a saved posting file):
    python3 -m cognitive_twin.careers.tailor fit    --posting job.txt
    python3 -m cognitive_twin.careers.tailor letter --posting job.txt [--resume NAME]

© Ankur Sinha. Personal use.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from . import jobpost as J
from . import resumes as R


@dataclass
class Fit:
    resume: str
    score: float
    matched: list[str] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)
    emphasis: list[str] = field(default_factory=list)   # your real lines to lead with
    summary: str = ""                                    # tailored summary line
    ranking: list[Any] = field(default_factory=list)


# ── pull the strongest of YOUR real lines for this posting ─────────────────────
def _clean_line(ln: str) -> str:
    """Strip markdown emphasis/bullets/headers so we surface clean prose."""
    ln = ln.strip().lstrip("#").lstrip("•-–*·⋅ ").strip()
    ln = re.sub(r"\*\*(.+?)\*\*", r"\1", ln)     # **bold** → bold
    ln = re.sub(r"\*(.+?)\*", r"\1", ln)          # *italic* → italic
    ln = ln.replace("**", "").strip()             # any stray markers
    return ln


def _resume_lines(text: str) -> list[str]:
    """Substantive achievement lines from a resume — skips titles, headers,
    contact rows, and dividers so emphasis surfaces real accomplishments."""
    out = []
    for raw in text.splitlines():
        ln = _clean_line(raw)
        if not (25 < len(ln) < 240):
            continue
        low = ln.lower()
        # skip section headers / job-title/company/date header rows / contact
        if raw.lstrip().startswith("#"):
            continue
        if "·" in ln and re.search(r"\b(present|20\d\d|jan|feb|mar|apr|may|jun|"
                                   r"jul|aug|sep|oct|nov|dec)\b", low):
            continue  # "Role — Company · Feb 2020 – Present"
        if "@" in ln or re.search(r"\+?\d[\d\-\s]{7,}", ln):
            continue  # contact line
        # keep lines that read like achievements (have a verb-y clause)
        out.append(ln)
    return out


def _score_line(line: str, wanted: set[str]) -> int:
    low = line.lower()
    return sum(1 for w in wanted if w in low)


def emphasis_for(resume_text: str, wanted: set[str], k: int = 5) -> list[str]:
    """Your real resume lines, ranked by how many of the posting's needs they hit.
    Pure surfacing — no rewriting, no invention."""
    lines = _resume_lines(resume_text)
    scored = [(_score_line(ln, wanted), ln) for ln in lines]
    scored = [(s, ln) for s, ln in scored if s > 0]
    scored.sort(key=lambda t: t[0], reverse=True)
    return [ln for _, ln in scored[:k]]


def _tailored_summary(jp: J.JobPost, matched: list[str]) -> str:
    """A one-line, factual positioning statement built from real overlap."""
    role = jp.title or "the role"
    top = ", ".join(matched[:4]) if matched else "the areas you're hiring for"
    who = jp.company or "your team"
    return (f"Designer–engineer targeting {role} at {who} — direct strength in "
            f"{top}, with a track record of shipping these end-to-end.")


def analyze(jp: J.JobPost, resume_name: str | None = None) -> Fit:
    wanted = set(s.lower() for s in jp.skills) | set(J._SKILLS) & set(
        s.lower() for s in (jp.keywords or []))
    wanted = set(s.lower() for s in jp.skills)  # skills are the reliable signal

    if resume_name:
        base = R.get(resume_name)
        info = None
        if base:
            have = base.profile()
            overlap = wanted & have
            info = {"score": len(overlap) / max(1, len(wanted)),
                    "matched": sorted(overlap), "missing": sorted(wanted - have),
                    "ranking": [(base.name, len(overlap) / max(1, len(wanted)))]}
    else:
        base, info = R.best_for(wanted)

    if not base:
        return Fit(resume="", score=0.0, summary=(info or {}).get(
            "note", "No resumes in your database — add one with `resumes add`."))

    fit = Fit(resume=base.name, score=round(info["score"], 2),
              matched=info["matched"], gaps=info["missing"],
              ranking=info.get("ranking", []))
    fit.emphasis = emphasis_for(base.text, wanted)
    fit.summary = _tailored_summary(jp, fit.matched)
    fit = _maybe_ai_polish(fit, jp, base)
    return fit


# ── cover letter (deterministic template, AI-polished if switched on) ──────────
def cover_letter(jp: J.JobPost, fit: Fit, *, your_name: str = "Ankur Sinha") -> str:
    company = jp.company or "your team"
    role = jp.title or "this role"
    strengths = fit.matched[:4]
    strength_line = (", ".join(strengths[:-1]) + f", and {strengths[-1]}"
                     if len(strengths) > 1 else (strengths[0] if strengths else "the work"))
    body_points = "\n".join(f"  • {ln}" for ln in fit.emphasis[:3]) or \
        "  • (add a specific, relevant win from your resume here)"

    letter = f"""Dear {company} team,

I'm writing about {role}. My background lines up closely with what you're after —
particularly {strength_line}.

A few things from my experience that map directly to this role:
{body_points}

I work at the design–engineering seam: I research, design, and prototype in code,
so I can move an idea from problem to shippable flow. I'd welcome the chance to do
that for {company}.

Thank you for your time.

Best,
{your_name}
"""
    return _maybe_ai_letter(letter, jp, fit)


# ── optional AI polish (only when the careers_ai switch is on) ─────────────────
def _ai_on() -> bool:
    try:
        from .. import controls
        return bool({c["key"]: c for c in controls.snapshot()}.get("careers_ai", {}).get("on"))
    except Exception:
        return False


def _client():
    from ..llm.openai_client import OpenAIClient
    import os
    c = OpenAIClient(model=os.environ.get("LLM_MODEL", "local-model"),
                     host=os.environ.get("LLM_BASE_URL", "http://localhost:1234/v1"),
                     api_key=os.environ.get("LLM_API_KEY", ""), temperature=0.3)
    return c if c.is_up() else None


def _maybe_ai_polish(fit: Fit, jp: J.JobPost, base: R.Resume) -> Fit:
    if not _ai_on():
        return fit
    try:
        from ..llm.ollama_client import ChatMessage
        c = _client()
        if not c:
            return fit
        prompt = ("Rewrite this positioning line to be crisp and specific, using "
                  "ONLY the facts given. One sentence.\n\n"
                  f"Line: {fit.summary}\nRole: {jp.title}\nStrengths: {', '.join(fit.matched)}")
        out = c.chat([ChatMessage(role="user", content=prompt)])
        if out.content and len(out.content) < 400:
            fit.summary = out.content.strip().strip('"')
    except Exception:
        pass
    return fit


def _maybe_ai_letter(letter: str, jp: J.JobPost, fit: Fit) -> str:
    if not _ai_on():
        return letter
    try:
        from ..llm.ollama_client import ChatMessage
        c = _client()
        if not c:
            return letter
        prompt = ("Polish this cover letter: warmer and more natural, same length, "
                  "keep every factual claim exactly as-is, no new claims.\n\n" + letter)
        out = c.chat([ChatMessage(role="user", content=prompt)])
        if out.content and len(out.content) > 200:
            return out.content.strip()
    except Exception:
        pass
    return letter


# ── human-readable report ──────────────────────────────────────────────────────
def report(fit: Fit) -> str:
    if not fit.resume:
        return fit.summary
    lines = [f"Best base resume: {fit.resume}  (fit {fit.score:.0%})",
             f"Matches: {', '.join(fit.matched) or '—'}",
             f"Gaps to address: {', '.join(fit.gaps) or 'none'}",
             "",
             "Lead with these (your real lines, ranked to this posting):"]
    for ln in fit.emphasis:
        lines.append(f"  • {ln}")
    lines += ["", "Tailored summary line:", f"  {fit.summary}"]
    if len(fit.ranking) > 1:
        lines += ["", "Resume ranking: " + ", ".join(f"{n} {s:.0%}" for n, s in fit.ranking)]
    return "\n".join(lines)


# ── CLI ─────────────────────────────────────────────────────────────────────
def _load_posting(args) -> J.JobPost | None:
    if "--posting" in args:
        return J.from_file(args[args.index("--posting") + 1])
    import sys
    if not sys.stdin.isatty():
        return J.from_text(sys.stdin.read())
    return None


def _main(argv: list[str]) -> int:
    cmd = argv[0] if argv else "fit"
    args = argv[1:]
    jp = _load_posting(args)
    if jp is None:
        print("Give a posting: --posting <file>  (or pipe text via stdin)")
        return 2
    resume_name = args[args.index("--resume") + 1] if "--resume" in args else None
    fit = analyze(jp, resume_name)

    if cmd == "fit":
        print(report(fit)); return 0
    if cmd == "letter":
        if not fit.resume:
            print(fit.summary); return 1
        print(cover_letter(jp, fit)); return 0
    print("usage: tailor [fit|letter] --posting <file> [--resume NAME]")
    return 2


if __name__ == "__main__":
    import sys

    raise SystemExit(_main(sys.argv[1:]))
