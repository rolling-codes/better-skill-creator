"""
Default skill generator — general-purpose archetype.

Creates the standard directory layout:
  <name>/
    SKILL.md
    skill.yaml
    references/
    tests/
      should_trigger.yaml
      should_not_trigger.yaml
"""
from __future__ import annotations

from pathlib import Path

from generators.base import Generator
from scripts.skill_ir import Skill

_DEFAULT_BODY = """\

## What it does

<!-- Describe what this skill does in 2-3 sentences. -->

## When to use it

<!-- Describe the trigger conditions: what user requests activate this skill? -->

## When NOT to use it

<!-- Describe the boundary: what does this skill explicitly not cover? -->

## How it works

1. <!-- Step 1 -->
2. <!-- Step 2 -->
3. <!-- Step 3 -->

## Reference files

<!-- List any agents/, references/, or scripts/ files this skill uses. -->

## Iron Law

<!-- State the one non-negotiable rule this skill enforces. -->
"""

_TRIGGER_YAML = """\
# Positive test cases — prompts that SHOULD trigger this skill
- prompt: "TODO: add a realistic positive example"
  expected: triggered
"""

_NO_TRIGGER_YAML = """\
# Negative test cases — prompts that should NOT trigger this skill
- prompt: "TODO: add a realistic near-miss negative example"
  expected: not_triggered
"""


class DefaultGenerator(Generator):
    archetypes = ["default", "general"]

    def scaffold(self, name: str, description: str, output_path: Path) -> Skill:
        """Write a general skill and trigger tests under output_path/name; return the Skill."""
        skill_dir = output_path / name
        skill_dir.mkdir(parents=True, exist_ok=True)
        (skill_dir / "references").mkdir(exist_ok=True)
        (skill_dir / "tests").mkdir(exist_ok=True)

        self._write_skill_md(
            skill_dir,
            name=name,
            description=description,
            allowed_tools=["Read", "Grep", "Glob"],
            body=_DEFAULT_BODY,
        )
        self._write_skill_yaml(skill_dir, name=name)
        (skill_dir / "tests" / "should_trigger.yaml").write_text(_TRIGGER_YAML, encoding="utf-8")
        (skill_dir / "tests" / "should_not_trigger.yaml").write_text(_NO_TRIGGER_YAML, encoding="utf-8")

        return Skill.from_path(skill_dir)
