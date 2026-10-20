"""Regression: the transcript behavior-grading route stays discoverable.

`skill_test.py --grade-transcript` grades a skill's expected_behavior.yaml from a
saved transcript — the headless/offline alternative to the live eval loop. It is
documented in CLAUDE.md/SETUP.md and the yaml header, but was absent from the two
surfaces an author actually follows (SKILL.md's eval workflow and the README).

doc_sync.py already guarantees any documented command is real; these checks only
guard the workflow pointer against silent deletion. No model calls; read-only.
"""
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
SKILL_MD = REPO / "skills" / "skill-creator" / "SKILL.md"
README = REPO / "README.md"


def _section(text, heading):
    """Return the body of a `## {heading}` section up to the next `## ` heading."""
    match = re.search(
        rf"^## {re.escape(heading)}\s*\n(.*?)(?=^## |\Z)",
        text, re.MULTILINE | re.DOTALL,
    )
    assert match is not None, f"Missing section: {heading}"
    return match.group(1)


def test_skill_md_eval_workflow_names_grade_transcript():
    body = _section(SKILL_MD.read_text(encoding="utf-8"),
                    "Running and evaluating test cases")
    assert "--grade-transcript" in body, (
        "SKILL.md eval workflow must point at the transcript behavior-grading route"
    )


def test_readme_how_it_works_mentions_transcript_grading():
    body = _section(README.read_text(encoding="utf-8"), "How it works")
    assert re.search(r"transcript", body, re.IGNORECASE), (
        "README 'How it works' must mention transcript-based behavior grading"
    )
