"""Dependency and eval references must resolve inside the owning skill."""
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
        "---\nname: my-skill\ndescription: "
        "Validate contained file references when checking a skill directory.\n---\nBody.\n",
        encoding="utf-8",
    )
    (root / "references").mkdir()
    (root / "references/guide.md").write_text("Local guide.", encoding="utf-8")
    return root


def _symlink(path, target):
    try:
        path.symlink_to(target, target_is_directory=target.is_dir())
    except OSError as exc:
        pytest.skip(f"OS does not permit test symlink creation: {exc}")


def _write_dependencies(skill_dir, dependencies):
    (skill_dir / "skill.yaml").write_text(
        yaml.safe_dump({"name": "my-skill", "dependencies": dependencies}), encoding="utf-8"
    )


def _eval_findings(skill_dir, references):
    evals = skill_dir / "evals"
    evals.mkdir(exist_ok=True)
    (evals / "evals.json").write_text(
        json.dumps({"evals": [{"files": references}]}), encoding="utf-8"
    )
    return _check_eval_files(Skill.from_path(skill_dir))


@pytest.fixture(params=[
    "parent", "absolute", "prefix-sibling", "missing-parent",
    "file-symlink", "directory-symlink", "broken-symlink",
])
def escaping_reference(request, skill_dir):
    # The sibling deliberately shares the skill's prefix to catch string-prefix guards.
    outside = skill_dir.parent / "my-skill-extra"
    outside.mkdir()
    external_file = outside / "guide.md"
    external_file.write_text("External guide.", encoding="utf-8")
    kind = request.param
    if kind == "parent":
        return "../my-skill-extra/guide.md"
    if kind == "absolute":
        return str(external_file)
    if kind == "prefix-sibling":
        return str(outside)
    if kind == "missing-parent":
        return "../my-skill-extra/missing.md"
    if kind == "directory-symlink":
        _symlink(skill_dir / "linked", outside)
        return "linked/guide.md"
    target = outside / "missing.md" if kind == "broken-symlink" else external_file
    _symlink(skill_dir / "linked.md", target)
    return "linked.md"


def test_validator_rejects_escaping_dependency(skill_dir, escaping_reference):
    _write_dependencies(skill_dir, ["references/guide.md", escaping_reference])
    valid, message = validate_skill(skill_dir)
    assert not valid
    assert "dependencies" in message
    assert "escape the skill directory" in message
    assert repr(escaping_reference) in message


def test_skill_ir_rejects_escaping_dependency(skill_dir, escaping_reference):
    _write_dependencies(skill_dir, ["references/guide.md", escaping_reference])
    with pytest.raises(ValueError, match="escapes the skill directory") as exc:
        Skill.from_path(skill_dir)
    assert escaping_reference in str(exc.value)


def test_lint_reports_one_escape_warning_per_reference(skill_dir, escaping_reference):
    findings = _eval_findings(skill_dir, [escaping_reference, "references/guide.md"])
    assert len(findings) == 1
    finding = findings[0]
    assert finding.severity == "warning"
    assert finding.rule == "eval-file-missing"
    assert escaping_reference in finding.message
    assert "escapes the skill directory" in finding.message


@pytest.mark.parametrize("kind", ["relative", "normalized", "absolute", "symlink"])
@pytest.mark.parametrize("relative_root", [False, True], ids=["absolute-root", "relative-root"])
def test_contained_references_are_accepted(skill_dir, monkeypatch, kind, relative_root):
    reference = "references/guide.md"
    if kind == "normalized":
        reference = "references/../references/guide.md"
    elif kind == "absolute":
        reference = str(skill_dir / reference)
    elif kind == "symlink":
        _symlink(skill_dir / "linked.md", skill_dir / reference)
        reference = "linked.md"
    _write_dependencies(skill_dir, [reference])
    if relative_root:
        monkeypatch.chdir(skill_dir.parent)
        skill_dir = Path(skill_dir.name)

    valid, message = validate_skill(skill_dir)
    assert valid, message
    assert Skill.from_path(skill_dir).dependencies == [reference]
    assert _eval_findings(skill_dir, [reference]) == []


def test_missing_contained_dependency_is_rejected_by_validator_but_loads_in_ir(skill_dir):
    reference = "references/missing.md"
    _write_dependencies(skill_dir, [reference])
    valid, message = validate_skill(skill_dir)
    assert not valid
    assert reference in message
    assert "missing" in message
    # The IR containment check does not require the dependency to exist yet.
    assert Skill.from_path(skill_dir).dependencies == [reference]


def test_lint_continues_after_escape_and_distinguishes_missing_local_file(skill_dir):
    findings = _eval_findings(
        skill_dir, ["../missing.md", "references/missing.md", "references/guide.md"]
    )
    assert len(findings) == 2
    assert all(f.rule == "eval-file-missing" and f.severity == "warning" for f in findings)
    assert "../missing.md" in findings[0].message
    assert "escapes the skill directory" in findings[0].message
    assert "references/missing.md" in findings[1].message
    assert "does not exist relative to skill root" in findings[1].message


def test_skill_ir_checks_trimmed_dependency_for_escape(skill_dir):
    _write_dependencies(skill_dir, ["  ../outside.md  "])
    with pytest.raises(ValueError, match="escapes the skill directory"):
        Skill.from_path(skill_dir)


@pytest.mark.parametrize("operation", ["resolve", "exists"])
def test_dependency_filesystem_error_fails_closed(skill_dir, monkeypatch, operation):
    def inaccessible(*args, **kwargs):
        raise OSError("Synthetic inaccessible filesystem")

    monkeypatch.setattr(Path, operation, inaccessible)
    assert _dep_safe(skill_dir, "references/guide.md") is False
