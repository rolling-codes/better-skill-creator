"""Offline acceptance checks for the README's navigation and quick-start examples.

Parse documented commands without executing installs or live model evaluations.
"""
import importlib.util
import json
from pathlib import Path
import re
import shlex
from urllib.parse import urlsplit

import pytest

ROOT = Path(__file__).resolve().parents[3]
README = (ROOT / "README.md").read_text(encoding="utf-8")
spec = importlib.util.spec_from_file_location("bsc", ROOT / "bsc.py")
assert spec and spec.loader
bsc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bsc)


def _section(title):
    match = re.search(
        rf"^## {re.escape(title)}\s*\n(.*?)(?=^## |\Z)",
        README,
        re.MULTILINE | re.DOTALL,
    )
    assert match is not None, f"README is missing the {title!r} section"
    return match.group(1)


def _code_blocks(section):
    return re.findall(r"^ *```[^\n]*\n(.*?)^ *``` *$", section, re.MULTILINE | re.DOTALL)


def test_readme_has_one_top_level_title():
    assert re.findall(r"^# (.+)$", README, re.MULTILINE) == ["Better Skill Creator"]


@pytest.mark.parametrize("section", ["Quick start", "Requirements"])
def test_onboarding_sections_have_no_unresolved_placeholders(section):
    assert not re.search(r"\bTODO\b", _section(section)), section


@pytest.mark.parametrize("command", ["check", "eval"])
def test_quick_start_python_examples_are_accepted_by_cli(command):
    examples = [shlex.split(block.strip()) for block in _code_blocks(_section("Quick start"))]
    matching = [args for args in examples if args[:3] == ["python", "bsc.py", command]]
    assert len(matching) == 1, f"Expected one runnable {command} example"

    args = bsc.build_parser().parse_args(matching[0][2:])

    assert args.command == command
    assert args.path == Path("skills/my-skill")
    if command == "eval":
        assert args.live, "The evaluation example must opt in to live evaluation"
    else:
        assert not args.strict, "The quick start should accept Claude Code skill extensions"


def test_python_badge_and_requirements_agree_with_supported_version():
    version = json.loads((ROOT / "pyrightconfig.json").read_text(encoding="utf-8"))["pythonVersion"]
    requirement = re.search(r"\bPython (\d+\.\d+)\+", _section("Requirements"))
    badge = re.search(
        r"\[!\[Python (\d+\.\d+)\+\]\(https://img\.shields\.io/badge/"
        r"Python-(\d+\.\d+)%2B-green\.svg\)\]\(#requirements\)",
        README,
    )

    assert requirement is not None, "Document the minimum Python version"
    assert requirement.group(1) == version
    assert badge is not None, "Link the Python version badge to Requirements"
    assert badge.groups() == (version, version)


def test_documented_yaml_install_matches_runtime_dependency():
    commands = re.findall(r"`([^`]+)`", _section("Requirements"))
    assert ["pip", "install", "pyyaml"] in [shlex.split(command) for command in commands]
    dependencies = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    assert re.search(r"^PyYAML\b", dependencies, re.MULTILINE | re.IGNORECASE)


# Include outer badge links as well as ordinary links; remote URLs are not fetched.
LOCAL_LINKS = sorted({
    target for target in re.findall(r"\]\(([^\s)]+)\)", README)
    if not urlsplit(target).scheme and not urlsplit(target).netloc
})


def test_readme_exposes_local_navigation():
    assert LOCAL_LINKS, "README should link to requirements and repository documentation"
    assert "#requirements" in LOCAL_LINKS
    assert "[CHANGELOG.md](CHANGELOG.md)" in _section("Release notes")
    assert re.search(r"\[LICENSE\]\([^)]+\)", _section("License"))


@pytest.mark.parametrize("target", LOCAL_LINKS)
def test_local_links_resolve(target):
    link = urlsplit(target)
    if link.path:
        assert (ROOT / link.path).is_file(), f"README links to a missing file: {target}"
    else:
        headings = re.findall(r"^#{1,6} (.+)$", README, re.MULTILINE)
        anchors = {re.sub(r"[^\w\- ]", "", heading.lower()).replace(" ", "-") for heading in headings}
        assert link.fragment in anchors, f"README links to a missing heading: {target}"


def test_repository_layout_lists_existing_files_and_directories():
    blocks = _code_blocks(_section("Repository layout"))
    assert len(blocks) == 1, "Keep the repository tree in one fenced block"
    paths = [line.split()[0] for line in blocks[0].splitlines() if line.strip()]
    assert len(paths) > 1, "Document the skill root and its contents"
    skill_root = ROOT / paths[0]
    assert skill_root.is_dir()
    for entry in paths[1:]:
        path = skill_root / entry
        assert path.is_dir() if entry.endswith("/") else path.is_file(), str(path)


def test_unfinished_model_example_is_not_visible_prose():
    section = _section("What makes it different")
    visible = re.sub(r"<!--.*?-->", "", section, flags=re.DOTALL)
    assert not re.search(r"\bTODO\b", visible), "Keep unfinished examples out of rendered prose"
