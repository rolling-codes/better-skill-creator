"""Scoring failures must block the unified validation CLI."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import validate
from scripts.finding_types import Finding
from scripts.utils import parse_skill_md


_DESCRIPTION = (
    "Drafts short notes from a request. Use when the user asks for a note or a summary. "
    "Not for sending email or publishing the result."
)


def _write_skill(directory: Path, name: str) -> None:
    directory.mkdir()
    directory.joinpath("SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {_DESCRIPTION}\n---\n# Notes\n\nWrite the note.\n",
        encoding="utf-8",
    )


@pytest.mark.parametrize("findings", [[], [Finding("warning", "lint", "warning")]])
def test_scoring_exception_blocks_validation(monkeypatch, capsys, findings):
    monkeypatch.setattr(sys, "argv", ["validate", "unused"])
    monkeypatch.setattr(validate, "validate", lambda path: list(findings))
    monkeypatch.setattr(validate.Skill, "from_path", lambda path: object())
    monkeypatch.setattr(validate, "assess_skill", lambda skill: None)

    def score(*args):
        raise RuntimeError("broken scorer")

    monkeypatch.setattr(validate, "compute_score", score)
    assert validate._main() == 1
    output = capsys.readouterr().out
    assert "score-error" in output
    assert "Scoring failed: broken scorer" in output
    assert "Validation passed" not in output


def test_commit_check_stops_on_structural_error(tmp_path, monkeypatch, capsys):
    skill = tmp_path / "bad"
    skill.mkdir()
    (skill / "SKILL.md").write_text(
        '---\nname: ""\ndescription: present\n---\n# Bad\n\nBody.\n',
        encoding="utf-8",
    )

    def boom(_skill):
        raise AssertionError("lint should not run after a structural error")

    monkeypatch.setattr(validate, "lint", boom)
    assert validate.commit_check(skill) == 1
    assert "non-empty" in capsys.readouterr().out


def test_commit_check_loads_the_skill_once(tmp_path, monkeypatch, capsys):
    skill = tmp_path / "my-skill"
    _write_skill(skill, "my-skill")
    calls = {"n": 0}
    original = validate.Skill.from_path

    def counting(path):
        calls["n"] += 1
        return original(path)

    monkeypatch.setattr(validate.Skill, "from_path", counting)

    def fail(*_args, **_kwargs):
        raise AssertionError("static analysis and scoring are not commit checks")

    monkeypatch.setattr(validate, "analyze", fail)
    monkeypatch.setattr(validate, "compute_score", fail)
    assert validate.commit_check(skill) == 0
    assert calls["n"] == 1
    output = capsys.readouterr().out
    assert "Skill is valid!" in output
    assert "Review gate: skipped" in output
    assert "Score:" not in output


def test_commit_flag_skips_score(tmp_path, monkeypatch, capsys):
    skill = tmp_path / "my-skill"
    _write_skill(skill, "my-skill")
    monkeypatch.setattr(sys, "argv", ["validate", "--commit", str(skill)])

    def fail(*_args, **_kwargs):
        raise AssertionError("scoring is not a commit check")

    monkeypatch.setattr(validate, "compute_score", fail)
    assert validate._main() == 0
    assert "Score:" not in capsys.readouterr().out


def test_commit_flag_requires_a_path(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["validate", "--commit"])
    assert validate._main() == 1
    assert "Usage:" in capsys.readouterr().err


def test_parse_skill_md_reads_skill_md_once(tmp_path, monkeypatch):
    skill = tmp_path / "demo"
    text = f"---\nname: demo\ndescription: {_DESCRIPTION}\n---\n# Demo\n\nBody.\n"
    skill.mkdir()
    (skill / "SKILL.md").write_text(text, encoding="utf-8")
    original = Path.read_text
    reads = []

    def counting(self, *args, **kwargs):
        if self.name == "SKILL.md":
            reads.append(self)
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", counting)
    name, description, content = parse_skill_md(skill)
    assert (name, description, content) == ("demo", _DESCRIPTION, text)
    assert len(reads) == 1
