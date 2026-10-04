"""Frontmatter stays inside the Agent Skills spec, and allowed-tools uses real names."""
from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

# CI runs pytest from the repo root; make the skill's packages importable.
_sys.path.insert(0, str(_Path(__file__).resolve().parent.parent))

import subprocess
import sys
import textwrap
from pathlib import Path

from scripts.lint import _check_invalid_tool_names
import yaml
import pytest

from scripts.quick_validate import _validate_frontmatter, validate_skill
from scripts.skill_ir import Skill, _read_allowed_tools

SKILL_ROOT = Path(__file__).resolve().parents[1]


def _skill(tmp_path: Path, frontmatter: str) -> Path:
    d = tmp_path / "probe-skill"
    d.mkdir()
    (d / "SKILL.md").write_text(
        f"---\n{textwrap.dedent(frontmatter).strip()}\n---\n\n# Probe\n\nBody text.\n",
        encoding="utf-8",
    )
    return d


def test_top_level_schema_version_is_rejected(tmp_path):
    d = _skill(tmp_path, "name: probe-skill\ndescription: Probes things.\nschemaVersion: 1")
    ok, msg = validate_skill(d)
    assert not ok and "metadata" in msg


def test_schema_version_under_metadata_is_read(tmp_path):
    d = _skill(tmp_path, "name: probe-skill\ndescription: Probes things.\nmetadata:\n  schemaVersion: 3")
    assert validate_skill(d)[0]
    assert Skill.from_path(d).schema_version == 3


def test_rewrite_moves_legacy_key_and_keeps_other_fields(tmp_path):
    d = _skill(tmp_path, """
        name: probe-skill
        description: Probes things.
        license: MIT
        schemaVersion: 1
        metadata:
          owner: tom
        """)
    skill = Skill.from_path(d)
    assert skill.legacy_schema_key
    skill.write_skill_md()
    again = Skill.from_path(d)
    assert not again.legacy_schema_key
    assert again.license == "MIT"
    assert again.metadata == {"owner": "tom", "schemaVersion": "1"}
    assert validate_skill(d)[0]


def test_model_survives_write_read_round_trip(tmp_path):
    d = _skill(tmp_path, "name: probe-skill\ndescription: Probes things.\nmodel: claude-opus-4-8")
    assert Skill.from_path(d).model == "claude-opus-4-8"
    Skill.from_path(d).write_skill_md()
    assert Skill.from_path(d).model == "claude-opus-4-8"
    assert validate_skill(d)[0]


def test_atomic_write_failure_preserves_original(tmp_path, monkeypatch):
    d = _skill(tmp_path, "name: probe-skill\ndescription: Probes things.")
    original = (d / "SKILL.md").read_bytes()

    def raiser(*_args, **_kwargs):
        raise OSError("replace failed")

    monkeypatch.setattr("scripts.skill_ir.os.replace", raiser)
    with pytest.raises(OSError):
        Skill.from_path(d).write_skill_md()

    assert (d / "SKILL.md").read_bytes() == original
    assert not (d / "SKILL.md.tmp").exists()


def test_allowed_tools_string_form_keeps_patterns_whole():
    assert _read_allowed_tools("Read Grep Bash(git add *), WebFetch") == [
        "Read", "Grep", "Bash(git add *)", "WebFetch"]


def test_lint_flags_non_tool_names(tmp_path):
    d = _skill(tmp_path, """
        name: probe-skill
        description: Probes things.
        allowed-tools:
          - filesystem.read
          - Read
          - Bash(git log *)
          - mcp__github__create_issue
        """)
    flagged = [f.message for f in _check_invalid_tool_names(Skill.from_path(d))]
    assert len(flagged) == 1 and "filesystem.read" in flagged[0]


def test_generated_skills_pass_validation(tmp_path):
    listing = subprocess.run([sys.executable, "-m", "generators", "--list"],
                             cwd=SKILL_ROOT, capture_output=True, text=True, check=True).stdout
    archetypes = [ln.strip() for ln in listing.splitlines() if ln.startswith("  ") and ln.strip()]
    assert archetypes
    for kind in archetypes:
        out = tmp_path / kind
        subprocess.run(
            [sys.executable, "-m", "generators", "--name", f"gen-{kind}",
             "--archetype", kind, "--output", str(out)],
            cwd=SKILL_ROOT, capture_output=True, text=True, check=True,
        )
        created = next(out.rglob("SKILL.md")).parent
        # Frontmatter only: some archetypes also write an empty tests/ dir,
        # which is a separate known issue tracked outside this test.
        text = (created / "SKILL.md").read_text(encoding="utf-8")
        fm = yaml.safe_load(text.split("---")[1])
        ok, msg = _validate_frontmatter(fm, fm.get("name", ""))
        assert ok, f"{kind}: {msg}"
        assert fm["metadata"]["schemaVersion"] == "1"
        assert not _check_invalid_tool_names(Skill.from_path(created)), kind


def test_shipped_skills_have_spec_frontmatter():
    for d in (SKILL_ROOT, SKILL_ROOT.parents[1] / "examples" / "release-notes"):
        ok, msg = validate_skill(d)
        assert ok, f"{d}: {msg}"
        assert not _check_invalid_tool_names(Skill.from_path(d))


@pytest.mark.parametrize("version", ['"oops"', 'null', '[]', '{}', '.inf', '.nan'])
def test_invalid_metadata_schema_version_is_rejected(tmp_path, version):
    d = _skill(tmp_path, f"name: probe-skill\ndescription: Probes things.\nmetadata:\n  schemaVersion: {version}")
    ok, msg = validate_skill(d)
    assert not ok and "metadata.schemaVersion" in msg
    with pytest.raises((TypeError, ValueError, OverflowError)):
        Skill.from_path(d)


@pytest.mark.parametrize("metadata", ['', 'metadata: {}', 'metadata: {schemaVersion: 3}', 'metadata: {schemaVersion: "3"}'])
def test_optional_schema_version_matches_reader(tmp_path, metadata):
    d = _skill(tmp_path, f"name: probe-skill\ndescription: Probes things.\n{metadata}")
    assert validate_skill(d)[0]
    assert Skill.from_path(d).schema_version == (3 if "schemaVersion" in metadata else 1)


def test_python_generator_command_runs_outside_skill(tmp_path):
    import shlex
    from generators.python_skill import PythonSkillGenerator

    skill = PythonSkillGenerator().scaffold("probe-skill", "Probes things.", tmp_path / "path with spaces")
    grant, = [tool for tool in skill.allowed_tools if tool.startswith("Bash(")]
    command = grant[len("Bash("):-1]
    assert command in skill.body
    args = shlex.split(command.replace("${CLAUDE_SKILL_DIR}", str(skill.skill_path)))
    assert args[0] == "python"
    completed = subprocess.run([sys.executable, *args[1:]], cwd=tmp_path,
                               capture_output=True, text=True, check=True)
    assert completed.stdout.strip() == "Hello from skill"


def test_research_generator_does_not_preapprove_fetch(tmp_path):
    from generators.research_skill import ResearchSkillGenerator

    skill = ResearchSkillGenerator().scaffold("probe-skill", "Probes things.", tmp_path)
    assert not any(tool.startswith("WebFetch") for tool in skill.allowed_tools)


def test_migration_command_preserves_schema_version(tmp_path):
    d = _skill(tmp_path, 'name: probe-skill\ndescription: Probes things.\nschemaVersion: 1')
    subprocess.run([sys.executable, "-m", "scripts.migrate_skill", str(d), "--to", "1"],
                   cwd=SKILL_ROOT, capture_output=True, text=True, check=True)
    assert validate_skill(d)[0]
    migrated = Skill.from_path(d)
    assert not migrated.legacy_schema_key
    assert migrated.metadata["schemaVersion"] == "1"
