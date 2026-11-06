"""Offline coverage for paired authoring evaluation and grading."""
import json
import shutil
import sys
from pathlib import Path

import pytest

SKILL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL))

from scripts.aggregate_benchmark import aggregate_results, generate_benchmark, load_run_results, validate_authoring_plan
from scripts.authoring_eval import check_outputs, main, merge_grades, preflight, prepare_run, replay_grades


def test_preflight_counts_pairs_and_rejects_invalid_inputs(tmp_path):
    suite = {"evals": [{"id": 1, "prompt": "Summarize", "files": ["input.txt"]}]}
    with pytest.raises(ValueError, match="Missing"):
        preflight(suite, tmp_path, None, ["sonnet"])
    (tmp_path / "input.txt").write_text("fixture", encoding="utf-8")
    with pytest.raises(ValueError, match="SKILL.md"):
        preflight(suite, tmp_path, tmp_path, ["sonnet"])
    (tmp_path / "SKILL.md").write_text("baseline", encoding="utf-8")
    assert preflight(suite, tmp_path, tmp_path, ["sonnet", "haiku"]) == {
        "pairs": 2, "execution_dispatches": 4, "max_grader_dispatches": 4,
        "eval_ids": [1], "models": ["sonnet", "haiku"], "baseline": "old_skill", "rubrics": {"1": []},
    }
    suite["evals"].append(suite["evals"][0])
    with pytest.raises(ValueError, match="unique"):
        preflight(suite, tmp_path, tmp_path, ["sonnet"])


@pytest.mark.parametrize("with_residual", [False, True])
def test_replay_keeps_paired_assertion_outcomes_and_benchmark(tmp_path, with_residual):
    metadata = {
        "assertions": ["Two items", "Two records"],
        "verifiers": {
            "Two items": {"reviewed": True, "kind": "json_value", "file": "out.json",
                          "pointer": "/a~1b/0", "equals": 2},
            "Two records": {"reviewed": True, "kind": "csv_rows", "file": "out.csv",
                            "equals": 2},
        },
    }
    if with_residual:
        metadata["assertions"].append("Clear summary")
    total = len(metadata["assertions"])
    replay = tmp_path / "replay"
    original = tmp_path / "original"
    for variant, item_count, csv_rows, readable in [
        ("with_skill", 2, 'name\n"row\n1"\nrow2\n', True),
        ("old_skill", True, "name\nrow1\n", False),
    ]:
        run = replay / "eval-0" / variant / "run-1"
        outputs = run / "outputs"
        identity = prepare_run(run, "sonnet")
        (outputs / "out.json").write_text(json.dumps({"a/b": [item_count]}), encoding="utf-8")
        (outputs / "out.csv").write_text(csv_rows, encoding="utf-8")
        verified = check_outputs(metadata, outputs)
        assert verified["residual"] == (["Clear summary"] if with_residual else [])
        assert verified["dispatch_grader"] is with_residual
        model = {"expectations": [
            {"text": text, "passed": readable, "evidence": "Reviewed"}
            for text in verified["residual"]
        ]}
        merged = merge_grades(metadata, verified, model)
        merged.update(identity)
        assert [row["passed"] for row in merged["expectations"]] == [readable] * total
        (run / "grading.json").write_text(json.dumps(merged), encoding="utf-8")

        original_run = original / "eval-0" / variant / "run-1"
        original_run.mkdir(parents=True)
        original_grade = {
            **identity,
            "expectations": [
                {"text": assertion, "passed": readable, "evidence": "Historical evidence"}
                for assertion in metadata["assertions"]
            ],
            "summary": {"passed": total if readable else 0, "failed": 0 if readable else total,
                        "pass_rate": float(readable), "total": total},
        }
        comparison = replay_grades(metadata, outputs, original_grade)
        assert not comparison["mismatches"]
        assert comparison["legacy_grader_dispatches"] == 1
        assert comparison["projected_grader_dispatches"] == int(with_residual)
        (original_run / "grading.json").write_text(json.dumps(original_grade), encoding="utf-8")

    replayed, legacy = load_run_results(replay), load_run_results(original)
    assert set(replayed) == set(legacy) == {"with_skill", "old_skill"}
    assert all(len(runs) == 1 for runs in replayed.values())
    plan = {"eval_ids": [0], "models": ["sonnet"], "baseline": "old_skill",
            "rubrics": {"0": metadata["assertions"]}}
    validate_authoring_plan(replayed, plan, "sonnet")
    benchmark = generate_benchmark(replay, authoring_plan=plan, model="sonnet")
    assert benchmark["metadata"]["runs_per_configuration"] == 1
    for verdict in ("FAIL", "unknown"):
        row = replayed["with_skill"][0]["expectations"][0]
        previous = row["verdict"]
        row["verdict"] = verdict
        with pytest.raises(ValueError, match="unexpected grades"):
            validate_authoring_plan(replayed, plan, "sonnet")
        row["verdict"] = previous
    with pytest.raises(ValueError, match="unexpected grades"):
        validate_authoring_plan(replayed, {**plan, "rubrics": {"0": []}}, "sonnet")
    with pytest.raises(ValueError, match="rubric for each planned case"):
        validate_authoring_plan(replayed, {**plan, "eval_ids": [0, 1]}, "sonnet")
    with pytest.raises(ValueError, match="unexpected grades"):
        validate_authoring_plan(replayed, {**plan, "rubrics": {"0": ["A different assertion"]}}, "sonnet")
    assert aggregate_results(replayed) == aggregate_results(legacy)
    assert aggregate_results(replayed)["delta"]["pass_rate"] == "+1.00"


@pytest.mark.parametrize("filename", ["../out.json", "..\\out.json", "missing.json", "invalid.json"])
def test_unusable_evidence_goes_to_model(tmp_path, filename):
    (tmp_path / "invalid.json").write_text("{", encoding="utf-8")
    metadata = {"assertions": ["value"], "verifiers": {
        "value": {"reviewed": True, "kind": "json_value", "file": filename, "pointer": "", "equals": 2}
    }}
    report = check_outputs(metadata, tmp_path)
    assert report == {"expectations": [], "residual": ["value"], "dispatch_grader": True}
    with pytest.raises(ValueError, match="exactly one"):
        merge_grades(metadata, report, {"expectations": []})


def test_unreviewed_verifier_does_not_supply_grade(tmp_path):
    metadata = {"assertions": ["value"], "verifiers": {
        "value": {"kind": "json_value", "file": "out.json", "pointer": "", "equals": 2}
    }}
    (tmp_path / "out.json").write_text("2", encoding="utf-8")
    assert check_outputs(metadata, tmp_path)["residual"] == ["value"]


def test_ambiguous_json_and_replay_disagreement(tmp_path):
    metadata = {"assertions": ["value"], "verifiers": {
        "value": {"reviewed": True, "kind": "json_value", "file": "out.json", "pointer": "/a", "equals": 2}
    }}
    run = tmp_path / "run-1"
    identity = prepare_run(run, "sonnet")
    outputs = run / "outputs"
    artifact = outputs / "out.json"
    for contents in ('{"a": 1, "a": 2}', '{"a": NaN}', "[" * 2000 + "]" * 2000):
        artifact.write_text(contents, encoding="utf-8")
        assert check_outputs(metadata, outputs)["residual"] == ["value"]
    artifact.write_text('{"a": 2}', encoding="utf-8")
    reference = {**identity, "expectations": [{"text": "value", "passed": False, "evidence": "Reviewed"}]}
    assert replay_grades(metadata, outputs, reference)["mismatches"] == ["value"]
    for wrong_identity in ({"run_id": "different"}, {"model": "haiku"}, {"run_id": None}):
        with pytest.raises(ValueError, match="must match"):
            replay_grades(metadata, outputs, {**reference, **wrong_identity})
    with pytest.raises(ValueError, match="independent grade"):
        replay_grades(metadata, outputs, {**reference, "offline_assertions": ["value"]})
    reference["expectations"][0]["verdict"] = "PASS"
    with pytest.raises(ValueError, match="conflicting"):
        replay_grades(metadata, outputs, reference)


def test_json_numbers_do_not_round_to_a_false_pass(tmp_path):
    from decimal import Decimal

    (tmp_path / "out.json").write_text('{"a": 0.123456789012345678902}', encoding="utf-8")
    metadata = {"assertions": ["value"], "verifiers": {
        "value": {"reviewed": True, "kind": "json_value", "file": "out.json", "pointer": "/a",
                  "equals": Decimal("0.123456789012345678901")}
    }}
    assert check_outputs(metadata, tmp_path)["expectations"][0]["passed"] is False


def test_merge_cli_preserves_prior_report_until_grades_are_complete(tmp_path, monkeypatch):
    metadata = tmp_path / "eval_metadata.json"
    metadata.write_text(json.dumps({"assertions": ["One"]}), encoding="utf-8")
    run = tmp_path / "run-1"
    identity = prepare_run(run, "sonnet")
    outputs = run / "outputs"
    grade = run / "grading.json"
    grade.write_text("prior", encoding="utf-8")
    residual = tmp_path / "model.json"
    args = ["authoring_eval", "merge", str(metadata), str(outputs), "--model", "sonnet", "--output", str(grade)]
    monkeypatch.setattr(sys, "argv", args)
    with pytest.raises(SystemExit) as failure:
        main()
    assert failure.value.code == 1
    assert grade.read_text(encoding="utf-8") == "prior"

    residual.write_text(json.dumps({**identity, "expectations": [
        {"text": "One", "verdict": "UNDETERMINED", "passed": False, "evidence": "Missing context"}
    ]}), encoding="utf-8")
    monkeypatch.setattr(sys, "argv", args + ["--model-grades", str(residual)])
    assert main() == 0
    (outputs / "metrics.json").write_text('{"total_tool_calls": 3}', encoding="utf-8")
    assert main() == 0
    report = json.loads(grade.read_text(encoding="utf-8"))
    assert report["model"] == "sonnet"
    assert report["execution_metrics"] == {"total_tool_calls": 3}
    assert report["summary"] == {
        "passed": 0, "failed": 1, "total": 1, "pass_rate": 0.0,
    }


def test_prepare_rejects_reuse_and_preflight_accepts_legacy_verifiers(tmp_path):
    run = tmp_path / "run-1"
    prepare_run(run, "sonnet")
    (run / "outputs" / "out.json").write_text("2", encoding="utf-8")
    with pytest.raises(FileExistsError):
        prepare_run(run, "sonnet")
    case = {"id": 1, "prompt": "Count", "expectations": ["value"], "verifiers": {
        "value": {"reviewed": True, "kind": "json_value", "file": "out.json", "pointer": "", "equals": 2}
    }}
    assert preflight({"evals": [case]}, tmp_path, None, ["sonnet"])["rubrics"] == {"1": ["value"]}
    assert check_outputs(case, run / "outputs")["dispatch_grader"] is False


def test_strict_benchmark_rejects_stale_and_incomplete_grades(tmp_path):
    run = tmp_path / "eval-0" / "with_skill" / "run-1"
    identity = prepare_run(run, "sonnet")
    grade = run / "grading.json"
    grade.write_text(json.dumps({**identity, "run_id": "copied"}), encoding="utf-8")
    with pytest.raises(ValueError, match="must match"):
        load_run_results(tmp_path, require_identity=True)
    grade.write_text(json.dumps(identity), encoding="utf-8")
    with pytest.raises(ValueError, match="Incomplete grade"):
        load_run_results(tmp_path, require_identity=True)
    grade.write_text(json.dumps({**identity, "expectations": [],
                                "summary": {"passed": 0, "failed": 0, "total": 0, "pass_rate": 0}}),
                     encoding="utf-8")
    assert load_run_results(tmp_path, require_identity=True)["with_skill"][0]["total"] == 0
    shutil.copytree(run, run.parents[1] / "without_skill" / "run-1")
    with pytest.raises(ValueError, match="Duplicate prepared run identity"):
        load_run_results(tmp_path, require_identity=True)


def test_check_cli_exposes_dispatch_decision(tmp_path, monkeypatch, capsys):
    run = tmp_path / "run-1"
    identity = prepare_run(run, "sonnet")
    outputs = run / "outputs"
    metadata = tmp_path / "eval_metadata.json"
    metadata.write_text(json.dumps({"assertions": ["value"], "verifiers": {
        "value": {"reviewed": True, "kind": "json_value", "file": "out.json", "pointer": "", "equals": 2}
    }}), encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["authoring_eval", "check", str(metadata), str(outputs)])
    assert main() == 0
    report = json.loads(capsys.readouterr().out)
    assert report["dispatch_grader"] is True
    assert report["residual"] == ["value"]
    assert {key: report[key] for key in identity} == identity

    (outputs / "out.json").write_text("1", encoding="utf-8")
    assert main() == 0
    report = json.loads(capsys.readouterr().out)
    assert report["dispatch_grader"] is False
    assert report["residual"] == []
    assert report["expectations"][0]["passed"] is False
