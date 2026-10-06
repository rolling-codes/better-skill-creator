"""`bsc.py check` must validate a Claude Code skill (with model:) as itself.

Regression guard for the dogfood bug where checks() called validate_skill() without
claude_code=True, so `python bsc.py check skills/skill-creator` always reported
'structure — failed: Unexpected key(s) ... model' on the repo's own skill.
"""
import importlib.util
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


def test_strict_check_rejects_model_key():
    """--strict (claude_code=False) still rejects the Claude-Code-only model: key."""
    row = _structure_row(bsc.checks(SKILL_PATH, claude_code=False))
    assert row["status"] == "failed"
    assert "model" in row["message"]
