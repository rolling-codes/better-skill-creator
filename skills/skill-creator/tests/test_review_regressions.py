"""Regressions for the v3.4.1 review: validation, runner, and the example skill."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from posix_shell import bash_executable

SKILL = Path(__file__).resolve().parent.parent
BASH = bash_executable()
ROOT = SKILL.parent.parent
sys.path.insert(0, str(SKILL))

from scripts.lint import _check_description_boundary, lint
from scripts.quick_validate import validate_skill
from scripts.skill_ir import Skill
from scripts.validate import validate


def write_skill(path: Path, name: str, description: str, body: str = "Body text.\n") -> None:
    path.mkdir(parents=True, exist_ok=True)
    escaped = description.replace("\\", "\\\\").replace('"', '\\"')
    (path / "SKILL.md").write_text(
        f'---\nname: {name}\ndescription: "{escaped}"\n---\n# {name}\n\n{body}',
        encoding="utf-8",
    )


def test_blank_name_and_description_are_rejected(tmp_path):
    cases = [
        ('name: ""\ndescription: "present"\n', "name must be non-empty"),
        ('name: "   "\ndescription: "present"\n', "name must be non-empty"),
        ('name: blank-desc\ndescription: ""\n', "description must be non-empty"),
        ('name: "   "\ndescription: "   "\n', "name must be non-empty"),
        ('name: blank-desc\ndescription: "   "\n', "description must be non-empty"),
    ]
    for index, (frontmatter, expected) in enumerate(cases):
        skill = tmp_path / f"blank-{index}"
        skill.mkdir()
        (skill / "SKILL.md").write_text(
            f"---\n{frontmatter}---\n# Blank\n\nBody.\n", encoding="utf-8",
        )
        valid, message = validate_skill(skill)
        assert valid is False
        assert expected in message


def test_directory_name_mismatch_is_a_warning(tmp_path):
    skill = tmp_path / "wsname"
    write_skill(skill, "wrongname", "A description that is present.")
    valid, message = validate_skill(skill)
    assert valid is True
    assert message.startswith("Skill is valid! Warning:")
    assert "wrongname" in message
    assert "wsname" in message
    findings = validate(skill)
    mismatch = [f for f in findings if f.rule == "name-directory-mismatch"]
    assert len(mismatch) == 1
    assert mismatch[0].severity == "warning"


def test_matching_directory_name_stays_exactly_valid(tmp_path):
    skill = tmp_path / "exact-name"
    write_skill(skill, "exact-name", "A description that is present.")
    assert validate_skill(skill) == (True, "Skill is valid!")


def test_quick_validate_cli_exits_2_on_name_mismatch(tmp_path):
    skill = tmp_path / "wsname"
    write_skill(skill, "wrongname", "A description that is present.")
    result = subprocess.run(
        [sys.executable, "-m", "scripts.quick_validate", str(skill)],
        cwd=SKILL, capture_output=True, text=True,
    )
    assert result.returncode == 2, result.stdout + result.stderr
    assert "does not match directory name" in result.stdout


def test_utf8_bom_skill_md_loads(tmp_path):
    skill = tmp_path / "bom-skill"
    skill.mkdir()
    text = "---\nname: bom-skill\ndescription: Saved by a Windows editor.\n---\n# Title\n\nBody.\n"
    (skill / "SKILL.md").write_bytes(b"\xef\xbb\xbf" + text.encode("utf-8"))
    valid, message = validate_skill(skill)
    assert valid, message
    loaded = Skill.from_path(skill)
    assert loaded.name == "bom-skill"
    assert "Title" in loaded.body
    lint(loaded)


def test_non_string_dependency_is_rejected_without_traceback(tmp_path):
    skill = tmp_path / "dep-skill"
    write_skill(skill, "dep-skill", "A description that is present.")
    (skill / "skill.yaml").write_text(
        "name: dep-skill\ndependencies:\n- {a: 1}\n", encoding="utf-8",
    )
    valid, message = validate_skill(skill)
    assert valid is False
    assert message == "skill.yaml dependencies must be strings"


@pytest.mark.parametrize("description,flagged", [
    ("Formats notes and cannot fail to draft another note.", True),
    ("Drafts notes. Use when asked. Not for publishing.", False),
    ("Drafts notes. Use when asked. This does not publish.", False),
    ("Drafts notes. Use when asked, except for tagging.", False),
    ("Drafts notes. Use when asked, with the exception of tagging.", False),
    ("Drafts notes. Use when asked, excluding publishing.", False),
    ("Drafts notes. Use when asked and when not to use it is publishing.", False),
    ("Drafts notes. Do not publish the result.", False),
])
def test_boundary_check_ignores_not_inside_words(tmp_path, description, flagged):
    skill = tmp_path / "bound-skill"
    write_skill(skill, "bound-skill", description)
    findings = _check_description_boundary(Skill.from_path(skill))
    assert bool(findings) is flagged
    if flagged:
        assert findings[0].rule == "description-no-boundary"


def test_lint_allows_agents_and_references_to_be_files(tmp_path):
    skill = tmp_path / "file-skill"
    write_skill(
        skill, "file-skill",
        "Drafts notes for a user. Use when the user asks for notes. Not for publishing them.",
    )
    (skill / "agents").write_text("not a directory", encoding="utf-8")
    (skill / "references").write_text("not a directory", encoding="utf-8")
    findings = lint(Skill.from_path(skill))
    assert not any(f.rule == "missing-reference-section" for f in findings)


def test_scripts_cwd_does_not_shadow_stdlib_types():
    result = subprocess.run(
        [sys.executable, "-c", "from types import GenericAlias; print(GenericAlias.__name__)"],
        cwd=SKILL / "scripts", capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "GenericAlias"


def test_skill_test_by_path_imports_stdlib_types():
    result = subprocess.run(
        [sys.executable, str(SKILL / "scripts" / "skill_test.py")],
        capture_output=True, text=True,
    )
    combined = result.stdout + result.stderr
    assert "GenericAlias" not in combined
    assert "No module named" not in combined
    assert result.returncode == 2


def test_validate_all_sh_is_executable_and_checks_other_skills():
    script = SKILL / "scripts" / "validate_all.sh"
    listed = subprocess.check_output(
        ["git", "ls-files", "-s", "--", "skills/skill-creator/scripts/validate_all.sh"],
        cwd=ROOT, text=True,
    )
    assert listed.startswith("100755"), listed
    env = os.environ.copy()
    env["PATH"] = os.pathsep.join(
        entry for entry in env.get("PATH", "").split(os.pathsep)
        if entry and not (Path(entry) / "claude").exists()
    )
    result = subprocess.run(
        [BASH, str(script), str(ROOT / "examples" / "release-notes")],
        cwd=ROOT, capture_output=True, text=True, env=env,
    )
    output = result.stdout + result.stderr
    assert "No module named" not in output
    assert "Skill is valid" in result.stdout
    assert result.returncode == 0, output


def test_release_notes_example_grants_read_only_git_inspection():
    text = (ROOT / "examples" / "release-notes" / "SKILL.md").read_text(encoding="utf-8")
    tools = text.split("allowed-tools:", 1)[1].split("---", 1)[0]
    for tool in ("Bash(git describe *)", "Bash(git log *)", "Bash(git diff *)", "Bash(git show *)"):
        assert tool in tools
    for denied in ("git commit", "git push", "git tag", "git rebase"):
        assert denied not in tools


def test_ci_validates_release_notes_and_can_run_the_release_canary():
    text = (ROOT / ".github" / "workflows" / "test.yml").read_text(encoding="utf-8")
    assert '"release/**"' in text or "release/**" in text
    assert "skills/skill-creator/scripts/validate_all.sh examples/release-notes" in text
    assert "python bsc.py check examples/release-notes" in text
    canary = text.split("trigger-canary:", 1)[1]
    job_header, steps = canary.split("steps:", 1)
    job_if = next(line.strip() for line in job_header.splitlines() if line.strip().startswith("if:"))
    assert "secrets" not in job_if
    assert "HAS_OAUTH_TOKEN: ${{ secrets.CLAUDE_CODE_OAUTH_TOKEN != '' }}" in job_header
    assert "env.HAS_OAUTH_TOKEN == 'true'" in steps
    assert "startsWith(github.ref, 'refs/heads/release/')" in text
