"""CLI model validation prevents duplicated calls and inconsistent reports."""
import importlib.util
import json
from pathlib import Path
from unittest.mock import Mock

import pytest

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location("bsc", ROOT / "bsc.py")
assert spec and spec.loader
bsc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bsc)


@pytest.mark.parametrize("models", ["haiku,haiku", "haiku, sonnet, haiku", " haiku ,haiku "])
def test_duplicate_models_rejected_before_calls(tmp_path, monkeypatch, models):
    from scripts import run_eval
    evaluate = Mock(side_effect=AssertionError("No calls should run"))
    monkeypatch.setattr(run_eval, "run_eval", evaluate)
    code = bsc.main(["eval", str(ROOT / "examples/release-notes"), "--live",
                     "--models", models, "--runs-dir", str(tmp_path)])
    evaluate.assert_not_called()
    result = json.loads(next(tmp_path.glob("*/results.json")).read_text())
    assert code == result["exit_code"] == 1
    assert result["status"] == "incomplete"
    assert "duplicate model names" in result["error"]
    assert "duplicate model names" in next(tmp_path.glob("*/report.md")).read_text()
    assert "trigger_by_model" not in result


def test_distinct_models_keep_calls_reports_and_status_consistent(tmp_path, monkeypatch):
    from scripts import run_eval
    evaluate = Mock(side_effect=[
        {"summary": {"infrastructure_failed": False, "failed": 1}, "results": []},
        {"summary": {"infrastructure_failed": False, "failed": 0}, "results": []},
    ])
    monkeypatch.setattr(run_eval, "run_eval", evaluate)
    code = bsc.main(["eval", str(ROOT / "examples/release-notes"), "--live",
                     "--models", "haiku, sonnet", "--max-calls", "100",
                     "--runs-dir", str(tmp_path)])
    result = json.loads(next(tmp_path.glob("*/results.json")).read_text())
    assert [call.args[7] for call in evaluate.call_args_list] == ["haiku", "sonnet"]
    assert result["max_calls"] == (1 + result["test_count"]) * 2
    assert list(result["trigger_by_model"]) == ["haiku", "sonnet"]
    assert code == result["exit_code"] == 2
    assert result["status"] == "failed"
    report = next(tmp_path.glob("*/report.md")).read_text()
    assert report.startswith("# eval: FAILED")
    for model in ("haiku", "sonnet"):
        assert report.count(f"## Trigger evaluation: {model}") == 1


def test_grade_uses_the_single_models_value(tmp_path, monkeypatch):
    from scripts import run_eval, skill_test
    evaluate = Mock(return_value={
        "summary": {"infrastructure_failed": False, "failed": 0}, "results": [],
    })
    grade = Mock(return_value=0)
    monkeypatch.setattr(run_eval, "run_eval", evaluate)
    monkeypatch.setattr(skill_test, "grade_behavior", grade)
    transcript = tmp_path / "transcript.txt"
    transcript.write_text("session\n", encoding="utf-8")
    runs = tmp_path / "runs"
    code = bsc.main(["eval", str(ROOT / "examples/release-notes"), "--live",
                     "--models", "haiku", "--grade-transcript", str(transcript),
                     "--max-calls", "100", "--runs-dir", str(runs)])
    assert code == 0
    assert grade.call_args.kwargs["model"] == "haiku"
    evaluate.assert_called_once()


def test_grade_rejects_multiple_models_before_calls(tmp_path, monkeypatch):
    from scripts import run_eval
    evaluate = Mock(side_effect=AssertionError("No calls should run"))
    monkeypatch.setattr(run_eval, "run_eval", evaluate)
    code = bsc.main(["eval", str(ROOT / "examples/release-notes"), "--live",
                     "--models", "haiku,sonnet", "--grade-transcript", str(tmp_path / "t.txt"),
                     "--max-calls", "100", "--runs-dir", str(tmp_path / "runs")])
    evaluate.assert_not_called()
    result = json.loads(next((tmp_path / "runs").glob("*/results.json")).read_text())
    assert code == result["exit_code"] == 1
    assert "one model" in result["error"]


@pytest.mark.parametrize("comparison,code,next_action,message", [
    ({"status": "invalid", "errors": ["skill_name mismatch", "no overlapping queries"]},
     1, "skill_name mismatch; no overlapping queries", "skill_name mismatch; no overlapping queries"),
    ({"status": "error", "error": "invalid input", "errors": ["secondary"]},
     1, "invalid input", "invalid input"),
    ({"report": "Comparison: demo\ndetails", "comparison": {"shared_queries": 2}},
     0, "Comparison: demo", "2 shared queries compared"),
    ({"comparison": {"shared_queries": 2}},
     0, "Comparison complete.", "2 shared queries compared"),
])
def test_compare_report_messages(tmp_path, monkeypatch, comparison, code, next_action, message):
    from scripts import compare_eval
    monkeypatch.setattr(compare_eval, "compare_main", lambda *args: (comparison, code))
    candidate = tmp_path / "candidate.json"
    baseline = tmp_path / "baseline.json"
    candidate.write_text("{}", encoding="utf-8")
    baseline.write_text("{}", encoding="utf-8")
    runs = tmp_path / "reports"
    assert bsc.main(["compare", "--candidate", str(candidate), "--baseline", str(baseline),
                     "--runs-dir", str(runs)]) == code
    result = json.loads(next(runs.glob("*/results.json")).read_text())
    assert result["next_action"] == next_action
    assert result["checks"][0]["message"] == message


def test_eval_baseline_rejects_multiple_models(tmp_path):
    runs = tmp_path / "runs"
    code = bsc.main(["eval", str(ROOT / "examples/release-notes"),
                     "--models", "haiku,sonnet", "--baseline", str(tmp_path / "b.json"),
                     "--runs-dir", str(runs)])
    assert code == 1
    result = json.loads(next(runs.glob("*/results.json")).read_text())
    assert "one model" in result["error"]


def test_eval_baseline_missing_file_rejected(tmp_path):
    runs = tmp_path / "runs"
    code = bsc.main(["eval", str(ROOT / "examples/release-notes"),
                     "--model", "haiku", "--baseline", str(tmp_path / "missing.json"),
                     "--runs-dir", str(runs)])
    assert code == 1
    result = json.loads(next(runs.glob("*/results.json")).read_text())
    assert "--baseline file not found" in result["error"]


def test_eval_baseline_preview_mode(tmp_path):
    base_file = tmp_path / "baseline.json"
    base_file.write_text(json.dumps({
        "skill_name": "release-notes", "summary": {}, "results": []
    }), encoding="utf-8")
    runs = tmp_path / "runs"
    code = bsc.main(["eval", str(ROOT / "examples/release-notes"),
                     "--model", "haiku", "--baseline", str(base_file),
                     "--runs-dir", str(runs)])
    assert code == 0
    result = json.loads(next(runs.glob("*/results.json")).read_text())
    assert result["status"] == "preview"
    check_names = [c["check"] for c in result["checks"]]
    assert "baseline input" in check_names


def test_eval_baseline_live_runs_comparison(tmp_path, monkeypatch):
    from scripts import run_eval, compare_eval
    cand_eval = {
        "skill_name": "release-notes",
        "description": "test",
        "model": "haiku",
        "summary": {"total": 1, "passed": 1, "failed": 0, "infrastructure_failed": False},
        "results": [{"query": "q1", "status": "passed", "pass": True, "should_trigger": True, "trigger_rate": 1.0, "runs": 1, "ok_runs": 1, "failed_runs": 0}],
    }
    monkeypatch.setattr(run_eval, "run_eval", Mock(return_value=cand_eval))
    comparison_obj = {
        "status": "complete",
        "report": "Comparison: release-note-draft (1 shared queries)\n  aggregate: delta +0.5",
        "comparison": {"shared_queries": 1},
    }
    monkeypatch.setattr(compare_eval, "compare_main", lambda *args: (comparison_obj, 0))

    base_file = tmp_path / "baseline.json"
    base_file.write_text(json.dumps(cand_eval), encoding="utf-8")
    runs = tmp_path / "runs"
    code = bsc.main(["eval", str(ROOT / "examples/release-notes"), "--live",
                     "--model", "haiku", "--baseline", str(base_file),
                     "--max-calls", "50", "--runs-dir", str(runs)])
    assert code == 0
    result = json.loads(next(runs.glob("*/results.json")).read_text())
    assert result["status"] == "passed"
    assert "comparison" in result
    check_names = [c["check"] for c in result["checks"]]
    assert "comparison" in check_names
    assert "baseline comparison" in result["next_action"]
    report = next(runs.glob("*/report.md")).read_text()
    assert "## Baseline comparison" in report
    assert "delta +0.5" in report


def test_eval_caution_banner_under_10_runs(tmp_path):
    runs = tmp_path / "runs"
    code = bsc.main(["eval", str(ROOT / "examples/release-notes"),
                     "--runs", "3", "--max-calls", "50", "--runs-dir", str(runs)])
    assert code == 0
    result = json.loads(next(runs.glob("*/results.json")).read_text())
    assert "sample_size_caution" in result
    assert "3 (<10)" in result["sample_size_caution"]
    report = next(runs.glob("*/report.md")).read_text()
    assert "Caution:" in report
    assert "3 (<10)" in report


def test_eval_caution_banner_at_least_10_runs(tmp_path):
    runs = tmp_path / "runs"
    code = bsc.main(["eval", str(ROOT / "examples/release-notes"),
                     "--runs", "10", "--max-calls", "500", "--runs-dir", str(runs)])
    assert code == 0
    result = json.loads(next(runs.glob("*/results.json")).read_text())
    assert "sample_size_caution" not in result


@pytest.mark.parametrize("live", [False, True])
def test_mismatched_baseline_rejected_before_evaluation(tmp_path, monkeypatch, live):
    from scripts import run_eval
    evaluate = Mock(side_effect=AssertionError("must reject before calls"))
    monkeypatch.setattr(run_eval, "run_eval", evaluate)
    baseline = tmp_path / "baseline.json"
    baseline.write_text(json.dumps({"skill_name": "different-skill", "results": [], "summary": {}}), encoding="utf-8")
    runs = tmp_path / "runs"
    args = ["eval", str(ROOT / "examples/release-notes"), "--baseline", str(baseline),
            "--runs-dir", str(runs)] + (["--live"] if live else [])
    assert bsc.main(args) == 1
    evaluate.assert_not_called()
    result = json.loads(next(runs.glob("*/results.json")).read_text(encoding="utf-8"))
    assert "skill_name mismatch" in result["error"]
