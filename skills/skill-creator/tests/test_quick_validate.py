"""Structural validation of generated trigger-test locations."""
from __future__ import annotations

from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.quick_validate import validate_skill


@pytest.fixture
def skill_dir(tmp_path):
    (tmp_path / "SKILL.md").write_text(
        "---\nname: test-skill\ndescription: "
        "Check the structural validation of generated skill trigger tests.\n---\nBody.\n",
        encoding="utf-8",
    )
    (tmp_path / "tests").mkdir()
    return tmp_path


def _write_case(skill_dir, filename):
    path = skill_dir / "tests" / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("- query: write a skill\n  should_trigger: true\n", encoding="utf-8")


@pytest.mark.parametrize("top_level", [False, True], ids=["generated-only", "mixed"])
def test_validator_accepts_generated_yaml_tests(skill_dir, top_level):
    _write_case(skill_dir, "generated/happy_path.yaml")
    if top_level:
        _write_case(skill_dir, "should_trigger.yaml")
    valid, message = validate_skill(skill_dir)
    assert valid, message


@pytest.mark.parametrize("layout", ["absent", "empty", "file", "yml", "nested", "top-level"])
def test_validator_rejects_test_directory_without_discoverable_yaml(skill_dir, layout):
    generated = skill_dir / "tests/generated"
    if layout == "empty":
        generated.mkdir()
    elif layout == "file":
        generated.write_text("not a directory", encoding="utf-8")
    elif layout == "yml":
        _write_case(skill_dir, "generated/ignored.yml")
    elif layout == "nested":
        _write_case(skill_dir, "generated/nested/ignored.yaml")
    elif layout == "top-level":
        _write_case(skill_dir, "unrecognized.yaml")

    valid, message = validate_skill(skill_dir)
    assert not valid
    assert "tests/ directory" in message
    assert "generated/" in message


@pytest.mark.parametrize("filename", [
    "should_trigger.yaml", "should_not_trigger.yaml", "expected_behavior.yaml",
])
def test_validator_still_accepts_known_tests_with_empty_generated_directory(skill_dir, filename):
    (skill_dir / "tests/generated").mkdir()
    _write_case(skill_dir, filename)
    valid, message = validate_skill(skill_dir)
    assert valid, message


@pytest.mark.parametrize("content,diagnostic", [
    ("[]", "must be a non-empty YAML list"),
    ("[", "Invalid YAML"),
])
def test_generated_tests_do_not_hide_invalid_top_level_tests(skill_dir, content, diagnostic):
    _write_case(skill_dir, "generated/happy_path.yaml")
    (skill_dir / "tests/should_trigger.yaml").write_text(content, encoding="utf-8")
    valid, message = validate_skill(skill_dir)
    assert not valid
    assert "tests/should_trigger.yaml" in message
    assert diagnostic in message
