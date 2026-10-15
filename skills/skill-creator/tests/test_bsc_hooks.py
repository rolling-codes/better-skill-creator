"""Hook installation and doctor must use Git's resolved hook directory."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location("bsc", ROOT / "bsc.py")
assert spec and spec.loader
bsc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bsc)


def git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()


@pytest.mark.parametrize("layout", ["repository", "worktree", "submodule", "custom-hooks"])
def test_install_and_doctor_use_resolved_hooks(tmp_path, monkeypatch, layout):
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init")
    git(repo, "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
        "commit", "--allow-empty", "-m", "fixture")
    root = repo
    if layout == "worktree":
        root = tmp_path / "worktree"
        git(repo, "worktree", "add", "--detach", str(root))
    elif layout == "submodule":
        if sys.platform == "win32":
            pytest.skip("git submodule add with local paths is unreliable on Windows CI")
        parent = tmp_path / "parent"
        parent.mkdir()
        git(parent, "init")
        root = parent / "submodule"
        git(parent, "-c", "protocol.file.allow=always", "submodule", "add", str(repo), str(root))
    elif layout == "custom-hooks":
        git(root, "config", "core.hooksPath", "custom-hooks")

    # Doctor's plugin JSON fallback needs the local manifests, and never calls Claude.
    (root / ".claude-plugin").mkdir()
    for name in ("plugin.json", "marketplace.json"):
        (root / ".claude-plugin" / name).write_text('{"name": "fixture"}', encoding="utf-8")
    from scripts import claude_process

    def unavailable(*args):
        raise FileNotFoundError("Claude is not used by this test")

    monkeypatch.chdir(root)
    monkeypatch.setattr(claude_process, "claude_command", unavailable)
    monkeypatch.setattr(bsc, "ROOT", root)
    hook = (root / git(root, "rev-parse", "--git-path", "hooks")).resolve() / "pre-commit"
    assert not hook.exists()
    assert next(row for row in bsc.doctor() if row["check"] == "pre-commit hook")["status"] == "skipped"
    runs = tmp_path / "runs"
    assert bsc.main(["hooks", "install", "--runs-dir", str(runs)]) == 0
    installed = hook.read_text(encoding="utf-8")
    assert f'BSC_TOOLKIT="{bsc.TOOLKIT.resolve().as_posix()}"' in installed
    assert 'BSC_TOOLKIT=""' not in installed
    if sys.platform != "win32":
        assert hook.stat().st_mode & 0o111
    assert next(row for row in bsc.doctor() if row["check"] == "pre-commit hook")["status"] == "passed"
    report = json.loads(next(runs.glob("*/results.json")).read_text())
    assert report["checks"][0]["status"] == "passed"


def test_install_replaces_symlink_without_overwriting_its_target(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init")
    shared = tmp_path / "shared-dispatcher"
    shared.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    shared.chmod(0o755)
    link = repo / ".git" / "hooks" / "pre-commit"
    if link.exists() or link.is_symlink():
        link.unlink()
    link.symlink_to(shared)
    monkeypatch.chdir(repo)
    runs = tmp_path / "runs"
    assert bsc.main(["hooks", "install", "--runs-dir", str(runs)]) == 0
    assert link.is_file()
    assert not link.is_symlink()
    assert shared.read_text(encoding="utf-8").startswith("#!/bin/sh")
    assert "BSC_TOOLKIT=" in link.read_text(encoding="utf-8")


def test_hooks_install_reports_missing_checkout(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    # Stop Git from walking into the parent, which may itself be a checkout.
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path.parent.resolve()))
    runs = tmp_path / "runs"
    assert bsc.main(["hooks", "install", "--runs-dir", str(runs)]) == 1
    report = json.loads(next(runs.glob("*/results.json")).read_text())
    assert report["checks"][0]["status"] == "failed"
    assert "Cannot resolve Git hooks directory" in report["checks"][0]["message"]


def test_hooks_install_targets_the_working_tree_not_the_toolkit(tmp_path, monkeypatch):
    """Installing from another repository must not write the toolkit checkout's hook."""
    repo = tmp_path / "userrepo"
    nested = repo / "nested"
    nested.mkdir(parents=True)
    git(repo, "init")
    monkeypatch.chdir(nested)
    toolkit_hook = (bsc.ROOT / ".git" / "hooks" / "pre-commit")
    before = toolkit_hook.read_bytes() if toolkit_hook.is_file() else None
    runs = tmp_path / "runs"
    assert bsc.main(["hooks", "install", "--runs-dir", str(runs)]) == 0
    installed = repo / ".git" / "hooks" / "pre-commit"
    text = installed.read_text(encoding="utf-8")
    assert f'BSC_TOOLKIT="{bsc.TOOLKIT.resolve().as_posix()}"' in text
    assert "validate \"skills/skill-creator\"" not in text
    after = toolkit_hook.read_bytes() if toolkit_hook.is_file() else None
    assert after == before


def _skill_md(name, description, body="Read the request and return a draft file.\n"):
    return (
        f"---\nname: {name}\ndescription: {description}\n---\n"
        f"# {name}\n\n{body}"
    )


def test_installed_hook_validates_staged_skills_only(tmp_path, monkeypatch):
    repo = tmp_path / "userrepo"
    repo.mkdir()
    git(repo, "init")
    git(repo, "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
        "commit", "--allow-empty", "-m", "init")
    monkeypatch.chdir(repo)
    runs = tmp_path / "runs"
    assert bsc.main(["hooks", "install", "--runs-dir", str(runs)]) == 0
    hook = repo / ".git" / "hooks" / "pre-commit"

    good = repo / "my skill"
    (good / "notes").mkdir(parents=True)
    description = (
        "Drafts short notes from a request. Use when the user asks for a note or a summary. "
        "Not for sending email or publishing the result."
    )
    (good / "SKILL.md").write_text(_skill_md("my-skill", description), encoding="utf-8")
    (good / "notes" / "a.txt").write_text("staged nested file\n", encoding="utf-8")
    bad = repo / "bad-skill"
    bad.mkdir()
    (bad / "SKILL.md").write_text(
        '---\nname: ""\ndescription: present\n---\n# Bad\n\nBody.\n',
        encoding="utf-8",
    )
    (repo / "README.md").write_text("not a skill\n", encoding="utf-8")

    def run_hook():
        return subprocess.run(
            ["bash", str(hook)], cwd=repo, capture_output=True, text=True,
        )

    # Unstaged skill files are not validated, even when one of them is invalid.
    clean = run_hook()
    assert clean.returncode == 0, clean.stdout + clean.stderr

    git(repo, "add", "README.md")
    readme_only = run_hook()
    assert readme_only.returncode == 0, readme_only.stdout + readme_only.stderr
    assert "bad-skill" not in readme_only.stdout

    git(repo, "add", "--", "bad-skill/SKILL.md")
    invalid = run_hook()
    assert invalid.returncode != 0
    assert "non-empty" in invalid.stdout + invalid.stderr

    git(repo, "reset", "-q")
    git(repo, "add", "--", "my skill/notes/a.txt")
    nested = run_hook()
    assert nested.returncode == 0, nested.stdout + nested.stderr
    assert "my skill" in nested.stdout
    assert "bad-skill" not in nested.stdout
