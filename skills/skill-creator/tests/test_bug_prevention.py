"""Regression tests for the Phase-1 bug-prevention fixes.

F2 (review.py) - findings match dispositions by stable id, else normalized text,
consume-once so one disposition can't silently cover two findings.
F1 (review_gate.py) - consolidated_decision must carry the synthesis keys, not
just be non-empty.
G5 (score.py) - robustness no longer rewards the literal phrases iron law / red flags.
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

SKILL = Path(__file__).resolve().parent.parent
REPO = SKILL.parent.parent
sys.path.insert(0, str(SKILL))

from scripts.review import ReviewRecord, REQUIRED_ROLES, COMPLETION_ROLE
from scripts.review_gate import analyze
from scripts.skill_ir import Skill
from scripts.score import score


# ---------------------------------------------------------------------------
# F2 - finding <-> disposition matching (ReviewRecord unit level)
# ---------------------------------------------------------------------------

def _high(text, **extra):
    """Build a high-severity review finding with optional extra fields."""
    return {"role": "outcome-analyst", "severity": "high", "finding": text, **extra}


def test_P1_one_disposition_does_not_cover_two_identical_findings():
    """Two identical-text high findings, one disposition -> one stays undisposed."""
    rec = ReviewRecord(
        independent_findings=[_high("same problem"), _high("same problem")],
        finding_disposition=[{"finding": "same problem", "disposition": "fixed"}],
    )
    assert len(rec.undisposed_blocking_findings()) == 1


def test_two_identical_findings_need_two_dispositions():
    """Two dispositions resolve two findings with identical text."""
    rec = ReviewRecord(
        independent_findings=[_high("same problem"), _high("same problem")],
        finding_disposition=[
            {"finding": "same problem", "disposition": "fixed"},
            {"finding": "same problem", "disposition": "accepted_limitation"},
        ],
    )
    assert rec.undisposed_blocking_findings() == []


def test_P2_case_and_whitespace_differences_still_match():
    """A capital letter or extra spaces must not block a correct disposition."""
    rec = ReviewRecord(
        independent_findings=[_high("Unsafe  Input Handling.")],
        finding_disposition=[{"finding": "unsafe input handling.", "disposition": "fixed"}],
    )
    assert rec.undisposed_blocking_findings() == []


def test_match_by_explicit_id_when_present():
    """A matching finding ID resolves a finding without repeating its text."""
    rec = ReviewRecord(
        independent_findings=[_high("wording A", id="OA-1")],
        finding_disposition=[{"finding_id": "OA-1", "disposition": "fixed"}],
    )
    assert rec.undisposed_blocking_findings() == []


def test_ids_distinguish_identical_text():
    """Same text, distinct ids: a disposition for one id leaves the other undisposed."""
    rec = ReviewRecord(
        independent_findings=[_high("dup", id="OA-1"), _high("dup", id="OA-2")],
        finding_disposition=[{"finding_id": "OA-1", "disposition": "fixed"}],
    )
    undisposed = rec.undisposed_blocking_findings()
    assert [f["id"] for f in undisposed] == ["OA-2"]


# ---------------------------------------------------------------------------
# F1 - consolidated_decision meaning check (analyze level)
# ---------------------------------------------------------------------------

@pytest.fixture
def minimal_skill(tmp_path):
    """Copy the example skill and add agent files required by the review gate."""
    root = tmp_path / "test-skill"
    shutil.copytree(REPO / "examples/release-notes", root)
    agents = root / "agents"
    agents.mkdir(exist_ok=True)
    for name in ("outcome-analyst", "scope-adversary", "architecture-reviewer", "completion-adversary"):
        (agents / f"{name}.md").write_text(f"# {name}\n", encoding="utf-8")
    return root


def _write(skill_dir, decision):
    """Write an otherwise complete review record with the supplied synthesis."""
    from scripts.file_policy import source_manifest
    ReviewRecord(
        source_manifest=source_manifest(skill_dir),
        activation_required=True,
        activation_reason="test",
        independent_findings=[{"role": r, "findings": []} for r in REQUIRED_ROLES],
        consolidated_decision=decision,
        completion_adversary_report={"role": COMPLETION_ROLE, "verdict": "complete"},
        completion_gate_status="passed",
    ).write(skill_dir)


def _rules(skill_dir):
    """Return the blocking rule IDs emitted by review analysis for the skill."""
    return {f.rule for f in analyze(Skill.from_path(skill_dir)) if f.severity == "error"}


def test_P5_placeholder_decision_is_rejected(minimal_skill):
    """{'ok': true} is non-empty but not a synthesis."""
    _write(minimal_skill, {"ok": True})
    assert "review-synthesis-incomplete" in _rules(minimal_skill)


def test_complete_decision_passes(minimal_skill):
    """A decision with all synthesis keys avoids the incomplete-synthesis error."""
    _write(minimal_skill, {"accepted_findings": [], "rejected_findings": [],
                           "chosen_interpretation": "x"})
    assert "review-synthesis-incomplete" not in _rules(minimal_skill)


# ---------------------------------------------------------------------------
# G5 - robustness no longer rewards wording
# ---------------------------------------------------------------------------

def test_robustness_ignores_iron_law_and_red_flags(minimal_skill):
    """Adding the former scoring phrases leaves the robustness score unchanged."""
    plain = Skill.from_path(minimal_skill)
    base = score(plain, []).robustness
    md = minimal_skill / "SKILL.md"
    md.write_text(md.read_text(encoding="utf-8") + "\n\nThis is the iron law. See the red flags table.\n",
                  encoding="utf-8")
    boosted = score(Skill.from_path(minimal_skill), []).robustness
    assert boosted == base
