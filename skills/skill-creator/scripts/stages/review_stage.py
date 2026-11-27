from __future__ import annotations

from scripts.compiler_context import CompilerContext
from scripts.review_gate import analyze


class ReviewStage:
    """Runs the deterministic review gate (review_gate.analyze) in the pipeline.

    Emits error-severity findings (missing reports, undisposed high-severity
    findings, false-completion, missing review agents) into ctx.diagnostics. Those
    errors block packaging: the package_skill.py driver returns before PackageStage
    when any error diagnostic is present, and PackageStage.run() additionally
    fails closed on error diagnostics so a direct StageRegistry.run_all caller
    can't bypass the gate either.
    """
    name = "review"
    requires = {"skill_spec"}
    provides = {"diagnostics"}

    def run(self, ctx: CompilerContext) -> None:
        # Packaging is a release action: a self-minted activation skip must carry
        # bound behavioral evidence (G4), not just a reason and a self-computed manifest.
        ctx.diagnostics.extend(analyze(ctx.skill_spec, release=True))
