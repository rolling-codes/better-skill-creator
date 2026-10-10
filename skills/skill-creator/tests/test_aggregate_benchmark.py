"""Malformed run names must not contribute synthetic run-zero results."""
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import json

from scripts.aggregate_benchmark import (
    load_run_results,
    aggregate_results,
    validate_benchmark_pairing,
    generate_benchmark,
)


@pytest.mark.parametrize("legacy", [False, True])
def test_malformed_run_numbers_are_skipped(tmp_path, capsys, legacy):
    root = tmp_path / "runs" if legacy else tmp_path
    config = root / "eval-1" / "with_skill"
    for name in ("run-0", "run-1", "run-12", "run-bad", "run-"):
        run = config / name
        run.mkdir(parents=True)
        (run / "grading.json").write_text('{"summary": {"pass_rate": 1.0}}', encoding="utf-8")

    results = load_run_results(tmp_path)["with_skill"]

    assert [run["run_number"] for run in results] == [0, 1, 12]
    assert all(run["pass_rate"] == 1.0 for run in results)
    warnings = capsys.readouterr().out
    for name in ("run-bad", "run-"):
        assert f"Warning: Invalid run number in {config / name}; skipping directory" in warnings


# ---------------------------------------------------------------------------
# Methodology guards (Phase 2): direction correctness and no fabricated metrics.
# Pure-Python aggregation only — no model is called.
# ---------------------------------------------------------------------------

def _write_runs(root, config, pass_rates):
    """Create <root>/eval-1/<config>/run-K/grading.json for each pass_rate."""
    for k, pr in enumerate(pass_rates, start=1):
        run = root / "eval-1" / config / f"run-{k}"
        run.mkdir(parents=True)
        (run / "grading.json").write_text(
            f'{{"summary": {{"pass_rate": {pr}}}}}', encoding="utf-8")


def test_regression_reports_negative_delta(tmp_path):
    # with_skill sorts before without_skill, so delta = with - without.
    _write_runs(tmp_path, "with_skill", [0.30, 0.30, 0.30])
    _write_runs(tmp_path, "without_skill", [0.80, 0.80, 0.80])
    summary = aggregate_results(load_run_results(tmp_path))
    assert summary["delta"]["pass_rate"].startswith("-")


def test_improvement_reports_positive_delta(tmp_path):
    _write_runs(tmp_path, "with_skill", [0.90, 0.90, 0.90])
    _write_runs(tmp_path, "without_skill", [0.40, 0.40, 0.40])
    summary = aggregate_results(load_run_results(tmp_path))
    assert summary["delta"]["pass_rate"].startswith("+")


def test_missing_grading_is_excluded_not_fabricated(tmp_path):
    # Two valid runs plus one run with no grading.json: the empty run must not
    # enter the mean as a fabricated 0.0.
    _write_runs(tmp_path, "with_skill", [1.0, 1.0])
    empty = tmp_path / "eval-1" / "with_skill" / "run-3"
    empty.mkdir(parents=True)
    results = load_run_results(tmp_path)["with_skill"]
    assert [r["run_number"] for r in results] == [1, 2]
    summary = aggregate_results({"with_skill": results})
    assert summary["with_skill"]["pass_rate"]["mean"] == 1.0


# ---------------------------------------------------------------------------
# Pairing guard (Phase 3 Step 3): reject cross-experiment comparisons.
# ---------------------------------------------------------------------------

def _grading(pass_rate=1.0, texts=("does X",), model=None):
    exp = [{"text": t, "passed": True, "evidence": "e"} for t in texts]
    doc = {"summary": {"pass_rate": pass_rate}, "expectations": exp}
    if model is not None:
        doc["model"] = model
    return json.dumps(doc)


def _write_grading(root, eval_name, config, run, **kw):
    d = root / eval_name / config / f"run-{run}"
    d.mkdir(parents=True)
    (d / "grading.json").write_text(_grading(**kw), encoding="utf-8")


def test_pairing_aligned_conditions_pass(tmp_path):
    for cfg in ("with_skill", "without_skill"):
        for run in (1, 2, 3):
            _write_grading(tmp_path, "eval-1", cfg, run, texts=("does X",))
    errors, warnings = validate_benchmark_pairing(load_run_results(tmp_path))
    assert errors == []
    assert any("model comparability" in w for w in warnings)  # model unrecorded → warn


def test_pairing_rejects_mismatched_task_sets(tmp_path):
    _write_grading(tmp_path, "eval-1", "with_skill", 1)
    _write_grading(tmp_path, "eval-2", "without_skill", 1)
    errors, _ = validate_benchmark_pairing(load_run_results(tmp_path))
    assert any("task-set mismatch" in e for e in errors)


def test_pairing_rejects_missing_condition(tmp_path):
    for cfg in ("with_skill", "without_skill"):
        _write_grading(tmp_path, "eval-1", cfg, 1)
    errors, _ = validate_benchmark_pairing(
        load_run_results(tmp_path),
        expected_conditions=["with_skill", "without_skill", "upstream"],
    )
    assert any("missing expected condition" in e and "upstream" in e for e in errors)


def test_pairing_rejects_unequal_run_counts(tmp_path):
    _write_grading(tmp_path, "eval-1", "with_skill", 1)
    _write_grading(tmp_path, "eval-1", "with_skill", 2)
    _write_grading(tmp_path, "eval-1", "without_skill", 1)  # only one run
    errors, _ = validate_benchmark_pairing(load_run_results(tmp_path))
    assert any("unequal run counts" in e for e in errors)


def test_pairing_rejects_rubric_mismatch(tmp_path):
    _write_grading(tmp_path, "eval-1", "with_skill", 1, texts=("does X", "does Y"))
    _write_grading(tmp_path, "eval-1", "without_skill", 1, texts=("does X", "does Z"))
    errors, _ = validate_benchmark_pairing(load_run_results(tmp_path))
    assert any("rubric mismatch" in e for e in errors)


def test_pairing_rejects_model_mismatch(tmp_path):
    _write_grading(tmp_path, "eval-1", "with_skill", 1, model="sonnet")
    _write_grading(tmp_path, "eval-1", "without_skill", 1, model="haiku")
    errors, _ = validate_benchmark_pairing(load_run_results(tmp_path))
    assert any("model configuration mismatch" in e for e in errors)


def test_pairing_matched_model_no_warning_no_error(tmp_path):
    for cfg in ("with_skill", "without_skill"):
        _write_grading(tmp_path, "eval-1", cfg, 1, model="sonnet")
    errors, warnings = validate_benchmark_pairing(load_run_results(tmp_path))
    assert errors == []
    assert not any("model comparability" in w for w in warnings)


# ---------------------------------------------------------------------------
# Missing vs measured-zero: an unmeasured metric must not count as a real 0.
# ---------------------------------------------------------------------------

def _write_raw(root, eval_name, config, run, doc):
    d = root / eval_name / config / f"run-{run}"
    d.mkdir(parents=True)
    (d / "grading.json").write_text(json.dumps(doc), encoding="utf-8")


def test_missing_timing_is_none_not_zero(tmp_path):
    # run-1 measured 0.0s; run-2 has no timing at all.
    _write_raw(tmp_path, "eval-1", "with_skill", 1,
               {"summary": {"pass_rate": 1.0}, "timing": {"total_duration_seconds": 0.0}})
    _write_raw(tmp_path, "eval-1", "with_skill", 2,
               {"summary": {"pass_rate": 1.0}})
    runs = load_run_results(tmp_path)["with_skill"]
    times = {r["run_number"]: r["time_seconds"] for r in runs}
    assert times[1] == 0.0      # measured zero
    assert times[2] is None     # not measured


def test_unmeasured_metric_excluded_from_stats(tmp_path):
    _write_raw(tmp_path, "eval-1", "with_skill", 1,
               {"summary": {"pass_rate": 1.0}, "timing": {"total_duration_seconds": 10.0}})
    _write_raw(tmp_path, "eval-1", "with_skill", 2,
               {"summary": {"pass_rate": 1.0}})  # no timing
    summary = aggregate_results(load_run_results(tmp_path))["with_skill"]
    # Only the one measured run contributes; the missing one does not drag the mean to 5.0.
    assert summary["time_seconds"]["mean"] == 10.0
    assert summary["time_seconds"]["n"] == 1
    assert summary["pass_rate"]["n"] == 2  # pass_rate measured on both


def test_measured_zero_counts_but_missing_does_not(tmp_path):
    _write_raw(tmp_path, "eval-1", "with_skill", 1,
               {"summary": {"pass_rate": 1.0}, "timing": {"total_duration_seconds": 0.0}})
    _write_raw(tmp_path, "eval-1", "with_skill", 2,
               {"summary": {"pass_rate": 1.0}})  # missing
    summary = aggregate_results(load_run_results(tmp_path))["with_skill"]
    assert summary["time_seconds"]["n"] == 1   # the measured 0.0, not the missing one
    assert summary["time_seconds"]["mean"] == 0.0


def test_serialized_runs_preserve_null_for_missing_metrics(tmp_path):
    # The viewer excludes missing via `!= null`; serializing 0 would silently
    # re-enter its recomputed averages and reintroduce the bias.
    _write_raw(tmp_path, "eval-1", "with_skill", 1, {"summary": {"pass_rate": 1.0}})
    _write_raw(tmp_path, "eval-1", "without_skill", 1, {"summary": {"pass_rate": 1.0}})
    bench = generate_benchmark(tmp_path)
    for run in bench["runs"]:
        assert run["result"]["time_seconds"] is None
        assert run["result"]["tokens"] is None
        assert run["result"]["tool_calls"] is None


def test_measured_zero_duration_is_not_replaced_by_timing_file(tmp_path):
    _write_raw(tmp_path, "eval-1", "with_skill", 1,
               {"timing": {"total_duration_seconds": 0.0}})
    timing_file = tmp_path / "eval-1/with_skill/run-1/timing.json"
    timing_file.write_text('{"total_duration_seconds": 42}', encoding="utf-8")
    run = load_run_results(tmp_path)["with_skill"][0]
    assert run["time_seconds"] == 0.0


@pytest.mark.parametrize("timing", [{}, {"total_tokens": None},
                                    {"total_tokens": 0}, {"total_tokens": 123}])
def test_tokens_use_only_measured_token_counts(tmp_path, timing):
    _write_raw(tmp_path, "eval-1", "with_skill", 1,
               {"execution_metrics": {"output_chars": 999}})
    timing_file = tmp_path / "eval-1/with_skill/run-1/timing.json"
    timing_file.write_text(json.dumps({"total_duration_seconds": 42, **timing}),
                           encoding="utf-8")
    run = load_run_results(tmp_path)["with_skill"][0]
    assert run["time_seconds"] == 42
    assert run["tokens"] == timing.get("total_tokens")
    stats = aggregate_results({"with_skill": [run]})["with_skill"]["tokens"]
    assert stats["n"] == (0 if timing.get("total_tokens") is None else 1)
