"""Offline checks for persisted comparison provenance."""
import pytest
from scripts import run_eval as evaluation
from scripts.structured_logging import QueryOutcome


@pytest.mark.parametrize("control_ok", [True, False])
def test_threshold_recorded_for_healthy_and_control_failure_results(monkeypatch, control_ok):
    calls = []
    def query(*args):
        calls.append(args[0])
        args[9].consume()
        return QueryOutcome.triggered_ok() if control_ok else QueryOutcome.not_triggered_ok()
    monkeypatch.setattr(evaluation, "run_single_query", query)
    result = evaluation.run_eval(
        [{"query": "test query", "should_trigger": True}], "demo", "description",
        1, 1, trigger_threshold=0.75, max_calls=2,
    )
    assert result["trigger_threshold"] == 0.75
    assert result["model"] == "configured default"
    assert result["summary"]["infrastructure_failed"] is not control_ok
    assert len(calls) == (2 if control_ok else 1)
