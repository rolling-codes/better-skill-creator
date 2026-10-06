"""Dependency and eval references must resolve within the owning skill."""
from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.lint import _check_eval_files
from scripts.quick_validate import _dep_safe, validate_skill
from scripts.skill_ir import Skill


@pytest.fixture
def skill_dir(tmp_path):
    root = tmp_path / "my-skill"
    root.mkdir()
    (root / "SKILL.md").write_text(
        "---\nname: my-skill\ndescription: A skill for testing dependency containment.\n"
        "---\n# My skill\n",
        encoding="utf-8",
    )
    return root


def _symlink(path, target):
    try:
        path.symlink_to(target, target_is_directory=target.is_dir())
    except OSError as exc:
        pytest.skip(f"OS does not permit test symlink creation: {exc}")


@pytest.fixture(params=[
    "relative", "normalized", "directory", "absolute-inside", "missing-inside",
    "parent", "absolute-outside", "prefix-sibling", "missing-outside",
    "symlink-inside", "symlink-outside", "symlink-directory", "symlink-broken-outside",
])
def reference(request, skill_dir, tmp_path):
    """Return a reference, its containment, and whether its target exists."""
    (skill_dir / "data").mkdir()
    (skill_dir / "data/input.txt").write_text("inside", encoding="utf-8")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "input.txt").write_text("outside", encoding="utf-8")
    sibling = tmp_path / "my-skill-other"
    sibling.mkdir()
    (sibling / "input.txt").write_text("sibling", encoding="utf-8")

    paths = {
        "relative": ("data/input.txt", True, True),
        "normalized": ("data/../data/input.txt", True, True),
        "directory": ("data", True, True),
        "absolute-inside": (str(skill_dir / "data/input.txt"), True, True),
        "missing-inside": ("data/missing.txt", True, False),
        "parent": ("../outside/input.txt", False, True),
        "absolute-outside": (str(outside / "input.txt"), False, True),
        "prefix-sibling": ("../my-skill-other/input.txt", False, True),
        "missing-outside": ("../outside/missing.txt", False, False),
    }
    if request.param in paths:
        return paths[request.param]

    if request.param == "symlink-inside":
        _symlink(skill_dir / "linked", skill_dir / "data/input.txt")
        return "linked", True, True
    if request.param == "symlink-directory":
        _symlink(skill_dir / "linked", outside)
        return "linked/input.txt", False, True
    exists = request.param == "symlink-outside"
    _symlink(skill_dir / "linked", outside / ("input.txt" if exists else "missing.txt"))
    return "linked", False, exists


def _write_dependencies(skill_dir, deps):
    (skill_dir / "skill.yaml").write_text(
        yaml.safe_dump({"name": "my-skill", "dependencies": deps}), encoding="utf-8"
    )


def _write_evals(skill_dir, entries):
    (skill_dir / "evals").mkdir()
    (skill_dir / "evals/evals.json").write_text(
        json.dumps({"evals": entries}), encoding="utf-8"
    )


def test_validate_dependency_containment(skill_dir, reference):
    path, contained, exists = reference
    _write_dependencies(skill_dir, ["SKILL.md", path])
    valid, message = validate_skill(skill_dir)
    assert valid is (contained and exists), message
    if not valid:
        assert "dependencies that are missing or escape" in message
        assert path in message


def test_skill_ir_dependency_containment(skill_dir, reference):
    path, contained, _ = reference
    _write_dependencies(skill_dir, ["SKILL.md", path])
    if contained:
        # Existence remains a validator concern; loading only enforces containment.
        assert Skill.from_path(skill_dir).dependencies == ["SKILL.md", path]
    else:
        with pytest.raises(ValueError, match="escapes the skill directory") as exc:
            Skill.from_path(skill_dir)
        assert path in str(exc.value)


def test_eval_file_containment(skill_dir, reference):
    path, contained, exists = reference
    _write_evals(skill_dir, [{"files": [path]}])
    findings = _check_eval_files(Skill.from_path(skill_dir))
    if contained and exists:
        assert findings == []
    else:
        assert len(findings) == 1
        finding = findings[0]
        assert finding.severity == "warning"
        assert finding.rule == "eval-file-missing"
        assert path in finding.message
        assert ("does not exist" if contained else "escapes the skill directory") in finding.message


def test_eval_file_escape_does_not_stop_checking_later_entries(skill_dir, tmp_path):
    (tmp_path / "outside.txt").write_text("outside", encoding="utf-8")
    _write_evals(skill_dir, [
        {"files": ["../outside.txt", "SKILL.md"]},
        {"files": ["missing.txt"]},
    ])
    findings = _check_eval_files(Skill.from_path(skill_dir))
    assert len(findings) == 2
    assert "'../outside.txt'" in findings[0].message
    assert "escapes" in findings[0].message
    assert "'missing.txt'" in findings[1].message
    assert "does not exist" in findings[1].message


@pytest.mark.parametrize("root_kind", ["relative", "symlink"])
def test_containment_uses_resolved_skill_root(skill_dir, tmp_path, monkeypatch, root_kind):
    _write_dependencies(skill_dir, ["SKILL.md"])
    _write_evals(skill_dir, [{"files": ["SKILL.md"]}])
    if root_kind == "relative":
        monkeypatch.chdir(tmp_path)
        root = Path(skill_dir.name)
    else:
        root = tmp_path / "skill-alias"
        _symlink(root, skill_dir)

    valid, message = validate_skill(root)
    assert valid, message
    skill = Skill.from_path(root)
    assert skill.skill_path == skill_dir.resolve()
    assert skill.dependencies == ["SKILL.md"]
    assert _check_eval_files(skill) == []


def test_dep_safe_rejects_resolution_oserror(skill_dir, monkeypatch):
    def fail_resolution(self, *args, **kwargs):
        raise OSError("Cannot resolve dependency")

    monkeypatch.setattr(Path, "resolve", fail_resolution)
    assert _dep_safe(skill_dir, "SKILL.md") is False
