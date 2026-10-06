"""Shared loader/normalizer for a skill's trigger test cases.

One place that turns every trigger-test file the repo uses into the
`{query, should_trigger: bool}` eval-set that run_eval.py consumes.

It accepts both field conventions so all archetypes load the same way:
  - tests/should_trigger.yaml / should_not_trigger.yaml   -> {prompt, expected}
  - tests/generated/*.yaml (from generate_tests.py)        -> {query, should_trigger}

It also interprets legacy string labels (triggered / not_triggered, yes / no,
0 / 1) for backward compatibility, rejects malformed entries with a clear
message, drops identical duplicate queries, and errors on a duplicate query
whose expected value contradicts an earlier one.
"""
from __future__ import annotations

from pathlib import Path

import yaml

# Recognized labels, compared case-insensitively after str/strip.
_TRUE_LABELS = {"true", "trigger", "triggered", "should_trigger", "yes", "y", "1", "pass"}
_FALSE_LABELS = {
    "false", "not_triggered", "not_trigger", "should_not_trigger", "no", "n",
    "0", "fail", "no_trigger",
}

# Field names accepted for the query text and the expected label.
_QUERY_KEYS = ("query", "prompt")
_EXPECTED_KEYS = ("should_trigger", "expected", "label", "triggered")


class TestCaseError(ValueError):
    """Raised when a test file is malformed or internally contradictory."""
    __test__ = False  # not a pytest test class despite the leading "Test"


def _coerce_expected(value, where: str) -> bool:
    """Coerce a bool / int(0,1) / recognized string label to bool."""
    if isinstance(value, bool):
        return value
    if isinstance(value, int):  # bool already handled above
        if value in (0, 1):
            return bool(value)
        raise TestCaseError(f"{where}: expected 0 or 1, got {value!r}")
    if isinstance(value, str):
        v = value.strip().lower()
        if v in _TRUE_LABELS:
            return True
        if v in _FALSE_LABELS:
            return False
        raise TestCaseError(f"{where}: unrecognized expected label {value!r}")
    raise TestCaseError(
        f"{where}: expected a bool or a label like true/false or "
        f"triggered/not_triggered, got {type(value).__name__}"
    )


def _extract_query(item: dict, where: str) -> str:
    # A present string is accepted even if empty — an empty prompt is a valid
    # "should not trigger" edge case (see generated/edge_cases.yaml), not a
    # malformed entry. Only a missing or non-string query field is malformed.
    for key in _QUERY_KEYS:
        if key in item:
            val = item[key]
            if isinstance(val, str):
                return val
            raise TestCaseError(f"{where}: '{key}' must be a string, got {type(val).__name__}")
    raise TestCaseError(f"{where}: missing a 'query' or 'prompt' field")


def _extract_expected(item: dict, where: str) -> bool:
    for key in _EXPECTED_KEYS:
        if key in item:
            return _coerce_expected(item[key], where)
    raise TestCaseError(
        f"{where}: missing an expected label "
        f"('should_trigger', 'expected', 'label', or 'triggered')"
    )


def normalize_cases(data, source: str = "<data>") -> list[dict]:
    """Normalize a raw list of test entries to `{query, should_trigger}` dicts.

    Idempotent: already-normalized dicts pass through unchanged (aside from
    dedupe), so merged suites can be re-normalized safely.
    """
    if not isinstance(data, list):
        raise TestCaseError(f"{source}: must be a list of test entries, got {type(data).__name__}")

    seen: dict[str, bool] = {}
    out: list[dict] = []
    for i, item in enumerate(data):
        where = f"{source} entry {i}"
        if not isinstance(item, dict):
            raise TestCaseError(f"{where}: must be a mapping, got {type(item).__name__}")
        query_values = [item[k] for k in _QUERY_KEYS if k in item]
        if len(query_values) > 1 and any(x != query_values[0] for x in query_values):
            raise TestCaseError(f"{where}: conflicting query fields")
        expected_values = [_coerce_expected(item[k], where) for k in _EXPECTED_KEYS if k in item]
        if len(set(expected_values)) > 1:
            raise TestCaseError(f"{where}: conflicting expected fields")
        query = _extract_query(item, where)
        expected = _extract_expected(item, where)
        key = query.strip()
        if key in seen:
            if seen[key] != expected:
                raise TestCaseError(
                    f"{where}: duplicate query with conflicting expected value: {query!r}"
                )
            continue  # identical duplicate — drop silently
        seen[key] = expected
        out.append({"query": query, "should_trigger": expected})
    return out


def load_yaml_cases(path: Path) -> list[dict]:
    """Load and normalize a single YAML test file (missing file -> [])."""
    if not path.exists():
        return []
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if data is None:
        return []
    return normalize_cases(data, source=str(path))


def load_trigger_suite(tests_dir: Path) -> list[dict]:
    """Load normalized trigger cases from tests_dir, merged and deduplicated.

    Read should_trigger.yaml, then should_not_trigger.yaml, then generated/*.yaml
    in sorted path order without recursion. Missing files and empty YAML
    documents contribute no cases. Return {query, should_trigger} dictionaries,
    keeping the first occurrence of each query after stripping whitespace for
    comparison; the returned query text is preserved.

    Raises:
        TestCaseError: If entries are malformed or duplicate queries have
            conflicting expectations, including across files.
        yaml.YAMLError: If a file contains invalid YAML.
        OSError: If a file cannot be read.
        UnicodeDecodeError: If a file is not valid UTF-8.
    """
    cases = (
        load_yaml_cases(tests_dir / "should_trigger.yaml")
        + load_yaml_cases(tests_dir / "should_not_trigger.yaml")
    )
    generated_dir = tests_dir / "generated"
    if generated_dir.is_dir():
        for yaml_file in sorted(generated_dir.glob("*.yaml")):
            cases += load_yaml_cases(yaml_file)
    # Re-normalize the merged list so a duplicate query spanning files is
    # caught (identical dropped, conflicting rejected).
    return normalize_cases(cases, source=str(tests_dir))
