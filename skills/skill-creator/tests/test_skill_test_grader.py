"""Tests for skill_test.py: grader completeness, bundled-grader fallback,
temp-file cleanup, and exit-code combination — with a faked `subprocess.run`.
"""
from __future__ import annotations

import json
import os
import sys
import types
from pathlib import Path

import pytest
import yaml

SKILL_PATH = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_PATH))

from scripts import skill_test as ST


def _make_skill(tmp_path, with_grader=True):
    skill = tmp_path / "target skill"      # note: space in path
    (skill / "tests").mkdir(parents=True)
    (skill / "tests" / "expected_behavior.yaml").write_text(
        yaml.safe_dump([{"prompt": "p", "expected_behavior": ["does X", "does Y"]}]),
        encoding="utf-8",
    )
    if with_grader:
        (skill / "agents").mkdir()
        (skill / "agents" / "grader.md").write_text("You are a grader.", encoding="utf-8")
    return skill


def _fake_claude(monkeypatch, grading_obj, returncode=0):
    monkeypatch.setattr(ST, "call_claude_text", lambda *a, **k: json.dumps(grading_obj))


def _grade(tmp_path, skill):
    transcript = tmp_path / "transcript.md"
    transcript.write_text("some transcript", encoding="utf-8")
    out = tmp_path / "grading.json"
    return ST.grade_behavior(skill, transcript, None, str(out))


# --------------------------------------------------------------------------- #
# Grader completeness
# --------------------------------------------------------------------------- #
def test_complete_all_pass_returns_0(monkeypatch, tmp_path):
    skill = _make_skill(tmp_path)
    _fake_claude(monkeypatch, {"expectations": [
        {"text": "does X", "passed": True, "evidence": "e"},
        {"text": "does Y", "passed": True, "evidence": "e"},
    ]})
    assert _grade(tmp_path, skill) == 0


def test_complete_some_fail_returns_2(monkeypatch, tmp_path):
    skill = _make_skill(tmp_path)
    _fake_claude(monkeypatch, {"expectations": [
        {"text": "does X", "passed": True, "evidence": "e"},
        {"text": "does Y", "passed": False, "evidence": "e"},
    ]})
    assert _grade(tmp_path, skill) == 2


def test_partial_response_returns_1(monkeypatch, tmp_path):
    skill = _make_skill(tmp_path)
    _fake_claude(monkeypatch, {"expectations": [
        {"text": "does X", "passed": True, "evidence": "e"},
    ]})
    assert _grade(tmp_path, skill) == 1


def test_empty_response_returns_1(monkeypatch, tmp_path):
    skill = _make_skill(tmp_path)
    _fake_claude(monkeypatch, {"expectations": []})
    assert _grade(tmp_path, skill) == 1


def test_mistyped_passed_returns_1(monkeypatch, tmp_path):
    skill = _make_skill(tmp_path)
    _fake_claude(monkeypatch, {"expectations": [
        {"text": "does X", "passed": "yes", "evidence": "e"},
        {"text": "does Y", "passed": "no", "evidence": "e"},
    ]})
    assert _grade(tmp_path, skill) == 1


def test_bundled_grader_used_when_target_lacks_one(monkeypatch, tmp_path):
    # Target has no agents/grader.md; the bundled one in TOOLKIT_ROOT is used.
    assert (ST.TOOLKIT_ROOT / "agents" / "grader.md").exists()
    skill = _make_skill(tmp_path, with_grader=False)
    _fake_claude(monkeypatch, {"expectations": [
        {"text": "does X", "passed": True, "evidence": "e"},
        {"text": "does Y", "passed": True, "evidence": "e"},
    ]})
    assert _grade(tmp_path, skill) == 0  # graded, not the "no grader" error (1)


# --------------------------------------------------------------------------- #
# Temp eval-set cleanup + exit codes
# --------------------------------------------------------------------------- #
def test_temp_eval_set_removed_on_every_path(monkeypatch, tmp_path):
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "should_trigger.yaml").write_text(
        yaml.safe_dump([{"prompt": "p", "expected": True}]), encoding="utf-8")

    seen = {}

    def fake_run(cmd, **kw):
        path = cmd[cmd.index("--eval-set") + 1]
        seen["path"] = path
        assert os.path.exists(path), "eval set should exist during the run"
        cases = json.loads(Path(path).read_text(encoding="utf-8"))
        return types.SimpleNamespace(
            stdout=json.dumps({
                "results": [{"query": c["query"], "pass": True, "status": "passed"} for c in cases],
                "summary": {"passed": len(cases), "total": len(cases)},
            }),
            stderr="", returncode=0)

    monkeypatch.setattr(ST.subprocess, "run", fake_run)
    rc = ST.run_trigger_tests(tmp_path, tests_dir, [])
    assert rc == 0
    assert not os.path.exists(seen["path"]), "temp eval set must be cleaned up"


@pytest.mark.parametrize("a,b,expected", [
    (0, 0, 0), (0, 2, 2), (2, 0, 2), (2, 2, 2),
    (1, 0, 1), (0, 1, 1), (1, 2, 1), (2, 1, 1),
])
def test_combine_rc(a, b, expected):
    assert ST._combine_rc(a, b) == expected


# --------------------------------------------------------------------------- #
# Programmatic summary.pass_rate (Step 2): derived from validated rows, not model
# --------------------------------------------------------------------------- #
def test_grading_json_includes_summary_pass_rate(monkeypatch, tmp_path):
    skill = _make_skill(tmp_path)
    _fake_claude(monkeypatch, {"expectations": [
        {"text": "does X", "passed": True, "evidence": "e"},
        {"text": "does Y", "passed": False, "evidence": "e"},
    ]})
    out = tmp_path / "grading.json"
    _grade(tmp_path, skill)
    written = json.loads(out.read_text(encoding="utf-8"))
    assert written["summary"] == {"passed": 1, "failed": 1, "total": 2, "pass_rate": 0.5}


def test_grading_summary_all_pass_is_one(monkeypatch, tmp_path):
    skill = _make_skill(tmp_path)
    _fake_claude(monkeypatch, {"expectations": [
        {"text": "does X", "passed": True, "evidence": "e"},
        {"text": "does Y", "passed": True, "evidence": "e"},
    ]})
    out = tmp_path / "grading.json"
    _grade(tmp_path, skill)
    written = json.loads(out.read_text(encoding="utf-8"))
    assert written["summary"]["pass_rate"] == 1.0


# --------------------------------------------------------------------------- #
# validate_grading edge cases
# --------------------------------------------------------------------------- #
def test_empty_evidence_returns_1(monkeypatch, tmp_path):
    skill = _make_skill(tmp_path)
    _fake_claude(monkeypatch, {"expectations": [
        {"text": "does X", "passed": True, "evidence": ""},
        {"text": "does Y", "passed": True, "evidence": "e"},
    ]})
    assert _grade(tmp_path, skill) == 1


def test_whitespace_only_evidence_returns_1(monkeypatch, tmp_path):
    skill = _make_skill(tmp_path)
    _fake_claude(monkeypatch, {"expectations": [
        {"text": "does X", "passed": True, "evidence": "   "},
        {"text": "does Y", "passed": True, "evidence": "e"},
    ]})
    assert _grade(tmp_path, skill) == 1


def test_duplicate_expectation_text_returns_1(monkeypatch, tmp_path):
    skill = _make_skill(tmp_path)
    _fake_claude(monkeypatch, {"expectations": [
        {"text": "does X", "passed": True, "evidence": "e"},
        {"text": "does X", "passed": False, "evidence": "e"},   # duplicate
    ]})
    assert _grade(tmp_path, skill) == 1


def test_unexpected_expectation_text_returns_1(monkeypatch, tmp_path):
    skill = _make_skill(tmp_path)
    _fake_claude(monkeypatch, {"expectations": [
        {"text": "does X", "passed": True, "evidence": "e"},
        {"text": "does Z", "passed": True, "evidence": "e"},    # "does Z" not in spec
    ]})
    assert _grade(tmp_path, skill) == 1
