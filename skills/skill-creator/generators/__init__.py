"""
Generator registry + CLI for pluggable skill scaffolding.

Usage:
  python -m generators --archetype python-skill --name my-skill --output ./skills/
  python -m generators --list
"""
from __future__ import annotations

import sys
from pathlib import Path

from generators.base import Generator
from generators.default import DefaultGenerator
from generators.python_skill import PythonSkillGenerator
from generators.research_skill import ResearchSkillGenerator


class GeneratorRegistry:
    def __init__(self) -> None:
        self._registry: dict[str, Generator] = {}
        self._default: Generator | None = None

    def register(self, generator: Generator, default: bool = False) -> None:
        for archetype in generator.archetypes:
            self._registry[archetype] = generator
        if default:
            self._default = generator

    def for_archetype(self, archetype: str) -> Generator:
        if archetype in self._registry:
            return self._registry[archetype]
        if self._default is not None:
            return self._default
        raise KeyError(f"No generator registered for archetype '{archetype}' and no default set.")

    def list_archetypes(self) -> list[str]:
        return sorted(self._registry.keys())


registry = GeneratorRegistry()
registry.register(DefaultGenerator(), default=True)
registry.register(PythonSkillGenerator())
registry.register(ResearchSkillGenerator())


def _main() -> int:
    args = sys.argv[1:]

    if "--list" in args:
        print("Available archetypes:")
        for a in registry.list_archetypes():
            print(f"  {a}")
        return 0

    def _get(flag: str) -> str | None:
        if flag in args:
            idx = args.index(flag)
            if idx + 1 < len(args) and not args[idx + 1].startswith("-"):
                return args[idx + 1]
        return None

    archetype = _get("--archetype") or "default"
    name = _get("--name")
    output = _get("--output")

    if not name:
        print("Usage: python -m generators --name <name> [--archetype <type>] [--output <dir>]", file=sys.stderr)
        print("       python -m generators --list", file=sys.stderr)
        return 1

    output_path = Path(output) if output else Path.cwd()
    generator = registry.for_archetype(archetype)
    skill = generator.scaffold(
        name=name,
        description=f"TODO: describe what {name} does, when to trigger it, and what it does NOT cover.",
        output_path=output_path,
    )
    print(f"Scaffolded '{skill.name}' at {skill.skill_path} (archetype: {archetype})")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
