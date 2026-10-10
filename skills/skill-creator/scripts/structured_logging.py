"""Structured logging and error handling for skill-creator scripts.

Provides consistent logging, error context, and exception types across
the skill-creator pipeline to replace silent failures with actionable diagnostics.
"""

from __future__ import annotations

import json
import logging
import sys
from dataclasses import dataclass, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional


class ErrorCategory(Enum):
    """Categories of errors in skill evaluation and processing."""
    TIMEOUT = "timeout"
    SUBPROCESS_CRASH = "subprocess_crash"
    AUTHENTICATION = "authentication"
    NOT_TRIGGERED = "not_triggered"
    PARSING = "parsing"
    VALIDATION = "validation"
    IO = "io"
    UNKNOWN = "unknown"


@dataclass
class EvalError:
    """Structured error context from skill evaluation."""
    category: ErrorCategory
    query: str
    message: str
    elapsed_seconds: float
    stderr: Optional[str] = None
    returncode: Optional[int] = None
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.utcnow().isoformat()

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            **asdict(self),
            "category": self.category.value,
        }

    def __str__(self) -> str:
        s = f"[{self.category.value.upper()}] {self.message}"
        if self.returncode is not None:
            s += f" (exit code: {self.returncode})"
        if self.elapsed_seconds:
            s += f" ({self.elapsed_seconds:.1f}s)"
        return s


@dataclass
class QueryOutcome:
    """Outcome of a single trigger-query run.

    A clean `triggered` or `not_triggered` completion is trustworthy signal.
    Any other category is an execution *failure* (timeout, auth, crash,
    malformed output) — it must never be counted as a passing negative test.
    Picklable so it can cross the ProcessPoolExecutor boundary in run_eval.
    """
    triggered: bool
    ok: bool
    category: Optional[ErrorCategory] = None
    detail: str = ""
    # Cost/usage/duration recovered from the Claude `result` event when present.
    # None (never 0) when the run short-circuited before the result arrived, so
    # aggregation can distinguish "not measured" from a real zero.
    metrics: Optional[dict] = None

    @property
    def failed(self) -> bool:
        return not self.ok

    def to_dict(self) -> dict[str, Any]:
        return {
            "triggered": self.triggered,
            "ok": self.ok,
            "category": self.category.value if self.category else None,
            "detail": self.detail,
            "metrics": self.metrics,
        }

    @classmethod
    def triggered_ok(cls, metrics: Optional[dict] = None) -> "QueryOutcome":
        return cls(triggered=True, ok=True, category=None, metrics=metrics)

    @classmethod
    def not_triggered_ok(cls, metrics: Optional[dict] = None) -> "QueryOutcome":
        return cls(triggered=False, ok=True, category=ErrorCategory.NOT_TRIGGERED, metrics=metrics)

    @classmethod
    def failure(cls, category: ErrorCategory, detail: str = "") -> "QueryOutcome":
        return cls(triggered=False, ok=False, category=category, detail=detail)


class SkillCreatorException(Exception):
    """Base exception for skill-creator errors."""
    pass


class RunEvalException(SkillCreatorException):
    """Raised when skill evaluation fails."""
    def __init__(self, error: EvalError):
        self.error = error
        super().__init__(str(error))


class ValidationException(SkillCreatorException):
    """Raised when skill validation fails."""
    pass


class StructuredLogger:
    """Logger that outputs structured JSON for integration with tools and CI/CD."""

    def __init__(self, name: str, log_file: Optional[Path] = None):
        self.name = name
        self.log_file = log_file
        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.DEBUG)

        # Console handler (human-readable)
        console_handler = logging.StreamHandler(sys.stderr)
        console_handler.setLevel(logging.INFO)
        console_formatter = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        console_handler.setFormatter(console_formatter)
        self.logger.addHandler(console_handler)

        # File handler (structured JSON)
        if log_file:
            file_handler = logging.FileHandler(log_file)
            file_handler.setLevel(logging.DEBUG)
            file_formatter = logging.Formatter("%(message)s")
            file_handler.setFormatter(file_formatter)
            self.logger.addHandler(file_handler)

    def error_eval(self, error: EvalError) -> None:
        """Log an evaluation error with full context."""
        self.logger.error(f"Eval error: {error}")
        if self.log_file:
            self.log_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.log_file, "a") as f:
                f.write(json.dumps(error.to_dict()) + "\n")

    def info(self, message: str, context: Optional[dict[str, Any]] = None) -> None:
        """Log info with optional JSON context."""
        self.logger.info(message)
        if context and self.log_file:
            self.log_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.log_file, "a") as f:
                f.write(json.dumps({"level": "info", "message": message, **context}) + "\n")

    def warning(self, message: str, context: Optional[dict[str, Any]] = None) -> None:
        """Log warning with optional JSON context."""
        self.logger.warning(message)
        if context and self.log_file:
            self.log_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.log_file, "a") as f:
                f.write(json.dumps({"level": "warning", "message": message, **context}) + "\n")

    def debug(self, message: str, context: Optional[dict[str, Any]] = None) -> None:
        """Log debug with optional JSON context."""
        self.logger.debug(message)
        if context and self.log_file:
            self.log_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.log_file, "a") as f:
                f.write(json.dumps({"level": "debug", "message": message, **context}) + "\n")
