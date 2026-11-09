import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import authoring_eval as author
from scripts.blind_judging import judge_packet
from scripts.call_budget import CallBudget, result_usage


def test_jsonl_packet_keeps_tool_evidence_but_omits_provenance(tmp_path):
    (tmp_path / "report.md").write_text("Quarterly totals", encoding="utf-8")
    (tmp_path / "behavior_evidence.json").write_text('{"model": "private-model"}', encoding="utf-8")
    transcript = "\n".join(json.dumps(row) for row in [
        {"type": "system", "subtype": "init", "model": "private-model", "cwd": "with_skill"},
        {"type": "assistant", "message": {"role": "assistant", "model": "private-model",
         "content": [{"type": "tool_use", "name": "Read", "input": {"path": "report.md"}}]}},
    ])
    packet, pending = judge_packet(["Uses a file", "Names my-skill"], task="Summarize",
        transcript=transcript, suffix=".jsonl", integrity={"complete": True, "issues": ["private-model"]},
        outputs=tmp_path, identities=("my-skill",))
    assert packet is not None
    assert packet["expectations"] == ["Uses a file"]
    assert "Read" in packet["transcript"]
    assert packet["outputs"] == [{"path": "report.md", "content": "Quarterly totals"}]
    assert "private-model" not in json.dumps(packet)
    assert pending[0]["verdict"] == "UNDETERMINED"


@pytest.mark.parametrize("evidence", ["my-skill_report.txt", "binary", "empty", "nested",
                                     "nested_content", "metadata_only", "blank_file", "blank_message",
                                     "plaintext_metadata"])
def test_unblindable_or_empty_evidence_skips_judge(tmp_path, monkeypatch, evidence):
    run = tmp_path / "with_skill" / "run-1"
    identity = author.prepare_run(run, "sonnet")
    outputs = run / "outputs"
    transcript = None
    if evidence == "binary":
        (outputs / "report.pdf").write_bytes(b"\xff\x00")
    elif evidence == "nested":
        transcript = run / "transcript.jsonl"
        transcript.write_text('{"type":"assistant","context":{"model":"gpt-5"}}', encoding="utf-8")
    elif evidence == "nested_content":
        transcript = run / "transcript.jsonl"
        transcript.write_text(json.dumps({"type": "assistant", "message": {"content": [
            {"type": "text", "text": "Result", "providerModel": "gpt-5", "session_id": "private-session"},
        ]}}), encoding="utf-8")
    elif evidence == "metadata_only":
        transcript = run / "transcript.jsonl"
        transcript.write_text('{"type":"result","model":"gpt-5","duration_ms":7}', encoding="utf-8")
    elif evidence == "blank_file":
        (outputs / "empty.txt").write_text("  \n", encoding="utf-8")
    elif evidence == "blank_message":
        transcript = run / "transcript.jsonl"
        transcript.write_text('{"type":"assistant","message":{"content":[{"type":"text","text":" "}]}}',
                              encoding="utf-8")
    elif evidence == "plaintext_metadata":
        transcript = run / "transcript.json"
        transcript.write_text('{"providerModel":"gpt-5","session_id":"private-session","content":"Result"}',
                              encoding="utf-8")
    elif evidence != "empty":
        (outputs / evidence).write_text("Evidence", encoding="utf-8")
    monkeypatch.setattr(author, "call_claude_text", lambda *a, **k: pytest.fail("Judge must not run"))
    grade = author.judge_run({"prompt": "Summarize", "assertions": ["Has totals"]},
                            outputs, transcript, identity, ("my-skill",))
    assert grade["human_review_required"] == ["Has totals"]
    assert grade["judge_cli_attempts"] == 0


def test_judge_dispatches_only_residual_and_keeps_usage_local(tmp_path, monkeypatch):
    identity = author.prepare_run(tmp_path / "run", "sonnet")
    outputs = tmp_path / "run" / "outputs"
    (outputs / "report.md").write_text("Results", encoding="utf-8")
    metadata = {"prompt": "Write a report", "assertions": ["Heading", "Useful"],
                "verifiers": {"Heading": {"kind": "text_line", "reviewed": True,
                                          "file": "report.md", "equals": "Results"}}}

    def judge(prompt, *, budget, stage, **kwargs):
        assert identity["run_id"] not in prompt
        assert "sonnet" not in prompt
        assert json.loads(prompt.splitlines()[-1])["expectations"] == ["Useful"]
        attempt = budget.consume(stage)
        budget.record_usage(attempt, {"cache_read_input_tokens": 0})
        return '{"expectations":[{"text":"Useful","passed":true,"evidence":"Results"}]}'

    monkeypatch.setattr(author, "call_claude_text", judge)
    grade = author.judge_run(metadata, outputs, None, identity, ("my-skill",))
    assert grade["attempt_usage"] == [{"stage": "judge", "reported_usage": {"cache_read_input_tokens": 0}}]
    assert author.merge_grades(metadata, author.check_outputs(metadata, outputs), grade)["summary"]["passed"] == 2


def test_swap_audit_does_not_call_same_position_a_winner(tmp_path, monkeypatch):
    left, right = (tmp_path / name / "run-1" / "outputs" for name in ("with_skill", "without_skill"))
    for directory, text in ((left, "Alpha"), (right, "Beta")):
        author.prepare_run(directory.parent, "sonnet")
        (directory / "report.md").write_text(text, encoding="utf-8")
    monkeypatch.setattr(author, "randbelow", lambda _: 0)
    packets = []

    def judge(prompt, *, budget, stage, **kwargs):
        budget.consume(stage)
        packets.append(json.loads(prompt.splitlines()[-1]))
        return '{"winner":"A","evidence":"Clearer"}'

    monkeypatch.setattr(author, "call_claude_text", judge)
    report = author.compare_pair({"prompt": "Summarize"}, left, right, ("my-skill",), swap=True)
    assert report["winner"] == "inconclusive"
    assert report["judge_cli_attempts"] == 2
    assert packets[0]["A"] == packets[1]["B"]
    assert packets[0]["B"] == packets[1]["A"]
    assert report["judgments"][0]["order"] == {"A": "left", "B": "right"}
    assert "with_skill" not in json.dumps(packets)


def test_usage_distinguishes_missing_from_zero():
    budget = CallBudget(2)
    budget.consume("discovery")
    attempt = budget.consume("retry")
    budget.record_usage(attempt, result_usage({"usage": {"cache_read_input_tokens": 0}}))
    assert budget.usage_report() == [
        {"stage": "discovery", "reported_usage": None},
        {"stage": "retry", "reported_usage": {"cache_read_input_tokens": 0}},
    ]


def test_unresolved_grade_blocks_even_unplanned_benchmark(tmp_path, monkeypatch):
    from scripts import aggregate_benchmark

    monkeypatch.setattr(aggregate_benchmark, "load_run_results", lambda *a, **k: {
        "old_skill": [{"expectations": [{"verdict": "UNDETERMINED"}]}],
    })
    with pytest.raises(ValueError, match="Resolve undetermined"):
        aggregate_benchmark.generate_benchmark(tmp_path)
