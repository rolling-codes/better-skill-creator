"""Bounded subprocess transport shared by Claude evaluation and grading."""
from __future__ import annotations

from dataclasses import dataclass
from contextlib import contextmanager
import os
from pathlib import Path
import queue
import re
import shutil
import signal
import subprocess
import tempfile
import threading

from scripts.call_budget import CallBudget
import time


@dataclass
class ProcessResult:
    stdout: str = ""
    stderr: str = ""
    returncode: int | None = None
    timed_out: bool = False
    stopped: bool = False
    transport_error: str = ""


def claude_command(*args: str) -> list[str]:
    """Use the native binary, or bypass the npm shell shim when available."""
    path = shutil.which("claude")
    if not path:
        raise FileNotFoundError("Claude CLI not found; install Claude Code and rerun doctor.")
    if Path(path).suffix.lower() in (".cmd", ".bat", ".ps1"):
        pkg = Path(path).parent / "node_modules/@anthropic-ai/claude-code"
        # Current Claude Code ships a native binary; older npm builds shipped cli.js.
        native = pkg / "bin" / ("claude.exe" if os.name == "nt" else "claude")
        if native.is_file():
            return [str(native), *args]
        script = pkg / "cli.js"
        node = shutil.which("node")
        if script.is_file() and node:
            return [node, str(script), *args]
        raise FileNotFoundError("Install native Claude Code or repair its npm installation (bin/claude or cli.js missing).")
    return [path, *args]


def model_args(model: str | None) -> list[str]:
    if model is None:
        return []
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]*", model):
        raise ValueError("Invalid model identifier")
    return ["--model", model]


def isolation_args(tools: str = "") -> list[str]:
    """Ignore user/project settings and MCP servers; disable hooks and persistence."""
    args = ["--tools", tools, "--permission-mode", "dontAsk",
            "--setting-sources", "", "--strict-mcp-config",
            "--mcp-config", '{"mcpServers":{}}',
            "--settings", '{"disableAllHooks":true}', "--no-session-persistence"]
    if tools:
        args += ["--allowedTools", tools]
    return args


@contextmanager
def model_environment():
    """Use a disposable profile, forwarding only runtime needs and explicit auth.

    This is a tool/configuration boundary, not an OS sandbox. No local login
    profile, plugins, hooks, arbitrary API endpoints, or unrelated secrets are
    copied into the model process. Provide ANTHROPIC_API_KEY or
    CLAUDE_CODE_OAUTH_TOKEN explicitly for live runs.
    """
    with tempfile.TemporaryDirectory(prefix="bsc-model-") as temp:
        home = Path(temp)
        config = home / ".claude"
        config.mkdir(mode=0o700)
        work = home / "work"
        work.mkdir()
        allowed = {"PATH", "SystemRoot", "SYSTEMROOT", "WINDIR", "PATHEXT",
                   "LANG", "LC_ALL", "ANTHROPIC_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN"}
        env = {k: v for k, v in os.environ.items() if k in allowed}
        env.update({"HOME": str(home), "USERPROFILE": str(home),
                    "APPDATA": str(home), "LOCALAPPDATA": str(home),
                    "XDG_CONFIG_HOME": str(home), "XDG_CACHE_HOME": str(home),
                    "TMPDIR": str(home), "TMP": str(home), "TEMP": str(home),
                    "CLAUDE_CONFIG_DIR": str(config), "PYTHONUTF8": "1"})
        yield env, work


def _terminate(process) -> None:
    # Always attempt group cleanup — the parent may have already exited while children survive.
    if os.name == "nt" and getattr(process, "pid", None):
        try:
            subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                           capture_output=True, timeout=3, creationflags=subprocess.CREATE_NO_WINDOW)
        except (OSError, subprocess.TimeoutExpired):
            pass
    elif os.name != "nt" and getattr(process, "pid", None):
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except OSError:
            pass
    if process.poll() is None:
        process.kill()
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        pass


def run_process(cmd, prompt: str, *, cwd: Path, timeout: float,
                on_line=None, capture_stdout=True, transcript: Path | None = None, env=None) -> ProcessResult:
    """Drain both pipes while a writer sends stdin; all waiting is bounded.

    on_line may return True to stop after an observed trigger. Such a stop is
    trigger evidence, not evidence that a behavior task completed.
    """
    if timeout <= 0:
        raise ValueError("timeout must be positive")
    if env is None:
        env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}
        env["PYTHONUTF8"] = "1"
    saved = transcript.open("w", encoding="utf-8") if transcript else None
    if os.name == "nt":
        process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=str(cwd),
            env=env,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW,
        )
    else:
        process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=str(cwd),
            env=env,
            start_new_session=True,
        )
    result = ProcessResult()
    events = queue.Queue(maxsize=256)
    stop = threading.Event()
    threads = []
    deadline = time.monotonic() + timeout

    def put(item):
        """Queue a transport event, retrying while full until shutdown is requested."""
        while not stop.is_set():
            try:
                events.put(item, timeout=0.05)
                return
            except queue.Full:
                continue

    def reader(stream, kind):
        """Queue decoded pipe output and signal errors and stream completion."""
        try:
            while not stop.is_set():
                data = stream.readline() if kind == "stdout" else stream.read1(4096)
                if not data:
                    break
                put((kind, data.decode("utf-8", errors="replace")))
        except Exception as exc:
            put(("error", f"{kind} reader: {type(exc).__name__}"))
        finally:
            put((kind + "_end", ""))

    def writer():
        """Send the UTF-8 prompt and close stdin, tolerating a closed or missing pipe."""
        if process.stdin is None:
            return
        try:
            process.stdin.write(prompt.encode("utf-8"))
            process.stdin.close()
        except (BrokenPipeError, OSError, ValueError):
            pass  # The exit status / completion stream decides success.

    try:
        for fn, args in [(reader, (process.stdout,"stdout")),
                         (reader, (process.stderr,"stderr")), (writer, ())]:
            t = threading.Thread(target=fn, args=args, daemon=True)
            t.start(); threads.append(t)
        ended = set()
        while time.monotonic() < deadline:
            if len(ended) == 2 and process.poll() is not None:
                break
            try:
                kind, text = events.get(timeout=min(0.05, max(0.001, deadline-time.monotonic())))
            except queue.Empty:
                continue
            if kind.endswith("_end"):
                ended.add(kind)
            elif kind == "error":
                result.transport_error = text
            elif kind == "stderr":
                result.stderr = (result.stderr + text)[-65536:]
            else:
                if saved:
                    saved.write(text)
                if capture_stdout:
                    if len(result.stdout) + len(text) > 4 * 1024 * 1024:
                        result.transport_error = "stdout exceeded 4 MiB capture limit"
                        break
                    result.stdout += text
                if on_line and on_line(text):
                    result.stopped = True
                    break
        else:
            result.timed_out = True
        result.returncode = process.poll()
    finally:
        stop.set()
        _terminate(process)
        for t in threads:
            t.join(timeout=0.5)
        # Avoid closing a pipe whose blocked reader owns its Python lock.
        if not any(t.is_alive() for t in threads):
            for stream in (process.stdin, process.stdout, process.stderr):
                if stream is None:
                    continue
                try:
                    stream.close()
                except (OSError, ValueError):
                    pass
        if saved:
            saved.close()
    return result


def call_claude_text(prompt: str, *, cwd: Path, timeout=60, model=None, budget=None) -> str:
    """Return Claude text from a disposable profile, charging one budget attempt.

    The cwd argument is retained for callers; execution uses a temporary directory.
    Raise TimeoutError on deadline expiry or RuntimeError on transport or exit failure.
    """
    budget = budget if budget is not None else CallBudget()
    with model_environment() as (env, work):
        cmd = claude_command("-p", "--output-format", "text", *isolation_args(), *model_args(model))
        budget.consume()
        result = run_process(cmd, prompt, cwd=work, timeout=timeout, env=env)
    if result.timed_out:
        raise TimeoutError("Claude request timed out")
    if result.transport_error or result.returncode != 0:
        raise RuntimeError(result.transport_error or f"Claude exited {result.returncode}; isolated runs require ANTHROPIC_API_KEY or CLAUDE_CODE_OAUTH_TOKEN")
    return result.stdout
