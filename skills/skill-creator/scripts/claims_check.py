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


def _test_function_exists(ref: str) -> bool:
    """True if '<file>::<func>' names a function defined in that file under the skill dir."""
    if "::" not in ref:
        return False
    rel, func = ref.split("::", 1)
    path = _SKILL_DIR / rel
    if not path.is_file():
        return False
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return False
    return any(
        isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == func
        for n in ast.walk(tree)
    )


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
        return findings

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
        findings.append(Finding("warning", "claim-manual",
            f"{cid}: manual verifier — not counted as verified"))
    elif "pending" in verifier:
        if status != "pending":
            findings.append(Finding("error", "claim-status",
                f"{cid}: pending verifier requires status 'pending', got '{status}'"))
    else:
        findings.append(Finding("error", "claim-schema",
            f"{cid}: verifier must have one of 'test', 'manual', 'pending'"))
    return findings


def analyze(claims_path: Path = _CLAIMS) -> list[Finding]:
    """Validate every claim in the registry."""
    if not claims_path.is_file():
        return [Finding("error", "claim-registry", f"{claims_path} not found")]
    data = yaml.safe_load(claims_path.read_text(encoding="utf-8")) or {}
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
