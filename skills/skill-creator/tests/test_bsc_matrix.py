"""Front-end integration for model-aware baseline reports; never calls a model."""
import importlib.util
import json
from pathlib import Path
from unittest.mock import Mock

import pytest

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location("bsc_matrix", ROOT / "bsc.py")
assert spec and spec.loader
bsc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bsc)


def evaluation(model, *, infra=False, passed=True):
    return {
        "skill_name": "release-notes", "model": model,
        "summary": {"total": 1, "passed": int(passed), "failed": int(not passed),
                    "infrastructure_failed": infra},
        "results": [{"query": "Write release notes for v2.1 based on the last 10 commits.", "should_trigger": True, "trigger_rate": float(passed),
                     "pass": passed, "status": "passed" if passed else "failed",
                     "runs": 1, "ok_runs": 1, "failed_runs": 0}],
    }


def baseline(tmp_path, models):
    path = tmp_path / "baseline.json"
    path.write_text(json.dumps({"trigger_by_model": models}), encoding="utf-8")
    return path


def result(runs):
    return json.loads(next(runs.glob("*/results.json")).read_text(encoding="utf-8"))


@pytest.mark.parametrize("bad", ["missing-model", "infrastructure", "unknown-model", "duplicate-query", "malformed-metrics", "label-conflict", "no-overlap", "threshold-mismatch"])
def test_invalid_matrix_baseline_prevents_calls(tmp_path, monkeypatch, bad):
    from scripts import run_eval
    models = {m: evaluation(m) for m in ("haiku", "sonnet")}
    if bad == "missing-model":
        del models["sonnet"]
    elif bad == "infrastructure":
        models["sonnet"]["summary"]["infrastructure_failed"] = True
    elif bad == "unknown-model":
        models["sonnet"]["model"] = "default"
    elif bad == "duplicate-query":
        models["haiku"]["results"] *= 2
    elif bad == "malformed-metrics":
        models["sonnet"]["results"][0]["trigger_rate"] = "broken"
    elif bad == "label-conflict":
        models["sonnet"]["results"][0]["should_trigger"] = False
    elif bad == "threshold-mismatch":
        models["sonnet"]["trigger_threshold"] = 0.25
    else:
        models["sonnet"]["results"][0]["query"] = "unrelated query"
    path = baseline(tmp_path, models)
    evaluate = Mock(side_effect=AssertionError("Baseline must be checked first"))
    monkeypatch.setattr(run_eval, "run_eval", evaluate)
    runs = tmp_path / "reports"
    assert bsc.main(["eval", str(ROOT / "examples/release-notes"), "--live",
                     "--models", "haiku,sonnet", "--baseline", str(path),
                     "--max-calls", "100", "--runs-dir", str(runs)]) == 1
    evaluate.assert_not_called()
    assert "Invalid baseline" in result(runs)["error"]


def test_matrix_evaluation_compares_each_model_and_shares_budget(tmp_path, monkeypatch):
    from scripts import run_eval
    models = {m: evaluation(m) for m in ("sonnet", "haiku")}
    path = baseline(tmp_path, models)
    budgets = []

    def fake_eval(*args, **kwargs):
        budgets.append(kwargs["budget"])
        kwargs["budget"].consume()
        return evaluation(args[7])

    monkeypatch.setattr(run_eval, "run_eval", fake_eval)
    runs = tmp_path / "reports"
    assert bsc.main(["eval", str(ROOT / "examples/release-notes"), "--live",
                     "--models", "haiku,sonnet", "--baseline", str(path),
                     "--max-calls", "100", "--runs-dir", str(runs)]) == 0
    data = result(runs)
    assert budgets[0] is budgets[1]
    assert data["call_budget"]["used"] == 2
    assert data["comparison"]["status"] == "complete"
    assert set(data["comparison"]["comparisons_by_model"]) == {"haiku", "sonnet"}
    report = next(runs.glob("*/report.md")).read_text(encoding="utf-8")
    assert "Baseline comparison" in report and "haiku" in report and "sonnet" in report


def test_compare_accepts_frontend_matrix_reports(tmp_path):
    path = baseline(tmp_path, {"haiku": evaluation("haiku"), "sonnet": evaluation("sonnet")})
    runs = tmp_path / "reports"
    assert bsc.main(["compare", "--candidate", str(path), "--baseline", str(path),
                     "--runs-dir", str(runs)]) == 0
    assert result(runs)["comparison"]["status"] == "complete"
    message = result(runs)["checks"][0]["message"]
    assert "haiku: 1 shared queries compared" in message
    assert "sonnet: 1 shared queries compared" in message
    assert "0 shared queries" not in message


def test_failed_model_comparison_keeps_healthy_model_report(tmp_path, monkeypatch):
    from scripts import run_eval
    path = baseline(tmp_path, {m: evaluation(m) for m in ("haiku", "sonnet")})
    monkeypatch.setattr(run_eval, "run_eval", Mock(side_effect=[
        evaluation("haiku"), evaluation("sonnet", infra=True, passed=False),
    ]))
    runs = tmp_path / "reports"
    assert bsc.main(["eval", str(ROOT / "examples/release-notes"), "--live",
                     "--models", "haiku,sonnet", "--baseline", str(path),
                     "--max-calls", "100", "--runs-dir", str(runs)]) == 1
    data = result(runs)
    assert data["comparison"]["status"] != "complete"
    assert data["comparison"]["comparisons_by_model"]["haiku"]["status"] == "complete"
