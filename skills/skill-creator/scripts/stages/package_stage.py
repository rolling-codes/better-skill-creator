from __future__ import annotations
import zipfile
from pathlib import Path
from scripts.compiler_context import CompilerContext
from scripts.file_policy import excluded, snapshot, package_files
from scripts.types import Finding
from scripts.skill_md_utils import extract_referenced_files, extract_referenced_dirs

def _should_exclude(rel_path: Path) -> bool:
    """Apply source exclusions to an archive path after removing its skill-name prefix."""
    return excluded(Path(*rel_path.parts[1:]))


class PackageStage:
    name = "package"
    requires = {"skill_spec"}
    provides = {"output_path"}

    def run(self, ctx: CompilerContext) -> None:
        """Write a new archive from permitted source bytes and set ctx.output_path.

        Block on existing errors or unsafe or omitted resources, recording source
        failures as diagnostics. Preserve file modes and refuse to overwrite archives.
        """
        # Fail closed: never write a .skill while error-severity diagnostics are
        # outstanding (e.g. an unresolved review gate). The package_skill.py driver
        # already gates before reaching here, but enforcing it in the stage too means
        # a caller invoking StageRegistry.run_all directly can't bypass the gate.
        errors = [f for f in ctx.diagnostics if getattr(f, "severity", None) == "error"]
        if errors:
            ctx.output_path = None
            return

        skill_path = ctx.skill_path
        skill_name = skill_path.name
        out_dir = ctx.output_dir if ctx.output_dir else Path.cwd()
        out_dir.mkdir(parents=True, exist_ok=True)
        skill_filename = out_dir / f"{skill_name}.skill"

        try:
            available = snapshot(skill_path)
            files = package_files(available)
            references = set(ctx.skill_spec.dependencies) | extract_referenced_files(ctx.skill_spec.body)
            directories = extract_referenced_dirs(ctx.skill_spec.body)
            omitted = [name for name in available if name not in files and
                       (name in references or any(name.startswith(d.rstrip('/') + '/') for d in references | directories))]
            if omitted:
                raise ValueError(f'Package manifest omits referenced files: {", ".join(omitted)}')
        except (OSError, ValueError) as exc:
            ctx.diagnostics.append(Finding("error", "unsafe-source", str(exc)))
            ctx.output_path = None
            return
        # Exclusive creation also rejects existing files and dangling symlinks.
        with skill_filename.open("xb") as output:
            with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as zipf:
                for name, item in files.items():
                    entry = zipfile.ZipInfo(f"{skill_name}/{name}")
                    entry.external_attr = (0o100000 | item.mode) << 16
                    entry.compress_type = zipfile.ZIP_DEFLATED
                    zipf.writestr(entry, item.data)
                    print(f"  Added: {skill_name}/{name}")

        ctx.output_path = skill_filename
