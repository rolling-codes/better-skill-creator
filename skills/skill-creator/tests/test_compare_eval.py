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

def _result(skill_name="my-skill", queries=None, model: str | None = "sonnet",
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


@pytest.mark.parametrize("row", [None, [], "query", 1, {}, {"query": None},
                                 {"query": 1}, {"query": []}, {"query": {}}])
@pytest.mark.parametrize("invalid_side", ["candidate", "baseline"])
def test_malformed_rows_return_input_error(tmp_path, row, invalid_side):
    paths = {}
    for side in ("candidate", "baseline"):
        data = _result()
        if side == invalid_side:
            data["results"].append(row)
        paths[side] = tmp_path / f"{side}.json"
        paths[side].write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match=r"results\[2\].*string 'query'"):
        load_result(paths[invalid_side])
    result, code = compare_main(paths["candidate"], paths["baseline"])
    assert code == 1
    assert result["status"] == "error"
    assert "results[2]" in result["error"]


# Model-envelope comparisons preserve raw single-result compatibility.
from scripts.compare_eval import normalize_result, validate_baseline, compare_results


def test_normalize_all_result_shapes():
    raw = _result()
    assert normalize_result(raw) == {"sonnet": raw}
    assert normalize_result({"trigger": raw}) == {"sonnet": raw}
    assert normalize_result({"trigger_by_model": {"sonnet": raw}}) == {"sonnet": raw}


def test_matrix_model_key_must_match_nested_model():
    with pytest.raises(ValueError, match="disagrees"):
        normalize_result({"trigger_by_model": {"haiku": _result()}})


@pytest.mark.parametrize("missing", [True, False])
def test_matrix_requires_explicit_nested_model(tmp_path, missing):
    raw = _result(model=None)
    if missing:
        del raw["model"]
    assert compare_results(raw, raw)[1] == 0  # Historical raw pairs retain permissive identity handling.
    data = {"trigger_by_model": {"sonnet": raw}}
    with pytest.raises(ValueError, match="explicit.*model"):
        normalize_result(data)
    assert compare_results(data, {"trigger": _result()})[1] == 1
    path = tmp_path / "baseline.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="explicit.*model"):
        validate_baseline(path, ["sonnet"])


def test_baseline_rejects_unidentified_unrequested_result(tmp_path):
    data = {"trigger_by_model": {"sonnet": _result(), "haiku": _result(model=None)}}
    path = tmp_path / "baseline.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="explicit.*model"):
        validate_baseline(path, ["sonnet"])


def test_matrix_compares_models_independent_of_order():
    matrix = {"sonnet": _result(), "haiku": _result(model="haiku")}
    result, code = compare_results({"trigger_by_model": matrix},
                                   {"trigger_by_model": dict(reversed(list(matrix.items())))})
    assert code == 0
    assert result["status"] == "complete"
    assert set(result["comparisons_by_model"]) == set(matrix)


def test_missing_model_retains_healthy_comparison():
    result, code = compare_results(
        {"trigger_by_model": {"sonnet": _result(), "haiku": _result(model="haiku")}},
        {"trigger": _result()})
    assert code == 1
    assert result["status"] == "incomplete"
    assert result["missing_models"]["baseline"] == ["haiku"]
    assert result["comparisons_by_model"]["sonnet"]["status"] == "complete"


def test_matrix_infrastructure_failure_is_incomplete():
    baseline = {"sonnet": _result(), "haiku": _result(model="haiku")}
    candidate = {**baseline, "haiku": _result(model="haiku", infra_failed=True)}
    result, code = compare_results({"trigger_by_model": candidate}, {"trigger_by_model": baseline})
    assert code == 1
    assert result["comparisons_by_model"]["sonnet"]["status"] == "complete"
    assert result["comparisons_by_model"]["haiku"]["status"] == "invalid"


def test_unknown_envelope_models_do_not_pair():
    result, code = compare_results({"trigger": _result(model=None)}, {"trigger": _result(model=None)})
    assert code == 1
    assert "unknown" in result["errors"][0]


def test_duplicate_query_rejected():
    raw = _result()
    raw["results"].append(raw["results"][0])
    with pytest.raises(ValueError, match="duplicate query"):
        normalize_result(raw)


def test_conflicting_expected_label_rejected():
    candidate, baseline = _result(), _result()
    candidate["results"][0]["should_trigger"] = False
    result, code = compare_results(candidate, baseline)
    assert code == 1
    assert any("conflicting should_trigger" in e for e in result["errors"])


@pytest.mark.parametrize("requested, model, error", [
    ([None], "sonnet", "explicit"), (["default"], None, "explicit"),
    (["haiku"], None, "explicit"), (["haiku"], "sonnet", "missing")])
def test_baseline_preflight_identity(tmp_path, requested, model, error):
    path = tmp_path / "baseline.json"
    path.write_text(json.dumps(_result(model=model)), encoding="utf-8")
    with pytest.raises(ValueError, match=error):
        validate_baseline(path, requested)


def test_baseline_preflight_skill_and_infrastructure(tmp_path):
    path = tmp_path / "baseline.json"
    path.write_text(json.dumps(_result(infra_failed=True)), encoding="utf-8")
    with pytest.raises(ValueError, match="infrastructure_failed"):
        validate_baseline(path, ["sonnet"])
    with pytest.raises(ValueError, match="skill_name mismatch"):
        validate_baseline(path, ["sonnet"], skill_name="another")


def test_baseline_preflight_accepts_known_matrix(tmp_path):
    path = tmp_path / "baseline.json"
    path.write_text(json.dumps({"trigger_by_model": {"sonnet": _result()}}), encoding="utf-8")
    assert set(validate_baseline(path, ["sonnet"], skill_name="my-skill")) == {"sonnet"}


def test_matrix_regression_completes_and_sample_claim_is_qualified():
    result, code = compare_results({"trigger": _result(queries=_queries(0.1))},
                                   {"trigger": _result(queries=_queries(0.9))})
    assert code == 0
    comparison = result["comparisons_by_model"]["sonnet"]
    assert comparison["comparison"]["aggregate"]["delta"] < 0
    assert comparison["comparison"]["sample_sufficient"]
    assert "not a statistical significance test" in result["report"]


def test_baseline_preflight_selects_requested_subset(tmp_path):
    path = tmp_path / "baseline.json"
    path.write_text(json.dumps({"trigger_by_model": {
        "sonnet": _result(), "haiku": _result(model="haiku")}}), encoding="utf-8")
    assert set(validate_baseline(path, ["haiku"])) == {"haiku"}


@pytest.mark.parametrize("field,value", [
    ("trigger_rate", None), ("trigger_rate", True), ("trigger_rate", "0.5"),
    ("trigger_rate", float("nan")), ("trigger_rate", float("inf")),
    ("trigger_rate", -0.1), ("trigger_rate", 1.1),
    ("ok_runs", None), ("ok_runs", True), ("ok_runs", -1), ("ok_runs", 1.5),
    ("failed_runs", False), ("failed_runs", -1), ("pass", 1), ("pass", "false")])
def test_malformed_metrics_rejected(field, value):
    raw = _result()
    raw["results"][0][field] = value
    with pytest.raises(ValueError, match=field):
        normalize_result(raw)


@pytest.mark.parametrize("field", ["trigger_rate", "ok_runs", "pass"])
def test_required_metric_missing_rejected(field):
    raw = _result()
    del raw["results"][0][field]
    with pytest.raises(ValueError, match=field):
        normalize_result(raw)


@pytest.mark.parametrize("should_trigger", [True, False])
@pytest.mark.parametrize("passed", [True, False])
def test_zero_successful_runs_cannot_be_compared_or_used_as_baseline(tmp_path, should_trigger, passed):
    raw = _result()
    raw["results"][0].update(ok_runs=0, trigger_rate=0.0, should_trigger=should_trigger, **{"pass": passed})
    path = tmp_path / "baseline.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ValueError, match="ok_runs"):
        load_result(path)
    with pytest.raises(ValueError, match="ok_runs"):
        validate_baseline(path, ["sonnet"])
    result, code = compare_results(raw, _result())
    assert code == 1
    assert result["status"] == "error"


@pytest.mark.parametrize("failure", [{"failed_runs": 1}, {"execution_error": "timeout"}, {"status": "incomplete"}])
def test_failed_execution_cannot_claim_pass(failure):
    raw = _result()
    raw["results"][0].update(failure)
    with pytest.raises(ValueError, match="incomplete.*pass"):
        normalize_result(raw)


@pytest.mark.parametrize("should_trigger", [True, False])
@pytest.mark.parametrize("rate", [0.0, 0.79, 0.8, 1.0])
def test_pass_must_agree_with_known_threshold(should_trigger, rate):
    raw = _result()
    raw["trigger_threshold"] = 0.8
    expected = rate >= 0.8 if should_trigger else rate < 0.8
    row = raw["results"][0]
    row.update(trigger_rate=rate, should_trigger=should_trigger, **{"pass": expected})
    assert normalize_result(raw) == {"sonnet": raw}
    row["pass"] = not expected
    with pytest.raises(ValueError, match="pass.*trigger_threshold"):
        normalize_result(raw)


@pytest.mark.parametrize("field,value", [("skill_name", " "), ("skill_name", 1),
    ("model", 42), ("model", " ")])
def test_invalid_result_identity_rejected(field, value):
    raw = _result()
    raw[field] = value
    with pytest.raises(ValueError, match=field):
        normalize_result(raw)


def test_invalid_matrix_nested_identity_rejected():
    raw = _result()
    raw["model"] = False
    with pytest.raises(ValueError, match="model"):
        normalize_result({"trigger_by_model": {"sonnet": raw}})


def test_infrastructure_flag_must_be_boolean():
    raw = _result()
    raw["summary"]["infrastructure_failed"] = "false"
    with pytest.raises(ValueError, match="infrastructure_failed"):
        normalize_result(raw)


@pytest.mark.parametrize("cases,error", [([], "no overlapping"),
    ([{"query": "unrelated", "should_trigger": True}], "no overlapping"),
    ([{"query": "trigger me", "should_trigger": False}], "conflicting")])
def test_baseline_preflight_checks_current_cases(tmp_path, cases, error):
    path = tmp_path / "baseline.json"
    path.write_text(json.dumps(_result()), encoding="utf-8")
    with pytest.raises(ValueError, match=error):
        validate_baseline(path, ["sonnet"], cases=cases)


def test_baseline_preflight_accepts_shared_normalized_case(tmp_path):
    path = tmp_path / "baseline.json"
    path.write_text(json.dumps(_result()), encoding="utf-8")
    assert validate_baseline(path, ["sonnet"], cases=[
        {"query": "trigger me", "should_trigger": True},
        {"query": "new query", "should_trigger": False}])


@pytest.mark.parametrize("sentinel", ["configured default", "default"])
def test_actual_unknown_model_reports_block_envelope_comparison_and_preflight(tmp_path, sentinel):
    raw = _result(model=sentinel)
    result, code = compare_results({"trigger": raw}, {"trigger": raw})
    assert code == 1
    assert "unknown" in result["errors"][0]
    # Historical raw-pair comparisons remain available.
    assert compare_results(raw, raw)[1] == 0
    path = tmp_path / "baseline.json"
    path.write_text(json.dumps({"trigger": raw}), encoding="utf-8")
    with pytest.raises(ValueError, match="explicit"):
        validate_baseline(path, [sentinel])


@pytest.mark.parametrize("failure", [{"failed_runs": 1}, {"execution_error": "timeout"}, {"status": "incomplete"}])
@pytest.mark.parametrize("threshold", [None, 0.5])
def test_query_failure_cannot_hide_behind_clean_summary(tmp_path, failure, threshold):
    raw = _result()
    if threshold is not None:
        raw["trigger_threshold"] = threshold
    raw["results"][0].update(failure)
    raw["results"][0]["pass"] = False  # Producer marks incomplete rows as non-passing.
    assert normalize_result(raw) == {"sonnet": raw}
    assert raw["summary"]["infrastructure_failed"] is False
    result, code = compare_results(raw, _result())
    assert code == 1
    assert "incomplete query" in "; ".join(result["errors"])
    path = tmp_path / "baseline.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ValueError, match="incomplete query"):
        validate_baseline(path, ["sonnet"])


@pytest.mark.parametrize("value", [None, False, 0, -1, 1.01, float("nan"), float("inf"), "0.5"])
def test_invalid_threshold_metadata_is_rejected(value):
    raw = _result()
    raw["trigger_threshold"] = value
    result, code = compare_results(raw, _result())
    assert code == 1
    assert "trigger_threshold" in result["error"]


def test_threshold_mismatch_prevents_false_pass_rate_delta(tmp_path):
    candidate, baseline = _result(), _result()
    candidate["trigger_threshold"], baseline["trigger_threshold"] = 0.9, 0.5
    candidate["results"][0]["pass"] = False  # Same 0.8 trigger rate, stricter criterion.
    result, code = compare_results(candidate, baseline)
    assert code == 1
    assert "trigger_threshold mismatch" in "; ".join(result["errors"])
    path = tmp_path / "baseline.json"
    path.write_text(json.dumps(baseline), encoding="utf-8")
    with pytest.raises(ValueError, match="trigger_threshold mismatch"):
        validate_baseline(path, ["sonnet"], trigger_threshold=0.9)
    assert validate_baseline(path, ["sonnet"], trigger_threshold=0.5)


def test_legacy_threshold_provenance_is_explicit_without_assumed_default():
    candidate, baseline = _result(), _result()
    candidate["trigger_threshold"] = 0.9
    candidate["results"][0]["pass"] = False
    candidate["summary"].update(passed=1, failed=1, status="failed")
    result, code = compare_results(candidate, baseline)
    assert code == 0
    assert any("threshold metadata missing" in warning for warning in result["warnings"])
    baseline["trigger_threshold"] = 0.9
    baseline["results"][0]["pass"] = False
    baseline["summary"].update(passed=1, failed=1, status="failed")
    result, code = compare_results(candidate, baseline)
    assert code == 0
    assert not any("threshold metadata missing" in warning for warning in result["warnings"])


def test_summary_counts_actual_models_and_retains_partial_comparisons():
    from scripts.compare_eval import comparison_summary
    candidate = {"trigger_by_model": {"sonnet": _result(), "haiku": _result(model="haiku")}}
    baseline = {"trigger": _result()}
    result, code = compare_results(candidate, baseline)
    assert code == 1
    assert result["missing_models"]["baseline"] == ["haiku"]
    assert comparison_summary(result) == "sonnet: 2 shared queries compared"
    raw, code = compare_results(_result(), _result())
    assert comparison_summary(raw) == "2 shared queries compared"


@pytest.mark.parametrize("model", ["sonnet", "opus", "haiku", "fable", "best", "opusplan", "sonnet[1m]", "opus[1m]"])
def test_matching_aliases_warn_without_guessing_runtime(model):
    result, code = compare_results({"trigger": _result(model=model)}, {"trigger": _result(model=model)})
    assert code == 0
    warnings = result["comparisons_by_model"][model]["warnings"]
    assert any("resolved runtime" in warning and "pinned full model IDs" in warning for warning in warnings)


def test_pinned_model_does_not_claim_alias_resolution():
    model = "claude-sonnet-4-20250514"
    result, code = compare_results(_result(model=model), _result(model=model))
    assert code == 0
    assert not any("model aliases" in warning for warning in result["warnings"])
