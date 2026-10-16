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
from pathlib import Path

from scripts.finding_types import Finding

# doc_sync.py lives at <repo>/skills/skill-creator/scripts/doc_sync.py
_SCRIPTS = Path(__file__).resolve().parent
_SKILL_DIR = _SCRIPTS.parent            # skills/skill-creator
_REPO_ROOT = _SKILL_DIR.parent.parent   # repo root (holds bsc.py)

_FENCE = re.compile(r"```.*?```", re.DOTALL)
_LINK = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
_MODULE = re.compile(r"python\s+-m\s+(scripts\.[A-Za-z0-9_.]+)")


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


def _check_commands(text: str, rel: str, commands: dict[str, set[str]]) -> list[Finding]:
    findings: list[Finding] = []
    for block in _FENCE.findall(text):
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
    findings: list[Finding] = []
    for module in _MODULE.findall(text):
        # scripts.review show -> file scripts/review.py; drop any trailing subcommand
        mod = module.split()[0].removeprefix("scripts.").split(".")[0]
        if not re.fullmatch(r"[a-z][a-z0-9_]*", mod):
            continue  # a metavariable like scripts.X, not a real module reference
        if not (_SCRIPTS / f"{mod}.py").is_file():
            findings.append(Finding("error", "doc-module",
                f"{rel}: documented 'python -m scripts.{mod}' has no module scripts/{mod}.py"))
    return findings


def _check_links(text: str, doc: Path, rel: str) -> list[Finding]:
    findings: list[Finding] = []
    for target in _LINK.findall(text):
        link = target.strip().split()[0]  # drop any "title"
        if link.startswith(("http://", "https://", "#", "mailto:")):
            continue
        path = link.split("#", 1)[0]
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
        findings += _check_links(text, doc, rel)
    return findings


def _main() -> int:
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
