"""Streaming + aggregation tests for run_eval.py using a controlled fake
subprocess (never a live `claude`).

`uuid.uuid4` is pinned so the synthetic skill name is deterministic
("demo-skill-deadbeef") and the fake stream can reference it.
"""
from __future__ import annotations

import json
import sys
import threading
import types
from pathlib import Path

import pytest

SKILL_PATH = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_PATH))

from scripts import run_eval as R
from scripts.structured_logging import ErrorCategory, QueryOutcome

CLEAN_NAME = "demo-skill-deadbeef"


# --------------------------------------------------------------------------- #
# Fake subprocess plumbing
# --------------------------------------------------------------------------- #
class _FakeStdin:
    def write(self, data):
        return len(data)

    def close(self):
        pass


class _FakeStdout:
    def __init__(self, lines, hang=False):
        self._lines = list(lines)
        self._hang = hang
        self._released = threading.Event()
        self.exhausted = False

    def readline(self):
        if self._lines:
            return self._lines.pop(0)
        if self._hang and not self._released.is_set():
            self._released.wait(timeout=10)
        self.exhausted = True
        return b""

    def release(self):
        self._released.set()

    def close(self):
        self.release()


class _FakeStderr:
    def __init__(self, data=b""):
        self._data = data

    def read(self, size=-1):
        data, self._data = self._data, b""
        return data

    def read1(self, size=-1):
        data, self._data = self._data, b""
        return data

    def close(self):
        pass


class FakeProcess:
    def __init__(self, lines, stderr=b"", returncode=0, hang=False):
        self.stdin = _FakeStdin()
        self.stdout = _FakeStdout(lines, hang=hang)
        self.stderr = _FakeStderr(stderr)
        self._returncode = returncode
        self._killed = False

    def poll(self):
        if self._killed or self.stdout.exhausted:
            return self._returncode
        return None

    def kill(self):
        self._killed = True
        self.stdout.release()

    def wait(self, timeout=None):
        return self._returncode


def _line(obj, newline=True):
    return (json.dumps(obj) + ("\n" if newline else "")).encode("utf-8")


def cb_start(name):
    return _line({"type": "stream_event", "event": {
        "type": "content_block_start",
        "content_block": {"type": "tool_use", "name": name}}})


def cb_delta(partial):
    return _line({"type": "stream_event", "event": {
        "type": "content_block_delta",
        "delta": {"type": "input_json_delta", "partial_json": partial}}})


def result_event(subtype="success", is_error=False, newline=True, **extra):
    return _line({"type": "result", "subtype": subtype, "is_error": is_error, **extra}, newline=newline)


def run_query(monkeypatch, tmp_path, proc, *, timeout=5, max_retries=0):
    monkeypatch.setattr(R.uuid, "uuid4", lambda: types.SimpleNamespace(hex="deadbeef"))
    monkeypatch.setattr(R, "claude_command", lambda *a: ["fake-claude", *a])
    monkeypatch.setattr(R.subprocess, "Popen", lambda *a, **k: proc)
    return R.run_single_query(
        query="q", skill_name="demo", skill_description="d",
        timeout=timeout, project_root=str(tmp_path), max_retries=max_retries,
    )


# --------------------------------------------------------------------------- #
# Trigger detection
# --------------------------------------------------------------------------- #
def test_triggered_via_stream_delta(monkeypatch, tmp_path):
    proc = FakeProcess([cb_start("Skill"), cb_delta('{"skill": "%s"}' % CLEAN_NAME)])
    out = run_query(monkeypatch, tmp_path, proc)
    assert out.triggered and out.ok


def test_not_triggered_via_result(monkeypatch, tmp_path):
    out = run_query(monkeypatch, tmp_path, FakeProcess([result_event()]))
    assert not out.triggered and out.ok
    assert out.category == ErrorCategory.NOT_TRIGGERED


def test_unrelated_tool_then_result_is_clean_not_triggered(monkeypatch, tmp_path):
    # An unrelated tool event must NOT short-circuit to a failed/false result.
    proc = FakeProcess([cb_start("Bash"), result_event()])
    out = run_query(monkeypatch, tmp_path, proc)
    assert not out.triggered and out.ok


def test_unrelated_tool_then_trigger(monkeypatch, tmp_path):
    proc = FakeProcess([cb_start("Bash"), cb_start("Skill"),
                        cb_delta('{"skill": "%s"}' % CLEAN_NAME)])
    out = run_query(monkeypatch, tmp_path, proc)
    assert out.triggered and out.ok


def test_final_line_without_newline_is_drained(monkeypatch, tmp_path):
    # The decisive event arrives with no trailing newline as the last chunk.
    proc = FakeProcess([result_event(newline=False)])
    out = run_query(monkeypatch, tmp_path, proc)
    assert out.ok and out.category == ErrorCategory.NOT_TRIGGERED


# --------------------------------------------------------------------------- #
# Cost/usage/duration capture from the result event (Step 1 instrumentation)
# --------------------------------------------------------------------------- #
def test_metrics_captured_from_result_event(monkeypatch, tmp_path):
    proc = FakeProcess([result_event(
        total_cost_usd=0.012,
        usage={"input_tokens": 1500, "output_tokens": 300},
        duration_ms=4200,
    )])
    out = run_query(monkeypatch, tmp_path, proc)
    assert out.ok and not out.triggered
    assert out.metrics == {"cost_usd": 0.012, "input_tokens": 1500,
                           "output_tokens": 300, "duration_ms": 4200}


def test_metrics_absent_default_to_none_not_zero(monkeypatch, tmp_path):
    # A plain result event (no cost/usage) must leave metrics None, not {0,0}.
    out = run_query(monkeypatch, tmp_path, FakeProcess([result_event()]))
    assert out.ok
    assert out.metrics is None


def test_metrics_partial_only_present_fields(monkeypatch, tmp_path):
    proc = FakeProcess([result_event(total_cost_usd=0.005)])
    out = run_query(monkeypatch, tmp_path, proc)
    assert out.metrics == {"cost_usd": 0.005}


def test_aggregate_sums_metrics_over_ok_runs_only():
    outcomes = {"pos": [
        QueryOutcome.triggered_ok(metrics={"cost_usd": 0.01, "input_tokens": 100}),
        QueryOutcome.triggered_ok(metrics={"cost_usd": 0.02, "input_tokens": 200}),
        QueryOutcome.failure(ErrorCategory.TIMEOUT, "t"),  # failed run contributes nothing
    ]}
    items = {"pos": {"query": "pos", "should_trigger": True}}
    results, summary = R._aggregate_results(outcomes, items, 0.5)
    assert results[0]["metrics"] == {"cost_usd": pytest.approx(0.03), "input_tokens": 300}
    assert summary["metrics"]["input_tokens"] == 300


def test_aggregate_metrics_none_when_unmeasured():
    outcomes = {"pos": [QueryOutcome.triggered_ok()]}
    items = {"pos": {"query": "pos", "should_trigger": True}}
    results, summary = R._aggregate_results(outcomes, items, 0.5)
    assert results[0]["metrics"] is None
    assert summary["metrics"] is None


# --------------------------------------------------------------------------- #
# Failure categorization (never a clean not-triggered)
# --------------------------------------------------------------------------- #
def test_timeout(monkeypatch, tmp_path):
    proc = FakeProcess([], hang=True)
    out = run_query(monkeypatch, tmp_path, proc, timeout=1)
    assert out.failed and out.category == ErrorCategory.TIMEOUT


def test_nonzero_exit_is_process_failure(monkeypatch, tmp_path):
    proc = FakeProcess([], stderr=b"boom", returncode=2)
    out = run_query(monkeypatch, tmp_path, proc)
    assert out.failed and out.category == ErrorCategory.SUBPROCESS_CRASH


def test_auth_failure_detected(monkeypatch, tmp_path):
    proc = FakeProcess([], stderr=b"Error: Invalid API key provided", returncode=1)
    out = run_query(monkeypatch, tmp_path, proc)
    assert out.failed and out.category == ErrorCategory.AUTHENTICATION


def test_malformed_output_is_parsing(monkeypatch, tmp_path):
    proc = FakeProcess([b"this is not json\n"], returncode=0)
    out = run_query(monkeypatch, tmp_path, proc)
    assert out.failed and out.category == ErrorCategory.PARSING


def test_missing_cli_is_failure(monkeypatch, tmp_path):
    def boom(*a, **k):
        raise FileNotFoundError("claude")
    monkeypatch.setattr(R.uuid, "uuid4", lambda: types.SimpleNamespace(hex="deadbeef"))
    monkeypatch.setattr(R, "claude_command", lambda *a: ["fake-claude", *a])
    monkeypatch.setattr(R.subprocess, "Popen", boom)
    out = R.run_single_query(query="q", skill_name="demo", skill_description="d",
                             timeout=5, project_root=str(tmp_path), max_retries=0)
    assert out.failed and out.category == ErrorCategory.SUBPROCESS_CRASH


def test_synthetic_command_file_cleaned_up(monkeypatch, tmp_path):
    run_query(monkeypatch, tmp_path, FakeProcess([result_event()]))
    cmd = tmp_path / ".claude" / "commands" / f"{CLEAN_NAME}.md"
    assert not cmd.exists()


# --------------------------------------------------------------------------- #
# Aggregation: a failed execution is never a pass
# --------------------------------------------------------------------------- #
def test_failed_negative_run_not_counted_as_pass():
    outcomes = {"neg": [QueryOutcome.failure(ErrorCategory.AUTHENTICATION, "auth")]}
    items = {"neg": {"query": "neg", "should_trigger": False}}
    results, summary = R._aggregate_results(outcomes, items, 0.5)
    assert results[0]["pass"] is False
    assert results[0]["execution_error"] == "authentication"
    assert summary["infrastructure_failed"] is True


def test_clean_not_triggered_passes_negative():
    outcomes = {"neg": [QueryOutcome.not_triggered_ok()]}
    items = {"neg": {"query": "neg", "should_trigger": False}}
    results, summary = R._aggregate_results(outcomes, items, 0.5)
    assert results[0]["pass"] is True
    assert summary["infrastructure_failed"] is False


def test_rate_computed_over_ok_runs_only():
    outcomes = {"pos": [QueryOutcome.triggered_ok(),
                        QueryOutcome.failure(ErrorCategory.TIMEOUT, "t")]}
    items = {"pos": {"query": "pos", "should_trigger": True}}
    results, _ = R._aggregate_results(outcomes, items, 0.5)
    assert results[0]["pass"] is False  # any infrastructure failure → incomplete, never a pass
    assert results[0]["trigger_rate"] == 1.0  # rate computed over ok runs only, not all runs
    assert results[0]["failed_runs"] == 1


def test_all_runs_failed_flags_infrastructure():
    outcomes = {
        "a": [QueryOutcome.failure(ErrorCategory.TIMEOUT, "t")],
        "b": [QueryOutcome.failure(ErrorCategory.SUBPROCESS_CRASH, "c")],
    }
    items = {"a": {"query": "a", "should_trigger": True},
             "b": {"query": "b", "should_trigger": False}}
    results, summary = R._aggregate_results(outcomes, items, 0.5)
    assert all(r["pass"] is False for r in results)
    assert summary["errored"] == 2
    assert summary["infrastructure_failed"] is True


# --------------------------------------------------------------------------- #
# Large stderr: cap applied, no hang, result is a categorized failure
# --------------------------------------------------------------------------- #
def test_large_stderr_no_hang(monkeypatch, tmp_path):
    # 100 KB of stderr must not cause the process runner to block indefinitely.
    # The key property: run_single_query returns a failed result in bounded time.
    large = b"E" * 100_000
    proc = FakeProcess([], stderr=large, returncode=1)
    out = run_query(monkeypatch, tmp_path, proc, timeout=5)
    assert out.failed
    assert out.category == ErrorCategory.SUBPROCESS_CRASH
