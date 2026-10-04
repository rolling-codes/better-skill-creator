"""Malformed run names must not contribute synthetic run-zero results."""
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.aggregate_benchmark import load_run_results


@pytest.mark.parametrize("legacy", [False, True])
def test_malformed_run_numbers_are_skipped(tmp_path, capsys, legacy):
    root = tmp_path / "runs" if legacy else tmp_path
    config = root / "eval-1" / "with_skill"
    for name in ("run-0", "run-1", "run-12", "run-bad", "run-"):
        run = config / name
        run.mkdir(parents=True)
        (run / "grading.json").write_text('{"summary": {"pass_rate": 1.0}}', encoding="utf-8")

    results = load_run_results(tmp_path)["with_skill"]

    assert [run["run_number"] for run in results] == [0, 1, 12]
    assert all(run["pass_rate"] == 1.0 for run in results)
    warnings = capsys.readouterr().out
    for name in ("run-bad", "run-"):
        assert f"Warning: Invalid run number in {config / name}; skipping directory" in warnings
