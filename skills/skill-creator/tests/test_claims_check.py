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
    ("def test_claim():\n    assert 1 == 1\n", "test_claim", "test_sample.py", True),
    ("def test_claim():\n    assert 1 == 1\n", "test_claim", "sample_test.py", True),
    ("def helper():\n    def test_claim():\n        pass\n", "test_claim", "test_sample.py", False),
    ("class Helper:\n    def test_claim(self):\n        pass\n", "test_claim", "test_sample.py", False),
    ("def helper():\n    pass\n", "helper", "test_sample.py", False),
    ("def test_claim():\n    pass\n", "test_claim", "helper.py", False),
])
def test_verifier_requires_collectable_top_level_test(tmp_path, monkeypatch, source, name, filename, expected):
    """Only top-level tests in files matching pytest's naming rules resolve."""
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
    """Manual and pending claims produce the expected diagnostics and exit codes."""
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
    """Duplicate verifier keys produce a registry error and a failing CLI exit."""
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


@pytest.mark.parametrize("body, expected", [
    ("def test_claim():\n    assert 1 == 1\n", True),
    ("def test_claim():\n    pass\n", False),
    ('def test_claim():\n    """only a docstring"""\n', False),
    ("import pytest\n\n@pytest.mark.skip\ndef test_claim():\n    assert 1 == 1\n", False),
    ("import pytest\n\n@pytest.mark.skipif(True, reason='x')\ndef test_claim():\n    assert 1 == 1\n", False),
    ("import pytest\n\n@pytest.mark.xfail\ndef test_claim():\n    assert 1 == 1\n", False),
])
def test_a_hollow_or_skipped_test_does_not_verify_a_claim(tmp_path, monkeypatch, body, expected):
    """A verifier that is skipped, xfailed, or has no statement besides pass/docstring proves nothing."""
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_sample.py").write_text(body, encoding="utf-8")
    monkeypatch.setattr(claims_check, "_SKILL_DIR", tmp_path)
    assert claims_check._test_function_exists("tests/test_sample.py::test_claim") is expected


def test_a_claim_source_that_does_not_exist_is_an_error(tmp_path, monkeypatch):
    skill = tmp_path / "skills" / "skill-creator"
    skill.mkdir(parents=True)
    (tmp_path / "bsc.py").write_text("x", encoding="utf-8")
    monkeypatch.setattr(claims_check, "_SKILL_DIR", skill)
    base = {"id": "CLM-X-001", "statement": "s", "status": "pending", "verifier": {"pending": "later"}}
    ok = claims_check._check_claim({**base, "sources": ["bsc.py  # repo-root file"]})
    ghost = claims_check._check_claim({**base, "sources": ["scripts/GHOST.py"]})
    assert [f.rule for f in ok if f.severity == "error"] == []
    assert [f.rule for f in ghost if f.severity == "error"] == ["claim-source"]


@pytest.mark.parametrize("body, expected", [
    # a conditional skip still runs, so it can verify; only an unconditional one cannot
    ("import pytest\n\n@pytest.mark.skipif(False, reason='x')\ndef test_claim():\n    assert 1 == 1\n", True),
    ("import sys, pytest\n\n@pytest.mark.skipif(sys.platform == 'nope', reason='x')\ndef test_claim():\n    assert 1 == 1\n", True),
    ("import pytest\n\n@pytest.mark.skipif(True, reason='x')\ndef test_claim():\n    assert 1 == 1\n", False),
    ("def skip(f):\n    return f\n\n@skip\ndef test_claim():\n    assert 1 == 1\n", True),  # user-defined helper
    ("def test_claim():\n    assert True\n", False),
    ("def test_claim():\n    raise NotImplementedError\n", False),
    ("import pytest\n\ndef test_claim():\n    pytest.skip('later')\n", False),
    ("import pytest\n\npytestmark = pytest.mark.skip(reason='x')\n\ndef test_claim():\n    assert 1 == 1\n", False),
    ("import pytest\n\npytestmark = [pytest.mark.xfail]\n\ndef test_claim():\n    assert 1 == 1\n", False),
    # a skip under a real condition still verifies on the other paths, so it counts (documented heuristic)
    ("import pytest\n\ndef test_claim():\n    if 1 == 2:\n        pytest.skip('x')\n    assert 1 == 1\n", True),
])
def test_hollow_test_detection_edges(tmp_path, monkeypatch, body, expected):
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_sample.py").write_text(body, encoding="utf-8")
    monkeypatch.setattr(claims_check, "_SKILL_DIR", tmp_path)
    assert claims_check._test_function_exists("tests/test_sample.py::test_claim") is expected


def test_a_claim_source_must_live_inside_the_skill_or_repo(tmp_path, monkeypatch):
    skill = tmp_path / "skills" / "skill-creator"
    skill.mkdir(parents=True)
    monkeypatch.setattr(claims_check, "_SKILL_DIR", skill)
    base = {"id": "CLM-X-002", "statement": "s", "status": "pending", "verifier": {"pending": "later"}}
    outside = str(Path(sys.executable))  # exists, but is neither under the skill nor the repo root
    findings = claims_check._check_claim({**base, "sources": [outside, "../../../escape.txt"]})
    assert [f.rule for f in findings if f.severity == "error"] == ["claim-source", "claim-source"]


def test_an_empty_source_entry_is_an_error(tmp_path, monkeypatch):
    skill = tmp_path / "skills" / "skill-creator"
    skill.mkdir(parents=True)
    monkeypatch.setattr(claims_check, "_SKILL_DIR", skill)
    base = {"id": "CLM-X-003", "statement": "s", "status": "pending", "verifier": {"pending": "later"}}
    for empty in ("", "   ", "# just a comment"):
        findings = claims_check._check_claim({**base, "sources": [empty]})
        assert [f.rule for f in findings if f.severity == "error"] == ["claim-source"], repr(empty)


def test_a_removed_claim_may_cite_sources_that_no_longer_exist(tmp_path, monkeypatch):
    skill = tmp_path / "skills" / "skill-creator"
    skill.mkdir(parents=True)
    monkeypatch.setattr(claims_check, "_SKILL_DIR", skill)
    removed = {"id": "CLM-X-004", "statement": "s", "status": "removed", "sources": ["scripts/long_gone.py"]}
    assert [f for f in claims_check._check_claim(removed) if f.severity == "error"] == []


def test_an_unresolvable_claim_source_is_not_a_usable_source(tmp_path, monkeypatch):
    monkeypatch.setattr(claims_check, "_SKILL_DIR", tmp_path / "skills" / "skill-creator")

    def boom(self, *args, **kwargs):
        raise RuntimeError("Symlink loop")

    monkeypatch.setattr(Path, "resolve", boom)
    assert claims_check._source_exists("looped/file.py") is False


def test_an_annotated_module_level_skip_marks_every_test_hollow(tmp_path, monkeypatch):
    body = ("import pytest\n\npytestmark: list = [pytest.mark.skip(reason='x')]\n\n"
            "def test_claim():\n    assert 1 == 1\n")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_sample.py").write_text(body, encoding="utf-8")
    monkeypatch.setattr(claims_check, "_SKILL_DIR", tmp_path)
    assert claims_check._test_function_exists("tests/test_sample.py::test_claim") is False
