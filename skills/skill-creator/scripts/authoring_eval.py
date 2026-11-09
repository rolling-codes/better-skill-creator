"""Offline preflight and assertion grading for paired authoring evaluations."""
import argparse
import csv
from decimal import Decimal
import json
import os
import re
from pathlib import Path, PureWindowsPath
from uuid import uuid4

from scripts.skill_test import _write_atomic, validate_grading

MAX_ARTIFACT_BYTES = 16 * 1024 * 1024


def unique_object(pairs):
    """Reject ambiguous duplicate JSON object keys."""
    result = dict(pairs)
    if len(result) != len(pairs):
        raise ValueError("Duplicate JSON object keys")
    return result


def invalid_constant(value: str):
    """Reject nonstandard JSON numeric constants."""
    raise ValueError(f"Invalid JSON constant: {value}")


def read_json(path: Path, *, exact_numbers=False):
    """Load strict JSON, optionally preserving exact numeric values."""
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique_object,
                      parse_constant=invalid_constant, parse_float=Decimal if exact_numbers else float)


def relative_file(name: str, *, portable: bool = False) -> Path:
    """Accept only nonempty relative paths without traversal."""
    relative = Path(name)
    windows = PureWindowsPath(name)
    if not relative.parts or relative.anchor or windows.anchor or ".." in windows.parts or "\x00" in name:
        raise ValueError("Expected a relative file path inside the supplied directory")
    if (portable or os.name == "nt") and any(
        part.endswith((" ", ".")) or re.search(r'[<>:"|?*\x00-\x1f]', part)
        or PureWindowsPath(part).is_reserved()
        for part in windows.parts
    ):
        raise ValueError("Expected a portable relative file path inside the supplied directory")
    return relative


def confined_file(root: Path, name: str, *, portable: bool = False) -> Path:
    """Resolve an existing file and enforce directory containment."""
    relative = relative_file(name, portable=portable)
    try:
        resolved_root = root.resolve()
        path = (root / relative).resolve()
    except RuntimeError as exc:
        raise ValueError("Could not resolve artifact path") from exc
    if root.is_symlink() or not path.is_relative_to(resolved_root) or not path.is_file():
        raise ValueError(f"Missing or unconfined file: {name}")
    return path


def assertion_texts(values) -> list[str]:
    """Validate the unique assertion strings that identify grades."""
    if not isinstance(values, list) or not all(
        isinstance(value, str) and value.strip() for value in values
    ) or len(set(values)) != len(values):
        raise ValueError("Expected a list of unique, nonempty assertion strings")
    return values


def validate_dispatch_ceiling(limit: int, executions: int, graders: int) -> None:
    """Reject a planned worst-case total above the requested allowance."""
    if type(limit) is not int or limit < 1:
        raise ValueError("--max-dispatches must be a positive integer")
    if executions + graders > limit:
        raise ValueError(
            f"Plan needs up to {executions + graders} dispatches "
            f"({executions} execution, {graders} grading), exceeding --max-dispatches={limit}"
        )


def preflight(
    suite: dict, fixtures: Path, baseline: Path | None, models: list[str],
    *, max_dispatches: int | None = None,
) -> dict:
    """Validate paired eval inputs and report planned dispatches and rubrics."""
    if baseline is not None and not (baseline / "SKILL.md").is_file():
        raise ValueError("Old-skill baseline must contain SKILL.md")
    if not models or any(not model.strip() for model in models) or len(set(models)) != len(models):
        raise ValueError("Expected a nonempty list of unique model names")
    cases = suite.get("evals") if isinstance(suite, dict) else None
    if not isinstance(cases, list) or not cases:
        raise ValueError("Expected a nonempty eval suite")
    ids = set()
    rubrics = {}
    coverage = {}
    for case in cases:
        if not isinstance(case, dict):
            raise ValueError("Expected an object for each eval case")
        case_id = case.get("id")
        if type(case_id) is not int or case_id < 0 or case_id in ids:
            raise ValueError("Expected unique nonnegative integer case IDs")
        ids.add(case_id)
        prompt = case.get("prompt")
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError("Expected a nonempty prompt")
        assertions, verifiers = verifier_config(case)
        reviewed = {text for text, spec in verifiers.items() if spec.get("reviewed")}
        for text in reviewed:
            spec = verifiers[text]
            relative_file(spec["file"], portable=spec["kind"] == "text_line")
        case_key = str(case_id)
        rubrics[case_key] = assertions
        coverage[case_key] = {
            "reviewed": [text for text in assertions if text in reviewed],
            "residual": [text for text in assertions if text not in reviewed],
        }
        files = case.get("files", [])
        if not isinstance(files, list) or not all(isinstance(name, str) for name in files):
            raise ValueError("Expected a list of fixture paths")
        for name in files:
            confined_file(fixtures, name)
    pairs = len(cases) * len(models)
    execution_dispatches = 2 * pairs
    max_grader_dispatches = execution_dispatches
    max_total_dispatches = execution_dispatches + max_grader_dispatches
    projected_grader_dispatches = 2 * len(models) * sum(
        bool(case["residual"]) for case in coverage.values()
    )
    if max_dispatches is not None:
        validate_dispatch_ceiling(max_dispatches, execution_dispatches, max_grader_dispatches)
    return {
        "pairs": pairs,
        "execution_dispatches": execution_dispatches,
        "max_grader_dispatches": max_grader_dispatches,
        "max_total_dispatches": max_total_dispatches,
        "projected_grader_dispatches": projected_grader_dispatches,
        "verifier_coverage": coverage,
        "eval_ids": sorted(ids), "models": models, "rubrics": rubrics,
        "baseline": "old_skill" if baseline is not None else "without_skill",
    }


def pointer_tokens(pointer: object) -> list[str]:
    """Parse an RFC 6901 JSON Pointer into unescaped tokens."""
    if not isinstance(pointer, str) or (pointer and (
        not pointer.startswith("/") or re.search(r"~(?![01])", pointer)
    )):
        raise ValueError("Invalid JSON Pointer")
    return [part.replace("~1", "/").replace("~0", "~") for part in pointer.split("/")[1:]]


def json_pointer(value, pointer: str):
    """Resolve a JSON Pointer against an artifact value."""
    for token in pointer_tokens(pointer):
        if isinstance(value, dict):
            value = value[token]
        elif isinstance(value, list) and re.fullmatch(r"0|[1-9][0-9]*", token):
            value = value[int(token)]
        else:
            raise ValueError("JSON Pointer does not resolve")
    return value


def same_json_value(actual, expected) -> bool:
    """Compare JSON structurally while distinguishing booleans from numbers."""
    numeric_types = (int, float, Decimal)
    if type(actual) in numeric_types and type(expected) in numeric_types:
        return Decimal(str(actual)) == Decimal(str(expected))
    if type(actual) is not type(expected):
        return False
    if isinstance(actual, dict):
        return actual.keys() == expected.keys() and all(
            same_json_value(value, expected[key]) for key, value in actual.items()
        )
    if isinstance(actual, list):
        return len(actual) == len(expected) and all(
            same_json_value(left, right) for left, right in zip(actual, expected)
        )
    return actual == expected


def evaluate(outputs: Path, assertion: str, spec: dict) -> dict:
    """Run a single reviewed offline assertion against a confined artifact."""
    path = confined_file(outputs, spec["file"], portable=spec["kind"] == "text_line")
    expected = spec["equals"]
    if spec["kind"] == "text_line":
        with path.open("rb") as stream:
            data = stream.read(MAX_ARTIFACT_BYTES + 1)
        if len(data) > MAX_ARTIFACT_BYTES:
            raise ValueError("Artifact is too large to verify offline")
        contents = data.decode("utf-8-sig").replace("\r\n", "\n")
        # Frame real lines with newlines without inventing a line at EOF.
        framed = "\n" + contents.removesuffix("\n") + "\n"
        passed = bool(contents) and f"\n{expected}\n" in framed
        evidence = "Exact line found" if passed else "Exact line absent"
        return {"text": assertion, "passed": passed, "evidence": f"{spec['file']}: {evidence}"}
    if path.stat().st_size > MAX_ARTIFACT_BYTES:
        raise ValueError("Artifact is too large to verify offline")
    if spec["kind"] == "json_value":
        actual = json_pointer(read_json(path, exact_numbers=True), spec["pointer"])
        passed = same_json_value(actual, expected)
    elif spec["kind"] == "csv_rows":
        if type(expected) is not int or expected < 0:
            raise ValueError("Expected a nonnegative CSV row count")
        with path.open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.reader(stream, strict=True)
            header = next(reader, [])
            if not header or any(not column.strip() for column in header):
                raise ValueError("CSV requires a header row")
            actual = 0
            for row in reader:
                if len(row) != len(header):
                    raise ValueError("CSV row does not match header width")
                actual += 1
        passed = actual == expected
    else:
        raise ValueError("Unsupported verifier kind")
    evidence = f"{spec['file']}: expected {expected!r}; observed {actual!r}"
    return {"text": assertion, "passed": passed, "evidence": evidence}


def verifier_config(metadata: dict) -> tuple[list[str], dict]:
    """Read assertion texts and validate the optional verifier configuration."""
    assertions = assertion_texts(metadata.get("assertions", metadata.get("expectations", [])))
    verifiers = metadata.get("verifiers", {})
    if not isinstance(verifiers, dict) or verifiers.keys() - set(assertions):
        raise ValueError("Verifier keys must match assertion text")
    for spec in verifiers.values():
        if not isinstance(spec, dict) or type(spec.get("reviewed", False)) is not bool:
            raise ValueError("Verifier must be an object with an optional boolean reviewed flag")
        if not spec.get("reviewed"):
            continue
        if not isinstance(spec.get("file"), str) or "equals" not in spec:
            raise ValueError("Reviewed verifier needs a file and expected value")
        if spec.get("kind") == "json_value":
            pointer_tokens(spec.get("pointer"))
        elif spec.get("kind") == "csv_rows":
            if type(spec["equals"]) is not int or spec["equals"] < 0:
                raise ValueError("Expected a nonnegative CSV row count")
        elif spec.get("kind") == "text_line":
            line = spec["equals"]
            if not isinstance(line, str) or "\r" in line or "\n" in line:
                raise ValueError("Expected one text line without a line ending")
            try:
                line.encode("utf-8")
            except UnicodeEncodeError as exc:
                raise ValueError("Expected a UTF-8 text line") from exc
        else:
            raise ValueError("Unsupported reviewed verifier kind")
    return assertions, verifiers


def check_outputs(metadata: dict, outputs: Path) -> dict:
    """Grade reviewed artifacts and decide whether a grader is required."""
    assertions, verifiers = verifier_config(metadata)
    require_rubric(assertions)
    rows, residual = [], []
    for assertion in assertions:
        spec = verifiers.get(assertion)
        if isinstance(spec, dict) and spec.get("reviewed") is True:
            try:
                rows.append(evaluate(outputs, assertion, spec))
                continue
            except (OSError, ValueError, TypeError, KeyError, IndexError, ArithmeticError,
                    RecursionError, csv.Error):
                # Unusable evidence needs an independent grade.
                residual.append(assertion)
        else:
            residual.append(assertion)
    return {"expectations": rows, "residual": residual, "dispatch_grader": bool(residual)}


def prepare_run(run: Path, model: str) -> dict:
    """Reserve a never-before-used run directory and record its identity."""
    if not model.strip():
        raise ValueError("Expected the execution model")
    run.mkdir(parents=True, exist_ok=False)
    (run / "outputs").mkdir()
    identity = {"run_id": uuid4().hex, "model": model}
    _write_atomic(run / "run-identity.json", json.dumps(identity) + "\n")
    return identity


def run_identity(outputs: Path) -> dict:
    """Read the identity recorded beside the prepared outputs."""
    if outputs.name != "outputs" or outputs.is_symlink() or not outputs.is_dir():
        raise ValueError("Expected the prepared run's outputs directory")
    identity = read_json(outputs.parent / "run-identity.json")
    if (not isinstance(identity, dict) or not isinstance(identity.get("run_id"), str)
            or not re.fullmatch(r"[0-9a-f]{32}", identity["run_id"])
            or not isinstance(identity.get("model"), str) or not identity["model"].strip()):
        raise ValueError("Invalid prepared run identity")
    return identity


def require_same_run(report: dict, identity: dict) -> None:
    """Reject grades whose run or model differs from the output identity."""
    if any(report.get(key) != identity[key] for key in ("run_id", "model")):
        raise ValueError("Grade run ID and execution model must match the prepared run")


def replay_grades(metadata: dict, outputs: Path, reference: dict) -> dict:
    """Compare proposed verifiers to independent grades of this same run."""
    require_same_run(reference, run_identity(outputs))
    if reference.get("offline_assertions"):
        raise ValueError("Replay requires an independent grade without offline assertions")
    assertions, verifiers = verifier_config(metadata)
    proposed = {text: {**spec, "reviewed": True} for text, spec in verifiers.items()}
    checked = check_outputs({**metadata, "verifiers": proposed}, outputs)
    saved = {row["text"]: row for row in validate_grading(reference, assertions)}
    if any(row["passed"] != (row["verdict"] == "PASS") for row in saved.values()):
        raise ValueError("Saved grades contain conflicting verdicts and outcomes")
    mismatches = [row["text"] for row in checked["expectations"]
                  if saved[row["text"]]["verdict"] != ("PASS" if row["passed"] else "FAIL")]
    return {
        "matched": [row["text"] for row in checked["expectations"] if row["text"] not in mismatches],
        "mismatches": mismatches,
        "residual": checked["residual"],
        "legacy_grader_dispatches": 1,
        "projected_grader_dispatches": int(bool(checked["dispatch_grader"] or mismatches)),
    }


def preserve_execution_metrics(report: dict, outputs: Path) -> None:
    """Carry forward optional executor metrics when available."""
    if "execution_metrics" in report:
        return
    try:
        path = confined_file(outputs, "metrics.json")
        if path.stat().st_size <= MAX_ARTIFACT_BYTES:
            metrics = read_json(path)
            if isinstance(metrics, dict):
                report["execution_metrics"] = metrics
    except (OSError, ValueError, RecursionError):
        # Optional metrics do not determine an assertion's grade.
        return


def require_rubric(assertions: list[str]) -> None:
    """Allow an initial empty plan, but require evidence criteria before grading."""
    if not assertions:
        raise ValueError("Finalize a nonempty rubric and rerun preflight before grading")


def merge_grades(metadata: dict, offline: dict, model: dict) -> dict:
    """Require one consistent grade per planned assertion before combining rows."""
    assertions = assertion_texts(metadata.get("assertions", metadata.get("expectations", [])))
    require_rubric(assertions)
    residual = assertion_texts(offline["residual"])
    offline_texts = [text for text in assertions if text not in residual]
    offline_rows = validate_grading(offline, offline_texts)
    model_rows = validate_grading(model, residual)
    rows_by_text = {row["text"]: row for row in offline_rows + model_rows}
    if rows_by_text.keys() != set(assertions):
        raise ValueError("Missing or unexpected assertion grades")
    rows = [rows_by_text[text] for text in assertions]
    if any(row["passed"] != (row["verdict"] == "PASS") for row in rows):
        raise ValueError("Conflicting verdict and outcome")
    passed = sum(row["passed"] for row in rows)
    total = len(rows)
    return {**model, "expectations": rows, "offline_assertions": offline_texts, "summary": {
        "passed": passed, "failed": total - passed, "total": total,
        "pass_rate": passed / total if total else 0.0,
    }}


def main() -> int:
    """Run the authoring evaluation command line."""
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    pre = commands.add_parser("preflight")
    pre.add_argument("suite", type=Path)
    pre.add_argument("--fixtures", type=Path, required=True)
    baseline = pre.add_mutually_exclusive_group(required=True)
    baseline.add_argument("--baseline", type=Path)
    baseline.add_argument("--no-skill", action="store_true")
    pre.add_argument("--model", action="append", required=True)
    pre.add_argument("--max-dispatches", type=int, help="Maximum planned executions plus worst-case grading")
    prepare = commands.add_parser("prepare")
    prepare.add_argument("run", type=Path)
    prepare.add_argument("--model", required=True)
    check = commands.add_parser("check")
    check.add_argument("metadata", type=Path)
    check.add_argument("outputs", type=Path)
    check.add_argument("--reference-grades", type=Path)
    merge = commands.add_parser("merge")
    merge.add_argument("metadata", type=Path)
    merge.add_argument("outputs", type=Path)
    merge.add_argument("--model-grades", type=Path)
    merge.add_argument("--model", required=True)
    merge.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "preflight":
            report = preflight(read_json(args.suite, exact_numbers=True), args.fixtures,
                               args.baseline, args.model, max_dispatches=args.max_dispatches)
        elif args.command == "prepare":
            report = prepare_run(args.run, args.model)
        else:
            identity = run_identity(args.outputs)
            metadata = read_json(args.metadata, exact_numbers=True)
            if args.command == "check" and args.reference_grades:
                report = replay_grades(metadata, args.outputs, read_json(args.reference_grades))
            else:
                report = check_outputs(metadata, args.outputs)
            if args.command == "merge":
                if args.output.resolve() != args.outputs.parent.resolve() / "grading.json":
                    raise ValueError("Write grading.json beside the prepared outputs")
                model = read_json(args.model_grades) if args.model_grades else {"expectations": []}
                if args.model != identity["model"]:
                    raise ValueError("Execution model must match the prepared run")
                if args.model_grades:
                    require_same_run(model, identity)
                report = merge_grades(metadata, report, model)
                preserve_execution_metrics(report, args.outputs)
            report.update(identity)
        rendered = json.dumps(report, indent=2, ensure_ascii=True) + "\n"
        if args.command == "merge":
            _write_atomic(args.output, rendered)
        else:
            print(rendered, end="")
    except (OSError, ValueError, KeyError, TypeError, ArithmeticError, RecursionError) as exc:
        parser.exit(1, f"Authoring eval: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
