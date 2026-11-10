"""Regressions for the remaining open analyzer, scaffold, and review-gate bugs."""
from __future__ import annotations

import subprocess
import sys
import textwrap
import zipfile
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
REPO = SKILL.parent.parent
sys.path.insert(0, str(SKILL))
sys.path.insert(0, str(REPO))

from generators import registry
from scripts.file_policy import source_manifest
from scripts.lint import lint
from scripts.package_skill import package_skill
from scripts.review import ReviewRecord
from scripts.review_gate import REVIEW_AGENTS, analyze as review_analyze
from scripts.semantic_analysis import semantic_analyze
from scripts.skill_ir import Skill
from scripts.static_analysis import analyze


def _skill(root: Path, description: str, body: str, tools: str = "") -> Path:
    root.mkdir(parents=True, exist_ok=True)
    tool_block = f"allowed-tools:\n{tools}\n" if tools else ""
    (root / "SKILL.md").write_text(
        f"---\nname: {root.name}\ndescription: {description}\n{tool_block}---\n{body}",
        encoding="utf-8",
    )
    return root


def _run_module(module: str, skill: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", module, str(skill)],
        cwd=SKILL,
        capture_output=True,
        text=True,
    )


def test_info_only_findings_exit_zero(tmp_path):
    """Issue 107: notes are not warnings. Exit 2 stays reserved for warnings."""
    description = (
        "Drafts a short note from a request. Use when the user asks for a note. "
        "Not for sending the note."
    )
    root = _skill(
        tmp_path / "probe",
        description,
        "\n# Probe\n\n## Steps\n\nWrite the note in plain language.\n",
        tools="  - Read\n",
    )
    static = _run_module("scripts.static_analysis", root)
    assert static.returncode == 0, static.stdout + static.stderr
    assert "info(s)" in static.stdout
    assert "unused-tool" in static.stdout

    validate = _run_module("scripts.validate", root)
    assert validate.returncode == 0, validate.stdout + validate.stderr

    repair = _run_module("scripts.repair", root)
    assert repair.returncode == 0, repair.stdout + repair.stderr
    assert "info finding(s)" in repair.stdout
    assert "warning(s) to review manually" not in repair.stdout

    semantic = _run_module("scripts.semantic_analysis", root)
    assert semantic.returncode == 0, semantic.stdout + semantic.stderr


def test_unedited_scaffolds_fail_check_until_placeholders_are_replaced(tmp_path):
    """Issue 106: a generator template is not a shippable skill."""
    import bsc
    import re

    for archetype in ("default", "python-skill", "research"):
        parent = tmp_path / archetype
        parent.mkdir()
        skill = registry.for_archetype(archetype).scaffold(
            name="demo",
            description="TODO: describe what demo does, when to trigger it, and what it does NOT cover.",
            output_path=parent,
        )
        findings = lint(Skill.from_path(skill.skill_path))
        assert any(f.rule == "placeholder-description" and f.severity == "error" for f in findings)
        empty = [f for f in semantic_analyze(Skill.from_path(skill.skill_path)) if f.rule == "empty-section"]
        assert empty, archetype
        runs = tmp_path / f"{archetype}-runs"
        assert bsc.main(["check", str(skill.skill_path), "--runs-dir", str(runs)]) == 2

        text = (skill.skill_path / "SKILL.md").read_text(encoding="utf-8")
        text = re.sub(
            r"TODO: describe what demo does,.*?cover\.?",
            "Drafts a demo note. Use when the user asks for a demo. Not for publishing it.",
            text,
            count=1,
            flags=re.DOTALL,
        )
        text = text.replace("<!--", "").replace("-->", "Filled in.")
        (skill.skill_path / "SKILL.md").write_text(text, encoding="utf-8")
        runs_ok = tmp_path / f"{archetype}-ok"
        assert bsc.main(["check", str(skill.skill_path), "--runs-dir", str(runs_ok)]) == 0


def test_orphan_check_does_not_treat_a_filename_tail_as_a_reference(tmp_path):
    """Issue 104: guide.md is not referenced just because style-guide.md is."""
    description = (
        "Drafts notes from a style guide. Use when the user asks for a styled note. "
        "Not for publishing the note."
    )
    body = textwrap.dedent("""
        # Probe

        ## Reference files

        - `references/style-guide.md` — read for tone.
        - `scripts/lint.py` — run the linter.
        - `scripts/test_common.py` — helper tests.
        """)
    root = _skill(tmp_path / "probe", description, body)
    (root / "references").mkdir()
    (root / "references" / "guide.md").write_text("orphan\n", encoding="utf-8")
    (root / "references" / "style-guide.md").write_text("style\n", encoding="utf-8")
    (root / "scripts").mkdir()
    (root / "scripts" / "lint.py").write_text("print('lint')\n", encoding="utf-8")
    (root / "scripts" / "lint_stage.py").write_text("print('stage')\n", encoding="utf-8")
    (root / "scripts" / "common.py").write_text("VALUE = 1\n", encoding="utf-8")
    (root / "scripts" / "test_common.py").write_text("import common\n", encoding="utf-8")
    # Mention the module form so a dotted prefix cannot hide lint_stage.
    text = (root / "SKILL.md").read_text(encoding="utf-8")
    text += "\nInvoke `scripts.lint` when checking the draft.\n"
    (root / "SKILL.md").write_text(text, encoding="utf-8")

    orphans = {f.message for f in analyze(Skill.from_path(root)) if f.rule == "orphaned-file"}
    assert any("references/guide.md" in message for message in orphans)
    assert any("scripts/lint_stage.py" in message for message in orphans)
    assert any("scripts/common.py" in message for message in orphans)
    assert not any("style-guide.md" in message for message in orphans)
    assert not any("scripts/lint.py" in message for message in orphans)
    assert not any("test_common.py" in message for message in orphans)


def _packaged_skill_text(archive: Path, skill_name: str) -> str:
    with zipfile.ZipFile(archive) as zf:
        return zf.read(f"{skill_name}/SKILL.md").decode("utf-8")


def test_packaging_keeps_headings_inside_code_fences(tmp_path):
    """Issue 103: an example heading is not a duplicate section to delete."""
    description = (
        "Drafts a summary in two lengths. Use when the user asks for a summary. "
        "Not for publishing the summary."
    )
    body = textwrap.dedent("""
        # Probe

        ## Output templates

        Short form:

        ```markdown
        ## Summary

        One line.
        ```

        Long form:

        ```markdown
        ## Summary

        Three paragraphs.
        ```
        """)
    root = _skill(tmp_path / "probe", description, body)
    archive = package_skill(root, tmp_path / "dist")
    assert archive is not None
    packaged = _packaged_skill_text(archive, "probe")
    assert packaged.count("## Summary") == 2


def test_duplicate_heading_repair_does_not_use_a_stale_line(tmp_path):
    """Issue 103: later repairs must not delete a different heading."""
    description = (
        "Explains setup and notes. Use when the user asks for setup notes. "
        "Not for changing the system."
    )
    body = textwrap.dedent("""
        # Probe

        ## Setup

        first

        ## Setup

        second

        ## Notes

        x

        ## Notes
        ### Keep me

        body
        """)
    root = _skill(tmp_path / "probe", description, body)
    archive = package_skill(root, tmp_path / "dist")
    assert archive is not None
    packaged = _packaged_skill_text(archive, "probe")
    assert packaged.count("## Setup") == 1
    assert packaged.count("## Notes") == 1
    assert "### Keep me" in packaged


def test_activation_skip_is_stale_after_a_source_edit(tmp_path):
    """Issue 102: a recorded skip covers one source state, not every later edit."""
    root = tmp_path / "probe"
    description = (
        "Drafts a note. Use when the user asks for a note. Not for sending it."
    )
    _skill(root, description, "\n# Probe\n\n## Steps\n\nWrite the note.\n")
    scripts = root / "scripts"
    scripts.mkdir()
    helper = scripts / "helper.py"
    helper.write_text("VALUE = 1\n", encoding="utf-8")
    for agent in REVIEW_AGENTS:
        path = root / agent
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("review instructions\n", encoding="utf-8")
    record = ReviewRecord(
        source_manifest=source_manifest(root),
        activation_required=False,
        activation_reason="Narrow docs edit recorded against this source.",
    )
    record.write(root)
    assert not [f for f in review_analyze(Skill.from_path(root)) if f.severity == "error"]

    helper.write_text("VALUE = 1\n# unreviewed edit\n", encoding="utf-8")
    rules = {f.rule for f in review_analyze(Skill.from_path(root)) if f.severity == "error"}
    assert "review-skip-stale" in rules


def test_activation_skip_does_not_require_review_agent_files(tmp_path):
    """A bound skip on a text-only skill passes without shipping the toolkit's agents/."""
    root = tmp_path / "probe"
    description = (
        "Drafts a note. Use when the user asks for a note. Not for sending it."
    )
    _skill(root, description, "\n# Probe\n\n## Steps\n\nWrite the note.\n")
    ReviewRecord(
        source_manifest=source_manifest(root),
        activation_required=False,
        activation_reason="Narrow text-only skill.",
    ).write(root)
    findings = review_analyze(Skill.from_path(root))
    assert not [f for f in findings if f.severity == "error"]
    assert "review-agent-missing" not in {f.rule for f in findings}

    # A required review on the same skill still needs the agent files.
    ReviewRecord(
        source_manifest=source_manifest(root),
        activation_required=True,
        activation_reason="Full review.",
    ).write(root)
    assert "review-agent-missing" in {f.rule for f in review_analyze(Skill.from_path(root))}
