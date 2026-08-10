"""
jobpost — read ONE job posting you point us at, and structure it. On-device.

The legal line (deliberate): this reads a *single* posting you're already looking
at — pasted text, a file you saved, or one URL — the way your browser would. It
does NOT crawl job feeds, does NOT bulk-scrape, and refuses a URL whose site
disallows it in robots.txt. LinkedIn feeds / mass harvesting are out of scope by
design.

From the text it extracts a structured JobPost: title, company, seniority,
required skills, responsibilities, and keywords — deterministically (regex +
keyword lexicon) so it works with **zero AI**. If the AI switch is on
(controls: careers_ai), a local-LLM pass refines the messy bits; it's optional
polish, never required.

CLI:
    python3 -m cognitive_twin.careers.jobpost parse --file posting.txt
    python3 -m cognitive_twin.careers.jobpost parse --url https://…/one-posting
    echo "<pasted text>" | python3 -m cognitive_twin.careers.jobpost parse --stdin

© Ankur Sinha. Personal use.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


# ── the structured posting ─────────────────────────────────────────────────────
@dataclass
class JobPost:
    title: str = ""
    company: str = ""
    location: str = ""
    seniority: str = ""
    skills: list[str] = field(default_factory=list)
    responsibilities: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    source: str = ""            # "paste" | "file:<path>" | "url:<host>"
    raw_len: int = 0

    def summary(self) -> str:
        bits = [self.title or "(untitled role)"]
        if self.company:
            bits.append(f"at {self.company}")
        if self.seniority:
            bits.append(f"· {self.seniority}")
        return " ".join(bits)


# ── a compact tech/role skill lexicon (extend freely) ──────────────────────────
_SKILLS = [
    # design / research
    "ux", "ui", "user research", "usability", "figma", "prototyping", "wireframe",
    "interaction design", "design system", "accessibility", "information architecture",
    "product design", "design thinking", "user testing", "journey mapping",
    # ai / ml
    "machine learning", "ml", "llm", "prompt", "generative ai", "genai", "nlp",
    "pytorch", "tensorflow", "computer vision", "rag", "fine-tuning", "ai",
    "human-ai interaction", "conversational ai", "ai engineering",
    # eng
    "python", "javascript", "typescript", "react", "node", "next.js", "swift",
    "sql", "api", "aws", "gcp", "azure", "oci", "docker", "kubernetes", "terraform",
    "rust", "go", "graphql", "postgres", "cloud", "saas", "frontend", "backend",
    # pm / other
    "product management", "agile", "scrum", "stakeholder", "roadmap", "analytics",
    "a/b testing", "metrics", "enterprise", "b2b", "b2c", "fintech",
]

_SENIORITY = [
    ("principal", "Principal"), ("staff", "Staff"), ("lead", "Lead"),
    ("senior", "Senior"), ("sr.", "Senior"), ("junior", "Junior"),
    ("jr.", "Junior"), ("entry", "Entry"), ("director", "Director"),
    ("head of", "Head"), ("vp", "VP"), ("intern", "Intern"),
]

_TITLE_HINTS = re.compile(
    r"\b(designer|engineer|manager|researcher|scientist|developer|architect|"
    r"analyst|lead|director|specialist|consultant|strategist)\b", re.IGNORECASE)


# ── HTML → text (for saved pages / URL fetch) ──────────────────────────────────
def _strip_html(html: str) -> str:
    # drop scripts/styles, then tags, then collapse whitespace
    html = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.I | re.S)
    html = re.sub(r"<[^>]+>", " ", html)
    html = re.sub(r"&nbsp;", " ", html)
    html = re.sub(r"&amp;", "&", html)
    html = re.sub(r"&#\d+;", " ", html)
    return re.sub(r"[ \t]*\n[ \t]*", "\n", re.sub(r"[ \t]+", " ", html)).strip()


def _looks_html(s: str) -> bool:
    return "<html" in s.lower() or "<div" in s.lower() or "<body" in s.lower()


# ── deterministic extraction (works with zero AI) ──────────────────────────────
def _extract(text: str, source: str) -> JobPost:
    jp = JobPost(source=source, raw_len=len(text))
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    low = text.lower()

    # Title: first line that reads like a role title. Trim anything after a
    # separator (·, |, —, "at") so "Senior AI Designer at Acme · Remote" → the role.
    def _clean_title(s: str) -> str:
        s = re.split(r"\s+(?:·|\||—|–|-\s|@|\bat\b)\s+", s, maxsplit=1)[0]
        return s.strip()[:80]
    for ln in lines[:12]:
        if _TITLE_HINTS.search(ln) and len(ln) < 110:
            jp.title = _clean_title(ln)
            break
    if not jp.title and lines:
        jp.title = _clean_title(lines[0])

    # Company: look for "at X", "Company: X", or a line before/after title
    m = re.search(r"\b(?:at|@)\s+([A-Z][\w&.\- ]{2,40})", text)
    if m:
        jp.company = m.group(1).strip(" .")
    m = re.search(r"company[:\s]+([A-Z][\w&.\- ]{2,40})", text, re.I)
    if m:
        jp.company = m.group(1).strip(" .")

    # Location
    m = re.search(r"\b(remote|hybrid|on-?site)\b", low)
    loc_words = re.search(r"\b(toronto|new york|san francisco|london|bangalore|"
                          r"seattle|austin|boston|vancouver|ontario|canada|usa|uk)\b", low)
    jp.location = ", ".join(x for x in [
        (m.group(1).title() if m else ""),
        (loc_words.group(1).title() if loc_words else "")] if x)

    # Seniority
    for needle, label in _SENIORITY:
        if needle in low:
            jp.seniority = label
            break

    # Skills present in the posting
    found = []
    for skill in _SKILLS:
        if re.search(r"\b" + re.escape(skill) + r"\b", low):
            found.append(skill)
    jp.skills = sorted(set(found))

    # Responsibilities: bullet-ish lines
    resp = [ln.lstrip("•-–*·⋅ ").strip() for ln in lines
            if re.match(r"^\s*[•\-–*·⋅]", ln) and 12 < len(ln) < 200]
    jp.responsibilities = resp[:12]

    # Keywords: capitalised multiword phrases + the skills
    kw = set(jp.skills)
    for m in re.finditer(r"\b([A-Z][a-z]+(?:\s[A-Z][a-z]+){1,2})\b", text):
        kw.add(m.group(1).lower())
    jp.keywords = sorted(kw)[:30]
    return jp


# ── input sources ──────────────────────────────────────────────────────────────
def from_text(text: str, *, source: str = "paste") -> JobPost:
    if _looks_html(text):
        text = _strip_html(text)
    return _extract(text, source)


def from_file(path: str | Path) -> JobPost:
    p = Path(path).expanduser()
    raw = p.read_text(encoding="utf-8", errors="replace")
    return from_text(raw, source=f"file:{p.name}")


def _robots_allows(url: str) -> bool:
    """Respect robots.txt for a single-page fetch. Fail-closed on doubt only for
    known bulk-scrape-hostile hosts; otherwise a single public page is fine."""
    import urllib.request
    import urllib.robotparser

    parsed = urlparse(url)
    # Hard refusal: never fetch from job-aggregator feeds / LinkedIn programmatically.
    host = (parsed.hostname or "").lower()
    if any(h in host for h in ("linkedin.com", "indeed.com/jobs", "glassdoor.com")):
        raise PermissionError(
            f"Refusing to fetch from {host} programmatically (ToS / anti-scraping). "
            f"Open the posting in your browser and paste the text instead "
            f"(`--stdin` or save it and use `--file`).")
    rp = urllib.robotparser.RobotFileParser()
    rp.set_url(f"{parsed.scheme}://{parsed.netloc}/robots.txt")
    try:
        rp.read()
    except Exception:
        return True  # no robots = allowed
    return rp.can_fetch("*", url)


def from_url(url: str, *, timeout: int = 15) -> JobPost:
    """Fetch ONE public posting page (like a browser). Refuses bulk/hostile hosts
    and respects robots.txt. Not for feeds."""
    import urllib.request

    if not _robots_allows(url):
        raise PermissionError(f"{url} disallows automated fetch (robots.txt). "
                              f"Open it in your browser and paste the text instead.")
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (personal resume assistant; single-page read)"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read().decode("utf-8", errors="replace")
    host = urlparse(url).hostname or "url"
    return from_text(raw, source=f"url:{host}")


# ── optional AI refinement (only if the switch is on) ──────────────────────────
def _ai_on() -> bool:
    try:
        from .. import controls
        snap = {c["key"]: c for c in controls.snapshot()}
        return bool(snap.get("careers_ai", {}).get("on"))
    except Exception:
        return False


def refine_with_ai(jp: JobPost, text: str) -> JobPost:
    """If the careers AI switch is on and a local LLM is reachable, tidy the
    extracted title/company/skills. Best-effort; returns jp unchanged otherwise."""
    if not _ai_on():
        return jp
    try:
        from ..llm.openai_client import OpenAIClient, OpenAIError
        from ..llm.ollama_client import ChatMessage
        import os
        client = OpenAIClient(model=os.environ.get("LLM_MODEL", "local-model"),
                              host=os.environ.get("LLM_BASE_URL", "http://localhost:1234/v1"),
                              api_key=os.environ.get("LLM_API_KEY", ""), temperature=0.0)
        if not client.is_up():
            return jp
        prompt = ("Extract as JSON {title, company, seniority, skills[]} from this "
                  "job posting. Only facts present in the text.\n\n" + text[:3000])
        reply = client.chat([ChatMessage(role="user", content=prompt)])
        data = json.loads(re.search(r"\{.*\}", reply.content, re.S).group(0))
        jp.title = data.get("title") or jp.title
        jp.company = data.get("company") or jp.company
        jp.seniority = data.get("seniority") or jp.seniority
        if isinstance(data.get("skills"), list):
            jp.skills = sorted(set(jp.skills) | {s.lower() for s in data["skills"]})
    except Exception:
        pass  # AI is optional polish; never fail the parse
    return jp


# ── CLI ─────────────────────────────────────────────────────────────────────
def _main(argv: list[str]) -> int:
    if not argv or argv[0] != "parse":
        print("usage: jobpost parse [--file PATH | --url URL | --stdin]")
        return 2
    args = argv[1:]
    jp = None
    try:
        if "--file" in args:
            jp = from_file(args[args.index("--file") + 1])
        elif "--url" in args:
            jp = from_url(args[args.index("--url") + 1])
        elif "--stdin" in args:
            jp = from_text(sys.stdin.read())
        else:
            print("give --file, --url, or --stdin"); return 2
    except PermissionError as e:
        print(f"✗ {e}"); return 1
    except Exception as e:
        print(f"✗ couldn't read posting: {e}"); return 1

    text = ""  # refine uses raw text; re-read cheaply for --file/--stdin isn't needed here
    jp = refine_with_ai(jp, text)
    print(json.dumps(asdict(jp), indent=2))
    print("\n" + jp.summary(), file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
