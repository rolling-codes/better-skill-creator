"""Scoring failures must block the unified validation CLI."""
import sys

import pytest

from scripts import validate
from scripts.finding_types import Finding


@pytest.mark.parametrize("findings", [[], [Finding("warning", "lint", "warning")]])
def test_scoring_exception_blocks_validation(monkeypatch, capsys, findings):
    monkeypatch.setattr(sys, "argv", ["validate", "unused"])
    monkeypatch.setattr(validate, "validate", lambda path: list(findings))
    monkeypatch.setattr(validate.Skill, "from_path", lambda path: object())
    monkeypatch.setattr(validate, "assess_skill", lambda skill: None)

    def score(*args):
        raise RuntimeError("broken scorer")

    monkeypatch.setattr(validate, "compute_score", score)
    assert validate._main() == 1
    output = capsys.readouterr().out
    assert "score-error" in output
    assert "Scoring failed: broken scorer" in output
    assert "Validation passed" not in output
