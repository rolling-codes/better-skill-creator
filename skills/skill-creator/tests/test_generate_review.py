"""Malformed optional inputs must not prevent review generation."""
import importlib.util
import io
from pathlib import Path
import sys

import pytest

VIEWER = Path(__file__).resolve().parent.parent / "eval-viewer" / "generate_review.py"
spec = importlib.util.spec_from_file_location("generate_review", VIEWER)
assert spec is not None and spec.loader is not None
viewer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(viewer)


@pytest.mark.parametrize("filename", ["eval_metadata.json", "transcript.md", "grading.json"])
def test_invalid_utf8_run_input_uses_parent_or_transcript_fallback(tmp_path, capsys, filename):
    """Malformed run inputs warn and fall back to parent metadata or transcripts."""
    run = tmp_path / "run-1"
    (run / "outputs").mkdir(parents=True)
    (run / filename).write_bytes(b"\xff")
    (tmp_path / "eval_metadata.json").write_text(
        '{"prompt": "parent prompt", "eval_id": 7}', encoding="utf-8")
    (tmp_path / "grading.json").write_text('{"summary": {"pass_rate": 1}}', encoding="utf-8")
    if filename == "transcript.md":
        (tmp_path / "eval_metadata.json").unlink()
        (run / "outputs" / "transcript.md").write_text(
            "## Eval Prompt\n\nfallback prompt", encoding="utf-8")
    result = viewer.build_run(tmp_path, run)
    assert result["prompt"] == ("fallback prompt" if filename == "transcript.md" else "parent prompt")
    assert result["grading"] == {"summary": {"pass_rate": 1}}
    assert str(run / filename) in capsys.readouterr().err


def test_invalid_utf8_previous_feedback_is_skipped(tmp_path, capsys):
    """Malformed prior feedback warns and leaves the run feedback empty."""
    (tmp_path / "run-1" / "outputs").mkdir(parents=True)
    (tmp_path / "feedback.json").write_bytes(b"\xff")
    previous = viewer.load_previous_iteration(tmp_path)
    assert previous["run-1"]["feedback"] == ""
    assert "skipping prior feedback" in capsys.readouterr().err


def test_invalid_utf8_benchmark_static_generation_continues(tmp_path, capsys, monkeypatch):
    """Static review export succeeds with a warning when benchmark UTF-8 is invalid."""
    (tmp_path / "run-1" / "outputs").mkdir(parents=True)
    benchmark = tmp_path / "benchmark.json"
    benchmark.write_bytes(b"\xff")
    output = tmp_path / "review.html"
    monkeypatch.setattr(sys, "argv", [str(VIEWER), str(tmp_path), "--benchmark", str(benchmark),
                                      "--static", str(output)])
    with pytest.raises(SystemExit) as exc:
        viewer.main()
    assert exc.value.code == 0
    assert "<html" in output.read_text(encoding="utf-8").lower()
    assert "benchmark omitted" in capsys.readouterr().err


def test_invalid_utf8_benchmark_http_generation_continues(tmp_path, capsys):
    """The review handler serves HTML with a warning when benchmark UTF-8 is invalid."""
    benchmark = tmp_path / "benchmark.json"
    benchmark.write_bytes(b"\xff")
    handler = object.__new__(viewer.ReviewHandler)
    handler.path = "/"
    handler.workspace = tmp_path
    handler.skill_name = "test"
    handler.previous = {}
    handler.benchmark_path = benchmark
    handler.wfile = io.BytesIO()
    statuses = []
    handler.send_response = statuses.append
    handler.send_header = lambda *args: None
    handler.end_headers = lambda: None
    handler.do_GET()
    assert statuses == [200]
    assert b"<html" in handler.wfile.getvalue().lower()
    assert "benchmark omitted" in capsys.readouterr().err
