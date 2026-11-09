from __future__ import annotations

from scripts.compiler_context import CompilerContext
from scripts.file_policy import secret_exclusion_message
from scripts.static_analysis import Finding

_SKIP_DIRS = {"__pycache__", "node_modules", ".pytest_cache"}
_SKIP_SUFFIXES = {".pyc"}
_SCAN_DIRS = ("scripts", "agents")


def _is_declared(rel: str, deps: set[str]) -> bool:
    """Exact match or directory-prefix match ('scripts/stages/' covers all files under it)."""
    if rel in deps:
        return True
    return any(dep.endswith("/") and rel.startswith(dep) for dep in deps)


class DependencyStage:
    name = "dependency"
    requires = {"skill_spec"}
    provides = {"diagnostics"}

    def run(self, ctx: CompilerContext) -> None:
        sp = ctx.skill_path
        deps = set(ctx.skill_spec.dependencies)

        # Check declared dependencies exist on disk.
        # Secret-like names are a static-analysis error even when the file exists;
        # packaging removes them before this stage sees the copy.
        for dep in ctx.skill_spec.dependencies:
            shown = str(dep).replace("\\", "/").strip()
            if secret_exclusion_message(shown):
                continue
            if not (sp / dep).exists():
                ctx.diagnostics.append(Finding(
                    severity="error",
                    rule="missing-dependency",
                    message=f"Dependency listed in skill.yaml not found: {dep}",
                ))

        # Check for files in scripts/ and agents/ not declared in skill.yaml
        for scan_dir in _SCAN_DIRS:
            scan_path = sp / scan_dir
            if not scan_path.exists():
                continue
            for file_path in scan_path.rglob("*"):
                if not file_path.is_file():
                    continue
                parts = file_path.relative_to(sp).parts
                if any(p in _SKIP_DIRS for p in parts):
                    continue
                if file_path.suffix in _SKIP_SUFFIXES:
                    continue
                rel = "/".join(parts)
                if not _is_declared(rel, deps):
                    ctx.diagnostics.append(Finding(
                        severity="warning",
                        rule="undeclared-dependency",
                        message=f"File not declared in skill.yaml dependencies: {rel}",
                    ))
