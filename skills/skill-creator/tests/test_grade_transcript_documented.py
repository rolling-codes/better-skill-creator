"""Regression: the transcript behavior-grading route stays discoverable and real.

`skill_test.py --grade-only --grade-transcript` grades a skill's
expected_behavior.yaml from a saved transcript without the live trigger/baseline
loop (one grader model call). It is documented in CLAUDE.md/SETUP.md and the yaml
header, but was absent from the two surfaces an author actually follows (SKILL.md's
eval workflow and the README).

doc_sync.py validates that documented `python -m scripts.<module>` references point
at a real module, but it does NOT validate their flags. So these checks guard two
things doc_sync can't: (1) the workflow pointer text isn't silently deleted, and
(2) the flags the docs teach (`--grade-only`, `--grade-transcript`) are still
*active* argparse options in skill_test's parser (checked via AST, so a commented-out
or stringified occurrence does not count). Read-only; no model/network calls.
"""
import ast
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
SKILL_MD = REPO / "skills" / "skill-creator" / "SKILL.md"
README = REPO / "README.md"
SKILL_TEST = REPO / "skills" / "skill-creator" / "scripts" / "skill_test.py"


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


def test_documented_flags_are_active_parser_options():
    # Closes doc_sync's blind spot: it checks the module exists, not its flags.
    # AST (not source regex) so a commented-out/stringified add_argument never counts.
    tree = ast.parse(SKILL_TEST.read_text(encoding="utf-8"))
    declared = {
        node.args[0].value
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "add_argument"
        and node.args
        and isinstance(node.args[0], ast.Constant)
        and isinstance(node.args[0].value, str)
    }
    for flag in ("--grade-transcript", "--grade-only"):
        assert flag in declared, (
            f"{flag} is documented but is not an active add_argument in skill_test.py's parser"
        )
