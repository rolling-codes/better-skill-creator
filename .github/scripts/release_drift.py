"""Compare release trigger inputs and summarize retained canary evidence without model calls."""

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "skills/skill-creator"))
from scripts.skill_ir import Skill
from scripts.tests_loader import load_yaml_cases, normalize_cases

MODELS = ("haiku", "sonnet")
FIXTURES = ".github/fixtures/trigger-canary"
CASE_FILES = ("should_trigger.yaml", "should_not_trigger.yaml")
SKILL = "skills/skill-creator/SKILL.md"
METRICS = ("cost_usd", "input_tokens", "output_tokens", "duration_ms")
COMPLETE = {"passed": 0, "expectations_failed": 2}
VERSION = re.compile(r"v([0-9]+)\.([0-9]+)\.([0-9]+)")
NETWORK_TIMEOUT = 30


def command(*args, cwd=ROOT, timeout=10):
    """Run a fixed executable with separate arguments and no shell."""
    return subprocess.run(args, cwd=cwd, shell=False, check=True, capture_output=True,
                          encoding="utf-8", timeout=timeout).stdout


def version(tag):
    """Return numeric components for a stable release tag."""
    match = VERSION.fullmatch(tag)
    return tuple(map(int, match.groups())) if match else ()


def previous_release(tags, candidate):
    """Select the highest published stable version below the candidate."""
    return max((tag for tag in tags if version(tag) and version(tag) < version(candidate)),
               key=version, default=None)


def prompt_inputs(root):
    """Read the trigger inputs from a repository snapshot."""
    skill = Skill.from_path((root / SKILL).parent)
    fields = {"name": skill.name, "description": skill.description}
    if not all(isinstance(value, str) and value for value in fields.values()):
        raise ValueError("Invalid skill name or description")
    suite = normalize_cases([case for name in CASE_FILES
                             for case in load_yaml_cases(root / FIXTURES / name)])
    if not suite:
        raise ValueError("No normalized trigger fixtures")
    return fields, {case["query"]: case["should_trigger"] for case in suite}


def compare_inputs(previous, candidate):
    """Report skill metadata changes and normalized fixture differences."""
    old_fields, old_cases = previous
    new_fields, new_cases = candidate
    return {
        "fields": {key: {"previous": old_fields[key], "candidate": new_fields[key],
                         "changed": old_fields[key] != new_fields[key]} for key in old_fields},
        "added": {query: new_cases[query] for query in sorted(new_cases.keys() - old_cases.keys())},
        "removed": {query: old_cases[query] for query in sorted(old_cases.keys() - new_cases.keys())},
        "label_changed": {
            query: {"previous": old_cases[query], "candidate": new_cases[query]}
            for query in sorted(old_cases.keys() & new_cases.keys())
            if old_cases[query] != new_cases[query]
        },
    }


def release_drift(repo, ref, sha):
    """Compare a release branch with the preceding published release."""
    tag = ref.removeprefix("refs/heads/release/")
    if not ref.startswith("refs/heads/release/") or not version(tag):
        return {"status": "unavailable", "reason": "Release branch must be named release/vMAJOR.MINOR.PATCH."}
    baseline = None
    try:
        tags = command("gh", "release", "list", "-R", repo, "--exclude-drafts",
                       "--exclude-pre-releases", "--limit", "100", "--json", "tagName",
                       timeout=NETWORK_TIMEOUT)
        baseline = previous_release((row["tagName"] for row in json.loads(tags)), tag)
        if baseline is None:
            return {"status": "unavailable", "reason": "No earlier published stable release found."}
        command("git", "fetch", "--no-tags", "origin", f"refs/tags/{baseline}",
                timeout=NETWORK_TIMEOUT)
        baseline_sha = command("git", "rev-parse", "FETCH_HEAD^{commit}").strip()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for path in (SKILL, *(f"{FIXTURES}/{name}" for name in CASE_FILES)):
                destination = root / path
                destination.parent.mkdir(parents=True, exist_ok=True)
                content = command("git", "show", f"{baseline_sha}:{path}")
                destination.write_text(content, encoding="utf-8")
            changes = compare_inputs(prompt_inputs(root), prompt_inputs(ROOT))
        return {"status": "compared", "baseline": baseline, "baseline_sha": baseline_sha,
                "candidate": tag, "candidate_sha": sha, **changes}
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError, yaml.YAMLError):
        return {"status": "unavailable", "baseline": baseline,
                "reason": "Could not read a valid published release and candidate snapshot."}


def known_metric(value):
    """Accept finite, nonnegative numeric measurements, including zero."""
    return type(value) in (int, float) and 0 <= value < math.inf


def canary_evidence(directory, model):
    """Distinguish real completed evidence, skips, and unusable artifacts."""
    try:
        status = json.loads((directory / "status.json").read_text(encoding="utf-8"))
        if not isinstance(status, dict) or status.get("model") != model:
            raise ValueError("Wrong canary model")
        outcome = status.get("status")
        if outcome == "skipped_missing_credentials":
            return {"status": outcome, "attempted_calls": 0}
        reports = list(directory.glob("*/results.json"))
        if len(reports) != 1:
            return {"status": "infrastructure_failed" if outcome == "infrastructure_failed"
                    else "unavailable"}
        report = json.loads(reports[0].read_text(encoding="utf-8"))
        trigger = report["trigger"]
        used = report["call_budget"]["used"]
        if type(used) is not int or not 0 <= used <= 5 or trigger["model"] != model or report["live"] is not True:
            raise ValueError("Invalid canary report")
        if outcome == "infrastructure_failed":
            return {"status": outcome, "attempted_calls": used}
        rows = trigger["results"]
        summary = trigger["summary"]
        if (not isinstance(outcome, str) or outcome not in COMPLETE or used != 5
                or status["exit_code"] != COMPLETE[outcome]
                or report["exit_code"] != COMPLETE[outcome] or summary["infrastructure_failed"] is not False
                or not isinstance(rows, list) or len(rows) != 4
                or any(row["runs"] != 1 or row["ok_runs"] != 1 or row["failed_runs"] != 0
                       or type(row["pass"]) is not bool or type(row["should_trigger"]) is not bool
                       or not isinstance(row["query"], str) for row in rows)
                or all(row["pass"] for row in rows) != (outcome == "passed")):
            raise ValueError("Incomplete canary evidence")
        outcomes = {sha256(row["query"].encode("utf-8")).hexdigest(): {
            "expected": row["should_trigger"], "passed": row["pass"]} for row in rows}
        threshold = trigger["trigger_threshold"]
        inputs = {key: trigger[key] for key in ("skill_name", "description")}
        if (len(outcomes) != len(rows) or not known_metric(threshold) or threshold > 1
                or any(not isinstance(value, str) or not value for value in inputs.values())):
            raise ValueError("Invalid canary suite")
        metrics = {}
        for key in METRICS:
            values = [(row.get("metrics") or {}).get(key) for row in rows]
            measured = [value for value in values if known_metric(value)]
            total = sum(measured)
            metrics[key] = {"observed_sum": total if measured and known_metric(total) else None,
                            "measured_cases": len(measured), "total_cases": len(rows)}
        return {"status": outcome, "attempted_calls": used, "case_metrics": metrics,
                "threshold": threshold, "case_outcomes": outcomes, "trigger_inputs": inputs}
    except (OSError, ValueError, KeyError, TypeError, AttributeError, OverflowError):
        return {"status": "unavailable"}


def read_canary_run(repo, run_id, sha):
    """Read both named artifacts and record network failures without losing partial evidence."""
    result = {"run_id": run_id, "sha": sha}
    with tempfile.TemporaryDirectory() as directory:
        try:
            command("gh", "run", "download", str(run_id), "-R", repo, "-D", directory,
                    "-n", "trigger-canary-haiku", "-n", "trigger-canary-sonnet",
                    timeout=NETWORK_TIMEOUT)
        except subprocess.TimeoutExpired:
            result["download_status"] = "timed_out"
        except (OSError, subprocess.SubprocessError):
            result["download_status"] = "download_failed"
        return {**result, "models": {model: canary_evidence(Path(directory) / f"trigger-canary-{model}", model)
                                     for model in MODELS}}


def scheduled_evidence(repo, branch):
    """Collect retained scheduled evidence in newest-first order."""
    since = (datetime.now(UTC) - timedelta(days=14)).isoformat(timespec="seconds")
    try:
        runs = json.loads(command("gh", "run", "list", "-R", repo, "--workflow", "test.yml",
                                  "--event", "schedule", "--branch", branch, "--status", "completed",
                                  "--created", f">={since}", "--limit", "14", "--json", "databaseId,headSha",
                                  timeout=NETWORK_TIMEOUT))
        # Limit concurrency and keep the history scan within the release job's timeout.
        with ThreadPoolExecutor(max_workers=4) as pool:
            pending = [pool.submit(read_canary_run, repo, row["databaseId"], row["headSha"]) for row in runs]
            evidence = [future.result() for future in pending]
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError):
        return {"status": "unavailable", "runs": []}
    return {"status": "collected", "runs": evidence}


def outcome_drift(current, history, model):
    """Compare the latest completed run with matching model and trigger inputs."""
    if "case_outcomes" not in current:
        return {"status": "unavailable", "reason": "No complete release canary."}
    candidate = current["case_outcomes"]
    expected = {key: outcome["expected"] for key, outcome in candidate.items()}
    for run in history:
        baseline = run["models"][model]
        old = baseline.get("case_outcomes", {})
        if (baseline.get("trigger_inputs") == current["trigger_inputs"]
                and baseline.get("threshold") == current["threshold"]
                and {key: outcome["expected"] for key, outcome in old.items()} == expected):
            return {"status": "compared", "baseline_run_id": run["run_id"], "baseline_sha": run["sha"],
                    "regressions": sum(old[key]["passed"] and not outcome["passed"]
                                       for key, outcome in candidate.items()),
                    "recoveries": sum(not old[key]["passed"] and outcome["passed"]
                                      for key, outcome in candidate.items())}
    return {"status": "unavailable", "reason": "No complete scheduled canary with matching trigger inputs."}


def render(report):
    """Render an advisory Actions summary with comparison and retrieval status."""
    drift = report["prompt_drift"]
    lines = ["## Release trigger prompt drift", "", "This report made zero model calls.", ""]
    if drift["status"] == "compared":
        lines += [f"Compared `{drift['candidate']}` against published release `{drift['baseline']}`.", ""]
        for key, values in drift["fields"].items():
            lines.append(f"- Skill {key} changed: **{values['changed']}**")
        lines.append(f"- Fixture prompts: **{len(drift['added'])}** added, **{len(drift['removed'])}** removed, "
                     f"**{len(drift['label_changed'])}** labels changed.")
    else:
        lines.append(f"Comparison unavailable. {drift['reason']}")
    scheduled = report["scheduled"]
    lines += ["", "## Retained canary evidence", "",
              f"Scheduled runs inspected: **{len(scheduled['runs'])}** (up to 14 days)."]
    if scheduled["status"] == "unavailable":
        lines.append("Scheduled run history unavailable.")
    scheduled_downloads = Counter(run["download_status"] for run in scheduled["runs"] if "download_status" in run)
    for status, count in sorted(scheduled_downloads.items()):
        lines.append(f"Scheduled artifact downloads marked {status}: {count}.")
    if "download_status" in report["release_canary"]:
        lines.append(f"Release artifact download: {report['release_canary']['download_status']}.")
    for model in MODELS:
        current = report["release_canary"]["models"][model]
        counts = Counter(run["models"][model]["status"] for run in scheduled["runs"])
        attempted = current.get("attempted_calls", "unknown")
        statuses = ", ".join(f"{name}: {value}" for name, value in sorted(counts.items())) or "no artifacts"
        lines.append(f"- **{model}** release canary: {current['status']}; attempted calls: {attempted}. "
                     f"Scheduled evidence: {statuses}.")
        comparison = report["outcome_drift"][model]
        if comparison["status"] == "compared":
            lines.append(f"  - Compared with scheduled run {comparison['baseline_run_id']}: "
                         f"{comparison['regressions']} new case failures, {comparison['recoveries']} recoveries.")
        else:
            lines.append(f"  - Comparison unavailable. {comparison['reason']}")
    lines += ["", "Download the JSON artifact for normalized prompt changes and measured case metrics. "
              "Metrics cover only observed case calls and exclude the control call. "
              "Missing metrics are unknown. Canary model aliases may change over time.", ""]
    return "\n".join(lines)


def main():
    """Read workflow context and write the report and job summary."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--default-branch", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    repo = os.environ["GITHUB_REPOSITORY"]
    run_id = os.environ["GITHUB_RUN_ID"]
    sha = os.environ["GITHUB_SHA"]
    if os.environ["GITHUB_RUN_ATTEMPT"] == "1":
        release_canary = read_canary_run(repo, run_id, sha)
    else:
        release_canary = {"run_id": run_id, "sha": sha, "models": {
            model: {"status": "unavailable"} for model in MODELS},
            "reason": "Retained artifacts cannot distinguish release reruns."}
    scheduled = scheduled_evidence(repo, args.default_branch)
    report = {
        "prompt_drift": release_drift(repo, os.environ["GITHUB_REF"], sha),
        "release_canary": release_canary,
        "scheduled": scheduled,
        "outcome_drift": {model: outcome_drift(release_canary["models"][model], scheduled["runs"], model)
                          for model in MODELS},
        "report_model_calls": 0,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    with Path(os.environ["GITHUB_STEP_SUMMARY"]).open("a", encoding="utf-8") as summary:
        summary.write(render(report))


if __name__ == "__main__":
    main()
