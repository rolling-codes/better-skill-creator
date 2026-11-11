"""Blank-prompt rejection in run_eval.py (Fix 3).

Blank prompts must be caught before any infra or dispatch call.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

SKILL_PATH = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_PATH))

from scripts import run_eval as R
from scripts.structured_logging import QueryOutcome


def _never_dispatch(*args, **kwargs):
    raise AssertionError("network call should not be reached on blank-prompt input")


def test_blank_prompt_rejected_before_infra_check(monkeypatch):
    monkeypatch.setattr(R, "_check_infra", _never_dispatch)
    with pytest.raises(ValueError, match="[Bb]lank"):
        R.run_eval(
            [{"query": "", "should_trigger": False}],
            "my-skill", "my description", 1, 60.0,
            max_calls=20,
        )


def test_whitespace_only_prompt_rejected(monkeypatch):
    monkeypatch.setattr(R, "_check_infra", _never_dispatch)
    with pytest.raises(ValueError, match="[Bb]lank"):
        R.run_eval(
            [{"query": "   ", "should_trigger": False}],
            "my-skill", "my description", 1, 60.0,
            max_calls=20,
        )


def test_blank_prompt_count_reported_in_message(monkeypatch):
    # normalize_cases deduplicates, so two blank strings collapse to one — test with 1
    monkeypatch.setattr(R, "_check_infra", _never_dispatch)
    with pytest.raises(ValueError, match="1 case"):
        R.run_eval(
            [
                {"query": "", "should_trigger": False},
                {"query": "valid prompt here", "should_trigger": True},
            ],
            "my-skill", "my description", 1, 60.0,
            max_calls=20,
        )


def test_valid_prompts_pass_blank_preflight_and_reach_infra(monkeypatch):
    infra_called = []

    def fake_infra(*args, **kwargs):
        infra_called.append(True)
        return QueryOutcome.not_triggered_ok()  # infra reachable but control missed

    monkeypatch.setattr(R, "_check_infra", fake_infra)
    result = R.run_eval(
        [{"query": "help me with something", "should_trigger": True}],
        "my-skill", "my description", 1, 60.0,
        max_calls=20,
    )
    assert infra_called, "valid prompts must reach _check_infra"
    assert result["summary"]["infrastructure_failed"]
