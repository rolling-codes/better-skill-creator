"""Regression: the transcript behavior-grading route stays discoverable and real.

`skill_test.py --grade-only --grade-transcript` grades a skill's
expected_behavior.yaml from a saved transcript without the live trigger/baseline
loop (one grader model call). It is documented in CLAUDE.md/SETUP.md and the yaml
header, but was absent from the two surfaces an author actually follows (SKILL.md's
eval workflow and the README).

doc_sync.py validates that documented `python -m scripts.<module>` references point
at a real module, but it does NOT validate their flags. So these checks guard two
things doc_sync can't: (1) the workflow pointer text isn't silently deleted, and
(2) the documented invocation still parses with the parser main() uses. Read-only; no model/network calls.
"""
import re
import shlex
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
SKILL_MD = REPO / "skills" / "skill-creator" / "SKILL.md"
README = REPO / "README.md"
sys.path.insert(0, str(REPO / "skills" / "skill-creator"))

from scripts import skill_test  # noqa: E402


def _section(text, heading):
    """Return the body of a `## {heading}` section up to the next `## ` heading."""
    match = re.search(
        rf"^## {re.escape(heading)}\s*\n(.*?)(?=^## |\Z)",
        text, re.MULTILINE | re.DOTALL,
    )
    assert match is not None, f"Missing section: {heading}"
    return match.group(1)


def test_skill_md_eval_workflow_names_behavior_grading_command():
    body = _section(SKILL_MD.read_text(encoding="utf-8"),
                    "Running and evaluating test cases")
    # Require the correct combined form: --grade-only alone errors (it requires
    # --grade-transcript), so the two must be documented together, not scattered.
    assert "--grade-only --grade-transcript" in body, (
        "SKILL.md eval workflow must point at the behavior-grading route as "
        "`--grade-only --grade-transcript` (the valid combination that skips the "
        "live trigger/baseline loop); --grade-only without --grade-transcript errors"
    )


def test_readme_how_it_works_mentions_transcript_grading():
    body = _section(README.read_text(encoding="utf-8"), "How it works")
    # Grading and transcript must appear together in one sentence, so a reword that
    # drops the saved-transcript grading pointer fails even if either word survives.
    assert re.search(r"grad\w*[^.\n]*transcript|transcript[^.\n]*grad\w*", body, re.IGNORECASE), (
        "README 'How it works' must mention grading behavior from a transcript, together"
    )


def test_documented_invocation_parses_with_main_parser():
    # Closes doc_sync's blind spot: it checks the module exists, not its flags. Parsing
    # with build_parser() -- the parser main() itself uses -- means a flag left on some
    # other parser in the file cannot satisfy this.
    match = re.search(r"`(python -m scripts\.skill_test [^`]*--grade-only[^`]*)`",
                      SKILL_MD.read_text(encoding="utf-8"))
    assert match, "SKILL.md no longer documents a --grade-only skill_test invocation"
    argv = shlex.split(match.group(1))[3:]  # drop `python -m scripts.skill_test`
    args = skill_test.build_parser().parse_args(argv)
    assert args.grade_only is True
    assert args.grade_transcript == "<transcript>"
    assert args.skill_path == "<skill>"


def test_write_atomic_replaces_whole_file_and_leaves_no_temp(tmp_path):
    target = tmp_path / "t.grading.json"
    target.write_text("old", encoding="utf-8")
    skill_test._write_atomic(target, '{"new": true}')
    assert target.read_text(encoding="utf-8") == '{"new": true}'
    assert [p.name for p in tmp_path.iterdir()] == ["t.grading.json"]


def test_write_atomic_failure_keeps_old_report_and_cleans_up(tmp_path, monkeypatch):
    target = tmp_path / "t.grading.json"
    target.write_text("old", encoding="utf-8")

    def boom(*_):
        raise OSError("disk full")

    monkeypatch.setattr(skill_test.os, "replace", boom)
    with pytest.raises(OSError):
        skill_test._write_atomic(target, "new")
    assert target.read_text(encoding="utf-8") == "old"
    assert [p.name for p in tmp_path.iterdir()] == ["t.grading.json"]
