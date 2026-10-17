"""Tests for the doc-sync check: documented commands/modules/links must exist (F3)."""
from __future__ import annotations

import sys
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL))

from scripts.doc_sync import (
    _bsc_commands, _check_commands, _check_modules, _check_links, analyze,
)

CMDS = _bsc_commands()


def _rules(findings):
    """Return rule IDs from doc-sync findings in their reported order."""
    return [f.rule for f in findings]


def test_real_repo_docs_are_clean():
    """The live docs must stay in sync with the parser (guards against drift)."""
    assert analyze(SKILL.parent.parent) == []


def test_unknown_command_flagged():
    """A command absent from the parser produces a doc-command finding."""
    text = "```\npython bsc.py frobnicate .\n```"
    assert _rules(_check_commands(text, "d.md", CMDS)) == ["doc-command"]


def test_unknown_flag_flagged():
    """An unsupported long option produces a doc-flag finding."""
    text = "```\npython bsc.py check . --nonexistent\n```"
    assert _rules(_check_commands(text, "d.md", CMDS)) == ["doc-flag"]


def test_valid_command_and_flags_pass():
    """A real command with supported long options produces no findings."""
    text = "```\npython bsc.py eval . --live --models haiku,sonnet\n```"
    assert _check_commands(text, "d.md", CMDS) == []


def test_trailing_comment_ignored():
    """A trailing shell comment does not invalidate a documented command."""
    text = "```\npython bsc.py doctor    # prerequisite checks\n```"
    assert _check_commands(text, "d.md", CMDS) == []


def test_missing_module_flagged():
    """An invocation of a nonexistent scripts module produces a module finding."""
    assert _rules(_check_modules("run `python -m scripts.nonexistent_mod .`", "d.md")) == ["doc-module"]


def test_metavariable_module_ignored():
    """A placeholder module name is excluded from module existence checks."""
    assert _check_modules("invoke as `python -m scripts.X` from the dir", "d.md") == []


def test_real_module_passes():
    """An invocation of an existing scripts module produces no findings."""
    assert _check_modules("`python -m scripts.review show .`", "d.md") == []


def test_broken_relative_link_flagged(tmp_path):
    """A relative link to a missing file produces a doc-link warning."""
    doc = tmp_path / "d.md"
    doc.write_text("See [guide](references/missing.md).", encoding="utf-8")
    assert _rules(_check_links(doc.read_text(encoding="utf-8"), doc, "d.md")) == ["doc-link"]


def test_resolving_link_and_url_and_anchor_pass(tmp_path):
    """An existing relative file, an HTTPS URL, and an anchor are accepted."""
    (tmp_path / "real.md").write_text("x", encoding="utf-8")
    doc = tmp_path / "d.md"
    doc.write_text("[a](real.md) [b](https://x.io) [c](#sec)", encoding="utf-8")
    assert _check_links(doc.read_text(encoding="utf-8"), doc, "d.md") == []
