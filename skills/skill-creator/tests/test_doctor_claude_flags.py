"""Doctor checks the installed Claude interface without authentication or model calls."""
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location("bsc_doctor_flags", ROOT / "bsc.py")
assert spec and spec.loader
bsc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bsc)


@pytest.mark.parametrize("mode", ["complete", "missing", "timeout", "transport", "launch"])
def test_doctor_capability_check_without_model_calls(monkeypatch, mode):
    from scripts import claude_process
    flags = ('--print --output-format --verbose --include-partial-messages --tools '
             '--permission-mode --strict-mcp-config --mcp-config --settings '
             '--no-session-persistence --allowedTools --model')
    if mode == "missing":
        flags = flags.replace("--tools", "")
    flags = '\n'.join('  '+flag+'  Option description' for flag in flags.split())
    calls = []
    monkeypatch.setattr(claude_process, "claude_command", lambda *args: ["claude", *args])

    def fake_process(cmd, prompt, **kwargs):
        calls.append(cmd[1:])
        assert prompt == "" and "-p" not in cmd
        if cmd[1:] == ["--help"]:
            if mode == "launch":
                raise OSError("cannot launch help")
            return claude_process.ProcessResult(
                stdout=flags, returncode=0, timed_out=mode == "timeout",
                transport_error="reader failed" if mode == "transport" else "")
        assert cmd[1:] == ["--version"] or cmd[1:3] == ["plugin", "validate"]
        return claude_process.ProcessResult(stdout="2.1.308", returncode=0)

    monkeypatch.setattr(claude_process, "run_process", fake_process)
    rows = bsc.doctor()
    capability = next(row for row in rows if row['check'] == 'claude eval CLI flags')
    assert capability['status'] == ('passed' if mode == 'complete' else 'failed')
    if mode == "missing":
        assert '--tools' in capability['message']
    assert calls.count(["--help"]) == 1
    assert next(row for row in rows if row['check'] == 'authentication and billing')['status'] == 'skipped'


def test_doctor_missing_cli_keeps_offline_fallback(monkeypatch):
    from scripts import claude_process

    def unavailable(*args):
        raise FileNotFoundError('no CLI installed')

    monkeypatch.setattr(claude_process, 'claude_command', unavailable)
    rows = bsc.doctor()
    assert next(row for row in rows if row['check'] == 'claude')['status'] == 'skipped'
    assert all('claude eval CLI flags' != row['check'] for row in rows)
    assert next(row for row in rows if row['check'] == '.claude-plugin/plugin.json')['status'] == 'passed'
