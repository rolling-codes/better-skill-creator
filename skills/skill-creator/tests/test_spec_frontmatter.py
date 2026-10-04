"""Frontmatter stays inside the Agent Skills spec, and allowed-tools uses real names."""
from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

# CI runs pytest from the repo root; make the skill's packages importable.
_sys.path.insert(0, str(_Path(__file__).resolve().parent.parent))

import os
import shutil
import stat
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
    ok, msg = validate_skill(d)
    assert not ok and "Unexpected key(s)" in msg and "model" in msg
    assert validate_skill(d, claude_code=True)[0]


def test_atomic_write_failure_preserves_original(tmp_path, monkeypatch):
    d = _skill(tmp_path, "name: probe-skill\ndescription: Probes things.")
    original = (d / "SKILL.md").read_bytes()

    def raiser(*_args, **_kwargs):
        raise OSError("replace failed")

    monkeypatch.setattr("scripts.skill_ir.os.replace", raiser)
    with pytest.raises(OSError):
        Skill.from_path(d).write_skill_md()

    assert (d / "SKILL.md").read_bytes() == original
    assert list(d.iterdir()) == [d / "SKILL.md"]


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


def test_shipped_skills_have_valid_frontmatter():
    for d in (SKILL_ROOT, SKILL_ROOT.parents[1] / "examples" / "release-notes"):
        ok, msg = validate_skill(d, claude_code=(d == SKILL_ROOT))
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


@pytest.mark.parametrize("model", ["42", "true", "null", "[]", "{}"])
def test_claude_code_model_must_be_a_string(tmp_path, model):
    d = _skill(tmp_path, f"name: probe-skill\ndescription: Probes things.\nmodel: {model}")
    ok, msg = validate_skill(d, claude_code=True)
    assert not ok and "model must be a string" in msg
    assert not validate_skill(d)[0]


def test_claude_code_mode_does_not_allow_other_extensions(tmp_path):
    d = _skill(tmp_path, "name: probe-skill\ndescription: Probes things.\nunknown: value")
    ok, msg = validate_skill(d, claude_code=True)
    assert not ok and "unknown" in msg


def test_packaging_rejects_claude_code_model(tmp_path):
    from scripts.package_skill import package_skill

    d = _skill(tmp_path, "name: probe-skill\ndescription: Probes things.\nmodel: sonnet")
    output = tmp_path / "dist"
    assert package_skill(d, output) is None
    assert not output.exists()


def test_claude_code_validation_cli_is_explicit(tmp_path):
    d = _skill(tmp_path, "name: probe-skill\ndescription: Probes things.\nmodel: sonnet")
    command = [sys.executable, "-m", "scripts.quick_validate", str(d)]
    strict = subprocess.run(command, cwd=SKILL_ROOT, capture_output=True, text=True)
    assert strict.returncode == 1 and "model" in strict.stdout
    extended = subprocess.run(command + ["--claude-code"], cwd=SKILL_ROOT,
                              capture_output=True, text=True)
    assert extended.returncode == 0, extended.stdout


def test_rewrite_ignores_preexisting_temp_path(tmp_path):
    d = _skill(tmp_path, "name: probe-skill\ndescription: Probes things.")
    existing = d / "SKILL.md.tmp"
    existing.write_text("unrelated data", encoding="utf-8")
    skill = Skill.from_path(d)
    skill.body = "Updated body."
    skill.write_skill_md()
    assert Skill.from_path(d).body == "Updated body."
    assert existing.read_text(encoding="utf-8") == "unrelated data"
    assert not list(d.glob(".SKILL.md.*.tmp"))


@pytest.mark.skipif(os.name != "posix", reason="POSIX permission bits")
@pytest.mark.parametrize("mode", [0o600, 0o640, 0o444])
def test_rewrite_preserves_permissions(tmp_path, mode):
    d = _skill(tmp_path, "name: probe-skill\ndescription: Probes things.")
    target = d / "SKILL.md"
    target.chmod(mode)
    Skill.from_path(d).write_skill_md()
    assert stat.S_IMODE(target.stat().st_mode) == mode


@pytest.mark.skipif(not sys.platform.startswith("linux") or not shutil.which("setfacl"),
                    reason="Linux ACL support and setfacl required")
def test_rewrite_preserves_access_acl(tmp_path):
    d = _skill(tmp_path, "name: probe-skill\ndescription: Probes things.")
    target = d / "SKILL.md"
    subprocess.run(["setfacl", "-m", "u:12345:r--", str(target)], check=True)
    original = os.getxattr(target, "system.posix_acl_access")
    Skill.from_path(d).write_skill_md()
    assert os.getxattr(target, "system.posix_acl_access") == original


def test_permission_copy_failure_preserves_original(tmp_path, monkeypatch):
    d = _skill(tmp_path, "name: probe-skill\ndescription: Probes things.")
    target = d / "SKILL.md"
    original = target.read_bytes()

    def fail(*args, **kwargs):
        raise PermissionError("cannot preserve permissions")

    monkeypatch.setattr("scripts.skill_ir.shutil.copystat", fail)
    with pytest.raises(PermissionError):
        Skill.from_path(d).write_skill_md()
    assert target.read_bytes() == original
    assert list(d.iterdir()) == [target]


@pytest.mark.skipif(not sys.platform.startswith("linux") or not shutil.which("setfacl"),
                    reason="Linux ACL support and setfacl required")
def test_rewrite_does_not_inherit_extra_access(tmp_path):
    d = _skill(tmp_path, "name: probe-skill\ndescription: Probes things.")
    target = d / "SKILL.md"
    assert "system.posix_acl_access" not in os.listxattr(target)
    # Only future files inherit this ACL; the original SKILL.md has none.
    subprocess.run(["setfacl", "-m", "d:u:12345:r--", str(d)], check=True)
    Skill.from_path(d).write_skill_md()
    assert "system.posix_acl_access" not in os.listxattr(target)


@pytest.mark.skipif(not sys.platform.startswith("linux") or not shutil.which("setfacl"),
                    reason="Linux ACL support and setfacl required")
def test_acl_copy_failure_preserves_original(tmp_path, monkeypatch):
    d = _skill(tmp_path, "name: probe-skill\ndescription: Probes things.")
    target = d / "SKILL.md"
    subprocess.run(["setfacl", "-m", "u:12345:r--", str(target)], check=True)
    original = target.read_bytes()
    original_acl = os.getxattr(target, "system.posix_acl_access")

    def fail(*args, **kwargs):
        raise PermissionError("cannot preserve ACL")

    monkeypatch.setattr("scripts.skill_ir.os.setxattr", fail)
    with pytest.raises(PermissionError):
        Skill.from_path(d).write_skill_md()
    assert target.read_bytes() == original
    assert os.getxattr(target, "system.posix_acl_access") == original_acl
    assert list(d.iterdir()) == [target]
