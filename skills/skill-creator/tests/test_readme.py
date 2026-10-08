"""Acceptance checks for the README's navigation and copyable quick start.

Read commands as data: parsing the examples must never install plugins or make
live model calls. These checks deliberately avoid assertions about prose style.
"""
import importlib.util
import json
from pathlib import Path
import re
import shlex
from urllib.parse import unquote, urlsplit

import pytest

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture
def readme():
    return (ROOT / "README.md").read_text(encoding="utf-8")


def _section(readme, heading):
    match = re.search(
        rf"^## {re.escape(heading)}\s*\n(.*?)(?=^## |\Z)",
        readme, re.MULTILINE | re.DOTALL,
    )
    assert match is not None, f"Missing README section: {heading}"
    return match.group(1)


def _code_blocks(section):
    return re.findall(r"^[ \t]*```[^\n]*\n(.*?)^[ \t]*```[ \t]*$",
                      section, re.MULTILINE | re.DOTALL)


def test_readme_has_navigable_sections(readme):
    assert re.findall(r"^# .+$", readme, re.MULTILINE) == ["# Better Skill Creator"]
    for heading in (
        "Quick start", "Requirements", "How it works", "What makes it different",
        "Relationship to Anthropic's skill creator", "When to use it",
        "Repository layout", "Contributing", "Release notes", "License",
    ):
        assert _section(readme, heading).strip(), f"Empty section: {heading}"


def test_readme_local_links_resolve(readme):
    # This also captures the outer destination of linked badge images.
    destinations = re.findall(r"\]\(([^\s)]+)\)", readme)
    local_links = [urlsplit(link) for link in destinations
                   if not urlsplit(link).scheme and not urlsplit(link).netloc]
    assert local_links, "README must expose local navigation links"
    assert "#requirements" in destinations
    for label in ("LICENSE", "CHANGELOG.md"):
        assert re.search(rf"\[{re.escape(label)}\]\([^)]+\)", readme), label
    for link in local_links:
        target = ROOT / unquote(link.path) if link.path else ROOT / "README.md"
        assert target.is_file(), f"Broken README link: {link.geturl()}"
        if link.fragment:
            headings = re.findall(r"^#{1,6}\s+(.+)$",
                                  target.read_text(encoding="utf-8"), re.MULTILINE)
            anchors = {re.sub(r"[^\w\- ]", "", heading.lower()).replace(" ", "-")
                       for heading in headings}
            assert unquote(link.fragment) in anchors, f"Broken anchor: {link.geturl()}"


@pytest.mark.parametrize("command", ["check", "eval"])
def test_quick_start_python_examples_match_cli(readme, command):
    spec = importlib.util.spec_from_file_location("bsc", ROOT / "bsc.py")
    assert spec and spec.loader
    bsc = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bsc)

    examples = [shlex.split(block) for block in _code_blocks(_section(readme, "Quick start"))]
    matches = [argv for argv in examples if argv[:3] == ["python", "bsc.py", command]]
    assert len(matches) == 1, f"Expected one copyable {command} example"
    args = bsc.build_parser().parse_args(matches[0][2:])
    assert args.command == command
    assert args.path == Path("skills/my-skill")
    if command == "eval":
        # Without --live the example only plans an evaluation instead of running it.
        assert args.live, "The evaluation example must explicitly opt in to model calls"


def test_quick_start_has_no_unfinished_instructions(readme):
    quick_start = _section(readme, "Quick start")
    requirements = _section(readme, "Requirements")
    assert not re.search(r"\bTODO\b", quick_start + requirements, re.IGNORECASE)
    assert len(_code_blocks(quick_start)) == 3, "Install, validate and evaluate need code blocks"


def test_requirements_agree_with_project_configuration(readme):
    requirements = _section(readme, "Requirements")
    python_version = json.loads((ROOT / "pyrightconfig.json").read_text(encoding="utf-8"))["pythonVersion"]
    assert f"Python {python_version}+" in requirements
    assert f"Python-{python_version}%2B" in readme, "Python badge must agree with requirements"
    dependencies = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    assert re.search(r"^PyYAML\b", dependencies, re.MULTILINE | re.IGNORECASE)
    assert "pip install pyyaml" in requirements
    assert "Claude Code" in requirements
    assert "authenticated" in requirements


def test_repository_layout_lists_existing_paths_in_a_code_block(readme):
    blocks = _code_blocks(_section(readme, "Repository layout"))
    assert len(blocks) == 1, "Repository tree must preserve indentation when rendered"
    lines = [line for line in blocks[0].splitlines() if line.strip()]
    skill_root = ROOT / lines[0].strip()
    assert skill_root.is_dir()
    entries = [line.split()[0] for line in lines[1:]]
    assert {"SKILL.md", "scripts/", "references/", "agents/"} <= set(entries)
    for entry in entries:
        target = skill_root / entry
        assert target.is_dir() if entry.endswith("/") else target.is_file(), entry


def test_model_example_todo_is_not_visible_to_readers(readme):
    section = _section(readme, "What makes it different")
    visible = re.sub(r"<!--.*?-->", "", section, flags=re.DOTALL)
    assert not re.search(r"\bTODO\b", visible, re.IGNORECASE)
