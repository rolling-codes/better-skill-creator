#!/usr/bin/env python3
"""
Compiler context — shared mutable IR passed through all pipeline stages.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from scripts.skill_ir import Skill
from scripts.finding_types import Finding
from scripts.score import SkillScore


@dataclass
class StageTrace:
    stage_name: str
    elapsed_ms: float
    diagnostics_added: int
    repairs_proposed: int
    repairs_applied: int


@dataclass
class RepairProposal:
    rule_id: str
    description: str
    apply: Callable[[Skill], Optional[Skill]]
    before: Optional[str] = None
    after: Optional[str] = None


@dataclass
class CompilerContext:
    skill_spec: Skill
    skill_path: Path
    diagnostics: list[Finding] = field(default_factory=list)
    repairs: list[RepairProposal] = field(default_factory=list)
    applied_fixes: list[str] = field(default_factory=list)
    score: Optional[SkillScore] = None
    output_path: Optional[Path] = None
    output_dir: Optional[Path] = None
    trace: list[StageTrace] = field(default_factory=list)

    @classmethod
    def create(cls, skill_path, output_dir=None) -> "CompilerContext":
        sp = Path(skill_path).resolve()
        return cls(
            skill_spec=Skill.from_path(sp),
            skill_path=sp,
            output_dir=Path(output_dir).resolve() if output_dir else None,
        )
