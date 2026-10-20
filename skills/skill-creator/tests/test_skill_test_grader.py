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
    assert written["summary"] == {
        "passed": 1,
        "failed": 1,
        "undetermined": 0,
        "total": 2,
        "pass_rate": 0.5,
        "verdict": "FAIL",
    }


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


# --------------------------------------------------------------------------- #
# Phase 1: Tri-state verdicts, transcript completeness & provenance
# --------------------------------------------------------------------------- #
def test_tri_state_verdicts_all_pass_returns_0(monkeypatch, tmp_path):
    skill = _make_skill(tmp_path)
    (tmp_path / "transcript.md").write_text("some complete transcript", encoding="utf-8")
    _fake_claude(monkeypatch, {"expectations": [
        {"text": "does X", "verdict": "PASS", "evidence": "found X"},
        {"text": "does Y", "verdict": "PASS", "evidence": "found Y"},
    ]})
    out = tmp_path / "grading.json"
    rc = ST.grade_behavior(skill, tmp_path / "transcript.md", None, str(out))
    assert rc == 0
    written = json.loads(out.read_text(encoding="utf-8"))
    assert written["summary"]["verdict"] == "PASS"
    assert written["summary"]["passed"] == 2
    assert written["summary"]["undetermined"] == 0


def test_tri_state_undetermined_verdict_returns_2(monkeypatch, tmp_path):
    skill = _make_skill(tmp_path)
    (tmp_path / "transcript.md").write_text("some complete transcript", encoding="utf-8")
    _fake_claude(monkeypatch, {"expectations": [
        {"text": "does X", "verdict": "PASS", "evidence": "found X"},
        {"text": "does Y", "verdict": "UNDETERMINED", "evidence": "unclear evidence"},
    ]})
    out = tmp_path / "grading.json"
    rc = ST.grade_behavior(skill, tmp_path / "transcript.md", None, str(out))
    assert rc == 2
    written = json.loads(out.read_text(encoding="utf-8"))
    assert written["summary"]["verdict"] == "UNDETERMINED"
    assert written["summary"]["undetermined"] == 1
    assert written["summary"]["passed"] == 1
    assert written["summary"]["failed"] == 0


def test_invalid_verdict_returns_1(monkeypatch, tmp_path):
    skill = _make_skill(tmp_path)
    _fake_claude(monkeypatch, {"expectations": [
        {"text": "does X", "verdict": "MAYBE", "evidence": "e"},
        {"text": "does Y", "verdict": "PASS", "evidence": "e"},
    ]})
    assert _grade(tmp_path, skill) == 1


def test_transcript_integrity_complete_jsonl(tmp_path):
    jsonl = tmp_path / "complete.jsonl"
    lines = [
        json.dumps({"type": "session_start"}),
        json.dumps({"type": "tool_use", "id": "t1", "tool": "read_file"}),
        json.dumps({"type": "tool_result", "tool_use_id": "t1", "content": "file data"}),
        json.dumps({"type": "stop", "stop_reason": "end_turn"}),
    ]
    jsonl.write_text("\n".join(lines), encoding="utf-8")
    integrity = ST.verify_transcript_integrity(jsonl)
    assert integrity["complete"] is True
    assert integrity["format"] == "jsonl"
    assert integrity["issues"] == []


def test_transcript_integrity_missing_tool_result_jsonl(tmp_path):
    jsonl = tmp_path / "incomplete.jsonl"
    lines = [
        json.dumps({"type": "session_start"}),
        json.dumps({"type": "tool_use", "id": "t1", "tool": "write_file"}),
        json.dumps({"type": "stop", "stop_reason": "end_turn"}),
    ]
    jsonl.write_text("\n".join(lines), encoding="utf-8")
    integrity = ST.verify_transcript_integrity(jsonl)
    assert integrity["complete"] is False
    assert any("Missing tool results" in i for i in integrity["issues"])


def test_transcript_integrity_unclosed_code_fence(tmp_path):
    md = tmp_path / "unclosed.md"
    md.write_text("# Step 1\n```python\nprint(1)\n", encoding="utf-8")
    integrity = ST.verify_transcript_integrity(md)
    assert integrity["complete"] is False
    assert any("Unclosed code fence" in i for i in integrity["issues"])


def test_transcript_integrity_abort_indicator(tmp_path):
    md = tmp_path / "aborted.md"
    md.write_text("# Step 1\nExecuting script...\n[Process interrupted]", encoding="utf-8")
    integrity = ST.verify_transcript_integrity(md)
    assert integrity["complete"] is False
    assert any("abort" in i for i in integrity["issues"])


def test_incomplete_transcript_downgrades_negative_assertion_to_undetermined(monkeypatch, tmp_path):
    skill = tmp_path / "neg_skill"
    (skill / "tests").mkdir(parents=True)
    (skill / "tests" / "expected_behavior.yaml").write_text(
        yaml.safe_dump([{"prompt": "p", "expected_behavior": ["does not leak credentials", "executes tests"]}]),
        encoding="utf-8",
    )
    (skill / "agents").mkdir()
    (skill / "agents" / "grader.md").write_text("You are a grader.", encoding="utf-8")

    # Incomplete transcript with unclosed fence
    transcript = tmp_path / "truncated_transcript.md"
    transcript.write_text("Step 1:\n```bash\necho running\n", encoding="utf-8")

    # Grader erroneously claims both passed
    _fake_claude(monkeypatch, {"expectations": [
        {"text": "does not leak credentials", "passed": True, "verdict": "PASS", "evidence": "no leak observed"},
        {"text": "executes tests", "passed": True, "verdict": "PASS", "evidence": "ran pytest"},
    ]})

    out = tmp_path / "grading.json"
    rc = ST.grade_behavior(skill, transcript, None, str(out))
    # Must return 2 because the negative assertion was downgraded to UNDETERMINED
    assert rc == 2
    written = json.loads(out.read_text(encoding="utf-8"))
    neg_row = next(r for r in written["expectations"] if r["text"] == "does not leak credentials")
    assert neg_row["verdict"] == "UNDETERMINED"
    assert neg_row["passed"] is False
    assert "cannot prove negative assertion" in neg_row["evidence"]
    assert written["summary"]["undetermined"] == 1


def test_behavior_evidence_artifact_and_provenance(monkeypatch, tmp_path):
    skill = _make_skill(tmp_path)
    _fake_claude(monkeypatch, {"expectations": [
        {"text": "does X", "passed": True, "evidence": "found X"},
        {"text": "does Y", "passed": True, "evidence": "found Y"},
    ]})
    transcript = tmp_path / "transcript.md"
    transcript.write_text("complete run\nAll steps finished successfully.", encoding="utf-8")
    out = tmp_path / "grading.json"
    rc = ST.grade_behavior(skill, transcript, None, str(out))
    assert rc == 0

    # Verify behavior_evidence.json was written alongside grading.json
    evidence_file = tmp_path / "behavior_evidence.json"
    assert evidence_file.is_file()
    data = json.loads(evidence_file.read_text(encoding="utf-8"))
    assert "provenance" in data
    prov = data["provenance"]
    assert prov["skill_name"] == skill.name
    assert "transcript_sha256" in prov
    assert prov["transcript_integrity"]["complete"] is True
    assert "timestamp" in prov

