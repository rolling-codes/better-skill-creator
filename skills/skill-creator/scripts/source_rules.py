#!/usr/bin/env python3
"""
Source rules — AST linter over the toolkit's own Python source.

Catches defect *classes* that have recurred here, repo-wide, so a fix at one
reported line isn't the whole fix (spec principle P7, failure modes F7/F8):

  H-ENCODING  open()/Path.open()/.read_text()/.write_text() on text with no
              encoding= — Python does not default to UTF-8 on Windows, and CI
              runs on windows-latest, so an unspecified encoding is a latent bug.
  H-SWALLOW   an except handler whose body is only `pass` — a swallowed error,
              usually silent data loss. Mark a deliberate one with a reason
              comment (`# reason:` / `# intentional:` / `# deliberate:`) on the
              except or the pass line to exempt it.

Distinct from static_analysis.py, which inspects a loaded Skill (SKILL.md +
resources); this walks raw .py files. Tests and fixtures are excluded from the
default tree scan so deliberately-bad fixtures don't fail CI — the fixture test
calls scan_file() directly on them.

Usage: python -m scripts.source_rules <root>
Exit codes: 0 = no errors, 1 = errors found, 2 = warnings only.
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

from scripts.types import Finding

# Every rule this linter can emit. The fixture test iterates this and fails if any
# rule lacks a bad fixture it must flag and a good fixture it must not (spec P2/5.3).
RULE_IDS: tuple[str, ...] = ("H-ENCODING", "H-SWALLOW")

# Directories never scanned by the default tree walk.
EXCLUDE_DIRS = {
    ".git", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    "node_modules", "dist", "build", ".venv", "venv", "env",
    "tests",  # test files + deliberately-bad fixtures are out of scope here
}

_ENCODING_METHODS = {"read_text", "write_text"}  # always text, always need encoding
_OPEN_NAMES = {"open"}                           # builtin open / Path.open
_REASON_MARKER = re.compile(r"#.*\b(reason|intentional|deliberate|expected|ok)\b\s*:", re.IGNORECASE)


def _call_name(func: ast.expr) -> str:
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return ""


def _has_kwarg(call: ast.Call, name: str) -> bool:
    # A **kwargs splat could carry encoding — don't flag when we can't be sure.
    return any(kw.arg == name for kw in call.keywords) or any(kw.arg is None for kw in call.keywords)


def _mode_is_binary(call: ast.Call) -> bool:
    """True if a builtin open(file, mode) call opens in binary mode (mode is 2nd positional)."""
    mode = None
    if len(call.args) > 1 and isinstance(call.args[1], ast.Constant):
        mode = call.args[1].value
    for kw in call.keywords:
        if kw.arg == "mode" and isinstance(kw.value, ast.Constant):
            mode = kw.value.value
    return isinstance(mode, str) and "b" in mode


class _Visitor(ast.NodeVisitor):
    def __init__(self, rel: str, lines: list[str]) -> None:
        self.rel = rel
        self.lines = lines
        self.findings: list[Finding] = []

    def _line_marked(self, *linenos: int) -> bool:
        for n in linenos:
            if 1 <= n <= len(self.lines) and _REASON_MARKER.search(self.lines[n - 1]):
                return True
        return False

    def visit_Call(self, node: ast.Call) -> None:
        name = _call_name(node.func)
        if name in _ENCODING_METHODS and not _has_kwarg(node, "encoding"):
            self.findings.append(Finding("error", "H-ENCODING",
                f"{self.rel}: .{name}() without encoding= (defaults are platform-dependent; pass encoding='utf-8')",
                line=node.lineno))
        elif isinstance(node.func, ast.Name) and name in _OPEN_NAMES and not _has_kwarg(node, "encoding"):
            # Builtin open() only. Method .open() is left alone: os.open() is fd-level
            # and webbrowser/socket .open() aren't files, so AST can't tell a text
            # Path.open() apart without type info (spec P2 — avoid the false positive).
            if not _mode_is_binary(node):
                self.findings.append(Finding("error", "H-ENCODING",
                    f"{self.rel}: open() in text mode without encoding= (pass encoding='utf-8')",
                    line=node.lineno))
        self.generic_visit(node)

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        if len(node.body) == 1 and isinstance(node.body[0], ast.Pass):
            pass_line = node.body[0].lineno
            if not self._line_marked(node.lineno, pass_line):
                self.findings.append(Finding("error", "H-SWALLOW",
                    f"{self.rel}: except handler silently passes - log/re-raise, or mark deliberate "
                    "with a '# reason:' comment",
                    line=node.lineno))
        self.generic_visit(node)


def scan_file(path: Path, *, root: Path | None = None) -> list[Finding]:
    """Run all source rules on one .py file. Syntax errors are reported, not raised."""
    rel = str(path.relative_to(root)) if root else path.name
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return [Finding("error", "H-READ", f"{rel}: cannot read source: {exc}")]
    try:
        tree = ast.parse(text, filename=str(path))
    except SyntaxError as exc:
        return [Finding("error", "H-SYNTAX", f"{rel}: syntax error: {exc}")]
    v = _Visitor(rel, text.splitlines())
    v.visit(tree)
    return v.findings


def scan_tree(root: Path) -> list[Finding]:
    """Scan every .py file under root, skipping EXCLUDE_DIRS."""
    findings: list[Finding] = []
    for path in sorted(root.rglob("*.py")):
        if any(part in EXCLUDE_DIRS for part in path.relative_to(root).parts):
            continue
        findings.extend(scan_file(path, root=root))
    return findings


def _main() -> int:
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
    if not root.exists():
        print(f"ERROR: {root} does not exist", file=sys.stderr)
        return 1
    findings = scan_tree(root)
    if not findings:
        print("Source rules: no issues.")
        return 0
    for f in findings:
        print(str(f))
    errors = [f for f in findings if f.severity == "error"]
    warnings = [f for f in findings if f.severity == "warning"]
    print(f"\n{len(findings)} finding(s): {len(errors)} error(s), {len(warnings)} warning(s)")
    return 1 if errors else (2 if warnings else 0)


if __name__ == "__main__":
    sys.exit(_main())
