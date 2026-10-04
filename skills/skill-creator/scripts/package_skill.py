#!/usr/bin/env python3
"""
Skill Packager - Creates a distributable .skill file of a skill folder

Usage (run as a module from the skill-creator directory):
    python -m scripts.package_skill <path/to/skill-folder> [output-directory] [--verbose]

Example:
    python -m scripts.package_skill skills/public/my-skill
    python -m scripts.package_skill skills/public/my-skill ./dist
    python -m scripts.package_skill skills/public/my-skill ./dist --verbose
"""
from __future__ import annotations

import sys
import time
import tempfile
from pathlib import Path
from scripts.quick_validate import validate_skill
from scripts.file_policy import snapshot, copy_snapshot
from scripts.compiler_context import CompilerContext, StageTrace
from scripts.stages import (
    LintStage, SemanticStage, DependencyStage, ReviewStage,
    RepairStage, ApplyRepairsStage, ScoreStage, PackageStage,
)


def _timed_run(stage, ctx: CompilerContext) -> None:
    """Run a stage and append a StageTrace entry to ctx.trace."""
    before_diag = len(ctx.diagnostics)
    before_repairs = len(ctx.repairs)
    before_applied = len(ctx.applied_fixes)
    t0 = time.monotonic()
    stage.run(ctx)
    ctx.trace.append(StageTrace(
        stage_name=stage.name,
        elapsed_ms=round((time.monotonic() - t0) * 1000, 1),
        diagnostics_added=len(ctx.diagnostics) - before_diag,
        repairs_proposed=len(ctx.repairs) - before_repairs,
        repairs_applied=len(ctx.applied_fixes) - before_applied,
    ))


def _print_trace(trace: list[StageTrace]) -> None:
    if not trace:
        return
    print("Stage trace:")
    print(f"  {'Stage':<22} {'ms':>7}  {'diag':>5}  {'repair':>6}  {'applied':>7}")
    print(f"  {'-'*22}  {'-'*5}  {'-'*5}  {'-'*6}  {'-'*7}")
    for t in trace:
        print(
            f"  {t.stage_name:<22} {t.elapsed_ms:>7.1f}"
            f"  {t.diagnostics_added:>5}  {t.repairs_proposed:>6}  {t.repairs_applied:>7}"
        )
    print()


def package_skill(skill_path, output_dir=None, verbose=False):
    """Package a private source snapshot; never repair the caller's files."""
    try:
        source = Path(skill_path).resolve(strict=True)
        files = snapshot(source, review=True)
        output = Path(output_dir).resolve() if output_dir else Path.cwd()
        with tempfile.TemporaryDirectory(prefix="bsc-package-") as temp:
            copy = Path(temp) / source.name
            copy_snapshot(files, copy)
            return _package_snapshot(copy, output, verbose)
    except (OSError, ValueError) as exc:
        print(f"ERROR: Cannot package skill: {exc}")
        return None


def _package_snapshot(skill_path, output_dir=None, verbose=False):
    """
    Package a skill folder into a .skill file.

    Args:
        skill_path: Path to the skill folder
        output_dir: Optional output directory for the .skill file (defaults to current directory)
        verbose: If True, print stage timing trace after completion

    Returns:
        Path to the created .skill file, or None if error
    """
    if hasattr(sys.stdout, "reconfigure"):
        getattr(sys.stdout, "reconfigure")(encoding="utf-8")

    skill_path = Path(skill_path).resolve()

    # Validate folder structure (unchanged)
    if not skill_path.exists():
        print(f"ERROR: Skill folder not found: {skill_path}")
        return None
    if not skill_path.is_dir():
        print(f"ERROR: Path is not a directory: {skill_path}")
        return None
    skill_md = skill_path / "SKILL.md"
    if not skill_md.exists():
        print(f"ERROR: SKILL.md not found in {skill_path}")
        return None

    # Reject unsafe source paths before any validator or repair reads them.
    try:
        snapshot(skill_path, review=True)
    except (OSError, ValueError) as exc:
        print(f"ERROR: Unsafe skill source: {exc}")
        return None

    # Quick structural validation (unchanged)
    print("Validating skill...")
    valid, message = validate_skill(skill_path)
    if not valid:
        print(f"ERROR: Validation failed: {message}")
        return None
    print(f"OK: {message}")

    # Build context
    ctx = CompilerContext.create(skill_path, output_dir)

    # Analysis pass
    print("Running analysis...")
    _timed_run(LintStage(), ctx)
    _timed_run(SemanticStage(), ctx)
    _timed_run(DependencyStage(), ctx)
    _timed_run(ReviewStage(), ctx)

    # Repair pass
    _timed_run(RepairStage(), ctx)
    _timed_run(ApplyRepairsStage(), ctx)

    if ctx.applied_fixes:
        print("  Auto-repaired:")
        for fix in ctx.applied_fixes:
            print(f"    {fix}")
        # Re-analyze after in-place repairs
        ctx.diagnostics.clear()
        ctx.trace.clear()
        _timed_run(LintStage(), ctx)
        _timed_run(SemanticStage(), ctx)
        _timed_run(DependencyStage(), ctx)
        _timed_run(ReviewStage(), ctx)

    # Report findings
    errors = [f for f in ctx.diagnostics if f.severity == "error"]
    if errors:
        for f in errors:
            print(f"  ERROR: {f}")
        print(f"\nERROR: {len(errors)} error(s) could not be auto-repaired. Fix before packaging.")
        if verbose:
            _print_trace(ctx.trace)
        return None
    for f in ctx.diagnostics:
        tag = "WARN" if f.severity == "warning" else "INFO"
        print(f"  {tag}: {f}")
    if not ctx.diagnostics and not ctx.applied_fixes:
        print("  No issues found.")
    print()

    # Score
    print("Architecture score...")
    _timed_run(ScoreStage(), ctx)
    if ctx.score:
        print(str(ctx.score))
        if ctx.score.overall < 70:
            print(f"\nWARN: Score {ctx.score.overall} is below 70. Consider improving before sharing.")
        else:
            print(f"\nOK: Score {ctx.score.overall}")
    print()

    # Package
    print("Packaging...")
    _timed_run(PackageStage(), ctx)

    if verbose:
        _print_trace(ctx.trace)

    if ctx.output_path:
        print(f"\nOK: Successfully packaged skill to: {ctx.output_path}")
        return ctx.output_path
    else:
        for finding in ctx.diagnostics:
            if finding.severity == "error":
                print(f"  ERROR: {finding}")
        print("ERROR: Packaging failed.")
        return None


def main():
    if hasattr(sys.stdout, "reconfigure"):
        getattr(sys.stdout, "reconfigure")(encoding="utf-8")

    verbose = "--verbose" in sys.argv
    args = [a for a in sys.argv[1:] if not a.startswith("--")]

    if not args:
        print("Usage: python -m scripts.package_skill <path/to/skill-folder> [output-directory] [--verbose]")
        print("\nExample:")
        print("  python -m scripts.package_skill skills/public/my-skill")
        print("  python -m scripts.package_skill skills/public/my-skill ./dist")
        print("  python -m scripts.package_skill skills/public/my-skill ./dist --verbose")
        sys.exit(1)

    skill_path = args[0]
    output_dir = args[1] if len(args) > 1 else None

    print(f"Packaging skill: {skill_path}")
    if output_dir:
        print(f"   Output directory: {output_dir}")
    print()

    result = package_skill(skill_path, output_dir, verbose=verbose)

    if result:
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
