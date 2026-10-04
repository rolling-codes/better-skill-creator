"""Tests for the v1.3.0+ compiler pipeline architecture."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Make the skill's local `scripts/` package win even when pytest is launched
# from a parent repo that has unrelated import roots.
SKILL_PATH = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_PATH))

from scripts.compiler_context import CompilerContext, RepairProposal, StageTrace
from scripts.pipeline import AgentStage, StageRegistry
from scripts.confidence import assess_spec
from scripts.quick_validate import validate_skill
from scripts.review import ReviewRecord
from scripts.file_policy import source_manifest
from scripts.review_gate import analyze as analyze_review_gate
from scripts.skill_ir import Skill
from scripts.spec import SkillSpec
from scripts.static_analysis import Finding
from scripts.stages import DependencyStage, LintStage, SemanticStage, RepairStage, ReviewStage, ScoreStage, PackageStage
from scripts.utils import safe_path_exists


def test_context_creation():
    ctx = CompilerContext.create(SKILL_PATH)
    assert ctx.skill_spec is not None
    assert isinstance(ctx.skill_path, Path)
    assert ctx.diagnostics == []
    assert ctx.repairs == []
    assert ctx.score is None
    assert ctx.output_path is None


def test_stage_order():
    execution_log = []

    class OrderStage:
        def __init__(self, stage_name):
            self.name = stage_name
            self.requires = set()
            self.provides = set()
        def run(self, ctx):
            execution_log.append(self.name)

    registry = StageRegistry()
    registry.register(OrderStage("alpha"))
    registry.register(OrderStage("beta"))
    registry.register(OrderStage("gamma"))

    ctx = CompilerContext.create(SKILL_PATH)
    registry.run_all(ctx)

    assert execution_log == ["alpha", "beta", "gamma"]


def test_lint_stage_populates_diagnostics():
    ctx = CompilerContext.create(SKILL_PATH)
    LintStage().run(ctx)
    assert len(ctx.diagnostics) > 0
    valid_severities = {"error", "warning", "info"}
    for f in ctx.diagnostics:
        assert f.severity in valid_severities


def test_repair_stage_no_filesystem_writes():
    ctx = CompilerContext.create(SKILL_PATH)
    skill_md = SKILL_PATH / "SKILL.md"
    LintStage().run(ctx)
    SemanticStage().run(ctx)
    mtime_before = skill_md.stat().st_mtime
    RepairStage().run(ctx)
    mtime_after = skill_md.stat().st_mtime
    assert mtime_before == mtime_after, "RepairStage must not write to disk"
    assert isinstance(ctx.repairs, list)


def test_run_until():
    ctx = CompilerContext.create(SKILL_PATH)
    registry = StageRegistry()
    registry.register(LintStage())
    registry.register(SemanticStage())
    registry.register(ScoreStage())
    registry.run_until(ctx, "semantic")
    assert len(ctx.diagnostics) > 0
    assert ctx.score is None


def test_stage_trace_populated():
    ctx = CompilerContext.create(SKILL_PATH)
    registry = StageRegistry()
    registry.register(LintStage())
    registry.run_all(ctx)
    assert len(ctx.trace) == 1
    t = ctx.trace[0]
    assert t.stage_name == "lint"
    assert t.elapsed_ms >= 0
    assert t.diagnostics_added == len(ctx.diagnostics)
    assert isinstance(t, StageTrace)


def test_dependency_stage_no_errors_on_valid_skill():
    ctx = CompilerContext.create(SKILL_PATH)
    DependencyStage().run(ctx)
    missing = [f for f in ctx.diagnostics if f.rule == "missing-dependency"]
    assert missing == [], f"Unexpected missing deps: {missing}"


def test_review_stage_is_available_and_runs():
    ctx = CompilerContext.create(SKILL_PATH)
    ReviewStage().run(ctx)
    # The review agents are wired, so the gate never reports them missing...
    assert all(f.rule != "review-agent-missing" for f in ctx.diagnostics)
    # The bundled historical review predates content binding. It must not
    # silently approve this changed release until fresh reports are recorded.
    assert {f.rule for f in ctx.diagnostics if f.severity == "error"} == {"review-unbound"}


def test_review_record_blocks_missing_reports_and_undisposed_findings(tmp_path):
    skill_path = tmp_path / "demo-skill"
    skill_path.mkdir()
    (skill_path / "SKILL.md").write_text((SKILL_PATH / "SKILL.md").read_text(encoding="utf-8"), encoding="utf-8")
    for rel in [
        "agents/outcome-analyst.md",
        "agents/scope-adversary.md",
        "agents/architecture-reviewer.md",
        "agents/completion-adversary.md",
    ]:
        target = skill_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("stub", encoding="utf-8")

    ReviewRecord(
        source_manifest=source_manifest(skill_path),
        activation_required=True,
        activation_reason="substantial update",
        consolidated_decision={"chosen_interpretation": "complex update"},
        independent_findings=[
            {"role": "outcome-analyst", "severity": "high", "finding": "missing scope", "evidence": "request"},
        ],
        completion_gate_status="not_run",
    ).write(skill_path)

    findings = analyze_review_gate(Skill.from_path(skill_path))
    rules = [f.rule for f in findings]
    assert "review-missing-report" in rules
    assert "review-undisposed-finding" in rules
    assert "review-gate-not-passed" in rules


def test_review_gate_fails_passed_status_without_completion_adversary(tmp_path):
    skill_path = tmp_path / "demo-skill"
    skill_path.mkdir()
    (skill_path / "SKILL.md").write_text((SKILL_PATH / "SKILL.md").read_text(encoding="utf-8"), encoding="utf-8")
    for rel in [
        "agents/outcome-analyst.md",
        "agents/scope-adversary.md",
        "agents/architecture-reviewer.md",
        "agents/completion-adversary.md",
    ]:
        target = skill_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("stub", encoding="utf-8")

    ReviewRecord(
        source_manifest=source_manifest(skill_path),
        activation_required=True,
        activation_reason="substantial update",
        consolidated_decision={"chosen_interpretation": "complex update"},
        independent_findings=[
            {"role": "outcome-analyst", "findings": []},
            {"role": "scope-adversary", "findings": []},
            {"role": "architecture-reviewer", "findings": []},
        ],
        completion_gate_status="passed",
    ).write(skill_path)

    findings = analyze_review_gate(Skill.from_path(skill_path))
    assert any(f.rule == "review-missing-completion-adversary" for f in findings)


def test_review_gate_reads_nested_report_findings_and_questions(tmp_path):
    skill_path = tmp_path / "demo-skill"
    skill_path.mkdir()
    (skill_path / "SKILL.md").write_text((SKILL_PATH / "SKILL.md").read_text(encoding="utf-8"), encoding="utf-8")
    for rel in [
        "agents/outcome-analyst.md",
        "agents/scope-adversary.md",
        "agents/architecture-reviewer.md",
        "agents/completion-adversary.md",
    ]:
        target = skill_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("stub", encoding="utf-8")

    ReviewRecord(
        source_manifest=source_manifest(skill_path),
        activation_required=True,
        activation_reason="substantial update",
        consolidated_decision={"chosen_interpretation": "complex update"},
        independent_findings=[
            {"role": "outcome-analyst", "findings": [
                {"severity": "material", "finding": "nested blocker", "evidence": "report"}
            ]},
            {"role": "scope-adversary", "findings": []},
            {"role": "architecture-reviewer", "findings": []},
        ],
        completion_adversary_report={"role": "completion-adversary", "verdict": "complete", "findings": []},
        completion_gate_status="passed",
        unresolved_decisive_questions=["Which storage backend?"],
    ).write(skill_path)

    findings = analyze_review_gate(Skill.from_path(skill_path))
    rules = [f.rule for f in findings]
    assert "review-undisposed-finding" in rules
    assert "review-unresolved-question" in rules


def test_review_record_passes_when_required_findings_are_disposed(tmp_path):
    skill_path = tmp_path / "demo-skill"
    skill_path.mkdir()
    (skill_path / "SKILL.md").write_text((SKILL_PATH / "SKILL.md").read_text(encoding="utf-8"), encoding="utf-8")
    for rel in [
        "agents/outcome-analyst.md",
        "agents/scope-adversary.md",
        "agents/architecture-reviewer.md",
        "agents/completion-adversary.md",
    ]:
        target = skill_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("stub", encoding="utf-8")

    ReviewRecord(
        source_manifest=source_manifest(skill_path),
        activation_required=True,
        activation_reason="substantial update",
        consolidated_decision={"chosen_interpretation": "complex update"},
        independent_findings=[
            {"role": "outcome-analyst", "severity": "high", "finding": "missing scope", "evidence": "request"},
            {"role": "scope-adversary", "severity": "medium", "finding": "over-scoped", "evidence": "request"},
            {"role": "architecture-reviewer", "severity": "low", "finding": "extra moving part", "evidence": "files"},
        ],
        completion_adversary_report={"role": "completion-adversary", "verdict": "incomplete", "findings": []},
        adversarial_findings=[
            {"severity": "material", "type": "hollow-test", "finding": "keyword-only gate"},
        ],
        finding_disposition=[
            {"finding": "missing scope", "disposition": "fixed", "note": "added scope synthesis"},
            {"finding": "keyword-only gate", "disposition": "accepted_limitation", "note": "manual review required"},
        ],
        completion_gate_status="passed",
    ).write(skill_path)

    findings = analyze_review_gate(Skill.from_path(skill_path))
    assert all(f.severity != "error" for f in findings)


def test_skill_spec_review_fields_round_trip_and_score():
    spec = SkillSpec(
        name="demo",
        purpose="Create a demo skill",
        outcome="A skill with independent review before completion",
        inputs=["request"],
        outputs=["skill files"],
        constraints=["no silent external mutation"],
        dependencies=["agents/outcome-analyst.md"],
        examples=[{"input": "Build a skill", "output": "Reviewed skill"}],
        workflows=["Analyze", "Review", "Build", "Gate"],
        interpretations=["simple skill", "complex skill"],
        chosen_interpretation="complex skill because architecture changes are requested",
        modes=["pre-draft review", "completion gate"],
        entailments=["collect independent findings", "record dispositions"],
        optional_features=[],
        authorization_boundaries=["external mutation requires explicit approval"],
        failure_points=["completion claimed before adversarial gate"],
        validation=["review_gate.py"],
        assumptions=["local filesystem packaging is allowed"],
        open_questions=[],
    )

    loaded = SkillSpec.from_yaml(_write_spec_tmp(spec))
    assert loaded.chosen_interpretation == spec.chosen_interpretation
    assert loaded.authorization_boundaries == spec.authorization_boundaries
    report = assess_spec(loaded)
    assert report.overall >= 80
    assert not any("unresolved decisive question" in item for item in report.missing_info)


def test_score_penalizes_review_gate_errors():
    ctx = CompilerContext.create(SKILL_PATH)
    ctx.diagnostics.append(Finding("error", "review-false-completion", "gate not passed"))
    ScoreStage().run(ctx)
    assert ctx.score is not None
    assert ctx.score.validation < 100


def test_agent_stage_uses_fallback():
    ctx = CompilerContext.create(SKILL_PATH)
    fallback_ran = []

    class StubFallback:
        name = "stub"
        requires: set = set()
        provides: set = set()

        def run(self, ctx):
            fallback_ran.append(True)

    agent = AgentStage(
        name="test-agent",
        requires=set(),
        provides=set(),
        model="sonnet",
        prompt_template="",
        fallback=StubFallback(),
    )
    agent.run(ctx)
    assert fallback_ran == [True]


def test_agent_stage_raises_without_fallback():
    ctx = CompilerContext.create(SKILL_PATH)
    agent = AgentStage(
        name="no-fallback",
        requires=set(),
        provides=set(),
        model="sonnet",
        prompt_template="",
    )
    with pytest.raises(NotImplementedError):
        agent.run(ctx)


def test_quick_validate_rejects_lifecycle_mismatch(tmp_path):
    skill_path = tmp_path / "demo-skill"
    skill_path.mkdir()
    (skill_path / "SKILL.md").write_text(
        "---\n"
        "name: demo-skill\n"
        "description: Demo skill for validation regression tests.\n"
        "---\n"
        "Body text.\n",
        encoding="utf-8",
    )
    (skill_path / "skill.yaml").write_text(
        "name: demo-skill\n"
        "version: 1.0.0\n"
        "lifecycle: active\n",
        encoding="utf-8",
    )
    (skill_path / "LIFECYCLE.md").write_text(
        "# Lifecycle\n\n"
        "status: experimental\n",
        encoding="utf-8",
    )

    valid, message = validate_skill(skill_path)

    assert not valid
    assert "Lifecycle mismatch" in message


def test_safe_path_exists_rejects_sibling_prefix_escape(tmp_path):
    base_path = tmp_path / "skills"
    base_path.mkdir()
    sibling_path = tmp_path / "skills-evil"
    sibling_path.mkdir()
    (sibling_path / "payload.txt").write_text("outside", encoding="utf-8")

    assert not safe_path_exists(base_path, Path("..") / "skills-evil" / "payload.txt")


def test_changed_modules_avoid_pep604_unions():
    for rel in [
        "scripts/quick_validate.py",
        "scripts/skill_ir.py",
        "scripts/utils.py",
    ]:
        source = (SKILL_PATH / rel).read_text(encoding="utf-8")
        assert " | " not in source


def _write_spec_tmp(spec: SkillSpec) -> Path:
    import tempfile

    td = Path(tempfile.mkdtemp())
    path = td / "spec.yaml"
    path.write_text(spec.to_yaml(), encoding="utf-8")
    return path
