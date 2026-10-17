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

from scripts.finding_types import Finding

# Every rule this linter can emit. The fixture test iterates this and fails if any
# rule lacks a bad fixture it must flag and a good fixture it must not (spec P2/5.3).
RULE_IDS: tuple[str, ...] = ("H-ENCODING", "H-SWALLOW")

# Directories never scanned by the default tree walk.
EXCLUDE_DIRS = {
    ".git", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    "node_modules", "dist", "build", ".venv", "venv", "env",
    "tests",  # test files + deliberately-bad fixtures are out of scope here
}

# Positional encoding index for bound path methods (always text).
_ENCODING_METHODS = {"read_text": 0, "write_text": 1}
_REASON_MARKER = re.compile(r"#.*\b(reason|intentional|deliberate|expected|ok)\b\s*:", re.IGNORECASE)


def _has_kwarg(call: ast.Call, name: str) -> bool:
    # A **kwargs splat could carry encoding — don't flag when we can't be sure.
    """Return whether a non-None keyword is supplied or may come from **kwargs."""
    return any(
        kw.arg is None or (kw.arg == name and not (
            isinstance(kw.value, ast.Constant) and kw.value.value is None
        ))
        for kw in call.keywords
    )


def _has_encoding(call: ast.Call, index: int) -> bool:
    """Accept explicit non-None encodings passed by keyword or position."""
    if _has_kwarg(call, "encoding"):
        return True
    if len(call.args) <= index or any(isinstance(arg, ast.Starred) for arg in call.args[:index + 1]):
        return False
    encoding = call.args[index]
    return not (isinstance(encoding, ast.Constant) and encoding.value is None)


def _mode_is_binary(call: ast.Call, mode_index: int = 1) -> bool | None:
    """Return False for known text, True for binary, and None for unknown modes."""
    mode: ast.expr = ast.Constant(value="r")
    if any(isinstance(arg, ast.Starred) for arg in call.args):
        return None
    if len(call.args) > mode_index:
        mode = call.args[mode_index]
    for kw in call.keywords:
        if kw.arg == "mode":
            mode = kw.value
    if not isinstance(mode, ast.Constant) or not isinstance(mode.value, str):
        return None
    value = mode.value
    if (not value or set(value) - set("rwaxbt+") or len(set(value)) != len(value)
            or sum(value.count(c) for c in "rwax") != 1 or {"b", "t"} <= set(value)):
        return None
    return "b" in value


class _Visitor(ast.NodeVisitor):
    def __init__(self, rel: str, lines: list[str]) -> None:
        """Store source context and initialize findings and known call bindings."""
        self.rel = rel
        self.lines = lines
        self.findings: list[Finding] = []
        # Track only bindings we can establish syntactically; unknown receivers
        # must not turn arbitrary .open()/.read_text() methods into file calls.
        self.bindings: dict[str, str | None] = {"open": "open"}

    def _kind(self, node: ast.expr) -> str | None:
        """Infer a known builtin or pathlib binding from the expression syntax."""
        if isinstance(node, ast.Name):
            return self.bindings.get(node.id)
        if isinstance(node, ast.Attribute):
            receiver = self._kind(node.value)
            if receiver == "pathlib" and node.attr in {"Path", "PosixPath", "WindowsPath"}:
                return "path_type"
            if receiver == "path" and node.attr == "parent":
                return "path"
        if isinstance(node, ast.Call) and self._kind(node.func) == "path_type":
            return "path"
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div) and self._kind(node.left) == "path":
            return "path"
        return None

    def visit_Import(self, node: ast.Import) -> None:
        """Record pathlib module aliases and clear bindings for other imports."""
        for alias in node.names:
            self.bindings[alias.asname or alias.name.split(".")[0]] = (
                "pathlib" if alias.name == "pathlib" else None
            )

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        """Record imported pathlib path types, including aliases."""
        for alias in node.names:
            self.bindings[alias.asname or alias.name] = (
                "path_type" if node.level == 0 and node.module == "pathlib"
                and alias.name in {"Path", "PosixPath", "WindowsPath"} else None
            )

    def visit_Assign(self, node: ast.Assign) -> None:
        """Visit assignment expressions and track simple name bindings."""
        self.generic_visit(node)
        for target in node.targets:
            if isinstance(target, ast.Name):
                self.bindings[target.id] = self._kind(node.value)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        """Track a simple name using its assigned value or path type annotation."""
        self.generic_visit(node)
        if isinstance(node.target, ast.Name):
            self.bindings[node.target.id] = (
                self._kind(node.value) if node.value else
                "path" if self._kind(node.annotation) == "path_type" else None
            )

    def visit_FunctionDef(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        """Visit a function with local argument bindings, then restore the outer scope."""
        self.bindings[node.name] = None
        outer = self.bindings
        self.bindings = outer.copy()
        args = node.args.posonlyargs + node.args.args + node.args.kwonlyargs
        args += [arg for arg in (node.args.vararg, node.args.kwarg) if arg is not None]
        for arg in args:
            self.bindings[arg.arg] = (
                "path" if arg.annotation and self._kind(arg.annotation) == "path_type" else None
            )
        self.generic_visit(node)
        self.bindings = outer

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        """Visit a class with copied bindings, then restore the outer scope."""
        self.bindings[node.name] = None
        outer = self.bindings
        self.bindings = outer.copy()
        self.generic_visit(node)
        self.bindings = outer

    def _line_marked(self, *linenos: int) -> bool:
        """Return whether any supplied source line has a deliberate-handler marker."""
        for n in linenos:
            if 1 <= n <= len(self.lines) and _REASON_MARKER.search(self.lines[n - 1]):
                return True
        return False

    def visit_Call(self, node: ast.Call) -> None:
        """Flag text file calls missing an encoding and visit their child nodes."""
        receiver = self._kind(node.func.value) if isinstance(node.func, ast.Attribute) else None
        name = node.func.attr if isinstance(node.func, ast.Attribute) else ""
        if (receiver in {"path", "path_type"} and name in _ENCODING_METHODS
                and not _has_encoding(node, _ENCODING_METHODS[name] + (receiver == "path_type"))):
            self.findings.append(Finding("error", "H-ENCODING",
                f"{self.rel}: .{name}() without encoding= (defaults are platform-dependent; pass encoding='utf-8')",
                line=node.lineno))
        elif (self._kind(node.func) == "open" or
              (receiver in {"path", "path_type"} and name == "open")) and not _has_encoding(
                  node, 2 if receiver == "path" else 3):
            # Path instances take mode first; builtin and unbound Path.open take
            # the filename/receiver first. Unknown modes are not known text.
            if _mode_is_binary(node, 0 if receiver == "path" else 1) is False:
                self.findings.append(Finding("error", "H-ENCODING",
                    f"{self.rel}: open() in text mode without encoding= (pass encoding='utf-8')",
                    line=node.lineno))
        self.generic_visit(node)

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        """Flag pass-only handlers without a reason marker and visit their children."""
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
    """Scan the CLI root, print findings, and return the severity-based exit code."""
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
