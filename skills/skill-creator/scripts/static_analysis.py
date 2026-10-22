#!/usr/bin/env python3
"""
Static analysis — semantic/wiring checks that go beyond structural validation.

These checks catch errors that survive quick_validate but surface at runtime:
dead references, unused tools, unreachable sections, etc.

Usage: python -m scripts.static_analysis <skill-path>
Exit codes: 0 = no errors, 1 = errors found, 2 = warnings only.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path, PurePosixPath, PureWindowsPath

from scripts.skill_ir import Skill
from scripts.finding_types import Finding, _cap
from scripts.analysis_config import (
    EXEMPT_LIBRARY_MODULES,
    RUNTIME_OUTPUT_PREFIXES,
    SCAN_DIRS,
    SKIP_DIRS,
    SEVERITY_ERROR,
    SEVERITY_WARNING,
    SEVERITY_INFO,
)
from scripts.skill_md_utils import (
    find_library_modules,
    extract_referenced_dirs,
    extract_referenced_files,
    is_reference_in_body,
)


def analyze(skill: Skill) -> list[Finding]:
    """Run all static-analysis rules on a loaded Skill. Returns findings list."""
    findings: list[Finding] = []
    findings.extend(_check_dead_references(skill))
    findings.extend(_check_orphaned_files(skill))
    findings.extend(_check_missing_assets(skill))
    findings.extend(_check_unused_tools(skill))
    findings.extend(_check_unreachable_sections(skill))
    findings.extend(_check_recursive_call(skill))
    return findings


# ---------------------------------------------------------------------------
# Rules
# ---------------------------------------------------------------------------

def _check_dead_references(skill: Skill) -> list[Finding]:
    """error: file listed in Reference files section but absent on disk."""
    findings: list[Finding] = []
    referenced_files = extract_referenced_files(skill.body)

    for ref in referenced_files:
        # Containment comes first, so a runtime-looking prefix (evals/../../x.md) cannot
        # smuggle a path out of the skill. Backslashes are separators on Windows, so they
        # are normalised before the check: `..\x.md` must not pass as a literal filename.
        target = skill.skill_path / ref.replace("\\", "/")
        if _foreign_absolute(ref) or not _inside_skill(skill.skill_path, target):
            findings.append(Finding(
                severity=SEVERITY_ERROR,
                rule="reference-escapes-skill",
                message=f"'{ref}' is absolute, resolves outside the skill directory, or cannot be resolved, so it is never packaged",
            ))
            continue
        # Runtime-generated workspace outputs (e.g. evals/evals.json) only exist
        # mid-workflow, not in the repo — they are not dead references.
        if any(ref.startswith(prefix) for prefix in RUNTIME_OUTPUT_PREFIXES):
            continue
        if not target.exists():
            findings.append(Finding(
                severity=SEVERITY_ERROR,
                rule="dead-reference",
                message=f"'{ref}' listed in Reference files section but not found on disk",
            ))
    return findings


def _inside_skill(skill_path: Path, target: Path) -> bool:
    """True when target, after resolving `..`, symlinks and absolute paths, stays under skill_path.

    A path that cannot be resolved (a symlink loop, an unreadable component) cannot be shown to stay
    inside, so it is reported as outside rather than aborting validation with a traceback.
    """
    try:
        target.resolve().relative_to(skill_path.resolve())
    except (ValueError, OSError, RuntimeError):
        return False
    return True


def _foreign_absolute(ref: str) -> bool:
    """True for a reference that is absolute or drive-qualified on any platform (`C:/x`, `\\\\srv\\x`, `/x`).

    On POSIX, `C:/x` parses as a relative path, so it must be rejected by shape, not by host semantics.
    """
    return bool(PureWindowsPath(ref).anchor) or PurePosixPath(ref).is_absolute()


def _check_orphaned_files(skill: Skill) -> list[Finding]:
    """warning: a resource file exists on disk but is never referenced in SKILL.md.

    This is the reverse of the dead-reference check, and the specific failure this
    fork exists to prevent: under progressive disclosure Claude only loads the
    files SKILL.md names, so a script or agent that ships unreferenced is invisible
    at runtime — the model never discovers it. A reference to a parent directory
    (e.g. `scripts/stages/`) covers everything beneath it, and internal library
    modules imported by other scripts rather than invoked directly are exempt.
    """
    findings: list[Finding] = []
    body = skill.body
    referenced_dirs = extract_referenced_dirs(body)
    library_modules = find_library_modules(skill.skill_path)
    
    for scan_dir in SCAN_DIRS:
        base = skill.skill_path / scan_dir
        if not base.exists():
            continue
        
        for path in sorted(base.rglob("*")):
            if not path.is_file():
                continue
            parts = path.relative_to(skill.skill_path).parts
            if any(p in SKIP_DIRS for p in parts):
                continue
            rel = "/".join(parts)
            if path.name in EXEMPT_LIBRARY_MODULES or rel in library_modules:
                continue

            if is_reference_in_body(rel, body, referenced_dirs):
                continue
            
            findings.append(Finding(
                severity=SEVERITY_WARNING,
                rule="orphaned-file",
                message=(
                    f"'{rel}' exists on disk but is never referenced in SKILL.md. "
                    "Under progressive disclosure Claude never loads it — wire it into "
                    "the Reference files section or remove it."
                ),
            ))
    return _cap(findings, "orphaned-file")


def _check_missing_assets(skill: Skill) -> list[Finding]:
    """warning: asset path referenced in SKILL.md body but not present on disk."""
    findings: list[Finding] = []
    # Backslashes are matched too, so `assets/..\..\x` is checked in full rather than truncated at the first one.
    asset_ref = re.compile(r"assets/[\w./\\\-]+")
    for lineno, line in enumerate(skill.body.split("\n"), start=1):
        for m in asset_ref.finditer(line):
            asset_path = skill.skill_path / m.group(0).replace("\\", "/")
            if not _inside_skill(skill.skill_path, asset_path):
                findings.append(Finding(
                    severity=SEVERITY_ERROR,
                    rule="reference-escapes-skill",
                    message=f"Asset '{m.group(0)}' resolves outside the skill directory or cannot be resolved, so it is never packaged",
                    line=lineno,
                ))
                continue
            if not asset_path.exists():
                findings.append(Finding(
                    severity=SEVERITY_WARNING,
                    rule="missing-asset",
                    message=f"Asset '{m.group(0)}' referenced but not found on disk",
                    line=lineno,
                ))
    return findings


def _check_unused_tools(skill: Skill) -> list[Finding]:
    """info: allowed-tools entry not mentioned anywhere in SKILL.md body."""
    findings: list[Finding] = []
    body_lower = skill.body.lower()
    for tool in skill.allowed_tools:
        # Bash(python -m scripts.lint *) counts as used when its command
        # (inside the parentheses) or the bare tool name appears in the body.
        inner = tool[tool.find("(") + 1:tool.rfind(")")] if "(" in tool and tool.endswith(")") else ""
        inner = inner.replace("*", "").strip().lower()
        if inner and inner in body_lower:
            continue
        tool_bare = tool.split("(")[0].split(".")[-1].split("/")[-1].lower()
        if tool_bare not in body_lower and tool.lower() not in body_lower:
            findings.append(Finding(
                severity=SEVERITY_INFO,
                rule="unused-tool",
                message=f"Tool '{tool}' is in allowed-tools but never mentioned in SKILL.md body",
            ))
    return findings


def _check_unreachable_sections(skill: Skill) -> list[Finding]:
    """info: ## Section header never linked, in a doc that navigates by link.

    A SKILL.md written as a linear procedure is read top to bottom, so an
    unlinked heading is normal and flagging it is pure noise. This rule only
    applies when the document actually uses in-body anchor links to navigate
    (three or more `](#anchor)` links). In that case an unlinked top-level
    section really is unreachable by the model following the links.
    """
    findings: list[Finding] = []
    body = skill.body
    anchor_links = re.findall(r"\]\(#([\w-]+)\)", body)
    if len(anchor_links) < 3:
        # Linear document: reachability by link is not the navigation model.
        return findings

    linked = {a.lower() for a in anchor_links}
    lines = body.split("\n")
    for lineno, line in enumerate(lines, start=1):
        m = re.match(r"^(#{2})\s+(.+)", line)   # top-level sections only
        if not m:
            continue
        heading = m.group(2).strip()
        # Sequential steps are reached by reading order, not by link.
        if re.match(r"^step\s+\d+", heading, re.IGNORECASE):
            continue
        anchor = re.sub(r"[^\w\s-]", "", heading.lower()).strip().replace(" ", "-")
        if anchor not in linked:
            findings.append(Finding(
                severity=SEVERITY_INFO,
                rule="unreachable-section",
                message=f"Section '{heading}' is never linked from any other section",
                line=lineno,
            ))
    return _cap(findings, "unreachable-section")


def _check_recursive_call(skill: Skill) -> list[Finding]:
    """warning: skill body mentions own skill name as a skill to invoke."""
    findings: list[Finding] = []
    name = skill.name.lower()
    if not name:
        return findings
    invoke_pattern = re.compile(
        rf"(?:invoke|call|use|run|load|skill)\s+[`'\"]?{re.escape(name)}[`'\"]?",
        re.IGNORECASE,
    )
    for lineno, line in enumerate(skill.body.split("\n"), start=1):
        if invoke_pattern.search(line):
            findings.append(Finding(
                severity=SEVERITY_WARNING,
                rule="recursive-call",
                message=f"Skill body appears to invoke itself ('{name}') — likely unintentional recursion",
                line=lineno,
            ))
    return findings


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _main() -> int:
    if len(sys.argv) < 2:
        print(f"Usage: python -m scripts.static_analysis <skill-path>", file=sys.stderr)
        return 1
    skill_path = Path(sys.argv[1])
    try:
        skill = Skill.from_path(skill_path)
    except (FileNotFoundError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    findings = analyze(skill)
    if not findings:
        print("No issues found.")
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
    return 1 if errors else 2


if __name__ == "__main__":
    sys.exit(_main())
