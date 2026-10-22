#!/usr/bin/env python3
"""
Test case generator — structured scenarios beyond trigger-query testing.

Reads the Skill IR and produces test cases across 6 scenario categories:
happy_path, edge_cases, malformed_input, ambiguous_request, missing_files,
and unsupported_env.

Output goes to tests/generated/ as YAML. Existing tests/ files are not modified.

Usage: python -m scripts.generate_tests <skill-path>
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

from scripts.skill_ir import Skill


def generate_tests(skill: Skill) -> dict:
    """
    Generate test scenarios from the Skill IR.

    Returns a dict with 6 category keys, each containing a list of test cases.
    Each test case has: scenario, prompt, should_trigger, notes.
    """
    name = skill.name or "this skill"
    desc_first_sentence = (skill.description.split(".")[0] + ".") if skill.description else ""

    scenarios: dict[str, list[dict]] = {
        "happy_path": _happy_path(name, desc_first_sentence, skill),
        "edge_cases": _edge_cases(name, desc_first_sentence, skill),
        "malformed_input": _malformed_input(name, skill),
        "ambiguous_request": _ambiguous_request(name, desc_first_sentence, skill),
        "missing_files": _missing_files(name, skill),
        "unsupported_env": _unsupported_env(name, skill),
    }
    return scenarios


def _happy_path(name: str, desc: str, skill: Skill) -> list[dict]:
    return [
        {
            "scenario": "standard-trigger-explicit",
            "prompt": f"Help me {name.replace('-', ' ')} — {desc}",
            "should_trigger": True,
            "notes": "Explicit use of skill name in request",
        },
        {
            "scenario": "standard-trigger-implicit",
            "prompt": (
                f"I need to {desc.lower().replace('use when ', '').rstrip('.')} "
                f"for my project."
            ),
            "should_trigger": True,
            "notes": "Implicit intent without naming the skill",
        },
        {
            "scenario": "casual-phrasing",
            "prompt": (
                f"hey can you help me with {name.replace('-', ' ')}? "
                f"i've got some stuff i need done"
            ),
            "should_trigger": True,
            "notes": "Casual lowercase phrasing — tests description robustness",
        },
    ]


def _edge_cases(name: str, desc: str, skill: Skill) -> list[dict]:
    return [
        {
            "scenario": "empty-body",
            "prompt": "",
            "should_trigger": False,
            "notes": "Empty prompt should not trigger any skill",
        },
        {
            "scenario": "very-long-prompt",
            "prompt": (
                f"I want to {desc.lower().rstrip('.')} but there is a lot of context here. "
                + ("Here is some background: " + "lorem ipsum " * 50).strip()
            ),
            "should_trigger": True,
            "notes": "Long prompt with relevant intent buried in background noise",
        },
        {
            "scenario": "special-characters",
            "prompt": f"Help with {name}? #urgent @me $result [ASAP] <skill>",
            "should_trigger": True,
            "notes": "Special chars in the request — tests description regex tolerance",
        },
        {
            "scenario": "wrong-capitalization",
            "prompt": f"{name.upper()} — PLEASE DO THIS NOW",
            "should_trigger": True,
            "notes": "All-caps phrasing with skill name",
        },
    ]


def _malformed_input(name: str, skill: Skill) -> list[dict]:
    return [
        {
            "scenario": "missing-required-context",
            "prompt": f"Run {name.replace('-', ' ')}.",
            "should_trigger": True,
            "notes": (
                "Bare invocation with no context — skill should trigger but may "
                "need to ask for missing information"
            ),
        },
        {
            "scenario": "contradictory-request",
            "prompt": (
                f"Use {name.replace('-', ' ')} but also don't use it, "
                f"just do whatever you think is best."
            ),
            "should_trigger": True,
            "notes": "Contradictory instruction — skill triggers but must handle ambiguity",
        },
        {
            "scenario": "partial-information",
            "prompt": (
                f"I need {name.replace('-', ' ')} for... actually never mind, "
                f"just do what makes sense."
            ),
            "should_trigger": True,
            "notes": "Trailing off mid-request — tests graceful handling",
        },
    ]


def _ambiguous_request(name: str, desc: str, skill: Skill) -> list[dict]:
    # Find candidate adjacent concepts from the description
    words = set(desc.lower().split())
    adjacent_verbs = [w for w in ("create", "edit", "review", "test", "deploy", "analyze") if w not in words]
    alt_verb = adjacent_verbs[0] if adjacent_verbs else "process"

    return [
        {
            "scenario": "adjacent-skill-candidate",
            "prompt": (
                f"I want to {alt_verb} something related to "
                f"{name.replace('-', ' ')} — not sure if that's the right approach."
            ),
            "should_trigger": False,
            "notes": (
                f"User mentions '{name}' but asks for '{alt_verb}' — "
                "should route to a more specific skill if available"
            ),
        },
        {
            "scenario": "keyword-overlap-no-intent",
            "prompt": (
                f"What is {name.replace('-', ' ')}? I've heard about it but "
                "just want to learn, not actually do anything."
            ),
            "should_trigger": False,
            "notes": "Educational question about the skill concept — not an actionable request",
        },
        {
            "scenario": "indirect-mention",
            "prompt": (
                f"My colleague told me about {name.replace('-', ' ')} but "
                "I actually just need a simple answer to a quick question."
            ),
            "should_trigger": False,
            "notes": "Skill mentioned but user actually wants something simpler",
        },
    ]


def _missing_files(name: str, skill: Skill) -> list[dict]:
    return [
        {
            "scenario": "references-nonexistent-file",
            "prompt": (
                f"Use {name.replace('-', ' ')} on the file at "
                "/does/not/exist/input.txt"
            ),
            "should_trigger": True,
            "notes": (
                "Skill triggers but referenced file doesn't exist — "
                "skill must handle FileNotFoundError gracefully"
            ),
        },
        {
            "scenario": "empty-directory",
            "prompt": (
                f"Run {name.replace('-', ' ')} on the files in "
                "/tmp/empty-dir/ (it's empty)"
            ),
            "should_trigger": True,
            "notes": "Skill triggers on an empty directory — must not crash or produce empty output silently",
        },
    ]


def _unsupported_env(name: str, skill: Skill) -> list[dict]:
    return [
        {
            "scenario": "headless-no-browser",
            "prompt": (
                f"Use {name.replace('-', ' ')} in a headless environment "
                "with no browser access."
            ),
            "should_trigger": True,
            "notes": (
                "Cowork/headless scenario — skill should use --static fallback "
                "if it has a browser-based viewer"
            ),
        },
        {
            "scenario": "no-subagents",
            "prompt": (
                f"Do {name.replace('-', ' ')} but I'm on Claude.ai "
                "which has no subagents."
            ),
            "should_trigger": True,
            "notes": (
                "Claude.ai environment — skill must degrade gracefully if it "
                "relies on subprocess/subagent spawning"
            ),
        },
        {
            "scenario": "no-terminal-access",
            "prompt": (
                f"Can you {name.replace('-', ' ')} without running any shell commands? "
                "I'm in a sandboxed environment."
            ),
            "should_trigger": True,
            "notes": (
                "No terminal.execute access — skill must handle the absence of "
                "shell execution capability"
            ),
        },
    ]


def _write_scenarios(skill: Skill, scenarios: dict) -> Path:
    """Write all scenarios to tests/generated/<category>.yaml files."""
    out_dir = skill.skill_path / "tests" / "generated"
    out_dir.mkdir(parents=True, exist_ok=True)

    written: list[Path] = []
    for category, cases in scenarios.items():
        out_file = out_dir / f"{category}.yaml"
        out_file.write_text(
            yaml.dump(cases, default_flow_style=False, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
        written.append(out_file)

    return out_dir


def _neighbor_metadata(neighbor: Skill) -> tuple[str, str]:
    """Resolve Claude Code's omitted metadata defaults without relaxing skill IR."""
    frontmatter = neighbor.raw_frontmatter
    values = {}
    for field in ("name", "description", "when_to_use"):
        if field in frontmatter:
            value = frontmatter[field]
            if not isinstance(value, str):
                raise ValueError(
                    f"Adjacent skill {neighbor.skill_path}: {field} must be a string; "
                    "omit the field to use its default"
                )
            values[field] = value.strip()
    name = values.get("name", neighbor.skill_path.name)
    description = values.get("description", next(
        (line.strip() for line in neighbor.body.splitlines() if line.strip()), ""
    ))
    # Defaults apply to omitted fields, not explicitly empty metadata.
    if not name or not description:
        raise ValueError(
            f"Adjacent skill requires a name and description: {neighbor.skill_path}; "
            "provide nonempty text or omit the field to use the directory/body default"
        )
    when_to_use = values.get("when_to_use", "")
    if when_to_use:
        description = f"{description} {when_to_use}"
    return name, description


def generate_near_miss_candidates(skill: Skill, adjacent_skills: Path) -> list[dict]:
    """Propose offline negatives from immediate neighboring skills, for review only."""
    adjacent_skills = Path(adjacent_skills)
    if not adjacent_skills.is_dir():
        raise ValueError(f"Adjacent skills directory does not exist: {adjacent_skills}")
    candidates = []
    seen = set()
    for directory in sorted(adjacent_skills.iterdir()):
        if not directory.is_dir() or not (directory / "SKILL.md").is_file():
            continue
        if directory.resolve() == skill.skill_path.resolve():
            continue
        neighbor = Skill.from_path(directory)
        neighbor_name, neighbor_description = _neighbor_metadata(neighbor)
        prompt = (
            f"I am working in the area of {skill.name.replace('-', ' ')}, "
            f"but my request is: {neighbor_description} "
            f"Please help me with {neighbor_name.replace('-', ' ')}."
        )
        if prompt in seen:
            continue
        seen.add(prompt)
        candidates.append({
            "scenario": f"near-miss-{neighbor_name}",
            "prompt": prompt,
            "proposed_should_trigger": False,
            "reviewed": False,
            "adjacent_skill": neighbor_name,
            "notes": "Proposed adjacent-domain negative; review scope and add a boolean should_trigger before promotion.",
        })
    if not candidates:
        raise ValueError("No eligible adjacent skills found")
    return candidates


def _write_near_miss_file(skill: Skill, relative: str, cases: list[dict], *, replace: bool) -> Path:
    destination = skill.skill_path / relative
    if not destination.resolve().is_relative_to(skill.skill_path.resolve()):
        raise ValueError(f"Output path escapes skill directory: {destination}")
    if destination.exists() and not replace:
        raise ValueError(f"Output already exists; use --replace: {destination}")
    payload = yaml.safe_dump(cases, allow_unicode=True, sort_keys=False)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w" if replace else "x", encoding="utf-8") as stream:
        stream.write(payload)
    return destination


def write_near_miss_candidates(skill: Skill, adjacent_skills: Path, *, replace: bool = False) -> Path:
    """Write proposals outside the automatically measured trigger suite."""
    cases = generate_near_miss_candidates(skill, adjacent_skills)
    return _write_near_miss_file(skill, "tests/candidates/near_misses.yaml", cases, replace=replace)


def promote_near_miss_candidates(skill: Skill, reviewed_yaml: Path, *, replace: bool = False) -> Path:
    """Validate reviewed labels and suite consistency before writing accepted cases."""
    from scripts.tests_loader import TestCaseError, load_yaml_cases, normalize_cases

    data = yaml.safe_load(Path(reviewed_yaml).read_text(encoding="utf-8"))
    if not isinstance(data, list) or not data:
        raise TestCaseError("Reviewed candidates must be a nonempty list")
    for index, case in enumerate(data):
        if not isinstance(case, dict) or case.get("reviewed") is not True:
            raise TestCaseError(f"Candidate {index} requires reviewed: true")
        if not isinstance(case.get("should_trigger"), bool):
            raise TestCaseError(f"Candidate {index} requires a boolean should_trigger")
    accepted = normalize_cases(data, source=str(reviewed_yaml))
    tests_dir = skill.skill_path / "tests"
    destination = tests_dir / "generated" / "near_misses.yaml"
    suite = load_yaml_cases(tests_dir / "should_trigger.yaml") + load_yaml_cases(tests_dir / "should_not_trigger.yaml")
    for existing in sorted((tests_dir / "generated").glob("*.yaml")):
        if existing != destination or not replace:
            suite += load_yaml_cases(existing)
    suite = normalize_cases(suite, source=str(tests_dir))
    normalize_cases(suite + accepted, source="promotion against existing suite")
    existing_queries = {case["query"].strip() for case in suite}
    accepted = [case for case in accepted if case["query"].strip() not in existing_queries]
    return _write_near_miss_file(skill, "tests/generated/near_misses.yaml", accepted, replace=replace)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("skill_path", type=Path)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--adjacent-skills", type=Path)
    modes.add_argument("--promote-candidates", type=Path)
    parser.add_argument("--replace", action="store_true", help="Replace the selected near-miss output file")
    args = parser.parse_args()
    if args.replace and not (args.adjacent_skills or args.promote_candidates):
        parser.error("--replace requires a near-miss mode")
    try:
        skill = Skill.from_path(args.skill_path)
        if args.adjacent_skills:
            output = write_near_miss_candidates(skill, args.adjacent_skills, replace=args.replace)
        elif args.promote_candidates:
            output = promote_near_miss_candidates(skill, args.promote_candidates, replace=args.replace)
        else:
            scenarios = generate_tests(skill)
            output = _write_scenarios(skill, scenarios)
            total = sum(len(v) for v in scenarios.values())
            print(f"Generated {total} test scenarios across {len(scenarios)} categories.")
            for category, cases in scenarios.items():
                print(f"  {category}: {len(cases)} scenario(s)")
        print(f"Written to: {output}")
    except (OSError, ValueError, TypeError, OverflowError, RuntimeError, yaml.YAMLError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(_main())
