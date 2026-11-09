"""Invalid package targets should use the same input diagnostic as check/eval."""
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("bsc", ROOT / "bsc.py")
assert spec and spec.loader
bsc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bsc)


@pytest.mark.parametrize("command", ["check", "eval", "package"])
@pytest.mark.parametrize("target_kind", ["missing", "file", "directory"])
def test_invalid_target_reports_input_error(command, target_kind, tmp_path, capsys):
    target = tmp_path / "target"
    if target_kind == "file":
        target.write_text("not a skill directory\n", encoding="utf-8")
    elif target_kind == "directory":
        target.mkdir()
    runs = tmp_path / "runs"

    assert bsc.main([command, str(target), "--runs-dir", str(runs)]) == 1

    report = json.loads(next(runs.glob("*/results.json")).read_text(encoding="utf-8"))
    diagnostic = "Target must be a skill directory containing SKILL.md."
    assert report["error"] == diagnostic
    assert report["status"] == "incomplete"
    assert report["exit_code"] == 1
    output = capsys.readouterr()
    assert f"InputError: {diagnostic}" in output.out
    assert "FileNotFoundError" not in output.out
    assert "NotADirectoryError" not in output.out
    assert not output.err
