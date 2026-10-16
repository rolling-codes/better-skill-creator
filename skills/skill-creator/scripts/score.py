#!/usr/bin/env python3
"""
Architecture scoring rubric — quality score across 7 dimensions.

Derives entirely from the Skill IR + a pre-computed findings list.
No additional analysis or LLM calls.

Usage: python -m scripts.score <skill-path>
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path

from scripts.skill_ir import Skill
from scripts.skill_md_utils import description_has_boundary
from scripts.static_analysis import Finding


@dataclass
class SkillScore:
    """Quality score across 7 architectural dimensions."""
    completeness: int       # 0–100
    maintainability: int    # 0–100
    extensibility: int      # 0–100
    clarity: int            # 0–100
    validation: int         # 0–100
    robustness: int         # 0–100
    testability: int        # 0–100
    overall: int            # weighted average

    def __str__(self) -> str:
        rows = [
            ("Completeness",    self.completeness),
            ("Maintainability", self.maintainability),
            ("Extensibility",   self.extensibility),
            ("Clarity",         self.clarity),
            ("Validation",      self.validation),
            ("Robustness",      self.robustness),
            ("Testability",     self.testability),
        ]
        lines = ["Category          Score", "-" * 26]
        for name, val in rows:
            bar = "█" * (val // 10) + "░" * (10 - val // 10)
            lines.append(f"{name:<18} {val:>3}  {bar}")
        lines.append("-" * 26)
        lines.append(f"{'Overall':<18} {self.overall:>3}")
        return "\n".join(lines)


def score(skill: Skill, findings: list[Finding]) -> SkillScore:
    """Compute a SkillScore from the Skill IR and a pre-computed finding list."""
    errors = [f for f in findings if f.severity == "error"]
    warnings = [f for f in findings if f.severity == "warning"]
    infos = [f for f in findings if f.severity == "info"]

    sp = skill.skill_path

    # ------------------------------------------------------------------
    # Completeness — description, body sections, reference section
    # ------------------------------------------------------------------
    comp = 100
    if not skill.description:
        comp -= 30
    elif len(skill.description) < 50:
        comp -= 15
    body_sections = len(re.findall(r"^##\s+", skill.body, re.MULTILINE))
    if body_sections == 0:
        comp -= 20
    elif body_sections < 3:
        comp -= 10
    has_ref_section = bool(
        re.search(r"^#{1,3}\s+reference files?", skill.body, re.IGNORECASE | re.MULTILINE)
    )
    if not has_ref_section:
        comp -= 15
    completeness = max(0, comp)

    # ------------------------------------------------------------------
    # Maintainability — SKILL.md length, dependency tracking, schema version
    # ------------------------------------------------------------------
    maint = 100
    body_lines = len(skill.body.split("\n"))
    if body_lines > 700:
        maint -= 25
    elif body_lines > 500:
        maint -= 10
    if not skill.dependencies:
        maint -= 15
    if skill.schema_version < 1:
        maint -= 10
    if not skill.version:
        maint -= 10
    maintainability = max(0, maint)

    # ------------------------------------------------------------------
    # Extensibility — references/, scripts/, assets/ present
    # ------------------------------------------------------------------
    ext = 40  # start at 40, earn the rest
    if (sp / "references").is_dir() and any((sp / "references").iterdir()):
        ext += 20
    if (sp / "scripts").is_dir() and any((sp / "scripts").iterdir()):
        ext += 20
    if (sp / "assets").is_dir() and any((sp / "assets").iterdir()):
        ext += 10
    spec_yaml = sp / "spec.yaml"
    if spec_yaml.exists():
        ext += 10
    extensibility = min(100, ext)

    # ------------------------------------------------------------------
    # Clarity — trigger/boundary clauses, no contradictions/duplicates
    # ------------------------------------------------------------------
    clar = 100
    desc_lower = skill.description.lower()
    trigger_phrases = ["use when", "when the user", "trigger", "fires when"]
    if not any(p in desc_lower for p in trigger_phrases):
        clar -= 20
    if not description_has_boundary(skill.description):
        clar -= 15
    # Penalise contradictory-instructions and conflicting-requirements
    sem_errors = [f for f in findings if f.rule in (
        "contradictory-instructions", "conflicting-requirements", "inconsistent-terminology"
    )]
    clar -= len(sem_errors) * 10
    clarity = max(0, clar)

    # ------------------------------------------------------------------
    # Validation — finding counts
    # ------------------------------------------------------------------
    # Cap info penalty: infos are advisory, not blocking.
    # Each warning costs 5 pts; infos cost 1 pt each, capped at 20 total.
    info_penalty = min(len(infos), 20)
    vali = 100 - (len(errors) * 15) - (len(warnings) * 5) - info_penalty
    validation = max(0, vali)

    # ------------------------------------------------------------------
    # Robustness — repair-safe (no unfixable errors)
    # ------------------------------------------------------------------
    # Points are not awarded for the literal phrases "red flags"/"iron law": that
    # rewarded wording, not content, and let a doc score by naming a concept it
    # never applied (spec G5). Robustness here reflects error-freedom only.
    robu = 60  # base
    unfixable_error_count = len([
        f for f in errors
        if f.rule not in {"description-no-trigger", "description-no-boundary",
                          "missing-reference-section", "duplicate-sections"}
    ])
    robu -= unfixable_error_count * 10
    robustness = max(0, min(100, robu))

    # ------------------------------------------------------------------
    # Testability — test count, expected_behavior.yaml, trigger tests
    # ------------------------------------------------------------------
    tests_dir = sp / "tests"
    test_yaml_count = len(list(tests_dir.glob("*.yaml"))) if tests_dir.exists() else 0
    testa = 0
    if test_yaml_count >= 1:
        testa += 30
    if test_yaml_count >= 2:
        testa += 20
    if (tests_dir / "expected_behavior.yaml").exists():
        testa += 20
    if (tests_dir / "generated").exists():
        testa += 15
    if (sp / "evals" / "evals.json").exists():
        testa += 15
    testability = min(100, testa)

    # ------------------------------------------------------------------
    # Overall — weighted average
    # ------------------------------------------------------------------
    weights = {
        "completeness": 0.20,
        "maintainability": 0.15,
        "extensibility": 0.10,
        "clarity": 0.20,
        "validation": 0.15,
        "robustness": 0.10,
        "testability": 0.10,
    }
    # weights sum to 1.0 (missing 0.00 slack absorbed into completeness)
    overall = int(
        completeness * weights["completeness"]
        + maintainability * weights["maintainability"]
        + extensibility * weights["extensibility"]
        + clarity * weights["clarity"]
        + validation * weights["validation"]
        + robustness * weights["robustness"]
        + testability * weights["testability"]
    )

    return SkillScore(
        completeness=completeness,
        maintainability=maintainability,
        extensibility=extensibility,
        clarity=clarity,
        validation=validation,
        robustness=robustness,
        testability=testability,
        overall=overall,
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        getattr(sys.stdout, "reconfigure")(encoding="utf-8")
    if len(sys.argv) < 2:
        print("Usage: python -m scripts.score <skill-path>", file=sys.stderr)
        return 1
    skill_path = Path(sys.argv[1])
    try:
        skill = Skill.from_path(skill_path)
    except (FileNotFoundError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    # Run all three analysis passes to get findings
    from scripts.static_analysis import analyze
    from scripts.lint import lint

    try:
        from scripts.semantic_analysis import semantic_analyze
        findings = analyze(skill) + lint(skill) + semantic_analyze(skill)
    except ImportError:
        findings = analyze(skill) + lint(skill)

    result = score(skill, findings)
    print(str(result))

    return 0


if __name__ == "__main__":
    sys.exit(_main())
