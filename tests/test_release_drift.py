"""Offline release report contracts and retained artifact edge cases."""

import importlib.util
import json
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("release_drift", ROOT / ".github/scripts/release_drift.py")
assert SPEC is not None and SPEC.loader is not None
drift = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(drift)


def test_release_job_only_adds_offline_release_reporting():
    workflow = yaml.safe_load((ROOT / ".github/workflows/test.yml").read_text(encoding="utf-8"))
    job = workflow["jobs"]["release-drift"]
    assert "github.event_name == 'push'" in job["if"]
    assert "startsWith(github.ref, 'refs/heads/release/')" in job["if"]
    assert job["needs"] == "trigger-canary"
    assert job["permissions"] == {"contents": "read", "actions": "read"}
    assert all("CLAUDE_CODE_OAUTH_TOKEN" not in str(step) for step in job["steps"])


def test_previous_stable_release_uses_numeric_order_and_excludes_candidate():
    tags = ["v3.7.9", "v3.7.10", "v3.8.0", "v4.0.0", "v3.9.0-rc.1", "arbitrary"]
    assert drift.previous_release(tags, "v3.8.0") == "v3.7.10"
    assert drift.previous_release(tags, "v1.0.0") is None


def test_fixture_drift_compares_normalized_prompts_and_labels(tmp_path):
    skill = tmp_path / drift.SKILL
    skill.parent.mkdir(parents=True)
    fixtures = tmp_path / drift.FIXTURES
    fixtures.mkdir(parents=True)
    skill.write_text("---\nname: previous\ndescription: old description\n---\n", encoding="utf-8")
    cases = fixtures / drift.CASE_FILES[0]
    cases.write_text("- {prompt: same, expected: yes}\n- {prompt: flips, expected: no}\n"
                     "- {prompt: removed, expected: yes}\n", encoding="utf-8")
    previous = drift.prompt_inputs(tmp_path)

    skill.write_text("---\nname: candidate\ndescription: new description\n---\n", encoding="utf-8")
    cases.write_text("- {query: added, should_trigger: false}\n- {query: flips, should_trigger: true}\n"
                     "- {query: same, should_trigger: true}\n", encoding="utf-8")
    changes = drift.compare_inputs(previous, drift.prompt_inputs(tmp_path))
    assert changes == {
        "fields": {
            "name": {"previous": "previous", "candidate": "candidate", "changed": True},
            "description": {"previous": "old description", "candidate": "new description", "changed": True},
        },
        "added": {"added": False},
        "removed": {"removed": True},
        "label_changed": {"flips": {"previous": False, "candidate": True}},
    }


@pytest.mark.parametrize("status,code,with_results,expected", [
    ("skipped_missing_credentials", None, False, "skipped_missing_credentials"),
    ("infrastructure_failed", 1, False, "infrastructure_failed"),
    ("passed", 0, False, "unavailable"),
    ("passed", 0, True, "passed"),
    ("expectations_failed", 2, True, "expectations_failed"),
])
def test_evidence_requires_complete_model_results(tmp_path, status, code, with_results, expected):
    (tmp_path / "status.json").write_text(json.dumps({
        "model": "haiku", "status": status, "exit_code": code,
    }), encoding="utf-8")
    if with_results:
        run = tmp_path / "timestamped"
        run.mkdir()
        rows = [{"query": str(i), "should_trigger": i < 2,
                 "pass": True, "runs": 1, "ok_runs": 1, "failed_runs": 0,
                 "metrics": {"input_tokens": 10}} for i in range(4)]
        rows[0]["pass"] = status == "passed"
        rows[0]["metrics"]["cost_usd"] = 0.125
        (run / "results.json").write_text(json.dumps({
            "trigger": {"model": "haiku", "summary": {"infrastructure_failed": False},
                        "results": rows, "trigger_threshold": 0.5},
            "live": True, "exit_code": code, "call_budget": {"used": 5},
        }), encoding="utf-8")

    evidence = drift.canary_evidence(tmp_path, "haiku")
    assert evidence["status"] == expected
    assert drift.canary_evidence(tmp_path, "sonnet") == {"status": "unavailable"}
    if with_results:
        assert evidence["attempted_calls"] == 5
        assert evidence["case_metrics"]["cost_usd"] == {
            "observed_sum": 0.125, "measured_cases": 1, "total_cases": 4,
        }
        assert evidence["case_metrics"]["input_tokens"] == {
            "observed_sum": 40, "measured_cases": 4, "total_cases": 4,
        }
        assert evidence["case_metrics"]["output_tokens"]["observed_sum"] is None
    elif status == "skipped_missing_credentials":
        assert evidence["attempted_calls"] == 0
    else:
        assert "attempted_calls" not in evidence


def test_outcome_drift_skips_incompatible_history():
    release = {"threshold": 0.5, "case_outcomes": {"case": {"expected": True, "passed": False}}}
    passed = {"threshold": 0.5, "case_outcomes": {"case": {"expected": True, "passed": True}}}
    history = [{"models": {"haiku": {**passed, "threshold": 1}}},
               {"models": {"haiku": passed}, "run_id": 123, "sha": "old"}]
    assert drift.outcome_drift(release, history[:1], "haiku")["status"] == "unavailable"
    assert drift.outcome_drift(release, history, "haiku") == {
        "status": "compared", "baseline_run_id": 123, "baseline_sha": "old",
        "regressions": 1, "recoveries": 0,
    }
