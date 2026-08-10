"""
resumes — your database of resume variants, on-device and sealed.

Not one resume — a small library of them (a UX-leaning one, an AI-engineering one,
a short one), so each application starts from the best base. You add resumes from
the formats they actually live in — **PDF** (the common one), Word (.docx),
Markdown, or plain text — and we parse each into searchable text + a skill profile,
then seal it with the security kernel.

Parsing is best-effort and dependency-light:
  • .md / .txt        — read directly.
  • .pdf              — pdftotext (poppler) if present, else PyPDF2/pypdf if
                        installed, else an honest "install one of these" note.
  • .docx             — unzip word/document.xml (stdlib zipfile) — no dependency.

Everything sealed via ``security`` (ChaCha20, device-bound). Nothing is uploaded.

CLI:
    python3 -m cognitive_twin.careers.resumes add <file> [--name NAME] [--tag ai]
    python3 -m cognitive_twin.careers.resumes list
    python3 -m cognitive_twin.careers.resumes show <name>
    python3 -m cognitive_twin.careers.resumes best "<job skills/text>"

© Ankur Sinha. Personal use.
"""

from __future__ import annotations

import json
import re
import subprocess
import zipfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .. import security
from .jobpost import _SKILLS  # reuse the same skill lexicon for consistency

_DB = "resumes.jsonl"        # sealed: one line per resume variant


@dataclass
class Resume:
    name: str                     # a handle, e.g. "ux-principal" or "ai-eng"
    text: str                     # full parsed plaintext
    tags: list[str] = field(default_factory=list)
    source: str = ""              # original filename
    skills: list[str] = field(default_factory=list)
    added: str = ""

    def profile(self) -> set[str]:
        return set(self.skills)


# ── format parsers ─────────────────────────────────────────────────────────────
def _parse_pdf(path: Path) -> str:
    # 1) poppler's pdftotext (fast, no python dep)
    if _has("pdftotext"):
        try:
            out = subprocess.run(["pdftotext", "-layout", str(path), "-"],
                                 capture_output=True, text=True, timeout=30)
            if out.returncode == 0 and out.stdout.strip():
                return out.stdout
        except (OSError, subprocess.TimeoutExpired):
            pass
    # 2) pypdf / PyPDF2 if installed
    for mod in ("pypdf", "PyPDF2"):
        try:
            m = __import__(mod)
            reader = m.PdfReader(str(path))
            return "\n".join((pg.extract_text() or "") for pg in reader.pages)
        except Exception:
            continue
    raise RuntimeError(
        "Can't read the PDF — install poppler (`brew install poppler`) for "
        "`pdftotext`, or `pip install pypdf`. (Or export the resume to .md/.txt.)")


def _parse_docx(path: Path) -> str:
    # .docx is a zip; the text lives in word/document.xml — read it with stdlib.
    with zipfile.ZipFile(path) as z:
        xml = z.read("word/document.xml").decode("utf-8", "replace")
    xml = re.sub(r"</w:p>", "\n", xml)          # paragraph breaks
    xml = re.sub(r"<[^>]+>", "", xml)            # strip tags
    return re.sub(r"[ \t]+", " ", xml).strip()


def parse_file(path: str | Path) -> str:
    p = Path(path).expanduser()
    ext = p.suffix.lower()
    if ext in (".md", ".txt", ".markdown"):
        return p.read_text(encoding="utf-8", errors="replace")
    if ext == ".pdf":
        return _parse_pdf(p)
    if ext == ".docx":
        return _parse_docx(p)
    # last resort: try as text
    return p.read_text(encoding="utf-8", errors="replace")


def _has(cmd: str) -> bool:
    from shutil import which
    return which(cmd) is not None


def _skills_in(text: str) -> list[str]:
    low = text.lower()
    return sorted({s for s in _SKILLS if re.search(r"\b" + re.escape(s) + r"\b", low)})


# ── the sealed database ────────────────────────────────────────────────────────
def _path():
    return security.path(_DB)


def add(path: str | Path, *, name: str | None = None, tags: list[str] | None = None) -> Resume:
    import datetime as dt
    p = Path(path).expanduser()
    text = parse_file(p)
    if not text.strip():
        raise RuntimeError(f"parsed no text from {p.name}")
    r = Resume(name=name or p.stem, text=text, tags=tags or [], source=p.name,
               skills=_skills_in(text), added=dt.datetime.now().isoformat(timespec="seconds"))
    # replace an existing variant with the same name
    others = [x for x in read_all() if x.name != r.name]
    _rewrite(others + [r])
    return r


def read_all() -> list[Resume]:
    out: list[Resume] = []
    for data in security.read_lines(_path()):
        try:
            out.append(Resume(**data))
        except Exception:
            continue
    return out


def get(name: str) -> Resume | None:
    return next((r for r in read_all() if r.name == name), None)


def remove(name: str) -> bool:
    keep = [r for r in read_all() if r.name != name]
    if len(keep) == len(read_all()):
        return False
    _rewrite(keep)
    return True


def _rewrite(resumes: list[Resume]) -> None:
    p = _path()
    p.unlink(missing_ok=True)
    for r in resumes:
        security.append_line(p, asdict(r))


# ── pick the best base resume for a posting ────────────────────────────────────
def best_for(job_skills: set[str] | list[str], job_text: str = "") -> tuple[Resume | None, dict[str, Any]]:
    """Score each resume by skill overlap with the posting; return the strongest
    plus a breakdown. Deterministic — no AI needed."""
    wanted = set(s.lower() for s in job_skills)
    if job_text:
        wanted |= set(_skills_in(job_text))
    ranked = []
    for r in read_all():
        have = r.profile()
        overlap = wanted & have
        score = len(overlap) / max(1, len(wanted))
        ranked.append((score, r, sorted(overlap), sorted(wanted - have)))
    ranked.sort(key=lambda t: t[0], reverse=True)
    if not ranked:
        return None, {"note": "no resumes in your database yet — add one with `resumes add <file>`."}
    score, r, matched, missing = ranked[0]
    return r, {"score": round(score, 2), "matched": matched, "missing": missing,
               "ranking": [(x[1].name, round(x[0], 2)) for x in ranked]}


# ── CLI ─────────────────────────────────────────────────────────────────────
def _main(argv: list[str]) -> int:
    cmd = argv[0] if argv else "list"
    args = argv[1:]

    def opt(flag):
        return args[args.index(flag) + 1] if flag in args and args.index(flag) + 1 < len(args) else None

    if cmd == "add":
        if not args:
            print("usage: add <file> [--name NAME] [--tag TAG]"); return 2
        tags = [opt("--tag")] if opt("--tag") else []
        try:
            r = add(args[0], name=opt("--name"), tags=tags)
        except Exception as e:
            print(f"✗ {e}"); return 1
        print(f"✓ Added resume '{r.name}' ({len(r.text)} chars, {len(r.skills)} skills, "
              f"from {r.source}).")
        return 0
    if cmd == "list":
        rs = read_all()
        if not rs:
            print("No resumes yet. Add one: `resumes add <file.pdf|.docx|.md>`"); return 0
        for r in rs:
            print(f"  • {r.name:<18} {len(r.skills)} skills  tags={r.tags or '—'}  ({r.source})")
        return 0
    if cmd == "show":
        r = get(args[0]) if args else None
        if not r:
            print("not found"); return 1
        print(r.text[:2000]); return 0
    if cmd == "remove":
        print("✓ removed." if args and remove(args[0]) else "not found."); return 0
    if cmd == "best":
        text = " ".join(args)
        r, info = best_for(set(), text)
        if not r:
            print(info["note"]); return 0
        print(f"Best base: {r.name} (fit {info['score']:.0%})")
        print(f"  matches: {', '.join(info['matched']) or '—'}")
        print(f"  gaps:    {', '.join(info['missing']) or '—'}")
        return 0
    print("usage: resumes [add|list|show|remove|best]")
    return 2


if __name__ == "__main__":
    import sys

    raise SystemExit(_main(sys.argv[1:]))
