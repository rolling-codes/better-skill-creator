"""Tests for the claim registry checker (spec 5.1 / P1)."""
from __future__ import annotations

import sys
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL))

from scripts.claims_check import analyze, _CLAIMS


def _rules(findings):
    """Return sorted rule IDs from claim-check findings."""
    return sorted(f.rule for f in findings)


def test_real_registry_is_clean():
    """Every seeded claim must resolve to an existing verifier (guards the registry)."""
    assert [f for f in analyze(_CLAIMS) if f.severity == "error"] == []


def _write(tmp_path, body: str) -> Path:
    """Write a temporary claim registry and return its path."""
    p = tmp_path / "claims.yaml"
    p.write_text(body, encoding="utf-8")
    return p


def test_missing_test_function_is_flagged(tmp_path):
    """A claim referencing a nonexistent test produces an unverified finding."""
    claims = _write(tmp_path, """
claims:
  - id: CLM-X
    statement: A claim whose test does not exist.
    sources: [scripts/review.py]
    verifier:
      test: tests/test_bug_prevention.py::test_does_not_exist
    status: verified
""")
    assert "claim-unverified" in _rules(analyze(claims))


def test_bad_status_is_flagged(tmp_path):
    """A claim with an unsupported status produces a schema finding."""
    claims = _write(tmp_path, """
claims:
  - id: CLM-X
    statement: A claim with a bogus status.
    sources: [scripts/review.py]
    verifier:
      test: tests/test_bug_prevention.py::test_P1_one_disposition_does_not_cover_two_identical_findings
    status: definitely
""")
    assert "claim-schema" in _rules(analyze(claims))


def test_manual_verifier_needs_owner_and_date(tmp_path):
    """A manual verifier without an owner and review date is rejected."""
    claims = _write(tmp_path, """
claims:
  - id: CLM-X
    statement: A manual claim missing owner/date.
    sources: [scripts/review.py]
    verifier:
      manual: Someone eyeballs it.
    status: pending
""")
    assert "claim-schema" in _rules(analyze(claims))


def test_valid_pending_claim_passes(tmp_path):
    """A pending verifier with a pending claim status produces no errors."""
    claims = _write(tmp_path, """
claims:
  - id: CLM-X
    statement: A pending claim with no verifier yet.
    sources: [scripts/review.py]
    verifier:
      pending: enforcement is future work
    status: pending
""")
    assert [f for f in analyze(claims) if f.severity == "error"] == []
