#!/usr/bin/env python3
"""Shared types used across all skill-creator scripts.

This module has no imports from other scripts.* modules to prevent circular
import chains. Everything that multiple scripts need as a type lives here.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

from scripts.analysis_config import MAX_FINDINGS_PER_RULE

# ---------------------------------------------------------------------------
# Review process constants (previously split between review.py and review_gate.py)
# ---------------------------------------------------------------------------

# Severities that block completion until disposed.
BLOCKING_SEVERITIES: set[str] = {"high", "critical", "material"}
# Dispositions that count as resolving a finding.
DISPOSITIONS: set[str] = {"fixed", "accepted_limitation", "returned_to_user"}
# Gate status values.
GATE_STATES: tuple[str, ...] = ("not_run", "failed", "passed")


# ---------------------------------------------------------------------------
# Finding
# ---------------------------------------------------------------------------

@dataclass
class Finding:
    severity: Literal["error", "warning", "info"]
    rule: str        # machine-readable rule id, e.g. "dead-reference"
    message: str
    line: Optional[int] = None

    def __str__(self) -> str:
        loc = f":{self.line}" if self.line else ""
        return f"[{self.severity.upper()}] {self.rule}{loc}: {self.message}"


# ---------------------------------------------------------------------------
# Noise control
# ---------------------------------------------------------------------------

def _cap(findings: list[Finding], rule: str,
         limit: int = MAX_FINDINGS_PER_RULE) -> list[Finding]:
    """Collapse a flood of same-rule findings into the first few plus a count.

    A rule that fires on nearly every line stops being a signal and starts
    being wallpaper. Showing a handful of concrete examples plus a total keeps
    the detail without burying the other rules.
    """
    if len(findings) <= limit:
        return findings
    hidden = len(findings) - limit
    return findings[:limit] + [Finding(
        severity=findings[0].severity,
        rule=rule,
        message=(
            f"...and {hidden} more '{rule}' finding(s) suppressed. "
            f"A rule firing this often usually means the rule is too broad, "
            f"not that the skill is broken."
        ),
    )]
