#!/usr/bin/env python3
"""Run the eval + improve loop until all pass or max iterations reached.

Combines run_eval.py and improve_description.py in a loop, tracking history
and returning the best description found. Supports a three-way train/val/held-out
split to prevent overfitting: candidate selection uses validation scores, and the
held-out set is evaluated exactly once after the loop on the selected candidate.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import tempfile
import time
import webbrowser
from pathlib import Path

from scripts.generate_report import generate_html
from scripts.improve_description import improve_description
from scripts.run_eval import run_eval
from scripts.utils import parse_skill_md
from scripts.tests_loader import normalize_cases
from scripts.run_eval import validate_options
from scripts.call_budget import CallBudget, DEFAULT_MAX_CALLS


def split_eval_set(eval_set: list[dict], holdout: float, seed: int = 42) -> tuple[list[dict], list[dict]]:
    """Split eval set into train and test sets, stratified by should_trigger."""
    random.seed(seed)

    # Separate by should_trigger
    trigger = [e for e in eval_set if e["should_trigger"]]
    no_trigger = [e for e in eval_set if not e["should_trigger"]]

    # Shuffle each group
    random.shuffle(trigger)
    random.shuffle(no_trigger)

    # Calculate split points
    n_trigger_test = min(max(0, len(trigger)-1), max(1, int(len(trigger) * holdout)))
    n_no_trigger_test = min(max(0, len(no_trigger)-1), max(1, int(len(no_trigger) * holdout)))

    # Split
    test_set = trigger[:n_trigger_test] + no_trigger[:n_no_trigger_test]
    train_set = trigger[n_trigger_test:] + no_trigger[n_no_trigger_test:]

    return train_set, test_set


def split_three_way(
    eval_set: list[dict],
    val_frac: float,
    held_frac: float,
    seed: int = 42,
) -> tuple[list[dict], list[dict], list[dict]]:
    """Split eval set into train / validation / held-out sets, stratified by should_trigger.

    The returned sets partition the input with no overlap:
      train   ≈ 1 - val_frac - held_frac
      val     ≈ val_frac
      held    ≈ held_frac

    Candidate selection during the optimization loop must use only val scores.
    The held-out set must be evaluated exactly once, after the loop, on the
    selected best candidate.  It must never be passed into improve_description
    or used to select among candidates.
    """
    if not (0 < val_frac < 1 and 0 < held_frac < 1 and val_frac + held_frac < 1):
        raise ValueError(
            f"val_frac={val_frac} and held_frac={held_frac} must each be in (0,1) "
            f"and sum to less than 1."
        )
    random.seed(seed)

    trigger = [e for e in eval_set if e["should_trigger"]]
    no_trigger = [e for e in eval_set if not e["should_trigger"]]
    random.shuffle(trigger)
    random.shuffle(no_trigger)

    def _cut(group: list[dict]) -> tuple[list[dict], list[dict], list[dict]]:
        n = len(group)
        # Reserve at least 1 item per non-empty split; clamp so train is never empty.
        n_held = min(max(0, n - 2), max(1 if n >= 3 else 0, round(n * held_frac)))
        n_val = min(max(0, n - n_held - 1), max(1 if n >= 3 else 0, round(n * val_frac)))
        held = group[:n_held]
        val = group[n_held:n_held + n_val]
        train = group[n_held + n_val:]
        return train, val, held

    tr_t, va_t, he_t = _cut(trigger)
    tr_n, va_n, he_n = _cut(no_trigger)

    return tr_t + tr_n, va_t + va_n, he_t + he_n


def run_loop(
    eval_set: list[dict],
    skill_path: Path,
    description_override: str | None,
    num_workers: int,
    timeout: int,
    max_iterations: int,
    runs_per_query: int,
    trigger_threshold: float,
    holdout: float,
    model: str,
    verbose: bool,
    live_report_path: Path | None = None,
    log_dir: Path | None = None,
    max_calls: int = DEFAULT_MAX_CALLS,
    val_holdout: float = 0.0,
) -> dict:
    """Run the eval + improvement loop.

    When val_holdout > 0 a three-way split is performed:
      train ≈ 1 - holdout - val_holdout
      val   ≈ val_holdout   (used for candidate selection)
      held  ≈ holdout       (evaluated exactly once after the loop)

    The held-out set is never passed to improve_description and never used to
    select among candidates.  If val_holdout == 0 the original two-way split
    (train + held-out) is used and best_description is selected by held-out
    score as before.
    """
    eval_set = normalize_cases(eval_set)
    validate_options(num_workers, timeout, runs_per_query, trigger_threshold)
    if not eval_set or max_iterations < 1 or not 0 <= holdout < 1:
        raise ValueError("Require nonempty cases, positive iterations, and holdout in [0,1)")
    budget = CallBudget(max_calls)
    # Determine split mode
    if val_holdout > 0 and holdout > 0:
        # Three-way split: train / val (candidate selection) / held-out (final check)
        train_set, val_set, held_set = split_three_way(eval_set, val_frac=val_holdout, held_frac=holdout)
        if verbose:
            print(
                f"Split: {len(train_set)} train, {len(val_set)} val, {len(held_set)} held-out "
                f"(val_holdout={val_holdout}, holdout={holdout})",
                file=sys.stderr,
            )
        # Legacy test_set kept empty during loop; val results feed candidate selection
        test_set = []
    elif holdout > 0:
        # Two-way split: train / held-out (backward-compatible)
        train_set, test_set = split_eval_set(eval_set, holdout)
        val_set = []
        held_set = []
        if verbose:
            print(f"Split: {len(train_set)} train, {len(test_set)} test (holdout={holdout})", file=sys.stderr)
    else:
        train_set = eval_set
        test_set = []
        val_set = []
        held_set = []

    eval_per_iter = 1 + (len(train_set) + len(val_set) + len(test_set)) * runs_per_query
    worst_case = eval_per_iter * max_iterations + 2 * (max_iterations - 1)
    if held_set:
        worst_case += 1 + len(held_set) * runs_per_query
    budget.require(worst_case)
    name, original_description, content = parse_skill_md(skill_path)
    current_description = description_override or original_description

    history = []
    exit_reason = "unknown"

    for iteration in range(1, max_iterations + 1):
        if verbose:
            print(f"\n{'='*60}", file=sys.stderr)
            print(f"Iteration {iteration}/{max_iterations}", file=sys.stderr)
            print(f"Description: {current_description}", file=sys.stderr)
            print(f"{'='*60}", file=sys.stderr)

        # Evaluate train + val + test together in one batch for parallelism.
        # val_set is evaluated per-iteration for candidate selection.
        # test_set is used in two-way-split mode only.
        # held_set is NEVER included here; it is evaluated once after the loop.
        all_queries = train_set + val_set + test_set
        t0 = time.time()
        all_results = run_eval(
            eval_set=all_queries,
            skill_name=name,
            description=current_description,
            num_workers=num_workers,
            timeout=timeout,
            runs_per_query=runs_per_query,
            trigger_threshold=trigger_threshold,
            model=model,
            max_calls=max_calls,
            budget=budget,
        )
        eval_elapsed = time.time() - t0

        # Split results back into train/val/test by matching queries
        train_queries_set = {q["query"] for q in train_set}
        val_queries_set = {q["query"] for q in val_set}
        train_result_list = [r for r in all_results["results"] if r["query"] in train_queries_set]
        val_result_list = [r for r in all_results["results"] if r["query"] in val_queries_set]
        test_result_list = [r for r in all_results["results"] if r["query"] not in train_queries_set and r["query"] not in val_queries_set]

        train_passed = sum(1 for r in train_result_list if r["pass"])
        train_total = len(train_result_list)
        train_summary = {"passed": train_passed, "failed": train_total - train_passed, "total": train_total}
        train_results = {"results": train_result_list, "summary": train_summary}

        if val_set:
            val_passed = sum(1 for r in val_result_list if r["pass"])
            val_total = len(val_result_list)
            val_summary = {"passed": val_passed, "failed": val_total - val_passed, "total": val_total}
            val_results: dict | None = {"results": val_result_list, "summary": val_summary}
        else:
            val_results = None
            val_summary = None

        if test_set:
            test_passed = sum(1 for r in test_result_list if r["pass"])
            test_total = len(test_result_list)
            test_summary = {"passed": test_passed, "failed": test_total - test_passed, "total": test_total}
            test_results: dict | None = {"results": test_result_list, "summary": test_summary}
        else:
            test_results = None
            test_summary = None

        history.append({
            "iteration": iteration,
            "description": current_description,
            "train_passed": train_summary["passed"],
            "train_failed": train_summary["failed"],
            "train_total": train_summary["total"],
            "train_results": train_results["results"],
            "val_passed": val_summary["passed"] if val_summary else None,
            "val_failed": val_summary["failed"] if val_summary else None,
            "val_total": val_summary["total"] if val_summary else None,
            "val_results": val_results["results"] if val_results else None,
            "test_passed": test_summary["passed"] if test_summary else None,
            "test_failed": test_summary["failed"] if test_summary else None,
            "test_total": test_summary["total"] if test_summary else None,
            "test_results": test_results["results"] if test_results else None,
            # For backward compat with report generator
            "passed": train_summary["passed"],
            "failed": train_summary["failed"],
            "total": train_summary["total"],
            "results": train_results["results"],
        })

        # Stop immediately if the eval infrastructure failed (auth / timeout /
        # process). Optimizing on untrustworthy signal is worse than stopping —
        # do not propose or write a new description from a broken run.
        if all_results["summary"].get("infrastructure_failed") or any(r.get("failed_runs", 0) or r.get("execution_error") for r in all_results["results"]):
            exit_reason = f"infrastructure_failed (iteration {iteration})"
            if verbose:
                print("\nEval infrastructure failed — stopping without optimizing.", file=sys.stderr)
            break

        # Write live report if path provided
        if live_report_path:
            partial_output = {
                "original_description": original_description,
                "best_description": current_description,
                "best_score": "in progress",
                "iterations_run": len(history),
                "holdout": holdout,
                "train_size": len(train_set),
                "test_size": len(test_set),
                "history": history,
            }
            live_report_path.write_text(generate_html(partial_output, auto_refresh=True, skill_name=name), encoding="utf-8")

        if verbose:
            def print_eval_stats(label, results, elapsed):
                """Print aggregate trigger metrics and per-query outcomes to stderr."""
                pos = [r for r in results if r["should_trigger"]]
                neg = [r for r in results if not r["should_trigger"]]
                tp = sum(r["triggers"] for r in pos)
                pos_runs = sum(r["runs"] for r in pos)
                fn = pos_runs - tp
                fp = sum(r["triggers"] for r in neg)
                neg_runs = sum(r["runs"] for r in neg)
                tn = neg_runs - fp
                total = tp + tn + fp + fn
                precision = tp / (tp + fp) if (tp + fp) > 0 else 1.0
                recall = tp / (tp + fn) if (tp + fn) > 0 else 1.0
                accuracy = (tp + tn) / total if total > 0 else 0.0
                print(f"{label}: {tp+tn}/{total} correct, precision={precision:.0%} recall={recall:.0%} accuracy={accuracy:.0%} ({elapsed:.1f}s)", file=sys.stderr)
                for r in results:
                    status = "PASS" if r["pass"] else "FAIL"
                    rate_str = f"{r['triggers']}/{r['runs']}"
                    print(f"  [{status}] rate={rate_str} expected={r['should_trigger']}: {r['query'][:60]}", file=sys.stderr)

            print_eval_stats("Train", train_results["results"], eval_elapsed)
            if val_results:
                print_eval_stats("Val  ", val_results["results"], 0)
            if test_results:
                print_eval_stats("Test ", test_results["results"], 0)

        if train_summary["failed"] == 0:
            exit_reason = f"all_passed (iteration {iteration})"
            if verbose:
                print(f"\nAll train queries passed on iteration {iteration}!", file=sys.stderr)
            break

        if iteration == max_iterations:
            exit_reason = f"max_iterations ({max_iterations})"
            if verbose:
                print(f"\nMax iterations reached ({max_iterations}).", file=sys.stderr)
            break

        # Improve the description based on train results
        if verbose:
            print(f"\nImproving description...", file=sys.stderr)

        t0 = time.time()
        # Strip val and test scores from history so the optimizer cannot see held-out
        # or validation results — it must improve based on train signal only.
        blinded_history = [
            {k: v for k, v in h.items() if not k.startswith("test_") and not k.startswith("val_")}
            for h in history
        ]
        try:
            new_description = improve_description(
                skill_name=name,
                skill_content=content,
                current_description=current_description,
                eval_results=train_results,
                history=blinded_history,
                model=model,
                log_dir=log_dir,
                iteration=iteration,
                budget=budget,
            )
        except Exception as exc:  # reason: any failure while improving must keep the iterations already paid for
            # Same contract as an eval failure: stop, keep the iterations already paid for.
            exit_reason = f"infrastructure_failed (improve, iteration {iteration}: {type(exc).__name__}: {exc})"
            if verbose:
                print(f"\nImproving the description failed ({type(exc).__name__}: {exc}) — stopping with the iterations completed so far.", file=sys.stderr)
            break
        improve_elapsed = time.time() - t0

        if verbose:
            print(f"Proposed ({improve_elapsed:.1f}s): {new_description}", file=sys.stderr)

        current_description = new_description

    # Find the best iteration.
    # Three-way mode: select by val score (held-out is never used for selection).
    # Two-way mode:   select by test score (backward-compatible).
    # No-holdout:     select by train score.
    if val_set:
        best = max(history, key=lambda h: h["val_passed"] or 0)
        best_score = f"{best['val_passed']}/{best['val_total']}"
    elif test_set:
        best = max(history, key=lambda h: h["test_passed"] or 0)
        best_score = f"{best['test_passed']}/{best['test_total']}"
    else:
        best = max(history, key=lambda h: h["train_passed"])
        best_score = f"{best['train_passed']}/{best['train_total']}"

    # Three-way mode: evaluate held-out set exactly once on the selected best candidate.
    # This must happen after the loop; the result must not be used to re-select or re-tune.
    held_out_result: dict | None = None
    held_out_score: str | None = None
    if held_set and not exit_reason.startswith("infrastructure_failed"):
        if verbose:
            print(f"\nEvaluating held-out set on best candidate (iteration {best['iteration']})...", file=sys.stderr)
        held_eval = run_eval(
            eval_set=held_set,
            skill_name=name,
            description=best["description"],
            num_workers=num_workers,
            timeout=timeout,
            runs_per_query=runs_per_query,
            trigger_threshold=trigger_threshold,
            model=model,
            max_calls=max_calls,
            budget=budget,
        )
        held_passed = held_eval["summary"]["passed"]
        held_total = held_eval["summary"]["total"]
        held_out_score = f"{held_passed}/{held_total}"
        held_out_result = held_eval
        if verbose:
            print(f"Held-out score: {held_out_score}", file=sys.stderr)

    if verbose:
        print(f"\nExit reason: {exit_reason}", file=sys.stderr)
        print(f"Best score: {best_score} (iteration {best['iteration']})", file=sys.stderr)

    return {
        "exit_reason": exit_reason,
        "call_budget": budget.report(),
        "planned_max_calls": worst_case,
        "original_description": original_description,
        "best_description": best["description"],
        "best_score": best_score,
        "best_train_score": f"{best['train_passed']}/{best['train_total']}",
        "best_val_score": f"{best['val_passed']}/{best['val_total']}" if val_set else None,
        "best_test_score": f"{best['test_passed']}/{best['test_total']}" if test_set else None,
        "held_out_score": held_out_score,
        "final_description": current_description,
        "iterations_run": len(history),
        "holdout": holdout,
        "val_holdout": val_holdout if val_set else None,
        "train_size": len(train_set),
        "val_size": len(val_set),
        "test_size": len(test_set),
        "held_size": len(held_set),
        "history": history,
    }


def main():
    """Run description optimization from CLI options, save reports, and exit with its status."""
    parser = argparse.ArgumentParser(description="Run eval + improve loop")
    parser.add_argument("--eval-set", required=True, help="Path to eval set JSON file")
    parser.add_argument("--skill-path", required=True, help="Path to skill directory")
    parser.add_argument("--description", default=None, help="Override starting description")
    parser.add_argument("--num-workers", type=int, default=10, help="Number of parallel workers")
    parser.add_argument("--timeout", type=int, default=30, help="Timeout per query in seconds")
    parser.add_argument("--max-calls", type=int, default=DEFAULT_MAX_CALLS, help="Shared allowance including improvement rewrites")
    parser.add_argument("--max-iterations", type=int, default=5, help="Max improvement iterations")
    parser.add_argument("--runs-per-query", type=int, default=3, help="Number of runs per query")
    parser.add_argument("--trigger-threshold", type=float, default=0.5, help="Trigger rate threshold")
    parser.add_argument("--holdout", type=float, default=0.2, help="Fraction of eval set to hold out as final test (0 to disable). When --val-holdout is also set, this becomes the held-out test fraction.")
    parser.add_argument("--val-holdout", type=float, default=0.2, help="Fraction to use as validation set for candidate selection (0 to use legacy two-way split). When >0, enables three-way train/val/held-out mode.")
    parser.add_argument("--model", required=True, help="Model for improvement")
    parser.add_argument("--verbose", action="store_true", help="Print progress to stderr")
    parser.add_argument("--report", default="auto", help="Generate HTML report at this path (default: 'auto' for temp file, 'none' to disable)")
    parser.add_argument("--results-dir", default=None, help="Save all outputs (results.json, report.html, log.txt) to a timestamped subdirectory here")
    args = parser.parse_args()

    try:
        eval_set = json.loads(Path(args.eval_set).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        print(f"Error: could not read eval set {args.eval_set}: {e}", file=sys.stderr)
        sys.exit(1)
    skill_path = Path(args.skill_path)

    if not (skill_path / "SKILL.md").exists():
        print(f"Error: No SKILL.md found at {skill_path}", file=sys.stderr)
        sys.exit(1)

    name, _, _ = parse_skill_md(skill_path)

    # Set up live report path
    if args.report != "none":
        if args.report == "auto":
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            live_report_path = Path(tempfile.gettempdir()) / f"skill_description_report_{skill_path.name}_{timestamp}.html"
        else:
            live_report_path = Path(args.report)
        # Open the report immediately so the user can watch
        live_report_path.write_text("<html><body><h1>Starting optimization loop...</h1><meta http-equiv='refresh' content='5'></body></html>", encoding="utf-8")
        webbrowser.open(str(live_report_path))
    else:
        live_report_path = None

    # Determine output directory (create before run_loop so logs can be written)
    if args.results_dir:
        timestamp = time.strftime("%Y-%m-%d_%H%M%S")
        results_dir = Path(args.results_dir) / timestamp
        results_dir.mkdir(parents=True, exist_ok=True)
    else:
        results_dir = None

    log_dir = results_dir / "logs" if results_dir else None

    output = run_loop(
        eval_set=eval_set,
        skill_path=skill_path,
        description_override=args.description,
        num_workers=args.num_workers,
        timeout=args.timeout,
        max_iterations=args.max_iterations,
        runs_per_query=args.runs_per_query,
        trigger_threshold=args.trigger_threshold,
        holdout=args.holdout,
        model=args.model,
        verbose=args.verbose,
        live_report_path=live_report_path,
        log_dir=log_dir,
        max_calls=args.max_calls,
        val_holdout=args.val_holdout,
    )

    # Save JSON output
    json_output = json.dumps(output, indent=2)
    print(json_output)
    if results_dir:
        (results_dir / "results.json").write_text(json_output, encoding="utf-8")

    # Write final HTML report (without auto-refresh)
    if live_report_path:
        live_report_path.write_text(generate_html(output, auto_refresh=False, skill_name=name), encoding="utf-8")
        print(f"\nReport: {live_report_path}", file=sys.stderr)

    if results_dir and live_report_path:
        (results_dir / "report.html").write_text(generate_html(output, auto_refresh=False, skill_name=name), encoding="utf-8")

    if results_dir:
        print(f"Results saved to: {results_dir}", file=sys.stderr)

    # Exit codes: 1 = eval infrastructure failed, 0 = converged (all passed),
    # 2 = ran to completion but did not reach all-passing.
    exit_reason = output.get("exit_reason", "")
    if exit_reason.startswith("infrastructure_failed"):
        sys.exit(1)
    sys.exit(0 if exit_reason.startswith("all_passed") else 2)


if __name__ == "__main__":
    main()
