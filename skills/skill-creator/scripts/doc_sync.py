#!/usr/bin/env python3
"""
Doc sync — every command and link the docs show must actually exist (spec F3/5.2).

Catches documentation that describes behavior the code lacks:
  * a `bsc.py <cmd>` invocation whose command or --flag isn't in the argument
    parser (discovered from bsc.build_parser(), never by scraping help text),
  * a `python -m scripts.<module>` whose module file is gone (e.g. a rename),
  * a relative markdown link that doesn't resolve on disk.

Scans the *live* docs only — README/CLAUDE/SETUP, SKILL.md, references/*.md — not
CHANGELOG/RELEASE_NOTES/handoff, which legitimately mention removed commands.

Usage: python -m scripts.doc_sync [repo-root]
Exit codes: 0 = no errors, 1 = errors found, 2 = warnings only.
"""
from __future__ import annotations

import argparse
import re
import sys
from importlib.machinery import PathFinder
from pathlib import Path
from urllib.parse import unquote

from scripts.finding_types import Finding
from scripts.review import COMMANDS as REVIEW_COMMANDS

# doc_sync.py lives at <repo>/skills/skill-creator/scripts/doc_sync.py
_SCRIPTS = Path(__file__).resolve().parent
_SKILL_DIR = _SCRIPTS.parent            # skills/skill-creator
_REPO_ROOT = _SKILL_DIR.parent.parent   # repo root (holds bsc.py)

_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")
_LINK = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
_INLINE_CODE = re.compile(r"`([^`\n]+)`")
# python, python3 or the Windows py launcher, optionally with interpreter flags before -m.
_PYTHON_M = r"\b(?:python3?|py)\b(?:[ \t]+-[A-Za-z0-9.]+)*[ \t]+-m\s+"
_MODULE = re.compile(_PYTHON_M + r"(scripts\.[A-Za-z0-9_.]+)")
# Trailing punctuation that ends a sentence or closes a parenthesis. `!`, `=`, `/` and an inner
# `.` stay part of the token, so `restart!` and `show.md` are still rejected.
_PROSE_PUNCTUATION = ".,;:)\"'"
# The module name must end at a delimiter (so scripts.review_gate is not matched); the
# subcommand token is optional so a bare `scripts.review` is captured and rejected. A trailing
# backslash (POSIX) or backtick (PowerShell) continues the command onto the next line.
_REVIEW_INVOCATION = re.compile(
    _PYTHON_M + r"scripts\.review(?=[\s`'\")]|$)"
    r"(?:[ \t]+(?:[\\`][ \t]*\n[ \t]*)?([^\s`]+))?"
)


def _live_docs(root: Path) -> list[Path]:
    """The docs whose commands/links must match current code."""
    docs: list[Path] = []
    for name in ("README.md", "CLAUDE.md", "SETUP.md"):
        if (root / name).is_file():
            docs.append(root / name)
    skill = root / "skills" / "skill-creator"
    if (skill / "SKILL.md").is_file():
        docs.append(skill / "SKILL.md")
    docs.extend(sorted((skill / "references").glob("*.md")))
    return docs


def _bsc_commands() -> dict[str, set[str]]:
    """Map each bsc.py subcommand to its valid option strings, from the real parser."""
    sys.path.insert(0, str(_REPO_ROOT))
    import bsc  # noqa: E402 — needs _REPO_ROOT on the path first
    parser = bsc.build_parser()
    sub = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction))
    return {
        name: {opt for action in sp._actions for opt in action.option_strings}
        for name, sp in sub.choices.items()
    }


def _split_fences(text: str) -> tuple[list[str], str]:
    """Split Markdown into fenced-code block bodies and the remaining prose.

    Fences are read with the opener's character and minimum length; an unclosed fence extends
    to the end of the document.
    """
    blocks: list[str] = []
    prose: list[str] = []
    lines: list[str] = []
    opener = ""
    for line in text.splitlines():
        match = _FENCE.match(line)
        if not opener:
            if match and not (match[1][0] == "`" and "`" in match[2]):
                opener = match[1]
            else:
                prose.append(line)
        elif (match and match[1][0] == opener[0] and len(match[1]) >= len(opener)
              and not match[2].strip()):
            blocks.append("\n".join(lines))
            lines = []
            opener = ""
        else:
            lines.append(line)
    if opener:  # An unclosed fence extends to the end of the document.
        blocks.append("\n".join(lines))
    return blocks, "\n".join(prose)


def _fenced_blocks(text: str) -> list[str]:
    """Read Markdown fences, matching the opener's character and minimum length."""
    return _split_fences(text)[0]


def _code_regions(text: str) -> list[str]:
    """Fenced blocks plus inline `code spans`: where a command is documented, as opposed to discussed."""
    blocks, prose = _split_fences(text)
    return blocks + _INLINE_CODE.findall(prose)


def _check_commands(text: str, rel: str, commands: dict[str, set[str]]) -> list[Finding]:
    """Flag unknown bsc.py commands and long options in fenced code blocks."""
    findings: list[Finding] = []
    for block in _fenced_blocks(text):
        for raw in block.splitlines():
            line = raw.split("#", 1)[0].strip()
            if "bsc.py" not in line:
                continue
            tokens = line.split()
            try:
                after = tokens[tokens.index(next(t for t in tokens if t.endswith("bsc.py"))) + 1:]
            except (StopIteration, ValueError):
                continue
            positionals = [t for t in after if not t.startswith("-")]
            if not positionals:
                continue
            cmd = positionals[0]
            if cmd not in commands:
                findings.append(Finding("error", "doc-command",
                    f"{rel}: documented 'bsc.py {cmd}' is not a command in the parser", ))
                continue
            for tok in after:
                if tok.startswith("--"):
                    flag = tok.split("=", 1)[0]
                    if flag not in commands[cmd]:
                        findings.append(Finding("error", "doc-flag",
                            f"{rel}: 'bsc.py {cmd}' has no option {flag}"))
    return findings


def _check_modules(text: str, rel: str) -> list[Finding]:
    """Flag documented scripts module invocations whose source files are missing."""
    findings: list[Finding] = []
    for module in _MODULE.findall(text):
        module = module.rstrip(".")
        parts = module.removeprefix("scripts.").split(".")
        if not all(re.fullmatch(r"[a-z][a-z0-9_]*", part) for part in parts):
            continue  # a metavariable like scripts.X, not a real module reference
        search_path = [str(_SCRIPTS)]
        for index, part in enumerate(parts):
            spec = PathFinder.find_spec(part, search_path)
            if spec is None or (index < len(parts) - 1 and spec.submodule_search_locations is None):
                findings.append(Finding("error", "doc-module",
                    f"{rel}: documented 'python -m {module}' does not resolve to a module"))
                break
            search_path = list(spec.submodule_search_locations or [])
    return findings


def _check_module_subcommands(text: str, rel: str) -> list[Finding]:
    """Flag a documented `python -m scripts.review <cmd>` whose subcommand is not real.

    _check_modules only proves the module resolves; it never checked the subcommand,
    which is how the documented 'scripts.review run' survived (spec F3/S6). Capture
    the complete token so a valid prefix cannot hide an invalid suffix.
    """
    findings: list[Finding] = []
    for sub in _REVIEW_INVOCATION.findall("\n".join(_code_regions(text))):
        sub = sub.rstrip(_PROSE_PUNCTUATION)  # `show.` / `show)` / `show,` end a sentence, not the token
        if sub == "<cmd>":
            continue  # documentation placeholder, not an executable subcommand
        if not sub:
            findings.append(Finding("error", "doc-subcommand",
                f"{rel}: documented 'python -m scripts.review' has no subcommand "
                f"(have: {', '.join(sorted(REVIEW_COMMANDS))})"))
        elif sub not in REVIEW_COMMANDS:
            findings.append(Finding("error", "doc-subcommand",
                f"{rel}: documented 'python -m scripts.review {sub}' is not a review subcommand "
                f"(have: {', '.join(sorted(REVIEW_COMMANDS))})"))
    return findings


def _check_links(text: str, doc: Path, rel: str) -> list[Finding]:
    """Warn about relative Markdown links that do not resolve beside the document."""
    findings: list[Finding] = []
    for target in _LINK.findall(text):
        tokens = target.strip().split()
        if not tokens:
            continue
        link = tokens[0]  # drop any "title"
        if link.startswith(("http://", "https://", "#", "mailto:")):
            continue
        path = unquote(link.split("#", 1)[0])
        if not path:
            continue
        if not (doc.parent / path).exists():
            findings.append(Finding("warning", "doc-link",
                f"{rel}: relative link '{path}' does not resolve"))
    return findings


def analyze(root: Path) -> list[Finding]:
    """Run every doc-sync rule over the live docs under root."""
    commands = _bsc_commands()
    findings: list[Finding] = []
    for doc in _live_docs(root):
        text = doc.read_text(encoding="utf-8")
        rel = doc.relative_to(root).as_posix()
        findings += _check_commands(text, rel, commands)
        findings += _check_modules(text, rel)
        findings += _check_module_subcommands(text, rel)
        findings += _check_links(text, doc, rel)
    return findings


def _main() -> int:
    """Check the CLI repository root, print findings, and return a severity exit code."""
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else _REPO_ROOT
    findings = analyze(root)
    if not findings:
        print("Doc sync: no issues.")
        return 0
    for f in findings:
        print(str(f))
    errors = [f for f in findings if f.severity == "error"]
    warnings = [f for f in findings if f.severity == "warning"]
    print(f"\n{len(findings)} finding(s): {len(errors)} error(s), {len(warnings)} warning(s)")
    return 1 if errors else (2 if warnings else 0)


if __name__ == "__main__":
    sys.exit(_main())
