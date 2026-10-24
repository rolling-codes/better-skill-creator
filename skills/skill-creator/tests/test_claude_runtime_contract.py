"""Offline Claude argument contracts; no authentication or model requests."""
import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.claude_process import missing_eval_flags, model_args

ROOT = Path(__file__).resolve().parents[3]


@pytest.mark.parametrize("model", [
    "sonnet[1m]", "opus[1m]", "claude-custom-1[1m]", "sonnet",
    "arn:aws:bedrock:us-east-1:123:inference-profile/provider.model-1",
])
def test_model_argument_preserves_supported_identifiers(model):
    assert model_args(model) == ["--model", model]


@pytest.mark.parametrize("model", [
    "--help", " sonnet", "sonnet --help", "sonnet[2m]", "sonnet[]",
    "sonnet[1m][1m]", "[1m]", "sonnet;whoami", "$(whoami)",
    "sonnet`whoami`", "sonnet\n", "sonnet[1m]/suffix",
])
def test_model_argument_rejects_flags_and_unsupported_syntax(model):
    with pytest.raises(ValueError, match="Invalid model identifier"):
        model_args(model)


def test_no_model_keeps_cli_default():
    assert model_args(None) == []


FLAGS = (
    "--print", "--output-format", "--verbose", "--include-partial-messages",
    "--tools", "--permission-mode", "--strict-mcp-config", "--mcp-config",
    "--settings", "--no-session-persistence", "--allowedTools", "--model",
)


def _help(flags):
    return "Options:\n" + "\n".join(f"  {flag} <value>    Description" for flag in flags)


def test_help_capabilities_require_declarations_and_report_missing_flags():
    assert missing_eval_flags(_help(FLAGS)) == []
    assert missing_eval_flags(_help(FLAGS[:-1])) == ["--model"]
    assert missing_eval_flags("") == list(FLAGS)
    assert missing_eval_flags("Use --model and --tools for evaluation.") == list(FLAGS)


def test_help_accepts_documented_aliases_and_short_print_option():
    text = _help(FLAGS).replace("--print", "-p, --print")
    text = text.replace("--allowedTools", "--allowed-tools")
    assert missing_eval_flags(text) == []


def test_help_does_not_accept_prefix_matches_or_description_mentions():
    text = _help(FLAGS).replace("--model <", "--models <")
    text += "\n    This option is similar to --model."
    assert missing_eval_flags(text) == ["--model"]


def test_eval_preview_accepts_extended_context_matrix_without_calls(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("bsc_runtime_contract", ROOT / "bsc.py")
    assert spec and spec.loader
    bsc = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bsc)
    from scripts import run_eval
    evaluate = Mock(side_effect=AssertionError("Preview cannot call a model"))
    monkeypatch.setattr(run_eval, "run_eval", evaluate)
    code = bsc.main(["eval", str(ROOT / "examples/release-notes"),
                     "--models", "sonnet[1m],opus[1m]", "--max-calls", "100",
                     "--runs-dir", str(tmp_path)])
    result = json.loads(next(tmp_path.glob("*/results.json")).read_text())
    assert code == result["exit_code"] == 0
    assert result["status"] == "preview"
    assert result["max_calls"] == (1 + result["test_count"]) * 2
    evaluate.assert_not_called()
