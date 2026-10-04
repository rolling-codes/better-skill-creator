"""
Research skill generator — archetype for skills that gather and synthesize information.

Pre-fills allowed-tools with WebSearch and creates a references/ stub.
"""
from __future__ import annotations

from pathlib import Path

from generators.base import Generator
from scripts.skill_ir import Skill

_BODY = """\

## What it does

<!-- Describe what this skill researches and synthesizes. -->

## When to use it

<!-- Trigger clause: what user requests activate this skill? -->

## When NOT to use it

<!-- Boundary clause: what does this skill explicitly not cover? -->

## How it works

1. Identify the research question from the user request.
2. Search for relevant sources using WebSearch.
3. Fetch full content for the most relevant results with WebFetch.
4. Synthesize findings into a structured summary.
5. Save results to `references/overview.md` for future reference.

## Reference files

- `references/overview.md` - accumulated research findings

## Iron Law

<!-- State the one non-negotiable rule this skill enforces. -->
"""

_OVERVIEW_MD = """\
# Research Overview

<!-- Populated by the research skill. Each session appends findings here. -->
"""


class ResearchSkillGenerator(Generator):
    archetypes: list[str] = ["research", "research-skill", "docs", "documentation"]

    def scaffold(self, name: str, description: str, output_path: Path) -> Skill:
        skill_dir = output_path / name
        skill_dir.mkdir(parents=True, exist_ok=True)
        (skill_dir / "references").mkdir(exist_ok=True)
        (skill_dir / "tests").mkdir(exist_ok=True)

        self._write_skill_md(
            skill_dir,
            name=name,
            description=description,
            allowed_tools=["Read", "Grep", "WebSearch"],
            body=_BODY,
        )
        self._write_skill_yaml(
            skill_dir,
            name=name,
            dependencies=["references/overview.md"],
        )
        (skill_dir / "references" / "overview.md").write_text(_OVERVIEW_MD, encoding="utf-8")
        (skill_dir / "tests" / "should_trigger.yaml").write_text(
            "# Positive test cases — prompts that SHOULD trigger this skill\n"
            "- prompt: \"TODO: add a realistic positive example\"\n"
            "  expected: triggered\n",
            encoding="utf-8",
        )
        (skill_dir / "tests" / "should_not_trigger.yaml").write_text(
            "# Negative test cases — prompts that should NOT trigger this skill\n"
            "- prompt: \"TODO: add a realistic near-miss negative example\"\n"
            "  expected: not_triggered\n",
            encoding="utf-8",
        )

        return Skill.from_path(skill_dir)
