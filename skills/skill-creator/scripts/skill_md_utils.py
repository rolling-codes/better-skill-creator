"""Utilities for parsing and validating SKILL.md structure.

Consolidates section detection, reference parsing, and skill validation
to prevent fragile regex duplication across lint and static_analysis.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path



def has_reference_section(body: str) -> bool:
    """Check if SKILL.md has a Reference files section."""
    pattern = re.compile(
        r"^#{1,3}\s+reference\s+files?",
        re.IGNORECASE | re.MULTILINE,
    )
    return bool(pattern.search(body))


def get_reference_section_content(body: str) -> str | None:
    """Extract the content of the Reference files section.
    
    Returns the section content between the heading and the next heading,
    or None if no Reference files section exists.
    """
    pattern = re.compile(
        r"^#{1,3}\s+reference\s+files?$(.*?)(?=^#{1,3}\s+|\Z)",
        re.IGNORECASE | re.MULTILINE | re.DOTALL,
    )
    match = pattern.search(body)
    if not match:
        return None
    return match.group(1).strip()


def extract_referenced_files(body: str) -> set[str]:
    """Extract all file paths referenced in backticks in SKILL.md.
    
    Returns a set of normalized file paths that appear in backtick references.
    """
    # Match backtick-quoted tokens containing a path separator
    ref_pattern = re.compile(r"`([^`]*[/\\][^`]*\.[a-zA-Z]{1,6})`")
    return {m.group(1).strip() for m in ref_pattern.finditer(body) if m.group(1).strip()}


def extract_referenced_dirs(body: str) -> set[str]:
    """Extract all directory references (ending in /) from SKILL.md.
    
    Returns a set of normalized directory paths.
    """
    # Match backtick-quoted tokens ending in a slash
    ref_pattern = re.compile(r"`([\w./\-]+/)`")
    return {m.rstrip("/") for m in re.findall(ref_pattern, body)}


def normalize_reference(ref: str) -> str:
    """Normalize a file or directory reference for comparison.
    
    Strips whitespace and converts backslashes to forward slashes.
    """
    return ref.strip().replace("\\", "/")


def reference_forms(rel: str) -> set[str]:
    """Generate all valid reference forms for a file path.
    
    For a file like 'scripts/confidence.py', returns:
    - scripts/confidence.py (full path)
    - confidence.py (bare filename)
    - scripts.confidence (Python module form, if .py file)
    """
    forms = {rel, rel.rsplit("/", 1)[-1]}
    if rel.endswith(".py"):
        forms.add(rel[:-3].replace("/", "."))
    return forms


def is_reference_in_body(rel: str, body: str, referenced_dirs: set[str]) -> bool:
    """Check if a file reference appears in SKILL.md body.
    
    Returns True if the file is referenced directly or via a parent directory.
    """
    # Check direct reference in any form
    if any(form in body for form in reference_forms(rel)):
        return True
    
    # Check if covered by a nested directory reference
    parts = rel.split("/")
    ancestors = {"/".join(parts[:i]) for i in range(1, len(parts))}
    nested_dirs = {d for d in referenced_dirs if "/" in d}
    return bool(ancestors & nested_dirs)


def validate_skill_structure(skill_path: Path) -> list[str]:
    """Validate basic SKILL.md structure (frontmatter, required fields).
    
    Returns a list of validation errors, empty if valid.
    """
    errors = []
    skill_md = skill_path / "SKILL.md"
    
    if not skill_md.exists():
        return ["SKILL.md not found"]
    
    content = skill_md.read_text(encoding="utf-8")
    
    # Check frontmatter
    if not content.startswith("---"):
        errors.append("Missing YAML frontmatter (should start with ---)")
    
    # Extract frontmatter
    fm_match = re.match(r"^---\n(.*?)\n---\n", content, re.DOTALL)
    if not fm_match:
        errors.append("Invalid YAML frontmatter format")
        return errors
    
    frontmatter = fm_match.group(1)
    
    # Check required fields
    if "name:" not in frontmatter:
        errors.append("Missing 'name' in frontmatter")
    if "description:" not in frontmatter:
        errors.append("Missing 'description' in frontmatter")
    
    return errors


def _has_main_guard(tree: ast.Module) -> bool:
    """True when the module has an `if __name__ == "__main__":` entry point."""
    for node in tree.body:
        if isinstance(node, ast.If):
            test = node.test
            if (
                isinstance(test, ast.Compare)
                and isinstance(test.left, ast.Name)
                and test.left.id == "__name__"
                and any(isinstance(c, ast.Constant) and c.value == "__main__"
                        for c in test.comparators)
            ):
                return True
    return False


def find_library_modules(skill_path: Path) -> set[str]:
    """Return skill-relative paths of Python files that are pure libraries.

    A file counts as a library when another Python file in the skill imports it
    and it has no `__main__` entry point of its own. Claude never invokes such a
    file directly, so it does not need a SKILL.md reference; the script that
    imports it carries the reference instead. Anything with an entry point is a
    command Claude might run, so it stays subject to the orphan rules.

    Files that are ONLY imported by other files within a closed import cycle (e.g.
    A→B and B→A with no external anchor) are not exempt — the exemption requires
    the import chain to reach at least one file outside the imported set.
    """
    skill_path = Path(skill_path)
    py_files = [p for p in skill_path.rglob("*.py")
                if "__pycache__" not in p.parts]
    by_module: dict[str, Path] = {}
    for p in py_files:
        rel = p.relative_to(skill_path).with_suffix("")
        by_module[".".join(rel.parts)] = p

    imported: set[Path] = set()
    importers: dict[Path, set[Path]] = {}  # target → files that import it
    trees: dict[Path, ast.Module] = {}
    for p in py_files:
        try:
            tree = ast.parse(p.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError, OSError):
            continue
        trees[p] = tree
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if node.level:
                    package = p.relative_to(skill_path).parts[:-1]
                    if node.level > len(package):
                        continue  # Relative import goes beyond the known package root.
                    base = package[:len(package) - node.level + 1]
                    module = ".".join((*base, module)) if module else ".".join(base)
                if module:
                    names = [module] + [f"{module}.{a.name}" for a in node.names]
            for name in names:
                target = by_module.get(name)
                if target is not None and target != p:
                    imported.add(target)
                    importers.setdefault(target, set()).add(p)

    # Forward edges derived from importers (importer → what it imports in `imported`)
    forward: dict[Path, set[Path]] = {}
    for target, importer_set in importers.items():
        for imp in importer_set:
            forward.setdefault(imp, set()).add(target)

    # An imported file is "anchored" if it has at least one importer outside `imported`
    # (meaning the import chain ultimately reaches an entry point or non-imported file).
    # Propagate anchored status forward: if an anchored file imports another imported
    # file, that file is also anchored.
    anchored: set[Path] = {
        f for f in imported
        if any(imp not in imported for imp in importers.get(f, set()))
    }
    queue = list(anchored)
    while queue:
        f = queue.pop()
        for g in forward.get(f, set()):
            if g in imported and g not in anchored:
                anchored.add(g)
                queue.append(g)

    return {
        "/".join(p.relative_to(skill_path).parts)
        for p in anchored
        if p in trees and not _has_main_guard(trees[p])
    }
