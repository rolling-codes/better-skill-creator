#!/usr/bin/env python3
"""
Skill Intermediate Representation (IR) — canonical in-memory model for a skill.

All scripts that need to read skill state should use Skill.from_path() rather
than parsing SKILL.md and skill.yaml independently.
"""
from __future__ import annotations

import os
import shutil
import tempfile
import re
from typing import Optional, Dict, List, Tuple, Any, Union

try:
    import yaml
except ModuleNotFoundError:  # pragma: no cover
    raise SystemExit(
        "PyYAML is required by skill-creator's validation scripts.\n"
        "Install it with:  pip install -r requirements.txt\n"
        "(or:  pip install PyYAML)"
    )
from dataclasses import dataclass, field
from pathlib import Path


def _read_schema_version(fm: Dict[str, Any]) -> int:
    """Read schemaVersion from frontmatter metadata, falling back to the legacy
    top-level field so skills written by older versions still load."""
    meta = fm.get("metadata")
    if isinstance(meta, dict) and "schemaVersion" in meta:
        return int(meta["schemaVersion"])
    return int(fm.get("schemaVersion", 1))


def _read_allowed_tools(raw: Any) -> List[str]:
    """allowed-tools may be a YAML list or a space- or comma-separated string.

    Parenthesized patterns such as `Bash(git add *)` contain spaces, so split
    only on separators that sit outside parentheses.
    """
    if not raw:
        return []
    if isinstance(raw, list):
        return [str(t).strip() for t in raw if str(t).strip()]
    tools, buf, depth = [], "", 0
    for ch in str(raw):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        if depth == 0 and ch in " ,":
            if buf.strip():
                tools.append(buf.strip())
            buf = ""
        else:
            buf += ch
    if buf.strip():
        tools.append(buf.strip())
    return tools


@dataclass
class Skill:
    """Canonical in-memory representation of a Claude Code skill.
    
    Attributes:
        name: The skill identifier (kebab-case).
        description: User-facing description of what the skill does.
        allowed_tools: Claude Code tools pre-approved while the skill runs.
        schema_version: The skill.yaml schema version (default 1).
        compatibility: Optional compatibility notes (e.g., required Claude version).
        skill_path: Absolute path to the skill directory.
        body: SKILL.md content after the closing --- frontmatter delimiter.
        yaml_data: Raw skill.yaml dict; empty {} if file absent.
        dependencies: File paths declared in skill.yaml dependencies list.
        lifecycle: Lifecycle state (active, experimental, deprecated, archived).
        version: Semantic version of the skill (e.g., '2.0.0').
        author: Optional author/maintainer name.
    """
    name: str
    description: str
    allowed_tools: List[str]
    schema_version: int          # from schemaVersion frontmatter field (default 1)
    compatibility: Optional[str]
    skill_path: Path
    body: str                    # SKILL.md content after the closing ---
    yaml_data: Dict[str, Any]    # raw skill.yaml dict; empty {} if file absent
    dependencies: List[str]      # from skill.yaml dependencies list
    lifecycle: Optional[str]
    version: Optional[str]
    author: Optional[str]
    # Spec fields carried through a rewrite so write_skill_md never drops them.
    license: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    legacy_schema_key: bool = False  # schemaVersion found at top level (pre-2.2)
    model: Optional[str] = None      # model: frontmatter field (Claude Code skill runner)

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    @classmethod
    def from_path(cls, skill_path: Union[Path, str]) -> Skill:
        """Load a Skill from a directory that contains SKILL.md.
        
        Args:
            skill_path: Path to the skill directory (must contain SKILL.md).
            
        Returns:
            A Skill instance with all metadata loaded from SKILL.md and skill.yaml.
            
        Raises:
            FileNotFoundError: If SKILL.md is not found.
            ValueError: If SKILL.md or skill.yaml has invalid YAML or missing required fields.
        """
        skill_path = Path(skill_path).resolve()
        skill_md = skill_path / "SKILL.md"
        if not skill_md.exists():
            raise FileNotFoundError(f"SKILL.md not found in {skill_path}")

        content = skill_md.read_text(encoding="utf-8")
        if not content.startswith("---"):
            raise ValueError("SKILL.md missing opening --- frontmatter delimiter")

        # Find closing ---
        lines = content.split("\n")
        end_idx = None
        for i, line in enumerate(lines[1:], start=1):
            if line.strip() == "---":
                end_idx = i
                break
        if end_idx is None:
            raise ValueError("SKILL.md frontmatter has no closing ---")

        fm_text = "\n".join(lines[1:end_idx])
        body = "\n".join(lines[end_idx + 1:])

        try:
            fm = yaml.safe_load(fm_text) or {}
        except yaml.YAMLError as exc:
            raise ValueError(f"Invalid YAML in frontmatter: {exc}") from exc
        if not isinstance(fm, dict):
            raise ValueError("Frontmatter must be a YAML mapping")

        # skill.yaml (optional)
        yaml_data: Dict[str, Any] = {}
        syp = skill_path / "skill.yaml"
        if syp.exists():
            try:
                yaml_data = yaml.safe_load(syp.read_text(encoding="utf-8")) or {}
            except yaml.YAMLError as exc:
                raise ValueError(f"Invalid YAML in skill.yaml: {exc}") from exc
            if not isinstance(yaml_data, dict):
                raise ValueError("skill.yaml must be a YAML mapping")

        deps = yaml_data.get("dependencies", [])
        if not isinstance(deps, list):
            deps = []

        return cls(
            name=str(fm.get("name", "")).strip(),
            description=str(fm.get("description", "")).strip(),
            allowed_tools=_read_allowed_tools(fm.get("allowed-tools")),
            schema_version=_read_schema_version(fm),
            compatibility=fm.get("compatibility") or None,
            skill_path=skill_path,
            body=body,
            yaml_data=yaml_data,
            dependencies=[str(d) for d in deps],
            lifecycle=yaml_data.get("lifecycle") or None,
            version=str(yaml_data.get("version", "")) or None,
            author=str(yaml_data.get("author", "")) or None,
            license=fm.get("license") or None,
            metadata=dict(fm.get("metadata") or {}) if isinstance(fm.get("metadata"), dict) else {},
            legacy_schema_key="schemaVersion" in fm,
            model=fm.get("model") or None,
        )

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_frontmatter_dict(self) -> Dict[str, Any]:
        """Return ordered dict suitable for writing back to SKILL.md frontmatter.
        
        Returns:
            A dictionary with name, description, schemaVersion, and optional fields.
        """
        fm: Dict[str, Any] = {"name": self.name, "description": self.description}
        if self.license:
            fm["license"] = self.license
        if self.model:
            fm["model"] = self.model
        if self.allowed_tools:
            fm["allowed-tools"] = self.allowed_tools
        if self.compatibility:
            fm["compatibility"] = self.compatibility
        fm["metadata"] = {**self.metadata, "schemaVersion": str(self.schema_version)}
        return fm

    def write_skill_md(self) -> None:
        """Serialise frontmatter + body back to SKILL.md (in-place).
        
        Raises:
            OSError: If the file cannot be written.
        """
        fm_yaml = yaml.dump(
            self.to_frontmatter_dict(),
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
        ).rstrip()
        content = f"---\n{fm_yaml}\n---\n{self.body}"
        target = self.skill_path / "SKILL.md"
        handle = tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=target.parent,
            prefix=".SKILL.md.", suffix=".tmp", delete=False,
        )
        tmp = Path(handle.name)
        try:
            with handle:
                handle.write(content)
            if target.exists():
                # Copy the POSIX access ACL explicitly: copystat may silently
                # ignore xattr errors. Remove any ACL inherited by the temp file
                # if the original has none. Abort replacement on copy failure.
                if hasattr(os, "listxattr"):
                    acl = "system.posix_acl_access"
                    if acl in os.listxattr(target):
                        os.setxattr(tmp, acl, os.getxattr(target, acl))
                    elif acl in os.listxattr(tmp):
                        os.removexattr(tmp, acl)
                shutil.copystat(target, tmp)
            os.replace(tmp, target)
        finally:
            tmp.unlink(missing_ok=True)
