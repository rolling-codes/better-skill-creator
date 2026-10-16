"""Tests for the source_rules AST linter (H-ENCODING, H-SWALLOW) and its fixtures.

Every rule ships a bad fixture it must flag and a good fixture it must not
(spec P2/5.3): a rule added without fixtures fails here. Also guards that shipped
code stays clean, so the encoding/silent-skip classes can't creep back (spec F7).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

SKILL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL))

from scripts.source_rules import RULE_IDS, scan_file, scan_tree

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _rules_in(path: Path) -> set[str]:
    rules: set[str] = set()
    for py in sorted(path.rglob("*.py")):
        rules.update(f.rule for f in scan_file(py, root=path))
    return rules


@pytest.mark.parametrize("rule", RULE_IDS)
def test_rule_has_bad_fixture_it_flags(rule):
    bad = FIXTURES / rule / "bad"
    assert bad.is_dir() and list(bad.glob("*.py")), f"{rule} has no bad fixture"
    assert rule in _rules_in(bad), f"{rule} did not flag its bad fixture"


@pytest.mark.parametrize("rule", RULE_IDS)
def test_rule_has_good_fixture_it_leaves_alone(rule):
    good = FIXTURES / rule / "good"
    assert good.is_dir() and list(good.glob("*.py")), f"{rule} has no good fixture"
    assert rule not in _rules_in(good), f"{rule} false-positived on its good fixture"


def test_shipped_code_is_clean():
    """The toolkit's own source must stay free of the classes we just fixed."""
    findings = scan_tree(SKILL)
    assert not findings, "source_rules regressions:\n" + "\n".join(str(f) for f in findings)
