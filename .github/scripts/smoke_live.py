"""Run the manually authorized trigger smoke using only trusted execution inputs."""

import json
import os
from pathlib import Path
import re
import subprocess
import sys

from evaluate_paths import needs_smoke


ROOT = Path(__file__).resolve().parents[2]
TOOLKIT = ROOT / "skills/skill-creator"
SKILL_PATH = "skills/skill-creator/SKILL.md"
FIXTURES = ROOT / ".github/fixtures/trigger-canary"
LIMIT = 5
MODEL = "haiku"
SHA_PATTERN = r"[0-9a-f]{40}"
ALLOWED_ROLES = {"admin", "maintain", "write"}


class StopSmoke(Exception):
    """A preflight check ended the run before spending model calls."""

    def __init__(self, status, exit_code=0):
        """Record the terminal report status and workflow exit code."""
        self.status = status
        self.exit_code = exit_code


def output(*args):
    """Run a trusted argv without shell expansion or model credentials."""
    if args[0] not in {"git", "gh"}:
        raise ValueError("Smoke commands must use git or gh")
    env = {key: value for key, value in os.environ.items() if key != "CLAUDE_CODE_OAUTH_TOKEN"}
    # Callers select fixed subcommands and validate dispatch values before using them as arguments.
    return subprocess.check_output(  # nosemgrep: python.lang.security.audit.dangerous-subprocess-use-audit
        args, cwd=ROOT, env=env, timeout=60, shell=False,
    )


def github(path, *options):
    """Read the JSON response from a fixed GitHub REST route."""
    return json.loads(output("gh", "api", *options, path))


def authorize(env):
    """Verify dispatch privileges and return the current base for the exact PR head."""
    number, target = env["PR_NUMBER"], env["TARGET_SHA"]
    if (
        env["GITHUB_REF"] != "refs/heads/main"
        or env["GITHUB_EVENT_NAME"] != "workflow_dispatch"
        or not re.fullmatch(r"[1-9][0-9]*", number)
        or not re.fullmatch(SHA_PATTERN, target)
        or env["CHOICE"] not in {"AUTO", "FORCE_RUN"}
    ):
        raise StopSmoke("rejected_invalid_dispatch", 1)
    repository = env["GITHUB_REPOSITORY"]
    # GitHub documents Metadata: read for this collaborator permission route.
    for actor in {env["GITHUB_ACTOR"], env["TRIGGERING_ACTOR"]}:
        if not re.fullmatch(r"[a-zA-Z0-9-]+(?:\[bot\])?", actor):
            raise StopSmoke("rejected_actor", 1)
        role = github(f"repos/{repository}/collaborators/{actor}/permission")
        if role["permission"] not in ALLOWED_ROLES:
            raise StopSmoke("rejected_actor", 1)
    pr = github(f"repos/{repository}/pulls/{number}")
    if pr["state"] != "open" or pr["base"]["ref"] != "main":
        raise StopSmoke("skipped_closed_or_retargeted")
    if (pr["head"]["repo"] or {}).get("full_name") != repository:
        raise StopSmoke("skipped_fork")
    if pr["head"]["sha"] != target:
        raise StopSmoke("stale_head")
    base = pr["base"]["sha"]
    if not re.fullmatch(SHA_PATTERN, base):
        raise StopSmoke("infrastructure_failed", 1)
    return base


def read_metadata(head):
    """Extract only the fixed skill's name and safe description from its Git blob."""
    import yaml

    entry = output("git", "ls-tree", head, "--", SKILL_PATH)
    if not entry.startswith((b"100644 blob ", b"100755 blob ")):
        raise StopSmoke("rejected_skill_metadata", 1)
    blob = f"{head}:{SKILL_PATH}"
    if int(output("git", "cat-file", "-s", blob)) > 32_768:
        raise StopSmoke("rejected_skill_metadata", 1)
    try:
        lines = output("git", "cat-file", "blob", blob).decode("utf-8-sig").splitlines()
        if not lines or lines[0] != "---":
            raise ValueError("missing frontmatter")
        end = lines.index("---", 1)
        metadata = yaml.safe_load("\n".join(lines[1:end]))
        name, description = metadata["name"], metadata["description"]
    except (KeyError, TypeError, ValueError, yaml.YAMLError):
        raise StopSmoke("rejected_skill_metadata", 1) from None
    if (
        name != "skill-creator"
        or not isinstance(description, str)
        or not description.strip()
        or "`" in description  # Disallow Claude Code's dynamic shell interpolation syntax.
    ):
        raise StopSmoke("rejected_skill_metadata", 1)
    return {"name": name, "description": description}


def prepare(env, state_dir):
    """Authorize and stage metadata without checking out or executing PR files."""
    base = authorize(env)
    head = env["TARGET_SHA"]
    # Fetch objects only. The checkout, fixtures, and runner remain on main.
    output(
        "git", "-c", "credential.helper=", "-c", "credential.helper=!gh auth git-credential",
        "fetch", "--no-tags", "origin", base, head,
    )
    if env["CHOICE"] == "AUTO" and not needs_smoke(base, head):
        raise StopSmoke("skipped_path_policy")
    metadata = read_metadata(head)
    (state_dir / "target.json").write_text(
        json.dumps({"base": base, "head": head, **metadata}), encoding="utf-8",
    )
    with open(env["GITHUB_OUTPUT"], "a", encoding="utf-8") as stream:
        stream.write("ready=true\n")


def evaluate(metadata, credential, report, before_first_call):
    """Run the fixed Haiku suite and guard the budget immediately before first launch."""
    # The trigger engine writes its own synthetic command, with YAML-serialized
    # description and a fixed body. It exposes only the Skill tool, disables
    # hooks and MCP, and forwards the credential through an isolated profile.
    sys.path.insert(0, str(TOOLKIT))
    from scripts.call_budget import CallBudget
    from scripts.run_eval import run_eval
    from scripts.tests_loader import load_trigger_suite

    cases = load_trigger_suite(FIXTURES)
    if len(cases) != LIMIT - 1:
        raise StopSmoke("infrastructure_failed", 1)
    class SmokeBudget(CallBudget):
        """Reserve the exact target on the first, synchronous discovery call."""

        def consume(self):
            """Authorize and reserve before letting the engine launch Claude."""
            if self.used == 0:
                before_first_call()
            super().consume()

    budget = SmokeBudget(LIMIT)
    os.environ["CLAUDE_CODE_OAUTH_TOKEN"] = credential
    try:
        result = run_eval(
            cases, metadata["name"], metadata["description"], 1, 60,
            runs_per_query=1, model=MODEL, max_retries=0, max_calls=LIMIT, budget=budget,
        )
    finally:
        os.environ.pop("CLAUDE_CODE_OAUTH_TOKEN", None)
        report["attempted_calls"] = budget.report()["used"]
    summary = result["summary"]
    rows = result["results"]
    report["completed_calls"] = (1 + sum(row["ok_runs"] for row in rows)) if rows else None
    report["reported_case_cost_usd"] = (summary.get("metrics") or {}).get("cost_usd")
    if summary["infrastructure_failed"]:
        raise StopSmoke("infrastructure_failed", 1)
    if summary["failed"]:
        raise StopSmoke("expectations_failed", 2)
    report["status"] = "passed"


def reserve(env):
    """Persist the single-use claim for this PR and head across workflow runs."""
    head = env["TARGET_SHA"]
    task = f"pr-smoke-reservation-{env['PR_NUMBER']}"
    route = f"repos/{env['GITHUB_REPOSITORY']}/deployments"
    if github(f"{route}?sha={head}&task={task}&per_page=1"):
        raise StopSmoke("skipped_already_reserved")
    claim = github(
        route, "--method", "POST",
        "-f", f"ref={head}",
        "-f", f"task={task}",
        "-f", "environment=pr-smoke-spend-ledger",
        "-f", "description=Reserve one manual PR smoke attempt",
        "-F", "auto_merge=false",
        "-F", "production_environment=false",
        "-F", "required_contexts[]",
    )
    if claim.get("sha") != head or claim.get("task") != task:
        raise StopSmoke("infrastructure_failed", 1)


def run(env, state_dir, credential, report):
    """Validate the staged target and spend only after a durable reservation."""
    report["planned_calls"] = LIMIT
    if env.get("PR_SMOKE_ENABLED") != "true" or not credential:
        raise StopSmoke("skipped_disabled_or_missing_credentials")
    metadata = json.loads((state_dir / "target.json").read_text(encoding="utf-8"))
    if metadata["head"] != env["TARGET_SHA"]:
        raise StopSmoke("stale_head")

    def check_target():
        """Compare the current authorized base with the staged policy input."""
        if metadata["base"] != authorize(env):
            raise StopSmoke("stale_base")

    def before_first_call():
        """Claim the budget and verify current PR state at the launch boundary."""
        # Concurrency serializes claims for a PR. Recheck after the reservation
        # request so stale targets cannot spend during its network round trip.
        reserve(env)
        check_target()
        os.environ.pop("GH_TOKEN", None)
        (state_dir / "started").touch()

    check_target()
    evaluate(metadata, credential, report, before_first_call)


def summarize(env, status_path, report):
    """Retain sanitized evidence and display explicit unknown accounting values."""
    if status_path.exists():
        report.update(json.loads(status_path.read_text(encoding="utf-8")))
    if report["status"] == "ready":
        report["status"] = "infrastructure_failed"
        if (status_path.parent / "started").exists():
            report.update(attempted_calls=None, completed_calls=None)
    status_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    labels = {
        "head": "Target commit",
        "status": "Status",
        "cli_version": "Verified Claude Code CLI version",
        "planned_calls": "Planned model calls",
        "attempted_calls": "Attempted model calls",
        "completed_calls": "Successfully completed model calls",
        "reported_case_cost_usd": "Reported case cost in USD (excludes control and unreported costs)",
    }
    with open(env["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as stream:
        stream.write("### Manual PR trigger smoke (Haiku)\n\n")
        stream.write("Automatic pull request checks use zero model calls.\n\n")
        for key, label in labels.items():
            value = report[key] if report[key] is not None else "unknown"
            stream.write(f"- {label}: `{value}`\n")


def main(mode):
    """Execute one workflow phase and persist its sanitized status."""
    # Keep the model secret out of Git, GitHub CLI, and preparatory subprocesses.
    credential = os.environ.pop("PR_SMOKE_CREDENTIAL", "")
    env = os.environ
    state_dir = Path(env["RUNNER_TEMP"]) / "manual-pr-smoke"
    state_dir.mkdir(exist_ok=True)
    status_path = state_dir / "status.json"
    head = env.get("TARGET_SHA", "")
    report = {
        "head": head if re.fullmatch(SHA_PATTERN, head) else None,
        "status": "infrastructure_failed",
        "cli_version": env.get("VERIFIED_CLI_VERSION"),
        "planned_calls": 0,
        "attempted_calls": 0,
        "completed_calls": 0,
        "reported_case_cost_usd": None,
    }
    if mode == "summarize":
        summarize(env, status_path, report)
        return 0
    code = 0
    try:
        if mode == "prepare":
            prepare(env, state_dir)
            report.update(status="ready", planned_calls=LIMIT)
        elif mode == "run":
            run(env, state_dir, credential, report)
        else:
            raise ValueError("unexpected smoke mode")
    except StopSmoke as exc:
        report["status"], code = exc.status, exc.exit_code
    except Exception as exc:
        print(f"Smoke infrastructure failed ({type(exc).__name__}).", file=sys.stderr)
        code = 1
    finally:
        status_path.write_text(json.dumps(report), encoding="utf-8")
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
