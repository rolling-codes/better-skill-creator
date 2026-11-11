"""Infra failure diagnostics in run_eval.py and run_loop.py (Fix 5).

_check_infra() must return a QueryOutcome. run_eval() must embed the failure
category and detail in the report. run_loop() must propagate them, and must
leave held_out_score absent (None) when the held-out eval itself fails.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

SKILL_PATH = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_PATH))

from scripts import run_eval as RE
from scripts import run_loop as RL
from scripts.structured_logging import ErrorCategory, QueryOutcome


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _make_infra_spy(outcome: QueryOutcome):
    """Return a fake _check_infra that returns the given outcome."""
    def fake(*args, **kwargs):
        return outcome
    return fake


def _run_eval_with_infra(monkeypatch, outcome: QueryOutcome):
    monkeypatch.setattr(RE, "_check_infra", _make_infra_spy(outcome))
    return RE.run_eval(
        [{"query": "some query", "should_trigger": True}],
        "my-skill", "my description", 1, 60.0,
        max_calls=20,
    )


# --------------------------------------------------------------------------- #
# run_eval: failure category propagated to report
# --------------------------------------------------------------------------- #

def test_timeout_failure_category_in_report(monkeypatch):
    result = _run_eval_with_infra(
        monkeypatch,
        QueryOutcome.failure(ErrorCategory.TIMEOUT, "exceeded 60s"),
    )
    assert result["summary"]["infrastructure_failed"]
    assert result["infrastructure_error"] == "timeout"
    assert "60s" in (result.get("infrastructure_error_detail") or "")
    assert result["results"] == []


def test_authentication_failure_category_in_report(monkeypatch):
    result = _run_eval_with_infra(
        monkeypatch,
        QueryOutcome.failure(ErrorCategory.AUTHENTICATION, "invalid api key"),
    )
    assert result["infrastructure_error"] == "authentication"
    assert "invalid api key" in (result.get("infrastructure_error_detail") or "")


def test_not_triggered_failure_in_report(monkeypatch):
    result = _run_eval_with_infra(
        monkeypatch,
        QueryOutcome.not_triggered_ok(),
    )
    assert result["summary"]["infrastructure_failed"]
    # not_triggered_ok has no failure category — 'unknown' or the enum value
    assert "infrastructure_error" in result


def test_zero_results_on_infra_failure(monkeypatch):
    result = _run_eval_with_infra(
        monkeypatch,
        QueryOutcome.failure(ErrorCategory.SUBPROCESS_CRASH, "process died"),
    )
    assert result["results"] == []
    assert result["summary"]["total"] == 0


# --------------------------------------------------------------------------- #
# run_loop: infrastructure_error propagated to loop result
# --------------------------------------------------------------------------- #

def _canned_infra_failure(error: str, detail: str) -> dict:
    return {
        "results": [],
        "summary": {"total": 0, "passed": 0, "failed": 0,
                    "errored": 1, "infrastructure_failed": True},
        "infrastructure_error": error,
        "infrastructure_error_detail": detail,
    }


def test_run_loop_propagates_infra_error(monkeypatch, tmp_path):
    canned = _canned_infra_failure("timeout", "exceeded 60s")
    monkeypatch.setattr(RL, "run_eval", lambda **kw: canned)
    monkeypatch.setattr(RL, "parse_skill_md", lambda p: ("demo", "desc", "content"))
    monkeypatch.setattr(RL, "improve_description", lambda **kw: (_ for _ in ()).throw(AssertionError("must not be called")))

    out = RL.run_loop(
        eval_set=[{"query": "q1", "should_trigger": True}, {"query": "q2", "should_trigger": False}],
        skill_path=tmp_path, description_override=None,
        num_workers=1, timeout=5, max_iterations=3, runs_per_query=1,
        trigger_threshold=0.5, holdout=0, model="x", verbose=False,
        live_report_path=None, log_dir=None,
    )
    assert out["exit_reason"].startswith("infrastructure_failed")
    assert out.get("infrastructure_error") == "timeout"
    assert "60s" in (out.get("infrastructure_error_detail") or "")


def test_run_loop_infra_error_none_on_clean_exit(monkeypatch, tmp_path):
    passing = {
        "results": [
            {"query": "q1", "should_trigger": True, "pass": True,
             "triggers": 1, "runs": 1, "trigger_rate": 1.0},
        ],
        "summary": {"total": 1, "passed": 1, "failed": 0,
                    "errored": 0, "infrastructure_failed": False},
    }
    monkeypatch.setattr(RL, "run_eval", lambda **kw: passing)
    monkeypatch.setattr(RL, "parse_skill_md", lambda p: ("demo", "desc", "content"))
    monkeypatch.setattr(RL, "improve_description", lambda **kw: "new desc")

    out = RL.run_loop(
        eval_set=[{"query": "q1", "should_trigger": True}],
        skill_path=tmp_path, description_override=None,
        num_workers=1, timeout=5, max_iterations=1, runs_per_query=1,
        trigger_threshold=0.5, holdout=0, model="x", verbose=False,
        live_report_path=None, log_dir=None,
    )
    assert out.get("infrastructure_error") is None
    assert out.get("infrastructure_error_detail") is None


# --------------------------------------------------------------------------- #
# run_loop: held-out infra failure → held_out_score is None
# --------------------------------------------------------------------------- #

def test_held_out_infra_failure_leaves_score_none(monkeypatch, tmp_path):
    passing = {
        "results": [
            {"query": "q1", "should_trigger": True, "pass": True,
             "triggers": 1, "runs": 1, "trigger_rate": 1.0},
            {"query": "q2", "should_trigger": False, "pass": True,
             "triggers": 0, "runs": 1, "trigger_rate": 0.0},
            {"query": "q3", "should_trigger": True, "pass": True,
             "triggers": 1, "runs": 1, "trigger_rate": 1.0},
            {"query": "q4", "should_trigger": False, "pass": True,
             "triggers": 0, "runs": 1, "trigger_rate": 0.0},
            {"query": "q5", "should_trigger": True, "pass": True,
             "triggers": 1, "runs": 1, "trigger_rate": 1.0},
            {"query": "q6", "should_trigger": False, "pass": True,
             "triggers": 0, "runs": 1, "trigger_rate": 0.0},
        ],
        "summary": {"total": 6, "passed": 6, "failed": 0,
                    "errored": 0, "infrastructure_failed": False},
    }
    held_infra_fail = _canned_infra_failure("authentication", "bad key")

    call_count = [0]

    def fake_run_eval(**kw):
        call_count[0] += 1
        # First call (loop) passes; second call (held-out) fails with infra
        return passing if call_count[0] == 1 else held_infra_fail

    monkeypatch.setattr(RL, "run_eval", fake_run_eval)
    monkeypatch.setattr(RL, "parse_skill_md", lambda p: ("demo", "desc", "content"))
    monkeypatch.setattr(RL, "improve_description", lambda **kw: "new desc")

    out = RL.run_loop(
        eval_set=[
            {"query": "q1", "should_trigger": True},
            {"query": "q2", "should_trigger": False},
            {"query": "q3", "should_trigger": True},
            {"query": "q4", "should_trigger": False},
            {"query": "q5", "should_trigger": True},
            {"query": "q6", "should_trigger": False},
        ],
        skill_path=tmp_path, description_override=None,
        num_workers=1, timeout=5, max_iterations=1, runs_per_query=1,
        trigger_threshold=0.5, holdout=0.3, val_holdout=0.3, model="x", verbose=False,
        live_report_path=None, log_dir=None,
    )
    assert out["held_out_score"] is None, (
        f"Expected None for held_out_score when held-out eval fails infra check, got {out['held_out_score']!r}"
    )
