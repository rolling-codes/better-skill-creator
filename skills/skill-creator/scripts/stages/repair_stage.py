from __future__ import annotations
from scripts.compiler_context import CompilerContext, RepairProposal
from scripts.repair import _FIXER_MAP, _UNFIXABLE, ordered_findings


class RepairStage:
    name = "repair"
    requires = {"diagnostics"}
    provides = {"repairs"}

    def run(self, ctx: CompilerContext) -> None:
        for finding in ordered_findings(ctx.diagnostics):
            if finding.rule in _UNFIXABLE:
                continue
            fixer = _FIXER_MAP.get(finding.rule)
            if fixer is None:
                continue
            _f = fixer
            _d = finding

            def _apply(skill, f=_f, d=_d):
                return f.fn(skill, d)

            ctx.repairs.append(RepairProposal(
                rule_id=finding.rule,
                description=fixer.description,
                apply=_apply,
            ))
