import importlib.util
from pathlib import Path
from unittest.mock import patch

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / ".github/scripts/evaluate_paths.py"
spec = importlib.util.spec_from_file_location("evaluate_paths", SCRIPT)
assert spec is not None and spec.loader is not None
triage = importlib.util.module_from_spec(spec)
spec.loader.exec_module(triage)


@pytest.mark.parametrize(("paths", "expected"), [
    (b"", False),
    (b"README.md\0docs/with\nnewline.md\0LICENSE\0", False),
    (b"docs/guide.md\0bsc.py\0", True),
    (b"skills/skill-creator/SKILL.md\0", True),
    (b"shared/unknown.txt\0", True),
    (b"docs-other/guide.md\0", True),
])
def test_smoke_preview_path_policy(paths, expected):
    with patch.object(triage.subprocess, "check_output", return_value=paths) as diff:
        assert triage.needs_smoke("base", "head") is expected
    args = diff.call_args.args[0]
    assert "--no-renames" in args and "-z" in args and "base...head" in args
