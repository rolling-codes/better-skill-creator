"""Tests for the three-way train/val/held-out dataset split in run_loop.py.

Key contracts verified:
1. split_three_way partitions the input with no overlap and correct proportions.
2. The optimization loop evaluates held-out set exactly once, after the loop.
3. The optimizer (improve_description) never receives val or held-out scores.
4. best_description is selected by val score, not held-out score.
5. Backward compat: val_holdout=0 preserves the two-way split behavior.
"""
from __future__ import annotations

import sys
from pathlib import Path

SKILL_PATH = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_PATH))

import pytest
from scripts import run_loop as RL


# ---------------------------------------------------------------------------
# split_three_way unit tests
# ---------------------------------------------------------------------------

def _make_cases(n_trigger: int, n_no_trigger: int) -> list[dict]:
    cases = [{"query": f"trigger_{i}", "should_trigger": True} for i in range(n_trigger)]
    cases += [{"query": f"no_{i}", "should_trigger": False} for i in range(n_no_trigger)]
    return cases


def test_split_three_way_no_overlap():
    """The three sets must be disjoint and cover all inputs."""
    cases = _make_cases(9, 9)
    train, val, held = RL.split_three_way(cases, val_frac=0.2, held_frac=0.2)
    all_queries = {c["query"] for c in cases}
    train_q = {c["query"] for c in train}
    val_q = {c["query"] for c in val}
    held_q = {c["query"] for c in held}
    assert train_q | val_q | held_q == all_queries, "Sets must cover all inputs"
    assert len(train_q & val_q) == 0, "train and val must be disjoint"
    assert len(train_q & held_q) == 0, "train and held must be disjoint"
    assert len(val_q & held_q) == 0, "val and held must be disjoint"


def test_split_three_way_proportions():
    """With 30 cases and 20/20 split, each set should be within reasonable bounds."""
    cases = _make_cases(15, 15)
    train, val, held = RL.split_three_way(cases, val_frac=0.2, held_frac=0.2)
    total = len(train) + len(val) + len(held)
    assert total == 30
    # Each non-train set should be at least 1 item but not dominate
    assert len(val) >= 1
    assert len(held) >= 1
    assert len(train) >= 1
    # Train should be the largest
    assert len(train) >= len(val)
    assert len(train) >= len(held)


def test_split_three_way_stratified():
    """Both should_trigger=True and False should appear in all three sets (when large enough)."""
    cases = _make_cases(9, 9)
    train, val, held = RL.split_three_way(cases, val_frac=0.2, held_frac=0.2, seed=1)
    # With 9 of each and 20/20 split we expect at least 1 of each class per split
    def has_both(s):
        return any(c["should_trigger"] for c in s) and any(not c["should_trigger"] for c in s)
    assert has_both(train), "train must contain both trigger and no-trigger"
    # val/held may be tiny with small sets; just assert no empty lists
    assert len(val) >= 1
    assert len(held) >= 1


def test_split_three_way_invalid_fracs():
    """Fractions that sum to >= 1 should raise ValueError."""
    cases = _make_cases(6, 6)
    with pytest.raises(ValueError):
        RL.split_three_way(cases, val_frac=0.5, held_frac=0.6)
    with pytest.raises(ValueError):
        RL.split_three_way(cases, val_frac=0.0, held_frac=0.2)
    with pytest.raises(ValueError):
        RL.split_three_way(cases, val_frac=0.2, held_frac=0.0)


# ---------------------------------------------------------------------------
# run_loop integration tests: held-out isolation
# ---------------------------------------------------------------------------

def _skill_md(tmp_path: Path) -> Path:
    """Write a minimal SKILL.md so parse_skill_md does not error."""
    skill_md = tmp_path / "SKILL.md"
    skill_md.write_text(
        "---\nname: test-skill\ndescription: desc\n---\n# Test\n",
        encoding="utf-8",
    )
    return skill_md


def _make_passing_result(query: str, should_trigger: bool) -> dict:
    return {"query": query, "should_trigger": should_trigger,
            "pass": True, "triggers": 1, "runs": 1, "trigger_rate": 1.0}


def _make_run_eval_spy(cases_by_query: dict[str, dict]):
    """Return a spy for run_eval that records which queries were evaluated."""
    seen_queries: list[list[str]] = []

    def _spy(eval_set, skill_name, description, num_workers, timeout,
              runs_per_query, trigger_threshold, model, max_calls, budget):
        qs = [e["query"] for e in eval_set]
        seen_queries.append(qs)
        results = [_make_passing_result(q, cases_by_query[q]["should_trigger"]) for q in qs]
        total = len(results)
        return {
            "results": results,
            "summary": {"passed": total, "failed": 0, "total": total,
                        "infrastructure_failed": False},
        }

    return _spy, seen_queries


def test_held_out_not_evaluated_during_loop(monkeypatch, tmp_path):
    """In three-way mode, held-out queries must not appear in any mid-loop eval call."""
    _skill_md(tmp_path)

    # Use a larger set so the split has room for all three partitions
    cases = _make_cases(6, 6)
    cases_by_query = {c["query"]: c for c in cases}

    spy, seen_queries = _make_run_eval_spy(cases_by_query)
    monkeypatch.setattr(RL, "run_eval", spy)
    monkeypatch.setattr(RL, "parse_skill_md", lambda p: ("test-skill", "desc", "content"))
    monkeypatch.setattr(RL, "improve_description", lambda **kw: kw["current_description"])
    monkeypatch.setattr(RL, "normalize_cases", lambda x: x)
    monkeypatch.setattr(RL, "validate_options", lambda *a: None)

    monkeypatch.setattr(RL, "CallBudget", lambda n: _UnlimitedBudget())

    out = RL.run_loop(
        eval_set=cases,
        skill_path=tmp_path,
        description_override=None,
        num_workers=1, timeout=5, max_iterations=2, runs_per_query=1,
        trigger_threshold=0.5, holdout=0.2, val_holdout=0.2,
        model="x", verbose=False,
    )

    assert out["held_size"] > 0
    held_queries = set(seen_queries[-1])
    assert len(held_queries) == len(seen_queries[-1]) == out["held_size"]
    for index, call_queries in enumerate(seen_queries[:-1]):
        assert not held_queries.intersection(call_queries), f"Held-out queries leaked into loop call {index}"


def test_held_out_evaluated_exactly_once(monkeypatch, tmp_path):
    """run_eval must be called exactly N_iterations+1 times in three-way mode (loop + 1 held-out eval)."""
    _skill_md(tmp_path)

    cases = _make_cases(6, 6)
    cases_by_query = {c["query"]: c for c in cases}

    call_count = [0]

    def counting_eval(eval_set, skill_name, description, num_workers, timeout,
                      runs_per_query, trigger_threshold, model, max_calls, budget):
        call_count[0] += 1
        results = [_make_passing_result(e["query"], e["should_trigger"]) for e in eval_set]
        total = len(results)
        return {
            "results": results,
            "summary": {"passed": total, "failed": 0, "total": total,
                        "infrastructure_failed": False},
        }

    monkeypatch.setattr(RL, "run_eval", counting_eval)
    monkeypatch.setattr(RL, "parse_skill_md", lambda p: ("test-skill", "desc", "content"))
    monkeypatch.setattr(RL, "improve_description", lambda **kw: kw["current_description"])
    monkeypatch.setattr(RL, "normalize_cases", lambda x: x)
    monkeypatch.setattr(RL, "validate_options", lambda *a: None)
    monkeypatch.setattr(RL, "CallBudget", lambda n: _UnlimitedBudget())

    out = RL.run_loop(
        eval_set=cases,
        skill_path=tmp_path,
        description_override=None,
        num_workers=1, timeout=5, max_iterations=2, runs_per_query=1,
        trigger_threshold=0.5, holdout=0.2, val_holdout=0.2,
        model="x", verbose=False,
    )

    # All train queries passed immediately (all pass=True), so loop exits after 1 iteration.
    # Plus 1 held-out eval = 2 total run_eval calls.
    assert call_count[0] == 2, (
        f"Expected 2 run_eval calls (1 loop + 1 held-out), got {call_count[0]}"
    )
    assert out["held_out_score"] is not None, "Three-way mode must produce held_out_score"


def test_optimizer_never_sees_val_or_held_scores(monkeypatch, tmp_path):
    """improve_description must not receive val_* or test_* keys in history."""
    _skill_md(tmp_path)

    # Make train fail so we enter the improve step
    cases = [
        {"query": "trigger_fail", "should_trigger": True},
        {"query": "trigger_pass", "should_trigger": True},
        {"query": "no_pass_1", "should_trigger": False},
        {"query": "no_pass_2", "should_trigger": False},
        {"query": "no_pass_3", "should_trigger": False},
        {"query": "no_pass_4", "should_trigger": False},
    ]

    def selective_eval(eval_set, skill_name, description, num_workers, timeout,
                       runs_per_query, trigger_threshold, model, max_calls, budget):
        results = []
        for e in eval_set:
            passes = e["query"] != "trigger_fail"
            results.append({
                "query": e["query"], "should_trigger": e["should_trigger"],
                "pass": passes, "triggers": 1 if passes else 0,
                "runs": 1, "trigger_rate": 1.0 if passes else 0.0,
            })
        passed = sum(1 for r in results if r["pass"])
        return {
            "results": results,
            "summary": {"passed": passed, "failed": len(results) - passed,
                        "total": len(results), "infrastructure_failed": False},
        }

    history_seen_in_improve: list[list[dict]] = []

    def spy_improve(**kw):
        history_seen_in_improve.append(kw.get("history", []))
        return kw["current_description"]

    monkeypatch.setattr(RL, "run_eval", selective_eval)
    monkeypatch.setattr(RL, "parse_skill_md", lambda p: ("test-skill", "desc", "content"))
    monkeypatch.setattr(RL, "improve_description", spy_improve)
    monkeypatch.setattr(RL, "normalize_cases", lambda x: x)
    monkeypatch.setattr(RL, "validate_options", lambda *a: None)
    monkeypatch.setattr(RL, "CallBudget", lambda n: _UnlimitedBudget())

    RL.run_loop(
        eval_set=cases,
        skill_path=tmp_path,
        description_override=None,
        num_workers=1, timeout=5, max_iterations=2, runs_per_query=1,
        trigger_threshold=0.5, holdout=0.2, val_holdout=0.2,
        model="x", verbose=False,
    )

    assert history_seen_in_improve, "improve_description should have been called at least once"
    for call_history in history_seen_in_improve:
        for entry in call_history:
            for key in entry:
                assert not key.startswith("val_"), (
                    f"improve_description received val_ key '{key}' in history — "
                    "optimizer must not see validation scores"
                )
                assert not key.startswith("test_"), (
                    f"improve_description received test_ key '{key}' in history — "
                    "optimizer must not see test/held-out scores"
                )


def test_two_way_split_backward_compat(monkeypatch, tmp_path):
    """val_holdout=0 must use the original two-way split (held_out_score=None, test_size>0)."""
    _skill_md(tmp_path)

    cases = _make_cases(5, 5)

    def passing_eval(eval_set, **kw):
        results = [_make_passing_result(e["query"], e["should_trigger"]) for e in eval_set]
        total = len(results)
        return {
            "results": results,
            "summary": {"passed": total, "failed": 0, "total": total,
                        "infrastructure_failed": False},
        }

    monkeypatch.setattr(RL, "run_eval", passing_eval)
    monkeypatch.setattr(RL, "parse_skill_md", lambda p: ("test-skill", "desc", "content"))
    monkeypatch.setattr(RL, "improve_description", lambda **kw: kw["current_description"])
    monkeypatch.setattr(RL, "normalize_cases", lambda x: x)
    monkeypatch.setattr(RL, "validate_options", lambda *a: None)
    monkeypatch.setattr(RL, "CallBudget", lambda n: _UnlimitedBudget())

    out = RL.run_loop(
        eval_set=cases,
        skill_path=tmp_path,
        description_override=None,
        num_workers=1, timeout=5, max_iterations=1, runs_per_query=1,
        trigger_threshold=0.5, holdout=0.4, val_holdout=0.0,
        model="x", verbose=False,
    )

    assert out["held_out_score"] is None, "Two-way mode must not produce held_out_score"
    assert out["best_val_score"] is None, "Two-way mode must not produce best_val_score"
    assert out["test_size"] > 0, "Two-way mode must populate test_size"
    assert out["val_size"] == 0, "Two-way mode must have val_size=0"


# ---------------------------------------------------------------------------
# Helper: unlimited budget stub
# ---------------------------------------------------------------------------

class _UnlimitedBudget:
    """A no-op budget that never raises, for unit tests that mock run_eval."""
    def require(self, n):
        pass

    def consume(self, n=1):
        pass

    def report(self):
        return {"limit": 9999, "used": 0, "remaining": 9999}


def test_best_candidate_uses_validation_score(monkeypatch, tmp_path):
    _skill_md(tmp_path)
    cases = _make_cases(6, 6)
    train, val, held = RL.split_three_way(cases, 0.2, 0.2)
    train_queries = {row["query"] for row in train}
    val_queries = {row["query"] for row in val}
    calls = []

    def evaluate(eval_set, description, **kwargs):
        calls.append((description, {row["query"] for row in eval_set}))
        results = []
        for row in eval_set:
            # Iteration 1 wins validation; iteration 2 wins training.
            passed = (row["query"] in val_queries) if len(calls) == 1 else (row["query"] in train_queries)
            result = _make_passing_result(row["query"], row["should_trigger"])
            result["pass"] = passed
            results.append(result)
        passed = sum(row["pass"] for row in results)
        return {"results": results, "summary": {"passed": passed, "total": len(results),
                "failed": len(results) - passed, "infrastructure_failed": False}}

    monkeypatch.setattr(RL, "run_eval", evaluate)
    monkeypatch.setattr(RL, "improve_description", lambda **kwargs: "iteration two")
    out = RL.run_loop(cases, tmp_path, None, 1, 5, 2, 1, 0.5, 0.2, "x", False,
                      max_calls=100, val_holdout=0.2)
    assert out["iterations_run"] == 2
    assert out["history"][0]["val_passed"] > out["history"][1]["val_passed"]
    assert out["history"][0]["train_passed"] < out["history"][1]["train_passed"]
    assert out["best_description"] == "desc"
    assert len(calls) == 3
    assert calls[-1] == ("desc", {row["query"] for row in held})


@pytest.mark.parametrize("holdout,val_holdout", [(0, 0), (0.2, 0), (0.2, 0.2)])
def test_budget_covers_every_evaluation_mode(monkeypatch, tmp_path, holdout, val_holdout):
    _skill_md(tmp_path)
    cases = _make_cases(6, 6)
    if val_holdout:
        train, val, held = RL.split_three_way(cases, val_holdout, holdout)
        loop_size = len(train) + len(val)
    else:
        loop_size, held = len(cases), []
    expected = (1 + loop_size * 2) * 2 + 2
    if held:
        expected += 1 + len(held) * 2
    calls = []

    def evaluate(eval_set, budget, **kwargs):
        for _ in range(1 + len(eval_set) * 2):
            budget.consume()
        calls.append(eval_set)
        return {"results": [dict(row, **{"pass": False}) for row in eval_set],
                "summary": {"passed": 0, "total": len(eval_set), "infrastructure_failed": False}}

    def improve(budget, **kwargs):
        budget.consume()
        budget.consume()
        return "new description"

    monkeypatch.setattr(RL, "run_eval", evaluate)
    monkeypatch.setattr(RL, "improve_description", improve)
    with pytest.raises(ValueError, match="calls"):
        RL.run_loop(cases, tmp_path, None, 1, 5, 2, 2, 0.5, holdout, "x", False,
                    max_calls=expected - 1, val_holdout=val_holdout)
    assert calls == []
    out = RL.run_loop(cases, tmp_path, None, 1, 5, 2, 2, 0.5, holdout, "x", False,
                      max_calls=expected, val_holdout=val_holdout)
    assert out["planned_max_calls"] == out["call_budget"]["used"] == expected


def test_infrastructure_failure_skips_held_out(monkeypatch, tmp_path):
    _skill_md(tmp_path)
    cases = _make_cases(6, 6)
    calls = []

    def evaluate(eval_set, **kwargs):
        calls.append(eval_set)
        return {"results": [dict(row, **{"pass": False}) for row in eval_set],
                "summary": {"passed": 0, "total": len(eval_set), "infrastructure_failed": True}}

    monkeypatch.setattr(RL, "run_eval", evaluate)
    monkeypatch.setattr(RL, "improve_description", lambda **kwargs: pytest.fail("must stop"))
    out = RL.run_loop(cases, tmp_path, None, 1, 5, 2, 1, 0.5, 0.2, "x", False,
                      max_calls=100, val_holdout=0.2)
    assert len(calls) == 1
    assert out["exit_reason"].startswith("infrastructure_failed")
    assert out["held_out_score"] is None


@pytest.mark.parametrize("scores,sizes,label", [
    ({"best_val_score": "2/2", "held_out_score": "1/2"}, {"val_size": 2, "held_size": 2, "test_size": 0}, "(val)"),
    ({"best_test_score": "2/2"}, {"test_size": 2}, "(test)"),
    ({}, {"test_size": 0}, "(train)"),
])
def test_report_labels_split_scores(scores, sizes, label):
    report = RL.generate_html({"best_score": "2/2", "history": [{"iteration": 1, "train_passed": 2, "train_total": 2}], **scores, **sizes})
    assert f"2/2 {label}" in report
    if sizes.get("held_size"):
        assert "Held-out Score:</strong> 1/2" in report
        assert "Val:</strong> 2" in report
        assert "Held-out:</strong> 2" in report
    assert ("<strong>Test:</strong>" in report) == bool(sizes.get("test_size"))
