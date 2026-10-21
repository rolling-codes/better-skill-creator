"""Tests for the doc-sync check: documented commands/modules/links must exist (F3)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

SKILL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL))

from scripts.doc_sync import (
    _bsc_commands, _check_commands, _check_modules, _check_module_subcommands,
    _check_links, analyze,
)
from scripts import doc_sync
from scripts import review

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


@pytest.mark.parametrize("subcommand", [
    "run", "show.md", "init.md", "restart.md", "show/extra", "restart!",
    "--help", "<cmd>.md", "showé", "restart=now",
])
@pytest.mark.parametrize("template", ["run `{command}`", "```bash\n{command}\n```"])
def test_unknown_review_subcommand_flagged(tmp_path, monkeypatch, subcommand, template):
    """Reject the whole invalid token, matching the CLI rather than a valid prefix."""
    text = template.format(command=f"python -m scripts.review {subcommand} .")
    findings = _check_module_subcommands(text, "d.md")
    assert _rules(findings) == ["doc-subcommand"]
    assert f"scripts.review {subcommand}'" in findings[0].message
    monkeypatch.setattr(sys, "argv", ["review", subcommand, str(tmp_path)])
    assert review._main() == 1


@pytest.mark.parametrize("subcommand", review.COMMANDS)
def test_real_review_subcommand_passes(tmp_path, monkeypatch, subcommand):
    """Every advertised command is accepted by both doc sync and the CLI dispatcher."""
    if subcommand == "show":
        review.ReviewRecord().write(tmp_path)
    text = f"`python -m scripts.review {subcommand} .`"
    assert _check_module_subcommands(text, "d.md") == []
    monkeypatch.setattr(sys, "argv", ["review", subcommand, str(tmp_path)])
    assert review._main() == 0


@pytest.mark.parametrize("text", [
    "`python -m scripts.review`",
    "run `python -m scripts.review`",
    "`python -m scripts.review .`",
    "```bash\npython -m scripts.review\n```",
])
def test_missing_or_non_command_review_subcommand_flagged(text):
    """A bare review invocation, or a path where the subcommand belongs, is rejected."""
    assert _rules(_check_module_subcommands(text, "d.md")) == ["doc-subcommand"]


def test_review_gate_module_is_not_a_review_invocation():
    """scripts.review_gate is a different module; its arguments are not review subcommands."""
    assert _check_module_subcommands("python -m scripts.review_gate .", "d.md") == []


def test_analyze_reports_bare_review_invocation(tmp_path):
    """analyze() applies the check, so dropping it from analyze() fails here."""
    (tmp_path / "README.md").write_text("`python -m scripts.review`", encoding="utf-8")
    assert _rules(analyze(tmp_path)) == ["doc-subcommand"]


@pytest.mark.parametrize("text", [
    "run `python -m scripts.review show`, then continue",
    "(`python -m scripts.review show.`)",
    "see \"`python -m scripts.review show`\"",
    "```bash\npython -m scripts.review restart; python -m scripts.review show)\n```",
    "```bash\npython -m scripts.review \\\n    show .\n```",
])
def test_prose_punctuation_and_continuations_are_accepted(text):
    """Sentence punctuation and shell line continuations must not turn a valid command into an error."""
    assert _check_module_subcommands(text, "d.md") == []


def test_continuation_before_invalid_subcommand_is_still_flagged():
    """A continuation is skipped, not trusted: the token after it is still validated."""
    text = "```bash\npython -m scripts.review \\\n    bogus .\n```"
    assert _rules(_check_module_subcommands(text, "d.md")) == ["doc-subcommand"]


@pytest.mark.parametrize("text", [
    "```powershell\npython -m scripts.review `\n    show .\n```",
    "```bash\npy -m scripts.review show .\n```",
    "```bash\npython3 -m scripts.review restart .\n```",
    "```bash\npython -u -m scripts.review init .\n```",
])
def test_other_launchers_and_powershell_continuations_accept_valid_commands(text):
    assert _check_module_subcommands(text, "d.md") == []


@pytest.mark.parametrize("text", [
    "```bash\npy -m scripts.review run .\n```",
    "```bash\npython3 -m scripts.review run .\n```",
    "```powershell\npython -m scripts.review `\n    bogus .\n```",
])
def test_other_launchers_and_powershell_continuations_still_reject_bad_commands(text):
    assert _rules(_check_module_subcommands(text, "d.md")) == ["doc-subcommand"]


@pytest.mark.parametrize("text", [
    "Run python -m scripts.review and then look at the record.",
    "python -m scripts.review run . is how the old docs put it.",
    "Prose mentioning python -m scripts.review --help is not a documented command.",
])
def test_prose_outside_code_is_not_scanned(text):
    """Only fenced blocks and `inline code` document a command; sentences about it are not parsed."""
    assert _check_module_subcommands(text, "d.md") == []


def test_inline_code_inside_prose_is_still_scanned():
    assert _rules(_check_module_subcommands("Use `python -m scripts.review run .` here.", "d.md")) == ["doc-subcommand"]


def test_review_subcommand_placeholder_is_ignored():
    """A documentation metavariable is not an executable subcommand."""
    assert _check_module_subcommands("`python -m scripts.review <cmd> .`", "d.md") == []


def test_analyze_checks_complete_review_subcommand(tmp_path):
    """The public analyzer catches suffixed commands in live documentation."""
    (tmp_path / "README.md").write_text("`python -m scripts.review show.md .`", encoding="utf-8")
    findings = analyze(tmp_path)
    assert _rules(findings) == ["doc-subcommand"]
    assert findings[0].severity == "error"
    assert "scripts.review show.md'" in findings[0].message


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


@pytest.mark.parametrize("opener, closer", [
    ("```bash", "```"), ("~~~bash", "~~~"),
    ("````bash", "`````"), ("~~~~bash", "~~~~~ \t"),
])
def test_fences_check_commands_and_stop_at_matching_close(opener, closer):
    text = f"{opener}\npython bsc.py frobnicate .\n{closer}\npython bsc.py outside .\n"
    findings = _check_commands(text, "d.md", CMDS)
    assert _rules(findings) == ["doc-command"]
    assert "frobnicate" in findings[0].message


@pytest.mark.parametrize("opener, false_close, closer", [
    ("````bash", "```", "````"),
    ("~~~~bash", "~~~", "~~~~"),
    ("```bash", "~~~", "```"),
    ("~~~bash", "```", "~~~"),
    ("```bash", "```still inside", "```"),
    ("~~~bash", "~~~still inside", "~~~"),
    ("```bash", "    ```", "```"),
])
def test_nonclosing_fences_keep_commands_in_block(opener, false_close, closer):
    text = f"{opener}\npython bsc.py doctor\n{false_close}\npython bsc.py frobnicate .\n{closer}"
    assert _rules(_check_commands(text, "d.md", CMDS)) == ["doc-command"]


@pytest.mark.parametrize("opener", ["```bash", "~~~bash"])
def test_unclosed_fences_extend_to_end_of_document(opener):
    assert _rules(_check_commands(f"{opener}\npython bsc.py frobnicate .", "d.md", CMDS)) == ["doc-command"]


@pytest.mark.parametrize("module, expected", [
    ("pkg.child", []), ("namespace.child", []), ("pkg", []),
    ("pkg.missing", ["doc-module"]),
    ("pkg.child.missing", ["doc-module"]),
    ("missing.child", ["doc-module"]),
])
def test_complete_module_path_is_checked_without_importing(tmp_path, monkeypatch, module, expected):
    monkeypatch.setattr(doc_sync, "_SCRIPTS", tmp_path)
    for package in ("pkg", "namespace"):
        (tmp_path / package).mkdir()
        (tmp_path / package / "child.py").write_text("raise RuntimeError('do not import')", encoding="utf-8")
    (tmp_path / "pkg" / "__init__.py").write_text("raise RuntimeError('do not import')", encoding="utf-8")
    assert _rules(_check_modules(f"`python -m scripts.{module}`", "d.md")) == expected


@pytest.mark.parametrize("filename, target", [
    ("my guide.md", "my%20guide.md"),
    ("my guide.md", "my%20guide.md#section"),
    ("hash#name.md", "hash%23name.md"),
    ("café.md", "caf%C3%A9.md"),
])
def test_percent_encoded_relative_links_resolve(tmp_path, filename, target):
    (tmp_path / filename).write_text("x", encoding="utf-8")
    doc = tmp_path / "d.md"
    assert _check_links(f"[guide]({target})", doc, "d.md") == []


def test_encoded_missing_link_is_flagged_and_empty_links_are_ignored(tmp_path):
    text = "[missing](no%20guide.md) [empty]() [space]( ) [anchor](#sec) [mail](mailto:a@b.io)"
    assert _rules(_check_links(text, tmp_path / "d.md", "d.md")) == ["doc-link"]
