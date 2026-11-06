"""Offline tests of the exact-commit manual smoke and its spending boundary."""

import importlib
import json
from pathlib import Path
import subprocess

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[1]
MAIN = "1" * 40
HEAD = "2" * 40
REPO = "owner/repo"


@pytest.fixture
def smoke(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / ".github/scripts"))
    monkeypatch.syspath_prepend(str(ROOT / "skills/skill-creator"))
    return importlib.import_module("smoke_live")


@pytest.fixture
def dispatch():
    return {
        "PR_NUMBER": "17",
        "TARGET_SHA": HEAD,
        "GITHUB_REF": "refs/heads/main",
        "GITHUB_EVENT_NAME": "workflow_dispatch",
        "GITHUB_REPOSITORY": REPO,
        "GITHUB_ACTOR": "original",
        "TRIGGERING_ACTOR": "rerunner",
        "CHOICE": "FORCE_RUN",
        "PR_SMOKE_ENABLED": "true",
    }


def patch_github(monkeypatch, smoke, *, head=HEAD, repo=REPO, rerunner_role="write"):
    seen = []

    def github(path):
        seen.append(path)
        if path.endswith("/permission"):
            role = rerunner_role if "/rerunner/" in path else "maintain"
            return {"permission": role}
        return {
            "state": "open",
            "base": {"ref": "main", "sha": MAIN},
            "head": {"sha": head, "repo": {"full_name": repo}},
        }

    monkeypatch.setattr(smoke, "github", github)
    return seen


@pytest.mark.parametrize(("head", "repo", "role", "status"), [
    (MAIN, REPO, "write", "stale_head"),
    (HEAD, "fork/repo", "write", "skipped_fork"),
    (HEAD, REPO, "read", "rejected_actor"),
])
def test_force_run_does_not_bypass_authorization(
    monkeypatch, smoke, dispatch, head, repo, role, status,
):
    patch_github(monkeypatch, smoke, head=head, repo=repo, rerunner_role=role)
    with pytest.raises(smoke.StopSmoke) as stopped:
        smoke.authorize(dispatch)
    assert stopped.value.status == status


def git(repo, *args):
    return subprocess.check_output(("git", *args), cwd=repo).decode().strip()


def test_exact_git_blob_and_three_dot_policy(tmp_path, monkeypatch, smoke):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(smoke, "ROOT", tmp_path)
    git(tmp_path, "init", "--initial-branch=main")
    git(tmp_path, "config", "user.name", "Fixture")
    git(tmp_path, "config", "user.email", "fixture@example.com")
    candidate = tmp_path / smoke.SKILL_PATH
    candidate.parent.mkdir(parents=True)
    candidate.write_text(
        "---\nname: skill-creator\ndescription: Original\n---\n", encoding="utf-8",
    )
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-m", "base")
    base = git(tmp_path, "rev-parse", "HEAD")
    git(tmp_path, "switch", "-c", "feature")
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "guide.md").write_text("docs", encoding="utf-8")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-m", "docs")
    docs_only = git(tmp_path, "rev-parse", "HEAD")
    candidate.write_text(
        "---\nname: skill-creator\ndescription: Candidate\n"
        "allowed-tools: [Bash]\n---\nUntrusted body\n",
        encoding="utf-8",
    )
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-m", "metadata")
    head = git(tmp_path, "rev-parse", "HEAD")
    candidate.write_text(
        "---\nname: skill-creator\ndescription: 'Inject !`env`'\n---\n",
        encoding="utf-8",
    )
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-m", "unsafe metadata")
    unsafe = git(tmp_path, "rev-parse", "HEAD")
    git(tmp_path, "switch", "main")
    git(tmp_path, "rm", smoke.SKILL_PATH)
    git(tmp_path, "commit", "-m", "divergent deletion")
    main = git(tmp_path, "rev-parse", "HEAD")
    assert not smoke.needs_smoke(main, docs_only)
    assert smoke.needs_smoke(main, head)
    assert smoke.read_metadata(head) == {"name": "skill-creator", "description": "Candidate"}
    with pytest.raises(smoke.StopSmoke, match="rejected_skill_metadata"):
        smoke.read_metadata(unsafe)
    assert git(tmp_path, "rev-parse", "HEAD") == main
    assert git(tmp_path, "merge-base", main, head) == base
    git(tmp_path, "switch", "--detach", docs_only)
    git(tmp_path, "mv", "docs/guide.md", "runtime.md")
    git(tmp_path, "commit", "-m", "move docs to runtime")
    moved_out = git(tmp_path, "rev-parse", "HEAD")
    assert smoke.needs_smoke(docs_only, moved_out)
    docs.mkdir(exist_ok=True)
    git(tmp_path, "mv", "runtime.md", "docs/guide.md")
    git(tmp_path, "commit", "-m", "move runtime to docs")
    assert smoke.needs_smoke(moved_out, git(tmp_path, "rev-parse", "HEAD"))


def test_stale_recheck_prevents_any_live_run(tmp_path, monkeypatch, smoke, dispatch):
    (tmp_path / "target.json").write_text(json.dumps({"base": MAIN, "head": HEAD}))
    seen = patch_github(monkeypatch, smoke, head=MAIN)
    monkeypatch.setattr(smoke, "evaluate", lambda *args: pytest.fail("stale head spent calls"))
    with pytest.raises(smoke.StopSmoke, match="stale_head"):
        smoke.run(dispatch, tmp_path, "fixture-secret", {})
    assert any("/original/permission" in path for path in seen)
    assert any("/rerunner/permission" in path for path in seen)


@pytest.mark.parametrize(("infra", "failed", "status"), [
    (False, 0, "passed"),
    (False, 1, "expectations_failed"),
    (True, 1, "infrastructure_failed"),
])
def test_fake_runner_has_five_call_cap(
    tmp_path, monkeypatch, smoke, dispatch, infra, failed, status,
):
    from scripts import run_eval

    seen = patch_github(monkeypatch, smoke)
    monkeypatch.setenv("GH_TOKEN", "must-not-reach-engine")
    (tmp_path / "target.json").write_text(
        json.dumps({"base": MAIN, "head": HEAD, "name": "skill-creator", "description": "Candidate"}),
        encoding="utf-8",
    )

    def fake(cases, name, description, workers, timeout, **options):
        assert "GH_TOKEN" not in smoke.os.environ
        assert smoke.os.environ["CLAUDE_CODE_OAUTH_TOKEN"] == "fixture-secret"
        assert (len(cases), name, description, workers) == (4, "skill-creator", "Candidate", 1)
        budget = options.pop("budget")
        assert options == {"runs_per_query": 1, "model": "haiku", "max_retries": 0, "max_calls": 5}
        for _ in range(5):
            budget.consume()
        with pytest.raises(ValueError, match="exhausted"):
            budget.consume()
        return {
            "summary": {"infrastructure_failed": infra, "failed": failed, "metrics": None},
            "results": [{"ok_runs": 1}] * 4,
        }

    monkeypatch.setattr(run_eval, "run_eval", fake)
    report = {}
    if status == "passed":
        smoke.run(dispatch, tmp_path, "fixture-secret", report)
        assert report["status"] == status
    else:
        with pytest.raises(smoke.StopSmoke, match=status):
            smoke.run(dispatch, tmp_path, "fixture-secret", report)
    assert report["planned_calls"] == report["attempted_calls"] == report["completed_calls"] == 5
    assert report["reported_case_cost_usd"] is None
    assert "CLAUDE_CODE_OAUTH_TOKEN" not in smoke.os.environ
    assert any("/original/permission" in path for path in seen)
    assert any("/rerunner/permission" in path for path in seen)


def test_workflow_keeps_paid_steps_manual_and_main_only():
    workflow = yaml.safe_load((ROOT / ".github/workflows/smoke-live.yml").read_text(encoding="utf-8"))
    assert set(workflow[True]) == {"workflow_dispatch"}  # PyYAML interprets "on" as YAML 1.1 bool.
    job = workflow["jobs"]["smoke"]
    assert job["environment"] == "pr-smoke"
    assert job["if"] == "github.ref == 'refs/heads/main'"
    checkout = job["steps"][0]["with"]
    assert checkout["ref"] == "${{ github.sha }}"
    assert not checkout["persist-credentials"]
    credential_steps = [step for step in job["steps"] if "PR_SMOKE_CREDENTIAL" in step.get("env", {})]
    assert len(credential_steps) == 1
    assert credential_steps[0]["run"] == "python .github/scripts/smoke_live.py run"
