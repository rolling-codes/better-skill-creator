"""`bsc.py check` must validate a Claude Code skill (with model:) as itself.

Regression guard for the dogfood bug where checks() called validate_skill() without
claude_code=True, so `python bsc.py check skills/skill-creator` always reported
'structure — failed: Unexpected key(s) ... model' on the repo's own skill.
"""
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SKILL_PATH = ROOT / "skills" / "skill-creator"

spec = importlib.util.spec_from_file_location("bsc", ROOT / "bsc.py")
assert spec and spec.loader
bsc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bsc)


def _structure_row(rows):
    assert rows and rows[0]["check"] == "structure"
    return rows[0]


def test_check_accepts_claude_code_skill():
    """Default check (claude_code=True) validates the skill's structure as valid."""
    row = _structure_row(bsc.checks(SKILL_PATH, claude_code=True))
    assert row["status"] == "passed", row["message"]


def test_strict_check_accepts_skill_without_model_key():
    """--strict (claude_code=False) passes now that model: has moved to metadata.target_model."""
    row = _structure_row(bsc.checks(SKILL_PATH, claude_code=False))
    assert row["status"] == "passed", row["message"]


def _report(runs):
    return json.loads(next(runs.glob("*/results.json")).read_text(encoding="utf-8"))


def test_check_next_action_distinguishes_warnings_from_errors(tmp_path):
    runs = tmp_path / "runs"
    code = bsc.main(["check", str(ROOT / "examples/release-notes"), "--runs-dir", str(runs)])
    result = _report(runs)
    assert code == result["exit_code"] == 0
    assert result["next_action"] == "Warnings found. Inspect them, then package or preview eval."

    bad = tmp_path / "bad-skill"
    bad.mkdir()
    (bad / "SKILL.md").write_text(
        '---\nname: ""\ndescription: present\n---\n# Bad\n\nBody.\n',
        encoding="utf-8",
    )
    bad_runs = tmp_path / "bad-runs"
    assert bsc.main(["check", str(bad), "--runs-dir", str(bad_runs)]) == 2
    assert _report(bad_runs)["next_action"] == (
        "Fix error findings, inspect warnings, then package or preview eval."
    )


def test_check_next_action_for_a_clean_skill(tmp_path):
    description = (
        "Drafts short notes from a request. Use when the user asks for a note or a summary. "
        "Not for sending email or publishing the result."
    )
    skill = tmp_path / "my-skill"
    skill.mkdir()
    (skill / "SKILL.md").write_text(
        f"---\nname: my-skill\ndescription: {description}\n---\n# Notes\n\nWrite the note.\n",
        encoding="utf-8",
    )
    runs = tmp_path / "runs"
    assert bsc.main(["check", str(skill), "--runs-dir", str(runs)]) == 0
    assert _report(runs)["next_action"] == "No blocking findings. Package the skill or preview an eval."


def test_failure_report_does_not_double_the_period(tmp_path, monkeypatch):
    runs = tmp_path / "runs"
    missing = tmp_path / "missing-skill"
    assert bsc.main(["check", str(missing), "--runs-dir", str(runs)]) == 1
    result = _report(runs)
    assert result["next_action"] == (
        "InputError: Target must be a skill directory containing SKILL.md. "
        "Correct this issue and retry; use doctor for environment problems."
    )

    skill = tmp_path / "present"
    skill.mkdir()
    (skill / "SKILL.md").write_text("placeholder\n", encoding="utf-8")

    def boom(*_args, **_kwargs):
        raise RuntimeError("disk full")

    monkeypatch.setattr(bsc, "checks", boom)
    bare = tmp_path / "bare-runs"
    assert bsc.main(["check", str(skill), "--runs-dir", str(bare)]) == 1
    assert _report(bare)["next_action"] == (
        "RuntimeError: disk full. Correct this issue and retry; use doctor for environment problems."
    )
