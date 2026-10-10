"""Regression tests for completion-adversary verdict enforcement in the review gate.

G5 gap: the gate previously passed when completion_gate_status='passed' but
the completion-adversary report contained verdict='incomplete'.  These tests
confirm the fix and guard its intended behaviour.
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


# ---------------------------------------------------------------------------
# Unit tests: ReviewRecord.completion_adversary_verdict()
# ---------------------------------------------------------------------------

def test_verdict_complete_from_report():
    rec = ReviewRecord(completion_adversary_report={"role": COMPLETION_ROLE, "verdict": "complete"})
    assert rec.completion_adversary_verdict() == "complete"


def test_verdict_incomplete_from_report():
    rec = ReviewRecord(completion_adversary_report={"role": COMPLETION_ROLE, "verdict": "incomplete"})
    assert rec.completion_adversary_verdict() == "incomplete"


def test_verdict_uppercase_normalized():
    rec = ReviewRecord(completion_adversary_report={"role": COMPLETION_ROLE, "verdict": "COMPLETE"})
    assert rec.completion_adversary_verdict() == "complete"


def test_verdict_missing_field_returns_empty():
    rec = ReviewRecord(completion_adversary_report={"role": COMPLETION_ROLE})
    assert rec.completion_adversary_verdict() == ""


def test_verdict_from_adversarial_findings_fallback():
    rec = ReviewRecord(adversarial_findings=[{"role": COMPLETION_ROLE, "verdict": "incomplete"}])
    assert rec.completion_adversary_verdict() == "incomplete"


def test_verdict_report_takes_priority_over_findings():
    rec = ReviewRecord(
        completion_adversary_report={"role": COMPLETION_ROLE, "verdict": "complete"},
        adversarial_findings=[{"role": COMPLETION_ROLE, "verdict": "incomplete"}],
    )
    assert rec.completion_adversary_verdict() == "complete"


def test_verdict_empty_report_falls_through_to_findings():
    rec = ReviewRecord(
        completion_adversary_report={"role": COMPLETION_ROLE},
        adversarial_findings=[{"role": COMPLETION_ROLE, "verdict": "incomplete"}],
    )
    assert rec.completion_adversary_verdict() == "incomplete"


def test_verdict_no_adversary_data_returns_empty():
    rec = ReviewRecord()
    assert rec.completion_adversary_verdict() == ""


# ---------------------------------------------------------------------------
# Integration tests: analyze() verdict enforcement
# ---------------------------------------------------------------------------

def _required_findings(roles=REQUIRED_ROLES):
    return [{"role": r, "findings": []} for r in roles]


@pytest.fixture
def minimal_skill(tmp_path):
    """Minimal skill directory with required agent stubs for gate testing."""
    root = tmp_path / "test-skill"
    shutil.copytree(REPO / "examples/release-notes", root)
    # Add required agent stubs so the gate doesn't fail on missing-agent checks
    agents = root / "agents"
    agents.mkdir(exist_ok=True)
    for name in ("outcome-analyst", "scope-adversary", "architecture-reviewer",
                 "completion-adversary"):
        (agents / f"{name}.md").write_text(f"# {name}\n", encoding="utf-8")
    return root


def _write_review(skill_dir, verdict, gate_status="passed"):
    from scripts.file_policy import source_manifest
    rec = ReviewRecord(
        source_manifest=source_manifest(skill_dir),
        activation_required=True,
        activation_reason="test",
        independent_findings=_required_findings(),
        consolidated_decision={"accepted": "test"},
        completion_adversary_report={"role": COMPLETION_ROLE, "verdict": verdict},
        completion_gate_status=gate_status,
    )
    rec.write(skill_dir)


def _error_rules(skill_dir):
    return {f.rule for f in analyze(Skill.from_path(skill_dir)) if f.severity == "error"}


def test_gate_errors_on_incomplete_verdict_with_passed_status(minimal_skill):
    """Dangerous mismatch: adversary says incomplete, gate says passed."""
    _write_review(minimal_skill, verdict="incomplete", gate_status="passed")
    assert "review-adversary-verdict" in _error_rules(minimal_skill)


def test_gate_passes_on_complete_verdict_with_passed_status(minimal_skill):
    """Valid state: adversary confirms complete, gate is passed."""
    _write_review(minimal_skill, verdict="complete", gate_status="passed")
    assert "review-adversary-verdict" not in _error_rules(minimal_skill)


def test_gate_errors_on_missing_verdict_with_passed_status(minimal_skill):
    """Adversary report present but verdict field absent."""
    from scripts.file_policy import source_manifest
    rec = ReviewRecord(
        source_manifest=source_manifest(minimal_skill),
        activation_required=True,
        activation_reason="test",
        independent_findings=_required_findings(),
        consolidated_decision={"accepted": "test"},
        completion_adversary_report={"role": COMPLETION_ROLE},  # no verdict key
        completion_gate_status="passed",
    )
    rec.write(minimal_skill)
    assert "review-adversary-verdict" in _error_rules(minimal_skill)


def test_gate_no_verdict_error_when_status_is_failed(minimal_skill):
    """When gate_status is failed, the verdict check should not fire."""
    _write_review(minimal_skill, verdict="incomplete", gate_status="failed")
    rules = _error_rules(minimal_skill)
    assert "review-adversary-verdict" not in rules
    # Gate still fails for the right reason
    assert "review-gate-not-passed" in rules


def test_gate_no_verdict_error_without_adversary_report(minimal_skill):
    """Missing adversary report triggers missing-adversary, not verdict error."""
    from scripts.file_policy import source_manifest
    rec = ReviewRecord(
        source_manifest=source_manifest(minimal_skill),
        activation_required=True,
        activation_reason="test",
        independent_findings=_required_findings(),
        consolidated_decision={"accepted": "test"},
        completion_gate_status="passed",
    )
    rec.write(minimal_skill)
    rules = _error_rules(minimal_skill)
    assert "review-missing-completion-adversary" in rules
    assert "review-adversary-verdict" not in rules


def test_gate_uppercase_verdict_passes(minimal_skill):
    """Verdict normalised to lowercase; COMPLETE must not trigger the error."""
    from scripts.file_policy import source_manifest
    rec = ReviewRecord(
        source_manifest=source_manifest(minimal_skill),
        activation_required=True,
        activation_reason="test",
        independent_findings=_required_findings(),
        consolidated_decision={"accepted": "test"},
        completion_adversary_report={"role": COMPLETION_ROLE, "verdict": "COMPLETE"},
        completion_gate_status="passed",
    )
    rec.write(minimal_skill)
    assert "review-adversary-verdict" not in _error_rules(minimal_skill)
