"""Compare two eval results and report deltas with validity checks.

Validates that both results are comparable (same skill, overlapping queries, no
infrastructure failures) before computing per-query and aggregate deltas.  Uses
a minimum of three valid runs as a sample-sufficiency guard, not a statistical
significance test.

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
_UNKNOWN_MODELS = {"default", "configured default"}
_MODEL_ALIASES = {"sonnet", "opus", "haiku", "fable", "best", "opusplan"}


def _validate_threshold(value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 < value <= 1:
        raise ValueError("trigger_threshold must be a finite number in (0, 1]")


def load_result(path: Path, *, skill_name: str | None = None) -> dict:
    """Load and minimally validate an eval result JSON file."""
    data = json.loads(path.read_text(encoding="utf-8"))
    return _validate_result(data, skill_name=skill_name)


def _validate_result(data: dict, *, skill_name: str | None = None) -> dict:
    path = "eval result"
    if not isinstance(data, dict):
        raise ValueError(f"{path}: must be a JSON object")
    if "skill_name" not in data:
        raise ValueError(f"{path}: missing 'skill_name' field — not a valid eval result")
    if not isinstance(data["skill_name"], str) or not data["skill_name"].strip():
        raise ValueError("skill_name must be a nonempty string")
    if "trigger_threshold" in data:
        _validate_threshold(data["trigger_threshold"])
    model = data.get("model")
    if model is not None and (not isinstance(model, str) or not model.strip()):
        raise ValueError("model must be a nonempty string or null")
    if not isinstance(data.get("results"), list):
        raise ValueError(f"{path}: missing or invalid 'results' list")
    seen: set[str] = set()
    for index, row in enumerate(data["results"]):
        if not isinstance(row, dict) or not isinstance(row.get("query"), str):
            raise ValueError(f"{path}: results[{index}] must be an object with a string 'query'")
        if row["query"] in seen:
            raise ValueError(f"duplicate query: {row['query']}")
        seen.add(row["query"])
        if not isinstance(row.get("should_trigger"), bool):
            raise ValueError(f"results[{index}] needs boolean should_trigger")
        rate = row.get("trigger_rate")
        if isinstance(rate, bool) or not isinstance(rate, (int, float)) or not math.isfinite(rate) or not 0 <= rate <= 1:
            raise ValueError(f"results[{index}] trigger_rate must be a finite number from 0 to 1")
        for field in ("ok_runs", "failed_runs"):
            if field == "failed_runs" and field not in row:
                continue
            count = row.get(field)
            if isinstance(count, bool) or not isinstance(count, int) or count < 0:
                raise ValueError(f"results[{index}] {field} must be a nonnegative integer")
        if not isinstance(row.get("pass"), bool):
            raise ValueError(f"results[{index}] pass must be a boolean")
        if row["ok_runs"] == 0:
            raise ValueError(f"results[{index}] ok_runs must be positive for comparison")
        incomplete = bool(row.get("failed_runs", 0) or row.get("execution_error") or row.get("status") == "incomplete")
        if incomplete and row["pass"]:
            raise ValueError(f"results[{index}] incomplete query execution cannot pass")
        if not incomplete and "trigger_threshold" in data:
            threshold = data["trigger_threshold"]
            expected_pass = rate >= threshold if row["should_trigger"] else rate < threshold
            if row["pass"] != expected_pass:
                raise ValueError(f"results[{index}] pass disagrees with trigger_rate, should_trigger and trigger_threshold")
    if not isinstance(data.get("summary"), dict):
        raise ValueError(f"{path}: missing or invalid 'summary'")
    if "infrastructure_failed" in data["summary"] and not isinstance(data["summary"]["infrastructure_failed"], bool):
        raise ValueError("summary.infrastructure_failed must be a boolean")
    if skill_name is not None and data["skill_name"] != skill_name:
        raise ValueError(
            f"skill_name mismatch: candidate='{skill_name}' baseline='{data['skill_name']}'"
        )
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

    for label, result in (("candidate", candidate), ("baseline", baseline)):
        if any(row.get("failed_runs", 0) or row.get("execution_error") or row.get("status") == "incomplete"
               for row in result["results"]):
            errors.append(f"{label} contains incomplete query executions; rerun before comparing")
    c_threshold, b_threshold = candidate.get("trigger_threshold"), baseline.get("trigger_threshold")
    if c_threshold is None or b_threshold is None:
        warnings.append("trigger threshold metadata missing; legacy pass criteria cannot be verified")
    elif c_threshold != b_threshold:
        errors.append(f"trigger_threshold mismatch: candidate={c_threshold} baseline={b_threshold}")

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
    aliases = sorted({model for model in (cand_model, base_model)
                      if isinstance(model, str) and model.removesuffix("[1m]") in _MODEL_ALIASES})
    if aliases:
        warnings.append(f"model aliases ({', '.join(aliases)}) do not verify the same resolved runtime across runs; use pinned full model IDs for reproducible comparisons")
    if cand_model and base_model and cand_model != base_model:
        warnings.append(
            f"model mismatch: candidate='{cand_model}' baseline='{base_model}' — "
            "comparison is between configurations, not iterations of the same model"
        )

    cand_by_q = {r["query"]: r for r in candidate["results"]}
    base_by_q = {r["query"]: r for r in baseline["results"]}
    for q in sorted(overlap):
        if cand_by_q[q].get("should_trigger") != base_by_q[q].get("should_trigger"):
            errors.append(f"conflicting should_trigger labels for query: {q}")
        c_ok = cand_by_q[q].get("ok_runs") or 0
        b_ok = base_by_q[q].get("ok_runs") or 0
        if c_ok < _MIN_RUNS_FOR_CLAIM:
            warnings.append(f"candidate has only {c_ok} valid run(s) for query: {q[:60]} "
                            f"(need ≥{_MIN_RUNS_FOR_CLAIM} for sample sufficiency)")
        if b_ok < _MIN_RUNS_FOR_CLAIM:
            warnings.append(f"baseline has only {b_ok} valid run(s) for query: {q[:60]} "
                            f"(need ≥{_MIN_RUNS_FOR_CLAIM} for sample sufficiency)")

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
        # Legacy field: sample sufficiency only, not statistical significance.
        "significance_claim": can_claim,
        "sample_sufficient": can_claim,
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
    lines.append("  sample sufficiency is not a statistical significance test")
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
            f"  result: not enough valid runs for sample sufficiency "
            f"(min ok_runs={delta['min_ok_runs']}, need ≥{_MIN_RUNS_FOR_CLAIM})"
        )
    lines.append("  per-query improvement (+ = candidate better; NO-TRIGGER sign flipped):")
    for pq in delta["per_query"]:
        tag = "TRIGGER   " if pq["should_trigger"] else "NO-TRIGGER"
        lines.append(f"  {tag} {pq['improvement']:+.2f}  (raw {pq['delta']:+.2f})  {pq['query'][:60]}")
    return "\n".join(lines)


def normalize_result(data: dict, *, skill_name: str | None = None) -> dict[str, dict]:
    """Normalize raw results or CLI envelopes without guessing model aliases."""
    if not isinstance(data, dict):
        raise ValueError("eval result must be a JSON object")
    if "trigger_by_model" in data:
        models = data["trigger_by_model"]
        if not isinstance(models, dict) or not models:
            raise ValueError("trigger_by_model must be a nonempty object")
        normalized = {}
        for key, value in models.items():
            if not isinstance(key, str) or not key.strip():
                raise ValueError("model keys must be nonempty strings")
            row = _validate_result(value, skill_name=skill_name)
            model = row.get("model")
            if model is None:
                raise ValueError(f"model key '{key}' requires an explicit result model")
            if model != key:
                raise ValueError(f"model key '{key}' disagrees with result model '{model}'")
            normalized[key] = row
        if len({r["skill_name"] for r in normalized.values()}) != 1:
            raise ValueError("matrix contains different skill names")
        return normalized
    raw = data.get("trigger", data)
    raw = _validate_result(raw, skill_name=skill_name)
    model = raw.get("model")
    if model is not None and not isinstance(model, str):
        raise ValueError("model must be a string or null")
    return {model or "default": raw}


def load_model_results(path: Path, *, skill_name: str | None = None) -> dict[str, dict]:
    return normalize_result(json.loads(path.read_text(encoding="utf-8")), skill_name=skill_name)


def validate_baseline(path: Path, requested_models: list[str | None], *,
                      skill_name: str | None = None, cases: list[dict] | None = None,
                      trigger_threshold: float | None = None) -> dict[str, dict]:
    """Fail before live calls if a baseline cannot cover the requested models."""
    if trigger_threshold is not None:
        _validate_threshold(trigger_threshold)
    if not requested_models or any(not m or m in _UNKNOWN_MODELS for m in requested_models):
        raise ValueError("baseline comparison requires explicit known model identities")
    models = load_model_results(path, skill_name=skill_name)
    if any(result.get("model") is None or result["model"] in _UNKNOWN_MODELS for result in models.values()):
        raise ValueError("baseline comparison requires explicit known model identities in each result")
    missing = sorted({m or "default" for m in requested_models} - models.keys())
    if missing:
        raise ValueError(f"baseline missing requested models: {', '.join(missing)}")
    current_cases = None
    if cases is not None:
        from scripts.tests_loader import normalize_cases
        current_cases = {row["query"]: row["should_trigger"] for row in normalize_cases(cases)}
    for model in {m or "default" for m in requested_models}:
        baseline = models[model]
        if any(row.get("failed_runs", 0) or row.get("execution_error") or row.get("status") == "incomplete"
               for row in baseline["results"]):
            raise ValueError(f"baseline model {model} contains incomplete query executions")
        if trigger_threshold is not None and "trigger_threshold" in baseline and baseline["trigger_threshold"] != trigger_threshold:
            raise ValueError(f"baseline model {model} trigger_threshold mismatch: current={trigger_threshold} baseline={baseline['trigger_threshold']}")
        if models[model]["summary"].get("infrastructure_failed"):
            raise ValueError(f"baseline model {model} has infrastructure_failed=true")
        if current_cases is not None:
            baseline_cases = {row["query"]: row["should_trigger"] for row in models[model]["results"]}
            shared = current_cases.keys() & baseline_cases.keys()
            if not shared:
                raise ValueError(f"baseline model {model} has no overlapping queries with current cases")
            for query in sorted(shared):
                if current_cases[query] != baseline_cases[query]:
                    raise ValueError(f"baseline model {model} has conflicting should_trigger labels for query: {query}")
    return {model: models[model] for model in sorted({m or "default" for m in requested_models})}


def _compare_pair(candidate: dict, baseline: dict) -> tuple[dict, int]:
    errors, warnings = validate_compatibility(candidate, baseline)
    if errors:
        return {"status": "invalid", "errors": errors, "warnings": warnings}, 1
    delta = compute_delta(candidate, baseline)
    return {"status": "complete", "warnings": warnings, "comparison": delta,
            "report": format_report(delta, warnings)}, 0


def compare_results(candidate: dict, baseline: dict) -> tuple[dict, int]:
    """Compare model-aligned inputs; regression is a result, not an execution error."""
    try:
        candidates = normalize_result(candidate)
        baselines = normalize_result(baseline)
    except (ValueError, TypeError) as exc:
        return {"status": "error", "error": str(exc)}, 1
    # Preserve historical raw single-pair API, including cross-model warning.
    if "results" in candidate and "results" in baseline:
        return _compare_pair(candidate, baseline)
    if _UNKNOWN_MODELS.intersection(candidates) or _UNKNOWN_MODELS.intersection(baselines):
        return {"status": "incomplete", "errors": ["model identity is unknown; use explicit model results"]}, 1
    missing_candidate = sorted(baselines.keys() - candidates.keys())
    missing_baseline = sorted(candidates.keys() - baselines.keys())
    errors = []
    if missing_candidate:
        errors.append(f"candidate missing models: {', '.join(missing_candidate)}")
    if missing_baseline:
        errors.append(f"baseline missing models: {', '.join(missing_baseline)}")
    comparisons = {}
    reports = []
    for model in sorted(candidates.keys() & baselines.keys()):
        comparison, code = _compare_pair(candidates[model], baselines[model])
        comparisons[model] = comparison
        reports.append(f"Model: {model}\n" + comparison.get("report", "; ".join(comparison.get("errors", []))))
        if code:
            errors.append(f"model {model}: comparison invalid")
    complete = not errors
    return {"status": "complete" if complete else "incomplete",
            "comparisons_by_model": comparisons,
            "missing_models": {"candidate": missing_candidate, "baseline": missing_baseline},
            "errors": errors,
            "report": "\n".join(errors + reports)}, 0 if complete else 1


def compare_main(candidate_path: Path, baseline_path: Path) -> tuple[dict, int]:
    """Load and compare raw eval files or CLI result envelopes."""
    try:
        candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
        baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        return {"status": "error", "error": str(exc)}, 1
    return compare_results(candidate, baseline)


def comparison_summary(result: dict) -> str:
    """Summarize actual compared queries for raw pairs and model matrices."""
    if "comparison" in result:
        return f"{result['comparison']['shared_queries']} shared queries compared"
    pairs = result.get("comparisons_by_model", {})
    counts = [(model, pair["comparison"]["shared_queries"]) for model, pair in sorted(pairs.items()) if "comparison" in pair]
    if counts:
        return "; ".join(f"{model}: {count} shared queries compared" for model, count in counts)
    return result.get("error") or "; ".join(result.get("errors", [])) or "No queries compared."
