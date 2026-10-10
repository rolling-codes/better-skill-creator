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
    assert result["max_calls"] == result["test_count"] * 2
    assert list(result["trigger_by_model"]) == ["haiku", "sonnet"]
    assert code == result["exit_code"] == 2
    assert result["status"] == "failed"
    report = next(tmp_path.glob("*/report.md")).read_text()
    assert report.startswith("# eval: FAILED")
    for model in ("haiku", "sonnet"):
        assert report.count(f"## Trigger evaluation: {model}") == 1


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
