"""Shared utilities for skill-creator scripts."""

from __future__ import annotations

from pathlib import Path
from typing import Tuple, Union

from scripts.skill_ir import Skill


def parse_skill_md(skill_path: Union[Path, str]) -> Tuple[str, str, str]:
    """Parse a SKILL.md file, returning (name, description, full_content).

    Delegates to Skill.from_path() so all scripts share one parsing path.
    Signature kept identical to preserve existing callers.
    
    Args:
        skill_path: Path to the skill directory containing SKILL.md.
        
    Returns:
        A tuple of (skill_name, skill_description, skill_md_full_content).
        
    Raises:
        FileNotFoundError: If SKILL.md is not found.
        ValueError: If SKILL.md has invalid YAML frontmatter.
    """
    skill_path = Path(skill_path)
    skill = Skill.from_path(skill_path)
    content = (skill_path / "SKILL.md").read_text(encoding="utf-8-sig")
    return skill.name, skill.description, content


def safe_path_exists(base_path: Path, relative_path: Union[str, Path]) -> bool:
    """Safely check if a path exists, preventing directory traversal attacks.
    
    Args:
        base_path: The base directory to check within.
        relative_path: The relative path to check (must not escape base_path).
        
    Returns:
        True if the path exists and is within base_path, False otherwise.
    """
    try:
        target = (base_path / relative_path).resolve()
        base = base_path.resolve()
        try:
            target.relative_to(base)
        except ValueError:
            return False
        return target.exists()
    except (ValueError, OSError):
        return False
