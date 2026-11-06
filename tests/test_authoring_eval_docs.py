"""The paired authoring runner stays named and distinct in human-facing docs.

v3.7.2 ships scripts/authoring_eval.py. Trigger eval, saved-result comparison, and
transcript grading are different commands. These checks keep the agent command list
and the user guide pointed at the real entrypoint, and they parse the documented
invocations with the parser main() uses.
"""
import argparse
import re
import shlex
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "skill-creator"))

from scripts import authoring_eval  # noqa: E402

AGENTS = ROOT / "AGENTS.md"
CLAUDE = ROOT / "CLAUDE.md"
GUIDE = ROOT / "docs" / "USER_GUIDE.md"
SUBCOMMANDS = {"preflight", "prepare", "check", "merge"}
INVOCATION = re.compile(r"^python -m scripts\.authoring_eval\b.*$", re.MULTILINE)


def _section(text: str, heading: str) -> str:
    """Return the body of one level-2 heading, through the next heading."""
    match = re.search(
        rf"^## {re.escape(heading)}\s*\n(.*?)(?=^## |\Z)",
        text, re.MULTILINE | re.DOTALL,
    )
    assert match is not None, f"Missing section: {heading}"
    return match.group(1)


def _invocations(text: str) -> list[str]:
    """Return documented authoring_eval command lines, excluding comments."""
    return [line.strip() for line in INVOCATION.findall(text)]


def _parse(argv: list[str]) -> None:
    """Stop after ArgumentParser.parse_args so prepare cannot create a directory."""
    real = argparse.ArgumentParser.parse_args

    def stop_after_parse(self, args=None, namespace=None):
        """Parse the documented arguments, then stop before the command runs."""
        real(self, args, namespace)
        raise SystemExit(0)

    argparse.ArgumentParser.parse_args = stop_after_parse
    saved = sys.argv
    sys.argv = ["authoring_eval", *argv]
    try:
        with pytest.raises(SystemExit) as exc:
            authoring_eval.main()
        assert exc.value.code == 0
    finally:
        sys.argv = saved
        argparse.ArgumentParser.parse_args = real


def test_agent_guidance_is_mirrored_and_names_authoring_eval():
    """Keep both guidance files on the real runner, including optional residual grades."""
    agents = AGENTS.read_text(encoding="utf-8")
    assert agents == CLAUDE.read_text(encoding="utf-8")
    commands = _invocations(agents)
    assert {shlex.split(line)[3] for line in commands} == SUBCOMMANDS
    assert "not a bsc.py subcommand" in agents.lower()
    assert "compare_eval" in agents
    assert "skill_test --grade-transcript" in agents
    merge_lines = [line for line in commands if shlex.split(line)[3] == "merge"]
    assert any("--model-grades" not in line for line in merge_lines)
    assert any("--model-grades" in line for line in merge_lines)
    assert "run_id" in agents and "model must match the prepared run" in agents


def test_user_guide_distinguishes_the_paired_authoring_runner():
    """Describe metadata, reference grades, and optional residual grades accurately."""
    body = _section(GUIDE.read_text(encoding="utf-8"), "Grade paired authoring runs")
    assert "scripts/authoring_eval.py" in body
    assert "does not call a model" in body
    assert "bsc.py` does not wrap `authoring_eval" in body
    assert "compare_eval" in body
    assert "grade-transcript" in body
    commands = _invocations(body)
    assert {shlex.split(line)[3] for line in commands} == SUBCOMMANDS
    assert any("--reference-grades" in line for line in commands)
    assert any("--no-skill" in line for line in commands)
    assert "--baseline" in body
    reference = next(line for line in commands if "--reference-grades" in line)
    assert reference.endswith("reference-grades.json")
    assert "grading.json" not in reference
    assert "does not create `eval_metadata.json`" in body
    assert "evals/evals.json" in body
    assert "Omit `--model-grades`" in body
    schema = (ROOT / "skills/skill-creator/references/schemas.md").read_text(encoding="utf-8")
    reference_lines = [line for line in schema.splitlines() if "--reference-grades" in line]
    assert reference_lines
    assert all(line.endswith("reference-grades.json") for line in reference_lines)


def test_documented_authoring_eval_commands_parse():
    """Parse every documented authoring_eval invocation with the runner's parser."""
    guide = _section(GUIDE.read_text(encoding="utf-8"), "Grade paired authoring runs")
    lines = _invocations(guide) + _invocations(AGENTS.read_text(encoding="utf-8"))
    assert lines
    for line in lines:
        _parse(shlex.split(line)[3:])
