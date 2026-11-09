#!/usr/bin/env python3
"""
Skill repair — auto-fix loop for known lint and analysis findings.

Applies deterministic fixers for rules that have safe, mechanical corrections.
Rules that require human judgment are reported but not touched.

Usage: python -m scripts.repair <skill-path> [--dry-run]
Exit codes: 0 = all fixable issues resolved (or nothing to fix),
            1 = unfixable errors remain,
            2 = only unfixable warnings remain.
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from scripts.skill_ir import Skill
from scripts.static_analysis import Finding


@dataclass
class Fixer:
    rule: str           # matches Finding.rule
    description: str    # human-readable description of what the fix does
    fn: Callable[[Skill, Finding], Optional[Skill]]


def _fix_description_no_trigger(skill: Skill, finding: Finding) -> Optional[Skill]:
    """Append a minimal trigger clause to the description."""
    name = skill.name or "this skill"
    phrase = f" Use when {name} is needed."
    if phrase.lower() in skill.description.lower():
        return None  # already there somehow
    from dataclasses import replace
    return replace(skill, description=skill.description.rstrip() + phrase)


def _fix_description_no_boundary(skill: Skill, finding: Finding) -> Optional[Skill]:
    """Append a minimal boundary clause to the description."""
    phrase = " Not for tasks outside this skill's scope."
    if "not for" in skill.description.lower():
        return None
    from dataclasses import replace
    return replace(skill, description=skill.description.rstrip() + phrase)


def _fix_missing_reference_section(skill: Skill, finding: Finding) -> Optional[Skill]:
    """Append a stub Reference files section to the skill body."""
    if re.search(r"^#{1,3}\s+reference files?", skill.body, re.IGNORECASE | re.MULTILINE):
        return None  # section exists, don't double-add

    stub = (
        "\n\n## Reference files\n\n"
        "<!-- List files from agents/ and references/ here with one-line guidance. -->\n"
        "<!-- Example: - `references/guide.md` — Read when you need ... -->\n"
    )
    from dataclasses import replace
    return replace(skill, body=skill.body.rstrip() + stub)


def ordered_findings(findings: list[Finding]) -> list[Finding]:
    """Return findings with duplicate-heading repairs ordered from the bottom.

    Each finding's line number was computed on the original body. Deleting a
    later heading does not change earlier line numbers. Deleting an earlier one
    shifts every line below it.
    """
    rest: list[Finding] = []
    duplicates: list[Finding] = []
    for finding in findings:
        if finding.rule == "duplicate-sections":
            duplicates.append(finding)
        else:
            rest.append(finding)
    duplicates.sort(key=lambda finding: finding.line if finding.line is not None else -1, reverse=True)
    return rest + duplicates


def _fix_duplicate_sections(skill: Skill, finding: Finding) -> Optional[Skill]:
    """Remove one duplicate section heading when that line still holds it."""
    if finding.line is None:
        return None

    lines = skill.body.split("\n")
    # finding.line is 1-based relative to skill.body
    target_idx = finding.line - 1
    if target_idx < 0 or target_idx >= len(lines):
        return None

    dup_line = lines[target_idx]
    m = re.match(r"^(#{2,3})\s+(.+)", dup_line)
    if not m:
        return None
    expected = re.search(r"Section heading '(.+)' appears more than once", finding.message or "")
    if expected and expected.group(1).strip().lower() != m.group(2).strip().lower():
        return None

    # Only remove the line itself (the heading); leave the content below intact
    new_lines = lines[:target_idx] + lines[target_idx + 1:]
    from dataclasses import replace
    return replace(skill, body="\n".join(new_lines))


# Registry of fixers — matched by rule id
_FIXERS: list[Fixer] = [
    Fixer(
        rule="description-no-trigger",
        description="Appended a trigger clause to the description",
        fn=_fix_description_no_trigger,
    ),
    Fixer(
        rule="description-no-boundary",
        description="Appended a boundary clause to the description",
        fn=_fix_description_no_boundary,
    ),
    Fixer(
        rule="missing-reference-section",
        description="Added a stub Reference files section to SKILL.md body",
        fn=_fix_missing_reference_section,
    ),
    Fixer(
        rule="duplicate-sections",
        description="Removed duplicate section heading",
        fn=_fix_duplicate_sections,
    ),
]

_FIXER_MAP: dict[str, Fixer] = {f.rule: f for f in _FIXERS}

# Rules that are explicitly unfixable — need human
_UNFIXABLE = {
    "description-length",   # requires substantive human content
    "empty-section",        # requires human content
    "token-budget",         # requires restructuring judgement
}


def repair(
    skill: Skill,
    findings: list[Finding],
    dry_run: bool = False,
) -> tuple[Skill, list[str]]:
    """
    Apply all available fixers to the skill.

    Returns (updated_skill, applied_fix_descriptions).
    If dry_run=True, returns what would be changed without writing files.
    """
    applied: list[str] = []
    current = skill

    for finding in ordered_findings(findings):
        if finding.rule in _UNFIXABLE:
            continue  # skip silently — reported separately
        fixer = _FIXER_MAP.get(finding.rule)
        if fixer is None:
            continue  # no fixer for this rule

        updated = fixer.fn(current, finding)
        if updated is None:
            continue  # fixer decided it couldn't help

        applied.append(f"{fixer.description} (rule: {finding.rule})")
        current = updated

    if applied and not dry_run:
        current.write_skill_md()

    return current, applied


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        getattr(sys.stdout, "reconfigure")(encoding="utf-8")
    dry_run = "--dry-run" in sys.argv
    args = [a for a in sys.argv[1:] if not a.startswith("--")]

    if not args:
        print("Usage: python -m scripts.repair <skill-path> [--dry-run]", file=sys.stderr)
        return 1

    skill_path = Path(args[0])
    try:
        skill = Skill.from_path(skill_path)
    except (FileNotFoundError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    # Collect findings from lint + static analysis
    from scripts.static_analysis import analyze
    from scripts.lint import lint

    findings = analyze(skill) + lint(skill)

    if not findings:
        print("No findings to repair.")
        return 0

    # Show unfixable items
    unfixable_errors = [
        f for f in findings
        if f.severity == "error" and (f.rule in _UNFIXABLE or f.rule not in _FIXER_MAP)
    ]
    unfixable_warnings = [
        f for f in findings
        if f.severity == "warning" and (f.rule in _UNFIXABLE or f.rule not in _FIXER_MAP)
    ]
    unfixable_infos = [
        f for f in findings
        if f.severity == "info" and (f.rule in _UNFIXABLE or f.rule not in _FIXER_MAP)
    ]

    prefix = "[DRY RUN] " if dry_run else ""
    updated, applied = repair(skill, findings, dry_run=dry_run)

    if applied:
        print(f"{prefix}Applied {len(applied)} fix(es):")
        for desc in applied:
            print(f"  ✅ {desc}")
    else:
        print("No auto-fixable issues found.")

    if unfixable_errors:
        print(f"\n{len(unfixable_errors)} error(s) require manual fix:")
        for f in unfixable_errors:
            print(f"  ❌ {f}")
        return 1

    if unfixable_warnings:
        print(f"\n{len(unfixable_warnings)} warning(s) to review manually:")
        for f in unfixable_warnings:
            print(f"  ⚠️  {f}")
    if unfixable_infos:
        print(f"\n{len(unfixable_infos)} info finding(s):")
        for f in unfixable_infos:
            print(f"  {f}")
    if unfixable_warnings:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(_main())
