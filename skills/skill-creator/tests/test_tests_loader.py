"""Regression tests for scripts/tests_loader.py — the shared trigger-test loader.

Covers both field conventions, legacy string labels, malformed rejection,
dedupe/conflict handling, Unicode, spaces in paths, external target dirs, and
that every generated archetype file loads.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

SKILL_PATH = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_PATH))

from scripts.tests_loader import (
    TestCaseError,
    load_trigger_suite,
    load_yaml_cases,
    normalize_cases,
)


def test_bool_labels_both_field_conventions():
    data = [
        {"query": "a", "should_trigger": True},
        {"prompt": "b", "expected": False},
    ]
    assert normalize_cases(data) == [
        {"query": "a", "should_trigger": True},
        {"query": "b", "should_trigger": False},
    ]


def test_legacy_string_labels():
    data = [
        {"query": "a", "expected": "triggered"},
        {"query": "b", "expected": "not_triggered"},
    ]
    out = normalize_cases(data)
    assert [c["should_trigger"] for c in out] == [True, False]


@pytest.mark.parametrize("label,expected", [
    ("yes", True), ("no", False), ("true", True), ("false", False),
    (1, True), (0, False), ("TRIGGERED", True), ("Not_Triggered", False),
])
def test_yesno_numeric_and_case_insensitive_labels(label, expected):
    assert normalize_cases([{"query": "q", "expected": label}])[0]["should_trigger"] is expected


def test_prompt_and_query_aliases_equivalent():
    a = normalize_cases([{"prompt": "x", "expected": True}])
    b = normalize_cases([{"query": "x", "should_trigger": True}])
    assert a == b


def test_dedupe_identical_query():
    data = [
        {"query": "dup", "should_trigger": True},
        {"query": "dup", "should_trigger": True},
    ]
    assert normalize_cases(data) == [{"query": "dup", "should_trigger": True}]


def test_conflicting_duplicate_raises():
    data = [
        {"query": "dup", "should_trigger": True},
        {"query": "dup", "should_trigger": False},
    ]
    with pytest.raises(TestCaseError, match="conflicting"):
        normalize_cases(data)


@pytest.mark.parametrize("bad", [
    [{"should_trigger": True}],             # missing query
    [{"query": "q"}],                       # missing expected
    [{"query": 123, "expected": True}],     # non-string query
    [{"query": "q", "expected": "maybe"}],  # unrecognized label
    ["not a dict"],                         # non-dict entry
])
def test_malformed_entries_raise(bad):
    with pytest.raises(TestCaseError):
        normalize_cases(bad)


def test_empty_prompt_is_a_valid_edge_case():
    # An empty prompt with an explicit label is a deliberate "should not trigger"
    # edge case (generated/edge_cases.yaml), not malformed.
    out = normalize_cases([{"prompt": "", "should_trigger": False}])
    assert out == [{"query": "", "should_trigger": False}]


def test_non_list_raises():
    with pytest.raises(TestCaseError):
        normalize_cases({"query": "q", "should_trigger": True})


def test_unicode_query_preserved():
    q = "créer une compétence — 日本語 — 🎯"
    out = normalize_cases([{"query": q, "should_trigger": True}])
    assert out[0]["query"] == q


def test_load_yaml_from_path_with_spaces(tmp_path):
    d = tmp_path / "dir with spaces"
    d.mkdir()
    f = d / "should_trigger.yaml"
    f.write_text(yaml.safe_dump([{"prompt": "p", "expected": True}]), encoding="utf-8")
    assert load_yaml_cases(f) == [{"query": "p", "should_trigger": True}]


def test_load_trigger_suite_external_dir(tmp_path):
    (tmp_path / "should_trigger.yaml").write_text(
        yaml.safe_dump([{"prompt": "pos", "expected": True}]), encoding="utf-8")
    (tmp_path / "should_not_trigger.yaml").write_text(
        yaml.safe_dump([{"prompt": "neg", "expected": False}]), encoding="utf-8")
    suite = load_trigger_suite(tmp_path)
    assert {c["query"]: c["should_trigger"] for c in suite} == {"pos": True, "neg": False}


def test_suite_dedupes_across_both_files(tmp_path):
    (tmp_path / "should_trigger.yaml").write_text(
        yaml.safe_dump([{"prompt": "same", "expected": True}]), encoding="utf-8")
    (tmp_path / "should_not_trigger.yaml").write_text(
        yaml.safe_dump([{"prompt": "same", "expected": True}]), encoding="utf-8")
    assert len(load_trigger_suite(tmp_path)) == 1


def test_missing_file_is_empty(tmp_path):
    assert load_yaml_cases(tmp_path / "nope.yaml") == []


def test_all_generated_archetypes_load():
    generated = Path(__file__).resolve().parent / "generated"
    files = sorted(generated.glob("*.yaml"))
    assert files, "expected generated archetype fixtures to exist"
    for f in files:
        cases = load_yaml_cases(f)
        assert cases, f"{f.name} produced no cases"
        for c in cases:
            assert isinstance(c["should_trigger"], bool)
            assert isinstance(c["query"], str)  # may be "" for empty-input edge cases


def test_suite_merges_generated_files_in_name_order_after_top_level_cases(tmp_path):
    generated = tmp_path / "generated"
    generated.mkdir()
    # Create in reverse name order so filesystem insertion order cannot decide it.
    for filename, cases in [
        ("generated/z.yaml", [{"prompt": "日本語", "expected": "not_triggered"}]),
        ("generated/a.yaml", [{"query": "", "should_trigger": False}]),
        ("should_not_trigger.yaml", [{"prompt": "negative", "expected": False}]),
        ("should_trigger.yaml", [{"query": "positive", "should_trigger": True}]),
    ]:
        (tmp_path / filename).write_text(yaml.safe_dump(cases), encoding="utf-8")

    assert load_trigger_suite(tmp_path) == [
        {"query": "positive", "should_trigger": True},
        {"query": "negative", "should_trigger": False},
        {"query": "", "should_trigger": False},
        {"query": "日本語", "should_trigger": False},
    ]


@pytest.mark.parametrize("first_file", ["should_trigger.yaml", "generated/a.yaml"])
@pytest.mark.parametrize("conflicting", [False, True], ids=["dedupe", "conflict"])
def test_suite_checks_duplicates_across_generated_file_boundaries(
    tmp_path, first_file, conflicting
):
    (tmp_path / "generated").mkdir()
    (tmp_path / first_file).write_text(
        yaml.safe_dump([{"prompt": "same", "expected": "triggered"}]), encoding="utf-8"
    )
    (tmp_path / "generated/b.yaml").write_text(
        yaml.safe_dump([{"query": " same ", "should_trigger": not conflicting}]),
        encoding="utf-8",
    )

    if conflicting:
        with pytest.raises(TestCaseError, match="duplicate query with conflicting"):
            load_trigger_suite(tmp_path)
    else:
        assert load_trigger_suite(tmp_path) == [{"query": "same", "should_trigger": True}]


@pytest.mark.parametrize("content", ["", "# no cases\n", "[]"])
def test_suite_skips_empty_generated_files_without_losing_valid_cases(tmp_path, content):
    generated = tmp_path / "generated"
    generated.mkdir()
    (generated / "a.yaml").write_text(content, encoding="utf-8")
    (generated / "b.yaml").write_text(
        '- query: generated only\n  should_trigger: true\n', encoding="utf-8"
    )
    assert load_trigger_suite(tmp_path) == [{"query": "generated only", "should_trigger": True}]


@pytest.mark.parametrize("content,error,match", [
    ("[", yaml.YAMLError, None),
    ("query: invalid root", TestCaseError, "must be a list"),
    ("- query: missing label", TestCaseError, "missing an expected label"),
    ("- query: bad label\n  expected: maybe", TestCaseError, "unrecognized expected label"),
])
def test_suite_surfaces_invalid_generated_files(tmp_path, content, error, match):
    generated = tmp_path / "generated"
    generated.mkdir()
    (generated / "invalid.yaml").write_text(content, encoding="utf-8")
    with pytest.raises(error, match=match):
        load_trigger_suite(tmp_path)


def test_suite_discovers_only_direct_yaml_files_in_generated(tmp_path):
    generated = tmp_path / "generated"
    (generated / "nested").mkdir(parents=True)
    for filename in ["ignored.yml", "ignored.json", "nested/ignored.yaml"]:
        (generated / filename).write_text("invalid test data", encoding="utf-8")
    (tmp_path / "unrelated.yaml").write_text("invalid test data", encoding="utf-8")
    (generated / "included.yaml").write_text(
        '- query: included\n  should_trigger: false\n', encoding="utf-8"
    )
    assert load_trigger_suite(tmp_path) == [{"query": "included", "should_trigger": False}]


@pytest.mark.parametrize("generated_state", ["absent", "empty", "file"])
def test_suite_with_no_generated_directory_cases_is_empty(tmp_path, generated_state):
    generated = tmp_path / "generated"
    if generated_state == "empty":
        generated.mkdir()
    elif generated_state == "file":
        generated.write_text("not a directory", encoding="utf-8")
    assert load_trigger_suite(tmp_path) == []
