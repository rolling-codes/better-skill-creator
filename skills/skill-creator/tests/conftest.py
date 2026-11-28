"""Shared test fixtures for the compiler and release gate."""
from collections.abc import Callable
from pathlib import Path

import pytest


@pytest.fixture
def record_passing_review() -> Callable[[Path], None]:
    """Record a synthetic review after test setup so packaging reaches its other gates."""
    from scripts.file_policy import source_manifest
    from scripts.review import COMPLETION_ROLE, PRACTICES_ROLE, REQUIRED_ROLES, ReviewRecord
    from scripts.review_gate import REVIEW_AGENTS

    def record(root: Path) -> None:
        with (root / "SKILL.md").open("a", encoding="utf-8") as body:
            body.write("\n")
            for agent in REVIEW_AGENTS:
                path = root / agent
                path.parent.mkdir(exist_ok=True)
                path.write_text("# Reviewer instructions\n", encoding="utf-8")
                body.write(f"- `{agent}`\n")
        ReviewRecord(
            source_manifest=source_manifest(root),
            activation_required=True,
            activation_reason="Synthetic review for a packaging test.",
            independent_findings=[{"role": role, "findings": []}
                                  for role in (*REQUIRED_ROLES, PRACTICES_ROLE)],
            consolidated_decision={"accepted_findings": [], "rejected_findings": [],
                                   "chosen_interpretation": "Test fixture"},
            completion_adversary_report={"role": COMPLETION_ROLE, "verdict": "complete"},
            completion_gate_status="passed",
        ).write(root)

    return record
