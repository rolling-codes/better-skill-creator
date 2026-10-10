"""Compare two eval results and report deltas with validity checks.

Validates that both results are comparable (same skill, overlapping queries, no
infrastructure failures) before computing per-query and aggregate deltas.  Does
not produce an improvement claim unless all shared queries have at least three
valid runs.

Sign convention: every per-query row carries both a raw ``delta`` (candidate minus
baseline trigger_rate) and an oriented ``improvement``.  ``improvement`` is defined
so that a positive value always means the candidate is better: for should_trigger
queries that is a higher trigger_rate, for NO-TRIGGER queries it is a lower one.
Read ``improvement`` for "did it get better"; read ``delta`` for the raw rate change.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

_MIN_RUNS_FOR_CLAIM = 3


def load_result(path: Path) -> dict:
    """Load and minimally validate an eval result JSON file."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path}: must be a JSON object")
    if "skill_name" not in data:
        raise ValueError(f"{path}: missing 'skill_name' field — not a valid eval result")
    if not isinstance(data.get("results"), list):
        raise ValueError(f"{path}: missing or invalid 'results' list")
    for index, row in enumerate(data["results"]):
        if not isinstance(row, dict) or not isinstance(row.get("query"), str):
            raise ValueError(f"{path}: results[{index}] must be an object with a string 'query'")
    if not isinstance(data.get("summary"), dict):
        raise ValueError(f"{path}: missing or invalid 'summary'")
    return data


def validate_compatibility(candidate: dict, baseline: dict) -> tuple[list[str], list[str]]:
    """Return (errors, warnings) for a candidate/baseline pair before computing deltas.

    Errors block comparison entirely; warnings are noted but comparison proceeds.
    """
    errors: list[str] = []
    warnings: list[str] = []

    if candidate["skill_name"] != baseline["skill_name"]:
        errors.append(
            f"skill_name mismatch: candidate='{candidate['skill_name']}' "
            f"baseline='{baseline['skill_name']}'"
        )

    if candidate["summary"].get("infrastructure_failed"):
        errors.append("candidate result has infrastructure_failed=true; rerun before comparing")
    if baseline["summary"].get("infrastructure_failed"):
        errors.append("baseline result has infrastructure_failed=true; rerun before comparing")

    cand_queries = {r["query"] for r in candidate["results"]}
    base_queries = {r["query"] for r in baseline["results"]}
    overlap = cand_queries & base_queries
    if not overlap:
        errors.append("no overlapping queries between candidate and baseline; results are incomparable")
    elif cand_queries != base_queries:
        only_cand = sorted(cand_queries - base_queries)
        only_base = sorted(base_queries - cand_queries)
        if only_cand:
            sample = ", ".join(only_cand[:3]) + ("..." if len(only_cand) > 3 else "")
            warnings.append(f"{len(only_cand)} query/queries only in candidate (not compared): {sample}")
        if only_base:
            sample = ", ".join(only_base[:3]) + ("..." if len(only_base) > 3 else "")
            warnings.append(f"{len(only_base)} query/queries only in baseline (not compared): {sample}")

    cand_model = candidate.get("model", "")
    base_model = baseline.get("model", "")
    if cand_model and base_model and cand_model != base_model:
        warnings.append(
            f"model mismatch: candidate='{cand_model}' baseline='{base_model}' — "
            "comparison is between configurations, not iterations of the same model"
        )

    cand_by_q = {r["query"]: r for r in candidate["results"]}
    base_by_q = {r["query"]: r for r in baseline["results"]}
    for q in overlap:
        c_ok = cand_by_q[q].get("ok_runs") or 0
        b_ok = base_by_q[q].get("ok_runs") or 0
        if c_ok < _MIN_RUNS_FOR_CLAIM:
            warnings.append(f"candidate has only {c_ok} valid run(s) for query: {q[:60]} "
                            f"(need ≥{_MIN_RUNS_FOR_CLAIM} for an improvement claim)")
        if b_ok < _MIN_RUNS_FOR_CLAIM:
            warnings.append(f"baseline has only {b_ok} valid run(s) for query: {q[:60]} "
                            f"(need ≥{_MIN_RUNS_FOR_CLAIM} for an improvement claim)")

    return errors, warnings


def compute_delta(candidate: dict, baseline: dict) -> dict:
    """Compute per-query and aggregate deltas over overlapping queries."""
    cand_by_q = {r["query"]: r for r in candidate["results"]}
    base_by_q = {r["query"]: r for r in baseline["results"]}
    shared = sorted(set(cand_by_q) & set(base_by_q))

    per_query: list[dict] = []
    min_ok_runs = float("inf")
    for q in shared:
        c, b = cand_by_q[q], base_by_q[q]
        c_rate = c.get("trigger_rate") or 0.0
        b_rate = b.get("trigger_rate") or 0.0
        ok = min(c.get("ok_runs") or 0, b.get("ok_runs") or 0)
        min_ok_runs = min(min_ok_runs, ok)
        should_trigger = c.get("should_trigger")
        raw = c_rate - b_rate
        # Oriented so positive always means "better": for NO-TRIGGER queries a
        # lower candidate rate is the improvement, so flip the sign.
        oriented = raw if should_trigger else -raw
        per_query.append({
            "query": q,
            "should_trigger": should_trigger,
            "candidate_trigger_rate": round(c_rate, 4),
            "baseline_trigger_rate": round(b_rate, 4),
            "delta": round(raw, 4),
            "improvement": round(oriented, 4),
            "ok_runs": int(ok),
        })

    n = len(shared)
    c_passed = sum(1 for q in shared if cand_by_q[q].get("pass"))
    b_passed = sum(1 for q in shared if base_by_q[q].get("pass"))
    agg_delta = (c_passed - b_passed) / n if n else 0.0
    can_claim = math.isfinite(min_ok_runs) and min_ok_runs >= _MIN_RUNS_FOR_CLAIM

    return {
        "skill_name": candidate["skill_name"],
        "shared_queries": n,
        "per_query": per_query,
        "aggregate": {
            "candidate_pass_rate": round(c_passed / n, 4) if n else 0.0,
            "baseline_pass_rate": round(b_passed / n, 4) if n else 0.0,
            "delta": round(agg_delta, 4),
        },
        "significance_claim": can_claim,
        "min_ok_runs": int(min_ok_runs) if math.isfinite(min_ok_runs) else 0,
    }


def format_report(delta: dict, warnings: list[str]) -> str:
    """Format a human-readable summary of the comparison result."""
    agg = delta["aggregate"]
    lines = [f"Comparison: {delta['skill_name']} ({delta['shared_queries']} shared queries)"]
    for w in warnings:
        lines.append(f"  warning: {w}")
    lines.append(
        f"  aggregate: candidate {agg['candidate_pass_rate']:.0%} vs "
        f"baseline {agg['baseline_pass_rate']:.0%} (delta {agg['delta']:+.4f})"
    )
    if delta["significance_claim"]:
        d = agg["delta"]
        if d > 0:
            lines.append("  result: candidate passes more queries than baseline")
        elif d < 0:
            lines.append("  result: candidate passes fewer queries than baseline (regression)")
        else:
            lines.append("  result: no difference between candidate and baseline")
    else:
        lines.append(
            f"  result: not enough valid runs to support an improvement claim "
            f"(min ok_runs={delta['min_ok_runs']}, need ≥{_MIN_RUNS_FOR_CLAIM})"
        )
    lines.append("  per-query improvement (+ = candidate better; NO-TRIGGER sign flipped):")
    for pq in delta["per_query"]:
        tag = "TRIGGER   " if pq["should_trigger"] else "NO-TRIGGER"
        lines.append(f"  {tag} {pq['improvement']:+.2f}  (raw {pq['delta']:+.2f})  {pq['query'][:60]}")
    return "\n".join(lines)


def compare_main(candidate_path: Path, baseline_path: Path) -> tuple[dict, int]:
    """Load, validate, compute, and return (result_dict, exit_code).

    exit_code 0 = comparison completed; 1 = error or incompatible inputs.
    """
    try:
        candidate = load_result(candidate_path)
        baseline = load_result(baseline_path)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        return {"status": "error", "error": str(exc)}, 1

    errors, warnings = validate_compatibility(candidate, baseline)
    if errors:
        return {"status": "invalid", "errors": errors, "warnings": warnings}, 1

    delta = compute_delta(candidate, baseline)
    report = format_report(delta, warnings)
    return {
        "status": "complete",
        "warnings": warnings,
        "comparison": delta,
        "report": report,
    }, 0
