#!/usr/bin/env python3
"""
Review gate — deterministic enforcement of the independent-review process
(references/independent-review.md), over review.yaml (scripts/review.py).

Fails on: a required review with missing reports; high-severity findings with no
disposition; invalid dispositions; unresolved decisive questions; a completion claim
while the gate isn't passed (false-completion detection); a passed status without a
completion-adversary report; and review agents that are missing on disk or unwired.

Absent review.yaml is a warning. Narrow edits are not forced through the full process,
but package/release work should record either activation or an explicit skip reason.

Usage: python -m scripts.review_gate <skill-path>
Exit codes: 0 = no errors, 1 = errors, 2 = warnings only.
"""
from __future__ import annotations

import sys
from pathlib import Path

from scripts.skill_ir import Skill
from scripts.types import Finding, GATE_STATES
from scripts.skill_md_utils import extract_referenced_dirs, is_reference_in_body
from scripts.review import ReviewRecord

REVIEW_AGENTS = (
    "agents/outcome-analyst.md",
    "agents/scope-adversary.md",
    "agents/architecture-reviewer.md",
    "agents/completion-adversary.md",
)


def review_applies(skill: Skill) -> bool:
    """Return True when the independent review process applies to this skill."""
    return (skill.skill_path / "review.yaml").exists() or any(a in skill.body for a in REVIEW_AGENTS)


def analyze(skill: Skill) -> list[Finding]:
    findings: list[Finding] = []
    if not review_applies(skill):
        return findings  # This optional review process does not apply to a minimal skill.
    body = skill.body
    rdirs = extract_referenced_dirs(body)

    # The review agents must exist and be discoverable for the process to run at all.
    for agent in REVIEW_AGENTS:
        if not (skill.skill_path / agent).exists():
            findings.append(Finding("error", "review-agent-missing", f"{agent} is missing on disk"))
        elif not is_reference_in_body(agent, body, rdirs):
            findings.append(Finding("warning", "review-agent-unwired",
                                    f"{agent} exists but is not referenced in SKILL.md"))

    review_path = skill.skill_path / "review.yaml"
    if not review_path.exists():
        findings.append(Finding("warning", "no-review-record",
            "no review.yaml - package assumes a narrow change; create one with activation.required false to record a deliberate skip"))
        return findings

    try:
        rec = ReviewRecord.from_yaml(review_path)
    except Exception as exc:  # malformed review.yaml
        findings.append(Finding("error", "review-parse", f"review.yaml could not be parsed: {exc}"))
        return findings

    if rec.completion_gate_status not in GATE_STATES:
        findings.append(Finding("error", "review-gate-status",
            f"completion_gate_status '{rec.completion_gate_status}' is not one of {list(GATE_STATES)}"))

    if not rec.activation_required:
        if not rec.activation_reason:
            findings.append(Finding("warning", "review-activation-unrecorded",
                "activation.required is false but no reason was recorded"))
        return findings

    # Review is required: enforce the full gate.
    if not rec.consolidated_decision:
        findings.append(Finding("error", "review-missing-synthesis",
            "independent review required but consolidated_decision is empty"))
    for role in rec.missing_reports():
        findings.append(Finding("error", "review-missing-report",
            f"independent review required but no report from '{role}'"))
    if rec.completion_gate_status == "passed" and not rec.completion_adversary_reported():
        findings.append(Finding("error", "review-missing-completion-adversary",
            "completion_gate_status is passed but no completion-adversary report was recorded"))
    for f in rec.undisposed_blocking_findings():
        findings.append(Finding("error", "review-undisposed-finding",
            f"high-severity finding without disposition: {str(f.get('finding', ''))[:80]}"))
    for d in rec.bad_dispositions():
        findings.append(Finding("error", "review-bad-disposition",
            f"disposition '{d.get('disposition')}' is not fixed/accepted_limitation/returned_to_user"))
    for f in rec.bad_severities():
        findings.append(Finding("warning", "review-bad-severity",
            f"unrecognised severity '{f.get('severity')}' in finding: {str(f.get('finding', ''))[:60]} "
            f"— typo? blocking check silently skips unrecognised severities"))
    if rec.completion_gate_status != "passed":
        findings.append(Finding("error", "review-gate-not-passed",
            f"review gate not passed: completion_gate_status is '{rec.completion_gate_status}', not 'passed'"))
    for question in rec.unresolved_decisive_questions:
        findings.append(Finding("error", "review-unresolved-question",
            f"unresolved decisive question remains: {str(question)[:80]}"))
    return findings


def _main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python -m scripts.review_gate <skill-path>", file=sys.stderr)
        return 1
    try:
        skill = Skill.from_path(Path(sys.argv[1]))
    except (FileNotFoundError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    findings = analyze(skill)
    if not findings:
        print("Review gate: no issues.")
        return 0
    for f in findings:
        print(str(f))
    errors = [f for f in findings if f.severity == "error"]
    warnings = [f for f in findings if f.severity == "warning"]
    print(f"\n{len(findings)} finding(s): {len(errors)} error(s), {len(warnings)} warning(s)")
    return 1 if errors else (2 if warnings else 0)


if __name__ == "__main__":
    sys.exit(_main())
