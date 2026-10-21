#!/usr/bin/env python3
"""
Review gate — deterministic enforcement of the independent-review process
(references/independent-review.md), over review.yaml (scripts/review.py).

Fails on: a required review with missing reports; high-severity findings with no
disposition; invalid dispositions; unresolved decisive questions; a completion claim
while the gate isn't passed (false-completion detection); a passed status without a
completion-adversary report; and review agents that are missing on disk or unwired.

Absent review.yaml is a warning. Narrow edits are not forced through the full process,
but package/release work should record either activation or an explicit skip reason.

Known limits (deliberately not closed here — the real guard is the maintainer reading
the reports; see references/independent-review.md and the bug-prevention spec Phase 4/5):
  * The gate trusts that reviewer reports were actually produced by an agent (G1) and
    that completion_gate_status reflects a real run (G2) — both are author-supplied.
  * Nothing here reads eval results or checks that a baseline run happened (G3).
  * activation.required=false with any reason skips the whole gate (G4).
These are addressed by the reviewer-brief/provenance and release-gate phases, not by
presence/shape checks, which a hand-written record can always satisfy.

Usage: python -m scripts.review_gate <skill-path>
Exit codes: 0 = no errors, 1 = errors, 2 = warnings only.
"""
from __future__ import annotations

import sys
from pathlib import Path

from scripts.skill_ir import Skill
from scripts.finding_types import CONSOLIDATED_REQUIRED_KEYS, Finding, GATE_STATES
from scripts.skill_md_utils import extract_referenced_dirs, is_reference_in_body
from scripts.review import PRACTICES_ROLE, ReviewRecord
from scripts.file_policy import SourceFile, snapshot, source_manifest, behavior_manifest_digest

REVIEW_AGENTS = (
    "agents/outcome-analyst.md",
    "agents/scope-adversary.md",
    "agents/architecture-reviewer.md",
    "agents/completion-adversary.md",
    f"agents/{PRACTICES_ROLE}.md",
)


def has_runnable_files(files: dict[str, SourceFile]) -> bool:
    """Recognize code across languages, shebang scripts, and executable files.

    Use the bounded source snapshot so excluded caches and installed dependencies
    do not activate the audit, and links cannot redirect inspection outside it.
    """
    code_suffixes = {
        ".py", ".pyw", ".sh", ".bash", ".zsh", ".fish", ".ksh",
        ".js", ".mjs", ".cjs", ".jsx", ".ts", ".mts", ".cts", ".tsx",
        ".rb", ".pl", ".pm", ".php", ".lua", ".r", ".ps1", ".psm1",
        ".bat", ".cmd", ".exe", ".com", ".wasm", ".jar",
        ".go", ".rs", ".c", ".cpp", ".cc", ".cs", ".java",
        ".kt", ".kts", ".swift", ".scala", ".ex", ".exs", ".jl",
        ".sql", ".ipynb", ".html", ".htm",
    }
    return any(
        Path(name).suffix.lower() in code_suffixes
        or Path(name).name.lower() in {"makefile", "dockerfile", "justfile", "rakefile"}
        or item.data.startswith(b"#!")
        or bool(item.mode & 0o111)
        for name, item in files.items()
    )


def review_applies(skill: Skill) -> bool:
    """Return True when the independent review process applies to this skill."""
    return (skill.skill_path / "review.yaml").exists() or any(a in skill.body for a in REVIEW_AGENTS)


def analyze(skill: Skill) -> list[Finding]:
    """Return findings for applicable review wiring, source identity, and completion gates."""
    findings: list[Finding] = []
    if not review_applies(skill):
        findings.append(Finding("info", "review-skipped",
            "review.yaml absent and no review agent referenced — gate skipped for this minimal skill; "
            "record activation.required=false with a reason to make the skip explicit"))
        return findings
    body = skill.body
    rdirs = extract_referenced_dirs(body)
    try:
        practices_required = has_runnable_files(snapshot(skill.skill_path, review=True))
    except (OSError, ValueError) as exc:
        return [Finding("error", "review-source", f"Cannot inspect reviewed source: {exc}")]

    # The review agents must exist and be discoverable for the process to run at all.
    for agent in REVIEW_AGENTS:
        if agent == f"agents/{PRACTICES_ROLE}.md" and not practices_required:
            continue
        if not (skill.skill_path / agent).exists():
            findings.append(Finding("error", "review-agent-missing", f"{agent} is missing on disk"))
        elif not is_reference_in_body(agent, body, rdirs):
            findings.append(Finding("warning", "review-agent-unwired",
                                    f"{agent} exists but is not referenced in SKILL.md"))

    review_path = skill.skill_path / "review.yaml"
    if not review_path.exists():
        findings.append(Finding("warning", "no-review-record",
            "no review.yaml - package assumes a narrow change; create one with activation.required false to record a deliberate skip"))
        return findings

    try:
        rec = ReviewRecord.from_yaml(review_path)
    except Exception as exc:  # malformed review.yaml
        findings.append(Finding("error", "review-parse", f"review.yaml could not be parsed: {exc}"))
        return findings

    if rec.completion_gate_status not in GATE_STATES:
        findings.append(Finding("error", "review-gate-status",
            f"completion_gate_status '{rec.completion_gate_status}' is not one of {list(GATE_STATES)}"))

    if not rec.activation_required:
        if not rec.activation_reason:
            findings.append(Finding("error", "review-activation-unrecorded",
                "activation.required is false but no reason was recorded; "
                "record an explicit skip reason to satisfy the independent-review contract"))
        return findings

    # Legacy records must be reviewed again, never silently stamped as current.
    if not rec.source_manifest:
        findings.append(Finding("error", "review-unbound",
            "Required review has no source manifest; restart the review and collect fresh reports"))
    else:
        try:
            current = source_manifest(skill.skill_path)
            if rec.source_manifest != current:
                findings.append(Finding("error", "review-stale",
                    "Skill files changed since review started; restart review on the current source"))
        except (OSError, ValueError) as exc:
            findings.append(Finding("error", "review-source", f"Cannot verify reviewed source: {exc}"))

    # Review is required: enforce the full gate.
    if not rec.consolidated_decision:
        findings.append(Finding("error", "review-missing-synthesis",
            "independent review required but consolidated_decision is empty"))
    else:
        # Presence isn't meaning: a non-empty dict like {"ok": true} is not a
        # synthesis. Require the keys that make it one.
        missing = CONSOLIDATED_REQUIRED_KEYS - set(rec.consolidated_decision)
        if missing:
            findings.append(Finding("error", "review-synthesis-incomplete",
                "consolidated_decision is missing required key(s): "
                + ", ".join(sorted(missing))))
    for role in rec.missing_reports(practices_required=practices_required):
        findings.append(Finding("error", "review-missing-report",
            f"independent review required but no report from '{role}'"))
    if rec.completion_gate_status == "passed" and not rec.completion_adversary_reported():
        findings.append(Finding("error", "review-missing-completion-adversary",
            "completion_gate_status is passed but no completion-adversary report was recorded"))
    if rec.completion_gate_status == "passed" and rec.completion_adversary_reported():
        verdict = rec.completion_adversary_verdict()
        if verdict != "complete":
            label = f"'{verdict}'" if verdict else "missing"
            findings.append(Finding("error", "review-adversary-verdict",
                f"completion-adversary verdict is {label}, not 'complete'; "
                "resolve or document findings before marking the gate passed"))

    # Behavior evidence enforcement (closing Limit G3 for evaluated workflows)
    requires_behavior = bool(rec.workflow in ("evaluation", "behavioral_evaluation") or rec.behavior_evidence_path)
    evidence_target = None
    if rec.behavior_evidence_path:
        evidence_target = skill.skill_path / rec.behavior_evidence_path
    elif requires_behavior:
        evidence_target = skill.skill_path / "behavior_evidence.json"

    if requires_behavior and evidence_target:
        if not evidence_target.exists():
            findings.append(Finding("error", "review-evidence-missing",
                f"Required behavioral evidence '{evidence_target.name}' is missing on disk"))
        else:
            try:
                import json
                import re
                ev_data = json.loads(evidence_target.read_text(encoding="utf-8"))
                if not isinstance(ev_data, dict):
                    findings.append(Finding("error", "review-evidence-malformed",
                        f"{evidence_target.name} must be a JSON object"))
                else:
                    summary = ev_data.get("summary")
                    provenance = ev_data.get("provenance")
                    expectations = ev_data.get("expectations")
                    if not isinstance(summary, dict) or not isinstance(provenance, dict) or not isinstance(expectations, list):
                        findings.append(Finding("error", "review-evidence-schema",
                            f"{evidence_target.name} is missing required summary/provenance/expectations keys"))
                    else:
                        integrity = provenance.get("transcript_integrity") or {}
                        if not integrity.get("complete", False):
                            issues = "; ".join(integrity.get("issues", []))
                            findings.append(Finding("error", "review-evidence-incomplete-transcript",
                                f"Behavioral evidence is based on an incomplete or corrupted transcript: {issues}"))

                        ev_manifest_hash = provenance.get("skill_manifest_sha256")
                        if not isinstance(ev_manifest_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", ev_manifest_hash):
                            findings.append(Finding("error", "review-evidence-unbound",
                                "Behavioral evidence requires a lowercase SHA-256 skill manifest digest"))
                        elif ev_manifest_hash != behavior_manifest_digest(skill.skill_path):
                            findings.append(Finding("error", "review-evidence-stale",
                                "Behavioral evidence was graded against an older skill snapshot; rerun evaluation"))

                        t_sha = str(provenance.get("transcript_sha256", ""))
                        if not re.fullmatch(r"[0-9a-f]{64}", t_sha):
                            findings.append(Finding("error", "review-evidence-tampered",
                                "Behavioral evidence transcript_sha256 is invalid or missing"))

                        if (not expectations
                                or any(not isinstance(row, dict) or row.get("verdict") != "PASS" for row in expectations)
                                or summary.get("total") != len(expectations)):
                            findings.append(Finding("error", "review-evidence-inconsistent",
                                "Behavioral evidence requires nonempty PASS rows and a matching summary total"))

                        ev_verdict = summary.get("verdict")
                        undetermined = summary.get("undetermined", 0)
                        failed = summary.get("failed", 0)
                        if ev_verdict != "PASS" or undetermined > 0 or failed > 0:
                            findings.append(Finding("error", "review-evidence-unmet-behavior",
                                f"Behavioral evaluation did not pass cleanly: verdict is '{ev_verdict}' ({undetermined} undetermined, {failed} failed)"))
            except Exception as exc:
                findings.append(Finding("error", "review-evidence-unreadable",
                    f"Cannot read or parse behavioral evidence: {exc}"))
    for f in rec.undisposed_blocking_findings():
        findings.append(Finding("error", "review-undisposed-finding",
            f"high-severity finding without disposition: {str(f.get('finding', ''))[:80]}"))
    for d in rec.bad_dispositions():
        findings.append(Finding("error", "review-bad-disposition",
            f"disposition '{d.get('disposition')}' is not fixed/accepted_limitation/returned_to_user"))
    for f in rec.bad_severities():
        findings.append(Finding("error", "review-bad-severity",
            f"unrecognised severity '{f.get('severity')}' in finding: {str(f.get('finding', ''))[:60]} "
            f"— typo? blocking check silently skips unrecognised severities"))
    if rec.completion_gate_status != "passed":
        findings.append(Finding("error", "review-gate-not-passed",
            f"review gate not passed: completion_gate_status is '{rec.completion_gate_status}', not 'passed'"))
    for question in rec.unresolved_decisive_questions:
        findings.append(Finding("error", "review-unresolved-question",
            f"unresolved decisive question remains: {str(question)[:80]}"))
    return findings


def _main() -> int:
    import argparse
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("skill_path")
    p.add_argument("--release", action="store_true",
                   help="Treat skipped-no-review-record as an error (not info)")
    args = p.parse_args()

    try:
        skill = Skill.from_path(Path(args.skill_path))
    except (FileNotFoundError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    findings = analyze(skill)

    # --release: upgrade info "review-skipped" to error
    if args.release:
        findings = [
            Finding("error", f.rule, f.message) if f.rule == "review-skipped" else f
            for f in findings
        ]

    errors = [f for f in findings if f.severity == "error"]
    warnings = [f for f in findings if f.severity == "warning"]
    infos = [f for f in findings if f.severity == "info"]

    for f in sorted(findings, key=lambda x: {"error": 0, "warning": 1, "info": 2}.get(x.severity, 3)):
        print(str(f))

    if findings:
        print(f"\n{len(findings)} finding(s): {len(errors)} error(s), {len(warnings)} warning(s), {len(infos)} info(s)")

    # Always print one summary line.
    skipped_finding = next((f for f in findings if f.rule == "review-skipped"), None)
    if errors:
        print(f"Review gate: failed — {len(errors)} error(s)")
    elif skipped_finding:
        print("Review gate: skipped — no review record")
    elif warnings:
        print("Review gate: passed (with warnings)")
    else:
        print("Review gate: passed")

    return 1 if errors else (2 if warnings else 0)


if __name__ == "__main__":
    sys.exit(_main())
