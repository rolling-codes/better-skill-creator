"""Structural validation accepts a skill with only generated trigger tests."""
from __future__ import annotations

from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.quick_validate import validate_skill


@pytest.fixture
def skill_dir(tmp_path):
    (tmp_path / "SKILL.md").write_text(
        "---\nname: my-skill\ndescription: A skill for testing generated test discovery.\n"
        "---\n# My skill\n",
        encoding="utf-8",
    )
    (tmp_path / "tests").mkdir()
    return tmp_path


def test_validate_accepts_only_generated_tests(skill_dir):
    generated = skill_dir / "tests/generated"
    generated.mkdir()
    (generated / "happy_path.yaml").write_text(
        "- query: create a skill\n  should_trigger: true\n", encoding="utf-8"
    )
    valid, message = validate_skill(skill_dir)
    assert valid, message


@pytest.mark.parametrize("layout", ["absent", "empty", "text-only", "yml-only", "nested", "file"])
def test_validate_requires_direct_generated_yaml_file(skill_dir, layout):
    generated = skill_dir / "tests/generated"
    if layout == "file":
        generated.write_text("not a directory", encoding="utf-8")
    elif layout != "absent":
        generated.mkdir()
        filename = {"text-only": "notes.txt", "yml-only": "cases.yml", "nested": "nested/cases.yaml"}.get(layout)
        if filename:
            path = generated / filename
            path.parent.mkdir(exist_ok=True)
            path.write_text("- query: ignored\n  should_trigger: true\n", encoding="utf-8")

    valid, message = validate_skill(skill_dir)
    assert not valid
    assert "tests/ directory" in message
    assert "generated/" in message


@pytest.mark.parametrize("filename", ["should_trigger.yaml", "should_not_trigger.yaml", "expected_behavior.yaml"])
def test_validate_still_accepts_known_test_files_with_empty_generated_dir(skill_dir, filename):
    (skill_dir / "tests/generated").mkdir()
    (skill_dir / "tests" / filename).write_text(
        "- prompt: manual\n  expected: true\n", encoding="utf-8"
    )
    valid, message = validate_skill(skill_dir)
    assert valid, message


@pytest.mark.parametrize("content", ["[]", "not a list", "[invalid yaml"])
def test_generated_tests_do_not_bypass_known_file_validation(skill_dir, content):
    generated = skill_dir / "tests/generated"
    generated.mkdir()
    (generated / "happy_path.yaml").write_text(
        "- query: create a skill\n  should_trigger: true\n", encoding="utf-8"
    )
    (skill_dir / "tests/should_trigger.yaml").write_text(content, encoding="utf-8")
    valid, message = validate_skill(skill_dir)
    assert not valid
    assert "tests/should_trigger.yaml" in message
