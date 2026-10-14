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

    monkeypatch.setattr(claude_process, "claude_command", unavailable)
    monkeypatch.setattr(bsc, "ROOT", root)
    hook = (root / git(root, "rev-parse", "--git-path", "hooks")).resolve() / "pre-commit"
    assert not hook.exists()
    assert next(row for row in bsc.doctor() if row["check"] == "pre-commit hook")["status"] == "skipped"
    runs = tmp_path / "runs"
    assert bsc.main(["hooks", "install", "--runs-dir", str(runs)]) == 0
    assert hook.read_bytes() == (bsc.TOOLKIT / "scripts/hooks/pre-commit").read_bytes()
    if sys.platform != "win32":
        assert hook.stat().st_mode & 0o111
    assert next(row for row in bsc.doctor() if row["check"] == "pre-commit hook")["status"] == "passed"
    report = json.loads(next(runs.glob("*/results.json")).read_text())
    assert report["checks"][0]["status"] == "passed"


def test_hooks_install_reports_missing_checkout(tmp_path, monkeypatch):
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path.parent))
    monkeypatch.setattr(bsc, "ROOT", tmp_path)
    runs = tmp_path / "runs"
    assert bsc.main(["hooks", "install", "--runs-dir", str(runs)]) == 1
    report = json.loads(next(runs.glob("*/results.json")).read_text())
    assert report["checks"][0]["status"] == "failed"
    assert "Cannot resolve Git hooks directory" in report["checks"][0]["message"]
