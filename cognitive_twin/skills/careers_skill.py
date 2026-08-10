"""
careers_skill — Vera's resume/job-application skills.

Front-end over the standalone careers modules (jobpost, resumes, tailor,
applications). Legal + private: reads one posting you provide, works off your
sealed resume database, prepares tailoring + a cover-letter draft, and tracks
applications. It never auto-applies or submits anything.

Importing this module registers the skills on the default registry.

© Ankur Sinha. Personal use.
"""

from __future__ import annotations

from .base import default_registry as R


@R.add(
    "job_fit",
    "Analyse a job posting against your resume database: paste the posting text and "
    "get the best-matching resume, your fit %, matched strengths, gaps, and which of "
    "your real lines to lead with. Read-only; nothing is submitted.",
    {"type": "object", "properties": {
        "posting": {"type": "string", "description": "the job posting text (paste it)"},
        "resume": {"type": "string", "description": "optional: force a specific resume variant by name"},
    }, "required": ["posting"]},
)
def job_fit(posting: str, resume: str = "") -> str:
    from ..careers import jobpost, tailor
    jp = jobpost.from_text(posting)
    fit = tailor.analyze(jp, resume or None)
    return f"{jp.summary()}\n\n" + tailor.report(fit)


@R.add(
    "cover_letter",
    "Draft a cover letter for a job posting, grounded in your best-matching resume "
    "and the posting. Paste the posting text. A DRAFT for you to edit — never sent.",
    {"type": "object", "properties": {
        "posting": {"type": "string", "description": "the job posting text (paste it)"},
        "resume": {"type": "string", "description": "optional resume variant name"},
    }, "required": ["posting"]},
)
def cover_letter(posting: str, resume: str = "") -> str:
    from ..careers import jobpost, tailor
    jp = jobpost.from_text(posting)
    fit = tailor.analyze(jp, resume or None)
    if not fit.resume:
        return fit.summary
    return tailor.cover_letter(jp, fit)


@R.add(
    "list_resumes",
    "List the resume variants in your on-device database (names, skills, tags). "
    "Read-only.",
    {"type": "object", "properties": {}},
)
def list_resumes() -> str:
    from ..careers import resumes
    rs = resumes.read_all()
    if not rs:
        return ("No resumes yet. Add one from the CLI: "
                "`python3 -m cognitive_twin.careers.resumes add <file.pdf|.docx|.md>`")
    return "\n".join(f"• {r.name} — {len(r.skills)} skills, tags {r.tags or '—'} ({r.source})"
                     for r in rs)


@R.add(
    "track_application",
    "Record a job application in your sealed tracker (company + role, optional "
    "resume used + url). Nothing is submitted; this just logs what you did.",
    {"type": "object", "properties": {
        "company": {"type": "string"},
        "role": {"type": "string"},
        "resume": {"type": "string", "description": "resume variant used (optional)"},
        "url": {"type": "string", "description": "posting URL (optional)"},
    }, "required": ["company", "role"]},
)
def track_application(company: str, role: str, resume: str = "", url: str = "") -> str:
    from ..careers import applications
    a = applications.add(company, role, resume=resume, url=url)
    return f"Tracked {a.id}: {a.company} — {a.role} ({a.status})."


@R.add(
    "applications_status",
    "Show your job applications and where each stands (or just the open ones). "
    "Read-only.",
    {"type": "object", "properties": {
        "open_only": {"type": "boolean", "description": "only show open applications"},
    }},
)
def applications_status(open_only: bool = False) -> str:
    from ..careers import applications
    if open_only:
        apps = applications.open_apps()
        if not apps:
            return "No open applications."
        return "\n".join(f"• {a.id}  {a.status}  {a.company} — {a.role}" for a in apps)
    return applications.summary()
