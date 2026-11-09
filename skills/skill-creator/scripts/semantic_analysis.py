#!/usr/bin/env python3
"""
Semantic analysis — content-level checks that go beyond structural validation
and wiring checks. Catches contradictions, duplicates, and inconsistencies in
the skill body itself.

Usage: python -m scripts.semantic_analysis <skill-path>
Exit codes: 0 = no errors or warnings, 1 = errors found, 2 = warnings only.
Info findings do not change the exit code.
"""
from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path
from typing import Optional

from scripts.skill_ir import Skill
from scripts.static_analysis import Finding


def semantic_analyze(skill: Skill) -> list[Finding]:
    """Run all semantic rules on a loaded Skill. Returns findings list."""
    findings: list[Finding] = []
    findings.extend(_check_duplicate_sections(skill))
    findings.extend(_check_empty_sections(skill))
    findings.extend(_check_contradictory_instructions(skill))
    findings.extend(_check_conflicting_requirements(skill))
    findings.extend(_check_inconsistent_terminology(skill))
    return findings


# ---------------------------------------------------------------------------
# Rules
# ---------------------------------------------------------------------------

def _without_html_comment(line: str, in_comment: bool) -> tuple[str, bool]:
    """Drop HTML comments from one line and report whether a comment continues."""
    parts: list[str] = []
    index = 0
    while index < len(line):
        if in_comment:
            end = line.find("-->", index)
            if end < 0:
                return "".join(parts), True
            index = end + 3
            in_comment = False
            continue
        start = line.find("<!--", index)
        if start < 0:
            parts.append(line[index:])
            break
        parts.append(line[index:start])
        index = start + 4
        in_comment = True
    return "".join(parts), in_comment


def _check_duplicate_sections(skill: Skill) -> list[Finding]:
    """error: same ## or ### heading appears more than once outside code fences."""
    findings: list[Finding] = []
    heading_lines: dict[str, int] = {}  # normalised heading → first lineno
    in_code_fence = False
    for lineno, line in enumerate(skill.body.split("\n"), start=1):
        if line.strip().startswith("```"):
            in_code_fence = not in_code_fence
            continue
        if in_code_fence:
            continue
        m = re.match(r"^(#{2,3})\s+(.+)", line)
        if not m:
            continue
        heading = m.group(2).strip().lower()
        if heading in heading_lines:
            findings.append(Finding(
                severity="error",
                rule="duplicate-sections",
                message=(
                    f"Section heading '{m.group(2).strip()}' appears more than once "
                    f"(first at line {heading_lines[heading]})"
                ),
                line=lineno,
            ))
        else:
            heading_lines[heading] = lineno
    return findings


def _check_empty_sections(skill: Skill) -> list[Finding]:
    """warning: a ## section has no content before the next same-level heading.

    Sections that contain only subsections (###) are not flagged — a parent
    section organising child headings is intentional. Lines inside code fences
    count as content. HTML comments do not, so a section whose body is only a
    placeholder comment is empty.
    """
    findings: list[Finding] = []
    lines = skill.body.split("\n")
    in_section = False
    section_heading = ""
    section_level = 2
    section_lineno = 0
    has_content = False
    in_code_fence = False
    in_html_comment = False

    for lineno, line in enumerate(lines, start=1):
        stripped = line.strip()

        # Track code-fence state so we don't inspect example content
        if stripped.startswith("```"):
            in_code_fence = not in_code_fence

        if in_code_fence:
            if in_section:
                has_content = True  # code example = content
            continue

        visible, in_html_comment = _without_html_comment(line, in_html_comment)
        stripped = visible.strip()

        heading_match = re.match(r"^(#{2,3})\s+(.+)", visible)
        if heading_match:
            level = len(heading_match.group(1))
            if in_section and not has_content and level <= section_level:
                findings.append(Finding(
                    severity="warning",
                    rule="empty-section",
                    message=f"Section '{section_heading}' has no content",
                    line=section_lineno,
                ))
            if level == 2:
                # Only track ## headings as section boundaries
                section_heading = heading_match.group(2).strip()
                section_level = level
                section_lineno = lineno
                has_content = False
                in_section = True
            else:
                # A ### subsection counts as content for its ## parent
                if in_section:
                    has_content = True
        elif in_section and stripped:
            has_content = True

    if in_section and not has_content:
        findings.append(Finding(
            severity="warning",
            rule="empty-section",
            message=f"Section '{section_heading}' has no content",
            line=section_lineno,
        ))
    return findings


def _check_contradictory_instructions(skill: Skill) -> list[Finding]:
    """warning: lines that say 'always X' and 'never X' for the same keyword.

    Skips common stop-words (prepositions, articles, pronouns) that produce
    false positives when 'always in context' and 'never in doubt' happen to
    share the same next word.
    """
    findings: list[Finding] = []
    lines = skill.body.split("\n")
    in_code_fence = False

    # Words too common to be meaningful as a contradiction signal
    _STOP = {
        "a", "an", "the", "be", "been", "being", "is", "are", "was", "were",
        "in", "on", "at", "to", "for", "of", "with", "by", "from", "into",
        "it", "its", "this", "that", "these", "those", "and", "or", "not",
        "if", "so", "as", "up", "do", "use", "used", "just", "than", "more",
        "all", "any", "have", "has", "had", "i", "you", "we", "they",
    }

    always: dict[str, int] = {}
    never: dict[str, int] = {}

    always_pat = re.compile(r"\balways\s+(\w+)", re.IGNORECASE)
    never_pat = re.compile(r"\bnever\s+(\w+)", re.IGNORECASE)

    for lineno, line in enumerate(lines, start=1):
        if line.strip().startswith("```"):
            in_code_fence = not in_code_fence
        if in_code_fence:
            continue
        for m in always_pat.finditer(line):
            kw = m.group(1).lower()
            if kw not in _STOP:
                always.setdefault(kw, lineno)
        for m in never_pat.finditer(line):
            kw = m.group(1).lower()
            if kw not in _STOP:
                never.setdefault(kw, lineno)

    for kw in set(always) & set(never):
        findings.append(Finding(
            severity="warning",
            rule="contradictory-instructions",
            message=(
                f"Contradictory instructions: 'always {kw}' (line {always[kw]}) "
                f"and 'never {kw}' (line {never[kw]})"
            ),
            line=always[kw],
        ))
    return findings


def _check_conflicting_requirements(skill: Skill) -> list[Finding]:
    """warning: 'MUST X' and 'MUST NOT X' for the same subject verb."""
    findings: list[Finding] = []
    lines = skill.body.split("\n")

    must: dict[str, int] = {}
    must_not: dict[str, int] = {}

    # Match "MUST <verb>" and "MUST NOT <verb>"
    must_not_pat = re.compile(r"\bMUST NOT\s+(\w+)", re.IGNORECASE)
    must_pat = re.compile(r"\bMUST\s+(?!NOT\b)(\w+)", re.IGNORECASE)

    for lineno, line in enumerate(lines, start=1):
        for m in must_not_pat.finditer(line):
            verb = m.group(1).lower()
            must_not.setdefault(verb, lineno)
        for m in must_pat.finditer(line):
            verb = m.group(1).lower()
            must.setdefault(verb, lineno)

    for verb in set(must) & set(must_not):
        findings.append(Finding(
            severity="warning",
            rule="conflicting-requirements",
            message=(
                f"Conflicting requirements: 'MUST {verb}' (line {must[verb]}) "
                f"and 'MUST NOT {verb}' (line {must_not[verb]})"
            ),
            line=must[verb],
        ))
    return findings


def _check_inconsistent_terminology(skill: Skill) -> list[Finding]:
    """info: the same concept referred to by 3+ different terms."""
    findings: list[Finding] = []

    # Known synonym groups — flag if >=3 members appear
    synonym_groups = [
        ("user", "operator", "caller", "requester", "client"),
        ("skill", "plugin", "extension", "tool", "module"),
        ("output", "result", "response", "artifact", "product"),
        ("trigger", "activate", "invoke", "call", "fire"),
    ]

    body_lower = skill.body.lower()
    for group in synonym_groups:
        present = [term for term in group if re.search(rf"\b{re.escape(term)}\b", body_lower)]
        if len(present) >= 3:
            findings.append(Finding(
                severity="info",
                rule="inconsistent-terminology",
                message=(
                    f"Multiple terms used for the same concept: "
                    f"{', '.join(present[:5])}. Pick one and use it consistently."
                ),
            ))
    return findings


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        getattr(sys.stdout, "reconfigure")(encoding="utf-8")
    if len(sys.argv) < 2:
        print("Usage: python -m scripts.semantic_analysis <skill-path>", file=sys.stderr)
        return 1
    skill_path = Path(sys.argv[1])
    try:
        skill = Skill.from_path(skill_path)
    except (FileNotFoundError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    findings = semantic_analyze(skill)
    if not findings:
        print("No semantic issues found.")
        return 0

    errors = [f for f in findings if f.severity == "error"]
    warnings = [f for f in findings if f.severity == "warning"]
    infos = [f for f in findings if f.severity == "info"]

    for f in findings:
        print(str(f))

    print(
        f"\n{len(findings)} finding(s): "
        f"{len(errors)} error(s), {len(warnings)} warning(s), {len(infos)} info(s)"
    )
    return 1 if errors else (2 if warnings else 0)


if __name__ == "__main__":
    sys.exit(_main())
