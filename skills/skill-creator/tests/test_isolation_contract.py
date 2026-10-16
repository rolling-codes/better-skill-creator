"""Contract tests for the subprocess isolation layer.

These tests assert the exact argv that run_eval and bsc eval pass to claude,
so a flag change that breaks trigger detection fails here before any live call.
"""
from __future__ import annotations
import inspect
import pytest
from scripts.claude_process import isolation_args
from scripts.run_eval import _CONTROL_PROMPT_TEMPLATE, _check_infra
from scripts import run_eval as evaluation
from scripts.call_budget import CallBudget
from scripts.structured_logging import QueryOutcome, ErrorCategory


def test_isolation_args_excludes_setting_sources():
    """--setting-sources "" hides project commands; it must not be in isolation_args."""
    args = isolation_args()
    assert "--setting-sources" not in args, (
        "--setting-sources was found in isolation_args() — it hides .claude/commands/ "
        "making trigger detection impossible."
    )


def test_isolation_args_with_skill_tool_excludes_setting_sources():
    """The Skill-tool variant used by run_eval must also exclude --setting-sources."""
    args = isolation_args("Skill")
    assert "--setting-sources" not in args


def test_control_prompt_template_is_defined():
    """A non-empty control prompt template must exist so the infra check can fire."""
    assert isinstance(_CONTROL_PROMPT_TEMPLATE, str) and len(_CONTROL_PROMPT_TEMPLATE) > 10, (
        "_CONTROL_PROMPT_TEMPLATE is missing or too short — infra check cannot run."
    )


def test_check_infra_is_callable_with_expected_signature():
    """_check_infra must be importable and accept the expected number of parameters."""
    sig = inspect.signature(_check_infra)
    params = list(sig.parameters)
    assert len(params) >= 7, (
        f"_check_infra has {len(params)} parameters, expected at least 7 "
        "(skill_name, description, timeout, project_root, model, budget, max_retries)"
    )


@pytest.mark.parametrize("outcome", [QueryOutcome.not_triggered_ok(),
                                   QueryOutcome.failure(ErrorCategory.TIMEOUT)])
def test_failed_control_stops_evaluation(monkeypatch, outcome):
    """A failed control consumes one shared call and prevents all test queries."""
    calls = []
    budget = CallBudget(4)

    def query(*args):
        calls.append(args)
        args[9].consume()
        return outcome

    monkeypatch.setattr(evaluation, "run_single_query", query)
    result = evaluation.run_eval(
        [{"query": "test query", "should_trigger": True}], "demo", "description",
        1, 1, max_retries=2, max_calls=4, budget=budget,
    )
    assert len(calls) == 1
    assert calls[0][0].startswith("Please invoke the available skill")
    assert calls[0][6] == 0  # The control never retries.
    assert calls[0][9] is budget
    assert result["summary"]["infrastructure_failed"] is True
    assert result["results"] == []
    assert result["max_calls"] == 4
    assert result["call_budget"] == {"limit": 4, "used": 1, "remaining": 3}


def test_control_and_test_query_share_budget(monkeypatch):
    budgets = []
    budget = CallBudget(3)
    budget.consume()  # A prior operation used one call.

    def query(*args):
        budgets.append(args[9])
        args[9].consume()
        return QueryOutcome.triggered_ok()

    monkeypatch.setattr(evaluation, "run_single_query", query)
    result = evaluation.run_eval(
        [{"query": "test query", "should_trigger": True}], "demo", "description",
        1, 1, max_calls=2, budget=budget,
    )
    assert budgets == [budget, budget]
    assert result["summary"]["status"] == "passed"
    assert result["max_calls"] == 2
    assert result["call_budget"] == {"limit": 3, "used": 3, "remaining": 0}


@pytest.mark.parametrize("budget", [None, CallBudget(1)])
def test_control_is_included_in_preflight_budget(monkeypatch, budget):
    def query(*args):
        pytest.fail("No query should launch with insufficient budget")

    monkeypatch.setattr(evaluation, "run_single_query", query)
    with pytest.raises(ValueError, match="2 calls"):
        evaluation.run_eval(
            [{"query": "test query", "should_trigger": True}], "demo", "description",
            1, 1, max_calls=1 if budget is None else 2, budget=budget,
        )
