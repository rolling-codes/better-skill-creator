#!/usr/bin/env python3
"""
Review Record (ReviewRecord) — the artifact of the independent multi-agent review
and adversarial completion gate (see references/independent-review.md).

Written to review.yaml in the skill directory. Kept separate from SkillSpec (the
design brief) so review findings don't muddy the intent IR. scripts/review_gate.py
enforces it deterministically.

Usage:
    python -m scripts.review show <skill-path>    # print the record + gate summary
    python -m scripts.review init <skill-path>    # write a blank review.yaml
"""
from __future__ import annotations

import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from scripts.file_policy import source_manifest as compute_source_manifest
from scripts.finding_types import BLOCKING_SEVERITIES, DISPOSITIONS, GATE_STATES

# The pre-draft reviewer roles that must report when review is required.
REQUIRED_ROLES = ("outcome-analyst", "scope-adversary", "architecture-reviewer")
COMPLETION_ROLE = "completion-adversary"
PRACTICES_ROLE = "practices-reviewer"


@dataclass
class ReviewRecord:
    """Independent-review + completion-gate record for a skill."""
    source_manifest: dict[str, str] = field(default_factory=dict)
    activation_required: bool = False
    activation_reason: str = ""
    workflow: str = ""                                               # e.g. evaluation, behavioral_evaluation, docs_only
    behavior_evidence_path: str = ""                                 # optional relative path to behavior_evidence.json
    independent_findings: list[dict] = field(default_factory=list)   # {id?, role, severity, area, finding, evidence}
    disagreements: list[str] = field(default_factory=list)
    consolidated_decision: dict = field(default_factory=dict)        # accepted/rejected/unresolved_conflicts/...
    completion_adversary_report: dict = field(default_factory=dict)  # {role, verdict, summary, probes}
    adversarial_findings: list[dict] = field(default_factory=list)   # {id?, severity, type, finding}
    finding_disposition: list[dict] = field(default_factory=list)    # {finding_id?, finding, disposition, note}
    completion_gate_status: str = "not_run"                          # not_run | failed | passed
    accepted_limitations: list[str] = field(default_factory=list)
    unresolved_decisive_questions: list[str] = field(default_factory=list)

    # ------------------------------------------------------------------
    # Gate helpers (used by review_gate.py)
    # ------------------------------------------------------------------

    def roles_reported(self) -> set[str]:
        return {str(f.get("role", "")).strip() for f in self.independent_findings if f.get("role")}

    def _flatten_findings(self, reports: list[dict]) -> list[dict]:
        """Accept either flat finding entries or full reports with nested findings."""
        flattened: list[dict] = []
        for report in reports:
            role = str(report.get("role", "")).strip()
            nested = report.get("findings")
            if isinstance(nested, list):
                for item in nested:
                    if not isinstance(item, dict):
                        continue
                    copied = dict(item)
                    if role and "role" not in copied:
                        copied["role"] = role
                    flattened.append(copied)
            else:
                flattened.append(report)
        return flattened

    def all_independent_findings(self) -> list[dict]:
        return self._flatten_findings(self.independent_findings)

    def all_adversarial_findings(self) -> list[dict]:
        report_findings = self.completion_adversary_report.get("findings")
        combined = list(self.adversarial_findings)
        if isinstance(report_findings, list):
            combined.append({
                **self.completion_adversary_report,
                "findings": report_findings,
            })
        return self._flatten_findings(combined)

    def completion_adversary_reported(self) -> bool:
        if str(self.completion_adversary_report.get("role", "")).strip() == COMPLETION_ROLE:
            return True
        return any(
            str(f.get("role", "")).strip() == COMPLETION_ROLE
            for f in self.all_adversarial_findings()
        )

    def completion_adversary_verdict(self) -> str:
        """Return the normalized verdict from the completion-adversary report, or '' if absent."""
        reports = [self.completion_adversary_report, *self.adversarial_findings]
        for f in reports + self.all_adversarial_findings():
            if str(f.get("role", "")).strip() == COMPLETION_ROLE:
                v = str(f.get("verdict") or "").strip().lower()
                if v:
                    return v
        return ""

    def missing_reports(self, *, practices_required: bool = False) -> list[str]:
        """Missing pre-draft reports, plus the code audit when the skill ships code."""
        reported = self.roles_reported()
        required = REQUIRED_ROLES + ((PRACTICES_ROLE,) if practices_required else ())
        return [r for r in required if r not in reported]

    @staticmethod
    def _match_key(record: dict, id_field: str) -> tuple[str, str]:
        """Stable match key: an explicit id when present, else normalized finding text.

        Text is normalized (strip + casefold + collapsed internal whitespace) so a
        capital letter or extra space can't block a correct match. An id, when
        supplied, is matched verbatim and never confused with text.
        """
        rid = str(record.get(id_field, "")).strip()
        if rid:
            return ("id", rid)
        text = " ".join(str(record.get("finding", "")).strip().casefold().split())
        return ("text", text)

    def _disposition_pool(self) -> Counter:
        """Count valid dispositions by match key — each is consumed by one finding."""
        pool: Counter = Counter()
        for d in self.finding_disposition:
            if str(d.get("disposition", "")).strip() not in DISPOSITIONS:
                continue
            key = self._match_key(d, "finding_id")
            if key == ("text", ""):
                continue  # disposition names neither a finding_id nor any finding text
            pool[key] += 1
        return pool

    def undisposed_blocking_findings(self) -> list[dict]:
        """High/material findings (independent + adversarial) with no valid disposition.

        A disposition covers exactly one finding: two findings with identical text
        need two dispositions, not one (matching is consume-once, not set membership).
        """
        pool = self._disposition_pool()
        blocking: list[dict] = []
        for f in self.all_independent_findings() + self.all_adversarial_findings():
            sev = str(f.get("severity", "")).strip().lower()
            if sev not in BLOCKING_SEVERITIES:
                continue
            key = self._match_key(f, "id")
            if pool[key] > 0:
                pool[key] -= 1  # consume this disposition; it can't cover another finding
            else:
                blocking.append(f)
        return blocking

    def bad_dispositions(self) -> list[dict]:
        """Disposition entries whose value isn't one of the allowed dispositions."""
        return [
            d for d in self.finding_disposition
            if str(d.get("disposition", "")).strip() not in DISPOSITIONS
        ]

    def bad_severities(self) -> list[dict]:
        """Finding entries whose severity isn't a recognised value (case-insensitive).

        A misspelled severity ('critcal', 'hight') is silently treated as
        non-blocking by undisposed_blocking_findings() — this surfaces those typos.
        """
        KNOWN = BLOCKING_SEVERITIES | {"low", "medium", "info", "none"}
        result = []
        for f in self.all_independent_findings() + self.all_adversarial_findings():
            sev = str(f.get("severity", "")).strip().lower()
            if sev and sev not in KNOWN:
                result.append(f)
        return result

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        """Return the serializable review fields, including the bound source manifest."""
        d = {
            "source_manifest": self.source_manifest,
            "activation": {"required": self.activation_required, "reason": self.activation_reason},
            "independent_findings": self.independent_findings,
            "disagreements": self.disagreements,
            "consolidated_decision": self.consolidated_decision,
            "completion_adversary_report": self.completion_adversary_report,
            "adversarial_findings": self.adversarial_findings,
            "finding_disposition": self.finding_disposition,
            "completion_gate_status": self.completion_gate_status,
            "accepted_limitations": self.accepted_limitations,
            "unresolved_decisive_questions": self.unresolved_decisive_questions,
        }
        if self.workflow:
            d["workflow"] = self.workflow
        if self.behavior_evidence_path:
            d["behavior_evidence_path"] = self.behavior_evidence_path
        return d

    def to_yaml(self) -> str:
        return yaml.dump(self.to_dict(), default_flow_style=False, allow_unicode=True, sort_keys=False)

    def write(self, skill_path: Path) -> None:
        (skill_path / "review.yaml").write_text(self.to_yaml(), encoding="utf-8")

    @classmethod
    def from_yaml(cls, path: Path) -> "ReviewRecord":
        """Load a review record, rejecting a non-mapping document or malformed manifest."""
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(data, dict):
            raise ValueError("review.yaml must be a YAML mapping")
        activation = data.get("activation") or {}
        if not isinstance(activation, dict):
            activation = {}
        status = str(data.get("completion_gate_status", "not_run")).strip() or "not_run"
        manifest = data.get("source_manifest") or {}
        if not isinstance(manifest, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in manifest.items()):
            raise ValueError("source_manifest must map relative filenames to SHA-256 digests")
        return cls(
            source_manifest=manifest,
            activation_required=bool(activation.get("required", False)),
            activation_reason=str(activation.get("reason", "")).strip(),
            workflow=str(data.get("workflow", "")).strip(),
            behavior_evidence_path=str(data.get("behavior_evidence_path", "")).strip(),
            independent_findings=list(data.get("independent_findings") or []),
            disagreements=list(data.get("disagreements") or []),
            consolidated_decision=dict(data.get("consolidated_decision") or {}),
            completion_adversary_report=dict(data.get("completion_adversary_report") or {}),
            adversarial_findings=list(data.get("adversarial_findings") or []),
            finding_disposition=list(data.get("finding_disposition") or []),
            completion_gate_status=status,
            accepted_limitations=list(data.get("accepted_limitations") or []),
            unresolved_decisive_questions=list(data.get("unresolved_decisive_questions") or []),
        )

    @classmethod
    def from_skill_path(cls, skill_path: Path) -> "ReviewRecord":
        rf = skill_path / "review.yaml"
        if not rf.exists():
            raise FileNotFoundError(f"review.yaml not found in {skill_path}")
        return cls.from_yaml(rf)

    @classmethod
    def blank(cls) -> "ReviewRecord":
        return cls()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _cmd_show(skill_path: Path) -> int:
    rf = skill_path / "review.yaml"
    if not rf.exists():
        print(f"No review.yaml in {skill_path}. Run: python -m scripts.review init <skill-path>")
        return 1
    rec = ReviewRecord.from_yaml(rf)
    print(f"Activation required : {rec.activation_required} ({rec.activation_reason or 'no reason recorded'})")
    print(f"Roles reported      : {', '.join(sorted(rec.roles_reported())) or 'none'}")
    print(f"Completion gate     : {rec.completion_gate_status}")
    print(f"Undisposed blocking : {len(rec.undisposed_blocking_findings())}")
    print(f"Accepted limitations: {len(rec.accepted_limitations)}")
    print(f"Unresolved questions: {len(rec.unresolved_decisive_questions)}")
    return 0


def _cmd_init(skill_path: Path) -> int:
    """Write a source-bound review record; return 1 for an existing record or missing path."""
    rf = skill_path / "review.yaml"
    if rf.exists():
        print(f"review.yaml already exists in {skill_path}. Delete it first to reinitialise.")
        return 1
    if not skill_path.exists():
        print(f"Directory not found: {skill_path}", file=sys.stderr)
        return 1
    ReviewRecord(source_manifest=compute_source_manifest(skill_path)).write(skill_path)
    print(f"Created {rf}")
    return 0


def _main() -> int:
    """Dispatch the show, init, or restart review command and return its exit status."""
    if len(sys.argv) < 3:
        print("Usage:", file=sys.stderr)
        print("  python -m scripts.review show <skill-path>", file=sys.stderr)
        print("  python -m scripts.review init <skill-path>", file=sys.stderr)
        print("  python -m scripts.review restart <skill-path>", file=sys.stderr)
        return 1
    cmd, skill_path = sys.argv[1], Path(sys.argv[2])
    if cmd == "show":
        return _cmd_show(skill_path)
    if cmd == "init":
        return _cmd_init(skill_path)
    if cmd == "restart":
        # New source identity must never carry forward old approval or reports.
        ReviewRecord(source_manifest=compute_source_manifest(skill_path),
                     activation_required=True, activation_reason="Fresh review requested").write(skill_path)
        print("Started a new review; previous approval and reports were cleared.")
        return 0
    print(f"Unknown command: {cmd}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(_main())
