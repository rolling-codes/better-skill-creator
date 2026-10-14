#!/usr/bin/env python3
"""
Unified validation — runs structural, lint, static-analysis, review-gate, and score
checks in order, short-circuiting on structural errors.

Use this as the single canonical gate before shipping or committing a skill.
The individual scripts (quick_validate, lint, static_analysis, review_gate, score)
remain available for targeted use.

Usage: python -m scripts.validate <skill-path>
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
from scripts.types import Finding


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
    findings.extend(lint(skill))
    findings.extend(analyze(skill))
    findings.extend(review_gate_analyze(skill))
    return findings


def _main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python -m scripts.validate <skill-path>", file=sys.stderr)
        return 1
    skill_path = Path(sys.argv[1])

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
            print(f"Score: (error: {exc})", file=sys.stderr)

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
