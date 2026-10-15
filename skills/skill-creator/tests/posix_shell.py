"""Find a bash that actually runs scripts.

On Windows, ``bash`` on PATH is often ``System32\\bash.exe``, the WSL launcher.
With no distribution installed it exits before the script runs. Git for Windows
ships a real bash, and GitHub Actions uses that for ``shell: bash``.
"""
from __future__ import annotations

import subprocess
import sys
from functools import lru_cache
from pathlib import Path


def _candidates() -> list[str]:
    found: list[str] = []
    if sys.platform == "win32":
        try:
            exec_path = subprocess.check_output(
                ["git", "--exec-path"], text=True, stderr=subprocess.DEVNULL,
            ).strip().strip('"')
        except (OSError, subprocess.CalledProcessError):
            exec_path = ""
        if exec_path:
            # <Git>/mingw64/libexec/git-core -> <Git>/bin/bash.exe
            exec_dir = Path(exec_path)
            if len(exec_dir.parents) >= 3:
                root = exec_dir.parents[2]
                found.append(str(root / "bin" / "bash.exe"))
                found.append(str(root / "usr" / "bin" / "bash.exe"))
        try:
            listed = subprocess.check_output(
                ["where.exe", "bash"], text=True, stderr=subprocess.DEVNULL,
            )
        except (OSError, subprocess.CalledProcessError):
            listed = ""
        found.extend(line.strip() for line in listed.splitlines() if line.strip())
    found.append("bash")
    return list(dict.fromkeys(found))


@lru_cache(maxsize=1)
def bash_executable() -> str:
    """Return a bash that can execute ``-c`` and script files.

    Candidates that exit without running the command, including the Windows
    WSL launcher, are skipped.
    """
    for candidate in _candidates():
        try:
            result = subprocess.run(
                [candidate, "-c", "printf ok"],
                capture_output=True, text=True, timeout=15,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        if result.returncode == 0 and result.stdout.strip() == "ok":
            return candidate
    return "bash"
