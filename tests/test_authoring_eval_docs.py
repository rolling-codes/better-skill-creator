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
    match = re.search(
        rf"^## {re.escape(heading)}\s*\n(.*?)(?=^## |\Z)",
        text, re.MULTILINE | re.DOTALL,
    )
    assert match is not None, f"Missing section: {heading}"
    return match.group(1)


def _invocations(text: str) -> list[str]:
    return [line.strip() for line in INVOCATION.findall(text)]


def _parse(argv: list[str]) -> None:
    """Stop after ArgumentParser.parse_args so prepare cannot create a directory."""
    real = argparse.ArgumentParser.parse_args

    def stop_after_parse(self, args=None, namespace=None):
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
    agents = AGENTS.read_text(encoding="utf-8")
    assert agents == CLAUDE.read_text(encoding="utf-8")
    commands = _invocations(agents)
    assert {shlex.split(line)[3] for line in commands} == SUBCOMMANDS
    assert "not a bsc.py subcommand" in agents.lower()
    assert "compare_eval" in agents
    assert "skill_test --grade-transcript" in agents


def test_user_guide_distinguishes_the_paired_authoring_runner():
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


def test_documented_authoring_eval_commands_parse():
    guide = _section(GUIDE.read_text(encoding="utf-8"), "Grade paired authoring runs")
    lines = _invocations(guide) + _invocations(AGENTS.read_text(encoding="utf-8"))
    assert lines
    for line in lines:
        _parse(shlex.split(line)[3:])
