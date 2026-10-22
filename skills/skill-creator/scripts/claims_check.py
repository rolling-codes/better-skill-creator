#!/usr/bin/env python3
"""
Claims check — enforce the claim registry (spec 5.1 / principle P1).

Every entry in claims.yaml ties a behavioral claim to a verifier:
  * test:    <path-rel-to-skill>::<function> — the function must exist (a missing
             test id fails CI; if it exists, the suite step proves it passes).
  * manual:  a human check — must name an owner and review_date; never counted
             as verified, always reported.
  * pending: no verifier yet (future enforcement) — reported, not failed.

A test-backed claim must have status 'verified'; a claim whose test is gone, or
whose schema is malformed, is an error. 'removed' claims are skipped.

Usage: python -m scripts.claims_check [claims.yaml]
Exit codes: 0 = no errors, 1 = errors found, 2 = warnings only.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

import yaml

from scripts.finding_types import Finding

_SKILL_DIR = Path(__file__).resolve().parent.parent
_CLAIMS = _SKILL_DIR / "claims.yaml"
_STATUSES = {"verified", "pending", "removed"}


class _UniqueKeyLoader(yaml.SafeLoader):
    """Reject duplicate mapping keys rather than silently replacing a verifier."""

    def construct_mapping(self, node, deep=False):
        """Construct a YAML mapping, raising ConstructorError for duplicate keys."""
        mapping = super().construct_mapping(node, deep=deep)
        seen = set()
        for key_node, _ in node.value:
            key = self.construct_object(key_node, deep=deep)
            if key in seen:
                raise yaml.constructor.ConstructorError(
                    "while constructing a mapping", node.start_mark,
                    f"duplicate key {key!r}", key_node.start_mark,
                )
            seen.add(key)
        return mapping


def _mark_name(node: ast.expr) -> str:
    """The pytest marker name for `pytest.mark.<x>` / `mark.<x>` (called or not); '' for anything else.

    A bare `@skip` is deliberately not matched: it could be any user-defined helper.
    """
    target = node.func if isinstance(node, ast.Call) else node
    if isinstance(target, ast.Attribute):
        owner = target.value
        if (owner.attr if isinstance(owner, ast.Attribute) else getattr(owner, "id", "")) == "mark":
            return target.attr
    return ""


def _unconditional_marker(node: ast.expr) -> bool:
    """True for a marker that always prevents the test from verifying: skip, skipif(True), xfail."""
    name = _mark_name(node)
    if name == "skip":
        return True
    if name not in {"skipif", "xfail"}:
        return False
    args = node.args if isinstance(node, ast.Call) else []
    keywords = {k.arg: k.value for k in node.keywords} if isinstance(node, ast.Call) else {}
    condition = args[0] if args else keywords.get("condition")
    if condition is None:
        return name == "xfail"  # a bare xfail always expects failure; a conditionless skipif is a usage error
    return isinstance(condition, ast.Constant) and bool(condition.value)


def _module_skipped(tree: ast.Module) -> bool:
    """A module-level `pytestmark = pytest.mark.skip(...)` skips every test in the file."""
    for node in tree.body:
        value: ast.expr | None = None
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "pytestmark" for t in node.targets):
            value = node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == "pytestmark":
            value = node.value  # `pytestmark: list = [...]`; None for a bare annotation
        if value is None:
            continue
        marks = value.elts if isinstance(value, (ast.List, ast.Tuple)) else [value]
        if any(_unconditional_marker(m) for m in marks):
            return True
    return False


def _is_hollow(func: ast.FunctionDef) -> bool:
    """True when a test cannot verify anything. This is a heuristic gate, not a proof of strength.

    Caught: an unconditional skip/xfail marker (a conditional skipif still runs, so it is allowed),
    a body made only of pass/.../docstring/`assert <constant>`/`raise NotImplementedError`, and a
    top-level `pytest.skip()`. Not caught: assertions that are vacuous for subtler reasons.
    """
    if any(_unconditional_marker(deco) for deco in func.decorator_list):
        return True
    body = [s for s in func.body if not (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant))]

    def trivial(stmt: ast.stmt) -> bool:
        if isinstance(stmt, ast.Pass):
            return True
        if isinstance(stmt, ast.Assert):
            return isinstance(stmt.test, ast.Constant) and bool(stmt.test.value)
        if isinstance(stmt, ast.Raise) and stmt.exc is not None:
            exc = stmt.exc.func if isinstance(stmt.exc, ast.Call) else stmt.exc
            return getattr(exc, "id", "") == "NotImplementedError"
        return False

    def skips(stmt: ast.stmt) -> bool:
        call = stmt.value if isinstance(stmt, ast.Expr) else None
        return (isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute)
                and call.func.attr == "skip" and getattr(call.func.value, "id", "") == "pytest")

    return all(trivial(s) for s in body) or any(skips(s) for s in body)


def _source_exists(path: str) -> bool:
    """A claim source must exist inside the skill directory or the repo root, not merely somewhere."""
    for base in (_SKILL_DIR, _SKILL_DIR.parent.parent):
        try:
            candidate = (base / path).resolve()
            candidate.relative_to(base.resolve())
        except (ValueError, OSError, RuntimeError):
            continue  # outside the base, or unresolvable (e.g. a symlink loop): not a usable source
        if candidate.exists():
            return True
    return False


def _test_function_exists(ref: str) -> bool:
    """Resolve a top-level synchronous test using pytest's default naming rules."""
    if "::" not in ref:
        return False
    rel, func = ref.split("::", 1)
    path = _SKILL_DIR / rel
    if not path.is_file() or not (path.match("test_*.py") or path.match("*_test.py")):
        return False
    if not func.startswith("test"):
        return False
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return False
    if _module_skipped(tree):
        return False
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == func:
            return not _is_hollow(node)
    return False


def _check_claim(claim: dict) -> list[Finding]:
    """Return findings for a claim's schema, status, and verifier reference."""
    findings: list[Finding] = []
    cid = str(claim.get("id") or "").strip()
    if not cid:
        return [Finding("error", "claim-schema", "a claim is missing its 'id'")]
    if not str(claim.get("statement") or "").strip():
        findings.append(Finding("error", "claim-schema", f"{cid}: missing 'statement'"))
    if not isinstance(claim.get("sources"), list) or not claim["sources"]:
        findings.append(Finding("error", "claim-schema", f"{cid}: 'sources' must be a non-empty list"))
    status = str(claim.get("status") or "").strip()
    if status not in _STATUSES:
        findings.append(Finding("error", "claim-schema", f"{cid}: status '{status}' not in {sorted(_STATUSES)}"))
    if status == "removed":
        return findings  # a removed claim's sources are history: the files may legitimately be gone
    if isinstance(claim.get("sources"), list):
        for source in claim["sources"]:
            path = str(source).split("#", 1)[0].strip()
            # Sources are relative to the skill directory or, for repo-level files like bsc.py, the repo root.
            if not path:
                findings.append(Finding("error", "claim-source",
                    f"{cid}: source entry {str(source)!r} has no usable path"))
            elif not _source_exists(path):
                findings.append(Finding("error", "claim-source",
                    f"{cid}: source '{path}' does not exist"))

    verifier = claim.get("verifier")
    if not isinstance(verifier, dict):
        return findings + [Finding("error", "claim-schema", f"{cid}: 'verifier' must be a mapping")]

    if "test" in verifier:
        ref = str(verifier["test"]).strip()
        if not _test_function_exists(ref):
            findings.append(Finding("error", "claim-unverified",
                f"{cid}: verifier test '{ref}' does not resolve to an existing test function"))
        elif status != "verified":
            findings.append(Finding("warning", "claim-status",
                f"{cid}: has a passing test but status is '{status}', not 'verified'"))
    elif "manual" in verifier:
        if not str(verifier.get("owner") or "").strip() or not str(verifier.get("review_date") or "").strip():
            findings.append(Finding("error", "claim-schema",
                f"{cid}: manual verifier must name an 'owner' and 'review_date'"))
        findings.append(Finding("info", "claim-manual",
            f"{cid}: manual verifier — not counted as verified"))
    elif "pending" in verifier:
        if status != "pending":
            findings.append(Finding("error", "claim-status",
                f"{cid}: pending verifier requires status 'pending', got '{status}'"))
        else:
            findings.append(Finding("info", "claim-pending",
                f"{cid}: pending verifier — not counted as verified"))
    else:
        findings.append(Finding("error", "claim-schema",
            f"{cid}: verifier must have one of 'test', 'manual', 'pending'"))
    return findings


def analyze(claims_path: Path = _CLAIMS) -> list[Finding]:
    """Validate every claim in the registry."""
    if not claims_path.is_file():
        return [Finding("error", "claim-registry", f"{claims_path} not found")]
    try:
        data = yaml.load(claims_path.read_text(encoding="utf-8"), Loader=_UniqueKeyLoader) or {}
    except yaml.YAMLError as exc:
        return [Finding("error", "claim-registry", f"{claims_path}: invalid YAML: {exc}")]
    claims = data.get("claims") if isinstance(data, dict) else None
    if not isinstance(claims, list):
        return [Finding("error", "claim-registry", "claims.yaml must have a top-level 'claims' list")]
    seen: set[str] = set()
    findings: list[Finding] = []
    for claim in claims:
        if not isinstance(claim, dict):
            findings.append(Finding("error", "claim-schema", "each claim must be a mapping"))
            continue
        cid = str(claim.get("id") or "").strip()
        if cid and cid in seen:
            findings.append(Finding("error", "claim-schema", f"duplicate claim id '{cid}'"))
        seen.add(cid)
        findings += _check_claim(claim)
    return findings


def _main() -> int:
    """Check the CLI registry path, print findings, and return a severity exit code."""
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else _CLAIMS
    findings = analyze(path)
    if not findings:
        print("Claims check: no issues.")
        return 0
    for f in findings:
        print(str(f))
    errors = [f for f in findings if f.severity == "error"]
    warnings = [f for f in findings if f.severity == "warning"]
    print(f"\n{len(findings)} finding(s): {len(errors)} error(s), {len(warnings)} warning(s)")
    return 1 if errors else (2 if warnings else 0)


if __name__ == "__main__":
    sys.exit(_main())
