#!/usr/bin/env python3
"""
Confidence report — how complete and unambiguous is a skill's intent capture.

Derives entirely from structural analysis of the Skill IR and spec.yaml (if present).
No LLM calls.

Usage: python -m scripts.confidence <skill-path>
Exit codes: 0 = overall ≥80, 1 = overall <80.
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

from scripts.skill_ir import Skill
from scripts.skill_md_utils import description_has_boundary


@dataclass
class ConfidenceReport:
    """Confidence metrics for a skill's intent capture."""
    requirement_coverage: int       # 0–100: % of expected fields populated
    ambiguity_score: int            # 0–100: 0=very ambiguous, 100=precise
    missing_info: list[str]         # fields or sections absent/thin
    inferred_assumptions: list[str] # things assumed that weren't stated
    overall: int                    # weighted average (60% coverage, 40% clarity)

    def __str__(self) -> str:
        lines = [
            f"Requirement coverage : {self.requirement_coverage}%",
            f"Ambiguity score      : {self.ambiguity_score}%",
            f"Overall confidence   : {self.overall}%",
        ]
        if self.missing_info:
            lines.append("\nMissing information:")
            for item in self.missing_info:
                lines.append(f"  - {item}")
        if self.inferred_assumptions:
            lines.append("\nInferred assumptions:")
            for item in self.inferred_assumptions:
                lines.append(f"  - {item}")
        return "\n".join(lines)


def assess_skill(skill: Skill) -> ConfidenceReport:
    """Assess confidence from an existing skill."""
    missing: list[str] = []
    assumptions: list[str] = []
    coverage_checks: list[bool] = []

    # --- Name ---
    coverage_checks.append(bool(skill.name))
    if not skill.name:
        missing.append("name field is empty")

    # --- Description ---
    desc = skill.description
    coverage_checks.append(bool(desc and len(desc) >= 50))
    if not desc:
        missing.append("description is empty")
    elif len(desc) < 50:
        missing.append(f"description is too short ({len(desc)} chars; min 50)")

    # --- Trigger clause ---
    trigger_phrases = ["use when", "when the user", "trigger", "fires when", "invoked when"]
    has_trigger = any(p in desc.lower() for p in trigger_phrases)
    coverage_checks.append(has_trigger)
    if not has_trigger:
        missing.append("no trigger clause in description ('Use when...' or similar)")
        assumptions.append("assumed the skill triggers on any vaguely related request")

    # --- Boundary clause ---
    has_boundary = description_has_boundary(desc)
    coverage_checks.append(has_boundary)
    if not has_boundary:
        missing.append("no boundary clause in description ('NOT for...' or similar)")
        assumptions.append("assumed no adjacent skills overlap with this one")

    # --- SKILL.md body ---
    body_lines = len(skill.body.split("\n"))
    has_body = body_lines > 5
    coverage_checks.append(has_body)
    if not has_body:
        missing.append("SKILL.md body is empty or very thin")

    # --- Test coverage ---
    tests_dir = skill.skill_path / "tests"
    test_files = list(tests_dir.glob("*.yaml")) if tests_dir.exists() else []
    has_tests = len(test_files) >= 1
    coverage_checks.append(has_tests)
    if not has_tests:
        missing.append("no test files in tests/")
        assumptions.append("assumed triggering behaviour is correct without verification")

    # --- Reference section ---
    has_ref_section = bool(
        re.search(r"^#{1,3}\s+reference files?", skill.body, re.IGNORECASE | re.MULTILINE)
    )
    agents_dir = skill.skill_path / "agents"
    refs_dir = skill.skill_path / "references"
    has_ref_dirs = (
        (agents_dir.is_dir() and any(agents_dir.iterdir())) or
        (refs_dir.is_dir() and any(refs_dir.iterdir()))
    )
    if has_ref_dirs:
        coverage_checks.append(has_ref_section)
        if not has_ref_section:
            missing.append("agents/ or references/ exist but no Reference files section")
            assumptions.append("assumed Claude can find reference files without being told")
    else:
        coverage_checks.append(True)  # no ref dirs, not a gap

    # --- allowed-tools ---
    coverage_checks.append(bool(skill.allowed_tools))
    if not skill.allowed_tools:
        assumptions.append("assumed no specific tool permissions are needed")

    # --- Output format ---
    output_keywords = ["output", "format", "returns", "produces", "result"]
    body_lower = skill.body.lower()
    has_output_spec = any(kw in body_lower for kw in output_keywords)
    coverage_checks.append(has_output_spec)
    if not has_output_spec:
        missing.append("no output format or expected result described in body")
        assumptions.append("assumed any output format is acceptable")

    # --- spec.yaml (bonus) ---
    spec_file = skill.skill_path / "spec.yaml"
    has_spec = spec_file.exists()
    coverage_checks.append(has_spec)
    if not has_spec:
        assumptions.append("no spec.yaml; intent was captured directly in SKILL.md")

    # Scores
    requirement_coverage = int(100 * sum(coverage_checks) / max(len(coverage_checks), 1))

    # Ambiguity: fewer missing fields + fewer assumptions = higher clarity
    ambiguity_score = max(
        0,
        100 - (len(missing) * 8) - (len(assumptions) * 5)
    )

    overall = int(0.6 * requirement_coverage + 0.4 * ambiguity_score)

    return ConfidenceReport(
        requirement_coverage=requirement_coverage,
        ambiguity_score=ambiguity_score,
        missing_info=missing,
        inferred_assumptions=assumptions,
        overall=overall,
    )


def assess_spec(spec) -> ConfidenceReport:
    """Assess confidence from a SkillSpec (pre-generation)."""
    # Import here to avoid circular dependency if spec imports confidence
    missing: list[str] = []
    assumptions: list[str] = []
    coverage_checks: list[bool] = []

    fields = [
        ("name", spec.name),
        ("purpose", spec.purpose),
        ("outcome", spec.outcome),
        ("inputs", spec.inputs),
        ("outputs", spec.outputs),
        ("workflows", spec.workflows),
    ]
    optional_fields = [
        ("constraints", spec.constraints),
        ("dependencies", spec.dependencies),
        ("examples", spec.examples),
        ("interpretations", spec.interpretations),
        ("modes", spec.modes),
        ("optional_features", spec.optional_features),
        ("failure_points", spec.failure_points),
        ("validation", spec.validation),
    ]

    for name, val in fields:
        present = bool(val)
        coverage_checks.append(present)
        if not present:
            missing.append(f"'{name}' is empty in spec.yaml")

    for name, val in optional_fields:
        present = bool(val)
        coverage_checks.append(present)
        if not present:
            assumptions.append(f"no {name} specified — defaults assumed")

    # --- Design-analysis signals: the flat-scope problem this fork guards against ---
    # Entailments carry extra weight: an outcome that was never expanded into what it
    # actually requires is the exact "build the literal request" failure the multi-angle
    # scoping stage exists to catch (see references/design-analysis.md).
    coverage_checks.append(bool(spec.entailments))
    if not spec.entailments:
        missing.append("'entailments' is empty — the outcome was not expanded into what it requires")
        assumptions.append("assumed the literal request is the whole job (no entailments derived)")

    # Entailment is not permission: entailed work that was never classified for
    # authorization means the skill may silently do permissioned or destructive work.
    if spec.entailments and not spec.authorization_boundaries:
        assumptions.append(
            "assumed all entailed work is authorized (no authorization_boundaries recorded)"
        )

    # Multiple interpretations with none chosen is an unresolved design fork.
    if len(spec.interpretations) > 1 and not spec.chosen_interpretation:
        missing.append(
            "multiple interpretations recorded but none chosen (chosen_interpretation empty)"
        )

    # Unresolved decisive questions should be settled before proceeding.
    for q in spec.open_questions:
        missing.append(f"unresolved decisive question: {q}")

    requirement_coverage = int(100 * sum(coverage_checks) / max(len(coverage_checks), 1))
    ambiguity_score = max(0, 100 - (len(missing) * 12) - (len(assumptions) * 4))
    overall = int(0.6 * requirement_coverage + 0.4 * ambiguity_score)

    return ConfidenceReport(
        requirement_coverage=requirement_coverage,
        ambiguity_score=ambiguity_score,
        missing_info=missing,
        inferred_assumptions=assumptions,
        overall=overall,
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        getattr(sys.stdout, "reconfigure")(encoding="utf-8")
    if len(sys.argv) < 2:
        print("Usage: python -m scripts.confidence <skill-path>", file=sys.stderr)
        return 1
    skill_path = Path(sys.argv[1])
    try:
        skill = Skill.from_path(skill_path)
    except (FileNotFoundError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    report = assess_skill(skill)
    print(str(report))
    print()

    # If a pre-generation spec.yaml is present, also assess the design analysis
    # (assess_skill only sees the finished SKILL.md; assess_spec sees the intent
    # IR, where the flat-scope check lives). Gate on the lower of the two.
    overall = report.overall
    spec_path = skill_path / "spec.yaml"
    if spec_path.exists():
        from scripts.spec import SkillSpec
        try:
            spec_report = assess_spec(SkillSpec.from_yaml(spec_path))
            print("Design analysis (spec.yaml):")
            print(str(spec_report))
            print()
            overall = min(overall, spec_report.overall)
        except Exception as exc:  # malformed spec.yaml shouldn't crash the report
            print(f"(could not assess spec.yaml: {exc})\n")

    if overall >= 80:
        print(f"✅ Confidence OK ({overall}%)")
        return 0
    else:
        print(f"⚠️  Low confidence ({overall}%) — address missing info before sharing.")
        return 1


if __name__ == "__main__":
    sys.exit(_main())
