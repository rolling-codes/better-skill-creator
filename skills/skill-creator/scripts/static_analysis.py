#!/usr/bin/env python3
"""
Static analysis — semantic/wiring checks that go beyond structural validation.

These checks catch errors that survive quick_validate but surface at runtime:
dead references, unused tools, unreachable sections, etc.

Usage: python -m scripts.static_analysis <skill-path>
Exit codes: 0 = no errors or warnings, 1 = errors found, 2 = warnings only.
Info findings do not change the exit code.
"""
from __future__ import annotations

from html import unescape
import re
import sys
from pathlib import Path

from scripts.skill_ir import Skill
from scripts.finding_types import Finding, MAX_FINDINGS_PER_RULE, _cap
from scripts.file_policy import (secret_exclusion_message, defensive_path, is_external_reference,
                                 reference_contained, reference_is_absolute, snapshot)
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
    get_reference_section_content,
    is_reference_in_body,
)


def analyze(skill: Skill) -> list[Finding]:
    """Run all static-analysis rules on a loaded Skill. Returns findings list."""
    findings: list[Finding] = []
    findings.extend(_check_credential_content(skill))
    findings.extend(_check_secret_named_references(skill))
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


_ASSET_REFERENCE = re.compile(r"assets/[^\s`<>\[\](){},;]+")
_CREDENTIAL_PATTERNS = (
    ('private-key', re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----')),
    ('aws-access-key', re.compile(r'(?<![A-Z0-9])(?:AKIA|ASIA)[A-Z0-9]{16}(?![A-Z0-9])')),
    ('assigned-secret', re.compile(r"(?i)\b(?:api[_-]?key|access[_-]?token|password|client[_-]?secret)\b\s*[:=]\s*['\"]([^'\"\r\n]{8,})['\"]")),
)


def _check_credential_content(skill: Skill) -> list[Finding]:
    """Warn about credential-shaped content using bounded, link-free source bytes.

    Diagnostics contain only rule kind, source path, and line: never matched bytes
    or a source excerpt. Heuristic matches are advisory, not proof of a credential.
    """
    try:
        files = snapshot(skill.skill_path, review=True)
    except (ValueError, OSError):
        return [Finding('warning', 'credential-scan-unavailable',
                        'Credential-content scan could not read a bounded, link-free source snapshot.')]
    findings: list[Finding] = []
    suppressed = 0
    for name, item in files.items():
        if b'\x00' in item.data:
            continue
        text = item.data.decode('utf-8', errors='replace')
        for kind, pattern in _CREDENTIAL_PATTERNS:
            line = 1
            previous = 0
            for match in pattern.finditer(text):
                if len(findings) >= MAX_FINDINGS_PER_RULE:
                    suppressed += 1
                    continue
                line += text.count('\n', previous, match.start())
                previous = match.start()
                findings.append(Finding('warning', 'credential-content',
                    f'{name}:{line}: possible {kind}; inspect locally and remove real credentials before distribution.',
                    line=line))
    if suppressed:
        findings.append(Finding('warning', 'credential-content',
                                f'{suppressed} additional credential warnings suppressed.'))
    return findings


def _normalized_reference(reference: str) -> str:
    """Strip surrounding whitespace from a referenced path."""
    return reference.strip()


def _iter_referenced_paths(skill: Skill) -> list[str]:
    """Paths named by SKILL.md or skill.yaml that the secret-name policy can drop.

    Reference-section backticks are included even without a file extension, so
    a listed ``credentials`` file is covered. Glob samples and prose with
    spaces are not file paths.
    """
    raw: list[str] = []
    raw.extend(extract_referenced_files(skill.body))
    # Check escapes before dropping prose and glob examples. Keep the literal
    # spelling for subsequent file access.
    for _, token in re.findall(r"(?<!`)(`+)(?!`)([^`\r\n]+)\1(?!`)", skill.body):
        token = token.strip()
        view = defensive_path(token)
        if is_external_reference(view):
            # Quoted protocol-relative URLs and URI schemes are not local files.
            pass
        elif reference_is_absolute(token) and re.match(r'^/[a-z][a-z0-9-]*$', view):
            # Claude Code slash command (e.g. /skill-test). /.. and /%2e%2e
            # don't match because '.', '%', and '/' aren't in [a-z0-9-].
            pass
        elif '..' in view.split('/') or reference_is_absolute(token):
            raw.append(token)
        elif '/' in view and not any(ch.isspace() or ch in '*?' for ch in token):
            raw.append(token)
    # Inline Markdown links can name extensionless resources too. Check local
    # escape shapes without treating external URLs or anchors as local files.
    destinations = re.findall(
        r"(?:\]\(|^ {0,3}\[[^\]\n]+\]:)[ \t]*(?:<([^>\n]+)>|([^\s)]+))",
        skill.body, re.MULTILINE,
    )
    for angle, bare in destinations:
        token = unescape(angle or bare)
        view = defensive_path(token)
        if is_external_reference(view):
            # Anchors, protocol-relative DNS URLs, and URI schemes.
            # ///etc/passwd, //../escape, and UNC-shaped //host/share stay local.
            continue
        raw.append(token)
    for asset in _ASSET_REFERENCE.findall(skill.body):
        raw.append(asset)
        if asset.endswith((".", ":")):
            # Prose can add one punctuation mark after an unquoted asset.
            raw.append(asset[:-1])
    section = get_reference_section_content(skill.body) or ""
    for token in re.findall(r"`([^`]+)`", section):
        token = token.strip()
        if not token or any(ch.isspace() for ch in token) or "*" in token or "?" in token:
            continue
        raw.append(token)
    paths: list[str] = []
    seen: set[str] = set()
    for ref in raw:
        shown = _normalized_reference(ref)
        if not shown or shown in seen or is_external_reference(shown):
            continue
        seen.add(shown)
        paths.append(shown)
    return paths


def _secret_named(reference: str) -> bool:
    """True when the folded filename matches the secret-file list."""
    return secret_exclusion_message(reference) is not None


def _check_secret_named_references(skill: Skill) -> list[Finding]:
    """error: a referenced file is dropped because its name matches a secret-file pattern.

    The file may still be on disk. Packaging copies a tree that no longer
    contains it, so a later "not found" check would send the author looking
    for a path the policy removed. Paths that escape the skill are reported
    by the containment check instead.
    """
    findings: list[Finding] = []
    for ref in dict.fromkeys([*_iter_referenced_paths(skill), *map(str, skill.dependencies)]):
        if not reference_contained(skill.skill_path, ref):
            continue
        message = secret_exclusion_message(ref)
        if message is None:
            continue
        findings.append(Finding(
            severity=SEVERITY_ERROR,
            rule="secret-name-excluded",
            message=message,
        ))
    return findings


def _reference_exists(root: Path, reference: str) -> bool:
    """Prefer literal spelling, with legacy backslash separators as a fallback."""
    if (root / reference).exists():
        return True
    alternate = reference.replace("\\", "/")
    return alternate != reference and reference_contained(root, alternate) and (root / alternate).exists()


def _check_dead_references(skill: Skill) -> list[Finding]:
    """error: file listed in Reference files section but absent on disk."""
    findings: list[Finding] = []
    referenced_files = extract_referenced_files(skill.body)

    for ref in _iter_referenced_paths(skill):
        # Containment comes first, so a runtime-looking prefix (evals/../../x.md) cannot
        # smuggle a path out of the skill. Backslashes are separators on Windows, so they
        # are normalised before the check: `..\x.md` must not pass as a literal filename.
        if reference_is_absolute(ref) or not reference_contained(skill.skill_path, ref):
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
        if _secret_named(ref):
            continue
        if ref not in referenced_files:
            continue
        if not _reference_exists(skill.skill_path, ref):
            findings.append(Finding(
                severity=SEVERITY_ERROR,
                rule="dead-reference",
                message=f"'{ref}' listed in Reference files section but not found on disk",
            ))
    return findings



def _inside_skill(skill_path: Path, target: Path) -> bool:
    """Compatibility wrapper around shared literal and defensive containment."""
    try:
        reference = str(target.relative_to(skill_path))
    except ValueError:
        reference = str(target)
    return reference_contained(skill_path, reference)


def _foreign_absolute(ref: str) -> bool:
    """Recognize absolute and drive-qualified references independently of the host."""
    return reference_is_absolute(ref)


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
            if _secret_named(rel):
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
    for lineno, line in enumerate(skill.body.split("\n"), start=1):
        for m in _ASSET_REFERENCE.finditer(line):
            reference = m.group(0)
            if not reference_contained(skill.skill_path, reference):
                # The shared reference pass already reports this path as blocking.
                continue
            reference = reference.rstrip(".:")
            if _secret_named(reference):
                continue
            if not _reference_exists(skill.skill_path, reference):
                findings.append(Finding(
                    severity=SEVERITY_WARNING,
                    rule="missing-asset",
                    message=f"Asset '{reference}' referenced but not found on disk",
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
    return 1 if errors else (2 if warnings else 0)


if __name__ == "__main__":
    sys.exit(_main())
