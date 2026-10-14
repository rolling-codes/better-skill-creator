"""Contract tests for the subprocess isolation layer.

These tests assert the exact argv that run_eval and bsc eval pass to claude,
so a flag change that breaks trigger detection fails here before any live call.
"""
from __future__ import annotations
import inspect
import pytest
from scripts.claude_process import isolation_args
from scripts.run_eval import _CONTROL_PROMPT_TEMPLATE, _check_infra


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
