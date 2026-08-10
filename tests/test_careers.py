"""
Careers tests — job-posting parsing + resume database + best-fit, all offline.

Asserts the deterministic (zero-AI) core: a pasted posting yields structured
fields; a resume added from markdown is parsed, skill-profiled, and sealed; the
URL fetcher refuses LinkedIn/bulk hosts; best_for picks the higher-overlap resume.

Run: python -m pytest tests/test_careers.py -q  (or: python tests/test_careers.py)
"""

from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _fresh(tmp: Path):
    os.environ["CTWIN_MEMORY_DIR"] = str(tmp)
    from cognitive_twin import vault, security
    from cognitive_twin.careers import jobpost, resumes
    importlib.reload(vault)
    importlib.reload(security)
    importlib.reload(jobpost)
    importlib.reload(resumes)
    vault._key_cache = None
    return jobpost, resumes


_POSTING = """Senior AI Product Designer
at Acme AI · Remote (Toronto, Canada)

Responsibilities:
- Design conversational AI flows and prototyping in Figma
- Partner with ML engineers on generative AI features
- Run user research and usability testing

Requirements: 5+ years product design, UX, AI/LLM products, accessibility. Python a plus.
"""


def test_jobpost_parse_deterministic(tmp_path):
    J, _ = _fresh(tmp_path)
    jp = J.from_text(_POSTING)
    assert "Designer" in jp.title
    assert jp.company == "Acme AI"
    assert jp.seniority == "Senior"
    assert "ux" in jp.skills and "llm" in jp.skills and "figma" in jp.skills
    assert len(jp.responsibilities) >= 2


def test_jobpost_refuses_linkedin(tmp_path):
    J, _ = _fresh(tmp_path)
    try:
        J.from_url("https://www.linkedin.com/jobs/view/123456")
    except PermissionError as e:
        assert "linkedin" in str(e).lower()
        return
    assert False, "expected PermissionError for LinkedIn"


def test_html_is_stripped(tmp_path):
    J, _ = _fresh(tmp_path)
    jp = J.from_text("<html><body><h1>Staff UX Researcher</h1>"
                     "<p>Need usability, figma.</p></body></html>")
    assert "Researcher" in jp.title
    assert "usability" in jp.skills


def test_resume_add_parse_seal(tmp_path):
    _, R = _fresh(tmp_path)
    md = tmp_path / "r.md"
    md.write_text("# Me\nPrincipal UX Designer. Figma, prototyping, LLM, python, accessibility.")
    r = R.add(md, name="ux", tags=["ux"])
    assert r.name == "ux"
    assert {"figma", "prototyping", "llm", "python"} <= set(r.skills)
    # sealed at rest
    raw = R._path().read_bytes()
    assert b"Principal" not in raw
    assert R.get("ux") is not None


def test_best_for_picks_higher_overlap(tmp_path):
    _, R = _fresh(tmp_path)
    (tmp_path / "a.md").write_text("UX designer. figma, prototyping, usability.")
    (tmp_path / "b.md").write_text("AI engineer. llm, python, machine learning, rag.")
    R.add(tmp_path / "a.md", name="ux")
    R.add(tmp_path / "b.md", name="ai")
    best, info = R.best_for(["llm", "python", "machine learning"])
    assert best.name == "ai"
    assert info["score"] > 0.5


def test_tailor_fit_and_cover_letter(tmp_path):
    J, R = _fresh(tmp_path)
    from cognitive_twin.careers import tailor
    import importlib
    importlib.reload(tailor)
    (tmp_path / "r.md").write_text(
        "Principal UX Designer.\n"
        "- Designed encryption console flows with strong usability and accessibility.\n"
        "- Built human-ai interaction prototypes in figma with llm features.\n")
    R.add(tmp_path / "r.md", name="ux")
    jp = J.from_text("Senior AI Designer at Acme. Needs ux, figma, llm, "
                     "human-ai interaction, usability.")
    fit = tailor.analyze(jp)
    assert fit.resume == "ux"
    assert fit.score > 0.5
    assert "figma" in fit.matched and "llm" in fit.matched
    assert len(fit.emphasis) >= 1
    # emphasis lines are clean (no markdown markers)
    assert all("**" not in ln for ln in fit.emphasis)
    letter = tailor.cover_letter(jp, fit)
    assert "Acme" in letter and "Best," in letter


def test_applications_lifecycle_sealed(tmp_path):
    _fresh(tmp_path)
    from cognitive_twin.careers import applications as A
    import importlib
    importlib.reload(A)
    a = A.add("Acme AI", "Senior Designer", resume="ux")
    assert a.status == "saved"
    A.set_status(a.id, "applied")
    A.add_note(a.id, "recruiter emailed")
    got = A.get(a.id)
    assert got.status == "applied"
    assert len(got.history) == 2 and len(got.notes) == 1
    assert A.open_apps()[0].id == a.id
    # sealed at rest
    raw = A._path().read_bytes()
    assert b"Acme" not in raw
    # bad status rejected
    try:
        A.set_status(a.id, "nonsense")
    except ValueError:
        pass
    else:
        assert False, "expected ValueError on bad status"


if __name__ == "__main__":
    import tempfile

    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            with tempfile.TemporaryDirectory() as d:
                try:
                    fn(Path(d)); print(f"  ✓ {name}")
                except AssertionError as e:
                    failures += 1; print(f"  ✗ {name}: {e}")
                except Exception as e:
                    failures += 1; print(f"  ✗ {name}: {type(e).__name__}: {e}")
    print("OK" if not failures else f"{failures} FAILED")
    sys.exit(1 if failures else 0)
