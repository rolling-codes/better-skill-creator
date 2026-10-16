#!/usr/bin/env python3
"""
Unified validation — runs structural, lint, static-analysis, review-gate, and score
checks in order, short-circuiting on structural errors.

Use this as the single canonical gate before shipping a skill.
The individual scripts (quick_validate, lint, static_analysis, review_gate, score)
remain available for targeted use.

`python -m scripts.validate --commit <skill-path>` is the pre-commit subset:
structure (including Claude Code frontmatter), lint, and the review gate. It
loads the skill once and does not run static analysis or scoring.

Usage: python -m scripts.validate [--commit] <skill-path>
Exit codes: 0 = no issues, 1 = errors found, 2 = warnings only.
"""
from __future__ import annotations

import sys
from pathlib import Path

from scripts.skill_ir import Skill
from scripts.quick_validate import validate_skill
from scripts.lint import lint
from scripts.static_analysis import analyze
from scripts.review_gate import analyze as review_gate_analyze
from scripts.score import score as compute_score
from scripts.confidence import assess_skill
from scripts.finding_types import Finding


def validate(skill_path: Path) -> list[Finding]:
    """Run structural, lint, static-analysis, and review-gate checks on a skill."""
    valid, message = validate_skill(skill_path)
    if not valid:
        return [Finding(severity="error", rule="structural", message=message)]

    try:
        skill = Skill.from_path(skill_path)
    except (FileNotFoundError, ValueError) as exc:
        return [Finding(severity="error", rule="load-error", message=str(exc))]

    findings: list[Finding] = []
    warning_prefix = "Skill is valid! Warning: "
    if message.startswith(warning_prefix):
        findings.append(Finding(
            severity="warning",
            rule="name-directory-mismatch",
            message=message[len(warning_prefix):],
        ))
    findings.extend(lint(skill))
    findings.extend(analyze(skill))
    findings.extend(review_gate_analyze(skill))
    return findings


def _report_findings(findings: list[Finding]) -> int:
    """Print findings the way the standalone tools do, and return their exit code."""
    if not findings:
        return 0
    errors = [f for f in findings if f.severity == "error"]
    warnings = [f for f in findings if f.severity == "warning"]
    infos = [f for f in findings if f.severity == "info"]
    order = {"error": 0, "warning": 1, "info": 2}
    for finding in sorted(findings, key=lambda item: order.get(item.severity, 3)):
        print(str(finding))
    print(
        f"\n{len(findings)} finding(s): "
        f"{len(errors)} error(s), {len(warnings)} warning(s), {len(infos)} info(s)"
    )
    return 1 if errors else (2 if warnings else 0)


def _review_summary(findings: list[Finding]) -> None:
    """Print the one review-gate summary line the standalone tool always prints."""
    errors = [f for f in findings if f.severity == "error"]
    warnings = [f for f in findings if f.severity == "warning"]
    skipped = next((f for f in findings if f.rule == "review-skipped"), None)
    if errors:
        print(f"Review gate: failed — {len(errors)} error(s)")
    elif skipped:
        print("Review gate: skipped — no review record")
    elif warnings:
        print("Review gate: passed (with warnings)")
    else:
        print("Review gate: passed")


def commit_check(skill_path: Path) -> int:
    """Run structure, lint, and the review gate in this process.

    A structural error stops the later checks, matching the hook's old
    short-circuit. Lint and the review gate share one loaded skill.
    """
    valid, message = validate_skill(skill_path, claude_code=True)
    print(message)
    if not valid:
        return 1
    code = 0 if message == "Skill is valid!" else 2
    try:
        skill = Skill.from_path(skill_path)
    except (FileNotFoundError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print("Linting...")
    lint_findings = lint(skill)
    if not lint_findings:
        print("No lint issues found.")
    lint_code = _report_findings(lint_findings)
    if lint_code == 1:
        return 1
    code = max(code, lint_code)

    print("Review gate...")
    review_findings = review_gate_analyze(skill)
    review_code = _report_findings(review_findings)
    _review_summary(review_findings)
    if review_code == 1:
        return 1
    return max(code, review_code)


def _main() -> int:
    args = sys.argv[1:]
    commit = False
    if args and args[0] == "--commit":
        commit = True
        args = args[1:]
    if len(args) != 1:
        print("Usage: python -m scripts.validate [--commit] <skill-path>", file=sys.stderr)
        return 1
    skill_path = Path(args[0])
    if commit:
        return commit_check(skill_path)

    findings = validate(skill_path)

    # Score and confidence — load skill only when structural checks passed.
    structural_fail = any(f.rule in ("structural", "load-error") for f in findings)
    skill_obj = None
    skill_score = None
    if not structural_fail:
        try:
            skill_obj = Skill.from_path(skill_path)
            skill_score = compute_score(skill_obj, findings)
            if skill_score.overall < 70:
                findings.append(Finding(
                    severity="error",
                    rule="score-below-threshold",
                    message=f"Score {skill_score.overall}/100 is below the 70 shipping threshold",
                ))
        except Exception as exc:
            findings.append(Finding(
                severity="error", rule="score-error", message=f"Scoring failed: {exc}",
            ))

    if not findings:
        print("Validation passed: no issues found.")
        if skill_score is not None:
            print(f"Score: {skill_score.overall}/100")
        return 0

    errors = [f for f in findings if f.severity == "error"]
    warnings = [f for f in findings if f.severity == "warning"]
    infos = [f for f in findings if f.severity == "info"]

    _SEV_ORDER = {"error": 0, "warning": 1, "info": 2}
    for f in sorted(findings, key=lambda x: _SEV_ORDER.get(x.severity, 3)):
        print(str(f))

    print(
        f"\n{len(findings)} finding(s): "
        f"{len(errors)} error(s), {len(warnings)} warning(s), {len(infos)} info(s)"
    )

    if skill_score is not None:
        print(f"Score: {skill_score.overall}/100")
    else:
        print("Score: not computed")

    if skill_obj is not None:
        try:
            confidence = assess_skill(skill_obj)
            print(f"Description confidence: {confidence.overall}%")
        except Exception:
            print("Description confidence: not computed")

    return 1 if errors else 2


if __name__ == "__main__":
    sys.exit(_main())
