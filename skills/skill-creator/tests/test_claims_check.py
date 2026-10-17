"""Tests for the claim registry checker (spec 5.1 / P1)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

SKILL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL))

from scripts import claims_check
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


@pytest.mark.parametrize("source, name, filename, expected", [
    ("def test_claim():\n    pass\n", "test_claim", "test_sample.py", True),
    ("def test_claim():\n    pass\n", "test_claim", "sample_test.py", True),
    ("def helper():\n    def test_claim():\n        pass\n", "test_claim", "test_sample.py", False),
    ("class Helper:\n    def test_claim(self):\n        pass\n", "test_claim", "test_sample.py", False),
    ("def helper():\n    pass\n", "helper", "test_sample.py", False),
    ("def test_claim():\n    pass\n", "test_claim", "helper.py", False),
])
def test_verifier_requires_collectable_top_level_test(tmp_path, monkeypatch, source, name, filename, expected):
    monkeypatch.setattr(claims_check, "_SKILL_DIR", tmp_path)
    (tmp_path / filename).write_text(source, encoding="utf-8")
    assert claims_check._test_function_exists(f"{filename}::{name}") is expected


@pytest.mark.parametrize("verifier, status, rule, exit_code", [
    ("manual: Inspect it\n      owner: Reviewer\n      review_date: 2026-10-17", "pending", "claim-manual", 0),
    ("manual: Inspect it", "pending", "claim-schema", 1),
    ("pending: Future work", "pending", "claim-pending", 0),
    ("pending: Future work", "verified", "claim-status", 1),
])
def test_manual_and_pending_cli_output(tmp_path, monkeypatch, capsys, verifier, status, rule, exit_code):
    claims = _write(tmp_path, f"""
claims:
  - id: CLM-X
    statement: A claim awaiting verification.
    sources: [scripts/review.py]
    verifier:
      {verifier}
    status: {status}
""")
    monkeypatch.setattr(sys, "argv", ["claims_check", str(claims)])
    assert claims_check._main() == exit_code
    output = capsys.readouterr().out
    assert rule in output
    if exit_code == 0:
        assert f"[INFO] {rule}" in output
        assert "0 error(s), 0 warning(s)" in output


@pytest.mark.parametrize("duplicate", [
    "    verifier: {pending: Future work}\n    verifier: {pending: Replacement}",
    "    verifier:\n      pending: Future work\n      pending: Replacement",
])
def test_duplicate_yaml_keys_are_rejected(tmp_path, monkeypatch, capsys, duplicate):
    claims = _write(tmp_path, f"""
claims:
  - id: CLM-X
    statement: Duplicate verifier keys must not be overwritten.
    sources: [scripts/review.py]
{duplicate}
    status: pending
""")
    findings = analyze(claims)
    assert [(f.severity, f.rule) for f in findings] == [("error", "claim-registry")]
    assert "duplicate key" in findings[0].message
    monkeypatch.setattr(sys, "argv", ["claims_check", str(claims)])
    assert claims_check._main() == 1
    assert "duplicate key" in capsys.readouterr().out
