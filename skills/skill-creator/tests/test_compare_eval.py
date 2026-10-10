"""Regression tests for compare_eval.py (G1 baseline enforcement)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SKILL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL))

from scripts.compare_eval import (
    load_result,
    validate_compatibility,
    compute_delta,
    format_report,
    compare_main,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _result(skill_name="my-skill", queries=None, model="sonnet",
            infra_failed=False):
    """Build a minimal eval result dict."""
    queries = queries or [
        {"q": "trigger me", "should_trigger": True, "trigger_rate": 0.8,
         "ok_runs": 5, "failed_runs": 0, "pass": True},
        {"q": "ignore me", "should_trigger": False, "trigger_rate": 0.1,
         "ok_runs": 5, "failed_runs": 0, "pass": True},
    ]
    rows = [
        {"query": q["q"], "should_trigger": q["should_trigger"],
         "trigger_rate": q["trigger_rate"], "ok_runs": q["ok_runs"],
         "failed_runs": q["failed_runs"], "pass": q["pass"]}
        for q in queries
    ]
    total = len(rows)
    passed = sum(1 for r in rows if r["pass"])
    return {
        "skill_name": skill_name,
        "description": "test",
        "model": model,
        "results": rows,
        "summary": {
            "total": total, "passed": passed, "failed": total - passed,
            "errored": 0, "infrastructure_failed": infra_failed,
            "status": "incomplete" if infra_failed else "passed" if passed == total else "failed",
        },
        "max_calls": total,
        "behavior_status": "not_tested",
    }


# ---------------------------------------------------------------------------
# load_result
# ---------------------------------------------------------------------------

def test_load_result_valid(tmp_path):
    r = _result()
    p = tmp_path / "result.json"
    p.write_text(json.dumps(r), encoding="utf-8")
    loaded = load_result(p)
    assert loaded["skill_name"] == "my-skill"


def test_load_result_missing_file(tmp_path):
    with pytest.raises(OSError):
        load_result(tmp_path / "missing.json")


def test_load_result_not_a_mapping(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text("[1, 2, 3]", encoding="utf-8")
    with pytest.raises(ValueError, match="JSON object"):
        load_result(p)


def test_load_result_missing_skill_name(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text(json.dumps({"results": [], "summary": {}}), encoding="utf-8")
    with pytest.raises(ValueError, match="skill_name"):
        load_result(p)


def test_load_result_missing_results(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text(json.dumps({"skill_name": "x", "summary": {}}), encoding="utf-8")
    with pytest.raises(ValueError, match="results"):
        load_result(p)


# ---------------------------------------------------------------------------
# validate_compatibility — errors
# ---------------------------------------------------------------------------

def test_different_skill_name_is_error():
    errors, _ = validate_compatibility(_result("a"), _result("b"))
    assert any("skill_name mismatch" in e for e in errors)


def test_no_overlapping_queries_is_error():
    c = _result(queries=[{"q": "A", "should_trigger": True, "trigger_rate": 1.0,
                           "ok_runs": 3, "failed_runs": 0, "pass": True}])
    b = _result(queries=[{"q": "B", "should_trigger": True, "trigger_rate": 0.0,
                           "ok_runs": 3, "failed_runs": 0, "pass": False}])
    errors, _ = validate_compatibility(c, b)
    assert any("no overlapping" in e for e in errors)


def test_candidate_infrastructure_failed_is_error():
    c = _result(infra_failed=True)
    errors, _ = validate_compatibility(c, _result())
    assert any("infrastructure_failed" in e and "candidate" in e for e in errors)


def test_baseline_infrastructure_failed_is_error():
    b = _result(infra_failed=True)
    errors, _ = validate_compatibility(_result(), b)
    assert any("infrastructure_failed" in e and "baseline" in e for e in errors)


# ---------------------------------------------------------------------------
# validate_compatibility — warnings
# ---------------------------------------------------------------------------

def test_different_models_is_warning():
    c = _result(model="sonnet")
    b = _result(model="haiku")
    errors, warnings = validate_compatibility(c, b)
    assert not errors
    assert any("model mismatch" in w for w in warnings)


def test_same_models_no_warning():
    _, warnings = validate_compatibility(_result(model="sonnet"), _result(model="sonnet"))
    assert not any("model mismatch" in w for w in warnings)


def test_candidate_zero_ok_runs_is_warning():
    c = _result(queries=[{"q": "x", "should_trigger": True, "trigger_rate": 0.0,
                           "ok_runs": 0, "failed_runs": 3, "pass": False}])
    b = _result(queries=[{"q": "x", "should_trigger": True, "trigger_rate": 0.8,
                           "ok_runs": 5, "failed_runs": 0, "pass": True}])
    _, warnings = validate_compatibility(c, b)
    assert any("only 0 valid run" in w and "candidate" in w for w in warnings)


def test_low_sample_warns_at_one_and_two_runs():
    # 1-2 valid runs is below the min-run gate (3); it must warn, not pass silently.
    for n in (1, 2):
        c = _result(queries=[{"q": "x", "should_trigger": True, "trigger_rate": 0.8,
                               "ok_runs": n, "failed_runs": 0, "pass": True}])
        b = _result(queries=[{"q": "x", "should_trigger": True, "trigger_rate": 0.8,
                               "ok_runs": 5, "failed_runs": 0, "pass": True}])
        _, warnings = validate_compatibility(c, b)
        assert any(f"only {n} valid run" in w and "candidate" in w for w in warnings)


def test_no_low_sample_warning_at_three_runs():
    c = _result(queries=[{"q": "x", "should_trigger": True, "trigger_rate": 0.8,
                           "ok_runs": 3, "failed_runs": 0, "pass": True}])
    b = _result(queries=[{"q": "x", "should_trigger": True, "trigger_rate": 0.8,
                           "ok_runs": 3, "failed_runs": 0, "pass": True}])
    _, warnings = validate_compatibility(c, b)
    assert not any("valid run" in w for w in warnings)


def test_partial_overlap_produces_warnings():
    shared_q = {"q": "shared", "should_trigger": True, "trigger_rate": 0.8,
                "ok_runs": 3, "failed_runs": 0, "pass": True}
    only_c = {"q": "only-cand", "should_trigger": True, "trigger_rate": 1.0,
              "ok_runs": 3, "failed_runs": 0, "pass": True}
    only_b = {"q": "only-base", "should_trigger": False, "trigger_rate": 0.0,
              "ok_runs": 3, "failed_runs": 0, "pass": True}
    c = _result(queries=[shared_q, only_c])
    b = _result(queries=[shared_q, only_b])
    errors, warnings = validate_compatibility(c, b)
    assert not errors
    assert any("only in candidate" in w for w in warnings)
    assert any("only in baseline" in w for w in warnings)


# ---------------------------------------------------------------------------
# compute_delta
# ---------------------------------------------------------------------------

def _queries(trigger_rate, ok_runs=5, should_trigger=True):
    return [{"q": f"q{i}", "should_trigger": should_trigger,
             "trigger_rate": trigger_rate, "ok_runs": ok_runs,
             "failed_runs": 0, "pass": trigger_rate >= 0.5 if should_trigger else trigger_rate < 0.5}
            for i in range(3)]


def test_delta_positive_when_candidate_better():
    # baseline at 0.3 fails the default 0.5 threshold; candidate at 0.9 passes
    c = _result(queries=_queries(0.9))
    b = _result(queries=_queries(0.3))
    delta = compute_delta(c, b)
    assert delta["aggregate"]["delta"] > 0


def test_delta_negative_when_candidate_worse():
    c = _result(queries=_queries(0.3))
    b = _result(queries=_queries(0.9))
    delta = compute_delta(c, b)
    assert delta["aggregate"]["delta"] < 0


def test_significance_claim_requires_min_ok_runs():
    c = _result(queries=_queries(0.9, ok_runs=2))
    b = _result(queries=_queries(0.5, ok_runs=2))
    delta = compute_delta(c, b)
    assert not delta["significance_claim"]
    assert delta["min_ok_runs"] == 2


def test_significance_claim_allowed_with_sufficient_runs():
    c = _result(queries=_queries(0.9, ok_runs=3))
    b = _result(queries=_queries(0.5, ok_runs=3))
    delta = compute_delta(c, b)
    assert delta["significance_claim"]


def test_per_query_deltas_computed():
    q = [{"q": "A", "should_trigger": True, "trigger_rate": 0.9,
           "ok_runs": 5, "failed_runs": 0, "pass": True}]
    c = _result(queries=q)
    b_q = [{"q": "A", "should_trigger": True, "trigger_rate": 0.5,
             "ok_runs": 5, "failed_runs": 0, "pass": True}]
    b = _result(queries=b_q)
    delta = compute_delta(c, b)
    assert delta["per_query"][0]["delta"] == pytest.approx(0.4, abs=1e-4)


def test_improvement_positive_when_no_trigger_candidate_triggers_less():
    # NO-TRIGGER query: candidate triggers LESS than baseline → improvement > 0.
    c = _result(queries=[{"q": "ignore", "should_trigger": False, "trigger_rate": 0.1,
                           "ok_runs": 5, "failed_runs": 0, "pass": True}])
    b = _result(queries=[{"q": "ignore", "should_trigger": False, "trigger_rate": 0.6,
                           "ok_runs": 5, "failed_runs": 0, "pass": False}])
    pq = compute_delta(c, b)["per_query"][0]
    assert pq["delta"] == pytest.approx(-0.5, abs=1e-4)      # raw rate dropped
    assert pq["improvement"] == pytest.approx(0.5, abs=1e-4)  # but that is an improvement


def test_improvement_negative_when_no_trigger_candidate_triggers_more():
    c = _result(queries=[{"q": "ignore", "should_trigger": False, "trigger_rate": 0.7,
                           "ok_runs": 5, "failed_runs": 0, "pass": False}])
    b = _result(queries=[{"q": "ignore", "should_trigger": False, "trigger_rate": 0.1,
                           "ok_runs": 5, "failed_runs": 0, "pass": True}])
    pq = compute_delta(c, b)["per_query"][0]
    assert pq["improvement"] == pytest.approx(-0.6, abs=1e-4)


def test_improvement_equals_raw_delta_for_trigger_queries():
    c = _result(queries=[{"q": "fire", "should_trigger": True, "trigger_rate": 0.9,
                           "ok_runs": 5, "failed_runs": 0, "pass": True}])
    b = _result(queries=[{"q": "fire", "should_trigger": True, "trigger_rate": 0.5,
                           "ok_runs": 5, "failed_runs": 0, "pass": True}])
    pq = compute_delta(c, b)["per_query"][0]
    assert pq["improvement"] == pytest.approx(pq["delta"], abs=1e-9)
    assert pq["improvement"] == pytest.approx(0.4, abs=1e-4)


def test_only_shared_queries_are_compared():
    shared = {"q": "shared", "should_trigger": True, "trigger_rate": 0.8,
              "ok_runs": 5, "failed_runs": 0, "pass": True}
    extra = {"q": "extra", "should_trigger": True, "trigger_rate": 1.0,
              "ok_runs": 5, "failed_runs": 0, "pass": True}
    c = _result(queries=[shared, extra])
    b = _result(queries=[shared])
    delta = compute_delta(c, b)
    assert delta["shared_queries"] == 1
    assert all(pq["query"] == "shared" for pq in delta["per_query"])


# ---------------------------------------------------------------------------
# compare_main (end-to-end)
# ---------------------------------------------------------------------------

def test_compare_main_missing_baseline(tmp_path):
    c_path = tmp_path / "cand.json"
    c_path.write_text(json.dumps(_result()), encoding="utf-8")
    result, code = compare_main(c_path, tmp_path / "missing.json")
    assert code == 1
    assert result["status"] in ("error", "invalid")


def test_compare_main_incompatible_names(tmp_path):
    c_path = tmp_path / "c.json"
    b_path = tmp_path / "b.json"
    c_path.write_text(json.dumps(_result("skill-a")), encoding="utf-8")
    b_path.write_text(json.dumps(_result("skill-b")), encoding="utf-8")
    result, code = compare_main(c_path, b_path)
    assert code == 1
    assert result["status"] == "invalid"
    assert any("skill_name mismatch" in e for e in result["errors"])


def test_compare_main_valid_returns_report(tmp_path):
    c_path = tmp_path / "c.json"
    b_path = tmp_path / "b.json"
    c_path.write_text(json.dumps(_result()), encoding="utf-8")
    b_path.write_text(json.dumps(_result()), encoding="utf-8")
    result, code = compare_main(c_path, b_path)
    assert code == 0
    assert result["status"] == "complete"
    assert "comparison" in result
    assert "report" in result


def test_compare_main_infrastructure_failed_errors(tmp_path):
    c_path = tmp_path / "c.json"
    b_path = tmp_path / "b.json"
    c_path.write_text(json.dumps(_result(infra_failed=True)), encoding="utf-8")
    b_path.write_text(json.dumps(_result()), encoding="utf-8")
    result, code = compare_main(c_path, b_path)
    assert code == 1
