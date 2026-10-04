#!/usr/bin/env python3
"""
Quick validation script for skills - structural and semantic checks.

Validates SKILL.md frontmatter, skill.yaml consistency, and test file presence.
Exit codes: 0 = valid, 1 = errors found, 2 = warnings only.
"""

import sys
import re
from typing import Tuple, Union

try:
    import yaml
except ModuleNotFoundError:  # pragma: no cover
    raise SystemExit(
        "PyYAML is required by skill-creator's validation scripts.\n"
        "Install it with:  pip install -r requirements.txt\n"
        "(or:  pip install PyYAML)"
    )
from pathlib import Path

LIFECYCLE_STATES = {'active', 'experimental', 'deprecated', 'archived'}


def _validate_frontmatter(frontmatter: dict, name: str) -> Tuple[bool, str]:
    """Validate SKILL.md frontmatter structure and required fields.
    
    Args:
        frontmatter: The parsed YAML frontmatter.
        name: The skill name (for cross-validation).
        
    Returns:
        Tuple of (is_valid, error_message).
    """
    # The Agent Skills spec fields. claude.ai uploads, the Skills API and the
    # upstream package_skill.py fail hard on any other top-level key.
    ALLOWED_PROPERTIES = {'name', 'description', 'license', 'allowed-tools',
                         'metadata', 'compatibility', 'model'}
    
    if 'schemaVersion' in frontmatter:
        return False, (
            "Top-level 'schemaVersion' is not an Agent Skills spec field, so claude.ai "
            "and the Skills API will reject this skill. Move it under metadata, e.g. "
            "'metadata: {schemaVersion: \"1\"}', or run scripts/migrate_skill.py."
        )
    metadata = frontmatter.get('metadata')
    if metadata is not None and not isinstance(metadata, dict):
        return False, f"metadata must be a mapping, got {type(metadata).__name__}"
    if isinstance(metadata, dict) and 'schemaVersion' in metadata:
        try:
            int(metadata['schemaVersion'])
        except (TypeError, ValueError, OverflowError):
            return False, "metadata.schemaVersion must be an integer"
    
    unexpected_keys = set(frontmatter.keys()) - ALLOWED_PROPERTIES
    if unexpected_keys:
        return False, (
            f"Unexpected key(s) in SKILL.md frontmatter: {', '.join(sorted(unexpected_keys))}. "
            f"Allowed properties are: {', '.join(sorted(ALLOWED_PROPERTIES))}"
        )
    
    # Validate name
    if not isinstance(name, str):
        return False, f"Name must be a string, got {type(name).__name__}"
    name = name.strip()
    if name:
        if not re.match(r'^[a-z0-9-]+$', name):
            return False, f"Name '{name}' should be kebab-case (lowercase letters, digits, and hyphens only)"
        if name.startswith('-') or name.endswith('-') or '--' in name:
            return False, f"Name '{name}' cannot start/end with hyphen or contain consecutive hyphens"
        if len(name) > 64:
            return False, f"Name is too long ({len(name)} characters). Maximum is 64 characters."
    
    # Validate description
    description = frontmatter.get('description', '')
    if not isinstance(description, str):
        return False, f"Description must be a string, got {type(description).__name__}"
    description = description.strip()
    if description:
        if '<' in description or '>' in description:
            return False, "Description cannot contain angle brackets (< or >)"
        if len(description) > 1024:
            return False, f"Description is too long ({len(description)} characters). Maximum is 1024 characters."
    
    # Validate compatibility
    compatibility = frontmatter.get('compatibility', '')
    if compatibility:
        if not isinstance(compatibility, str):
            return False, f"Compatibility must be a string, got {type(compatibility).__name__}"
        if len(compatibility) > 500:
            return False, f"Compatibility is too long ({len(compatibility)} characters). Maximum is 500 characters."
    
    # Validate allowed-tools
    allowed_tools = frontmatter.get('allowed-tools')
    if allowed_tools is not None:
        is_list = isinstance(allowed_tools, list) and all(isinstance(t, str) for t in allowed_tools)
        if not (is_list or isinstance(allowed_tools, str)):
            return False, "allowed-tools must be a list of strings or a space/comma separated string"
    
    return True, ""


def validate_skill(skill_path: Union[str, Path]) -> Tuple[bool, str]:
    """Validate a skill directory.
    
    Args:
        skill_path: Path to the skill directory.
        
    Returns:
        Tuple of (is_valid, message).
    """
    skill_path = Path(skill_path)

    # Check SKILL.md exists
    skill_md = skill_path / 'SKILL.md'
    if not skill_md.exists():
        return False, "SKILL.md not found"

    # Read and validate frontmatter
    try:
        content = skill_md.read_text(encoding="utf-8")
    except OSError as e:
        return False, f"Cannot read SKILL.md: {e}"
    
    if not content.startswith('---'):
        return False, "No YAML frontmatter found"

    # Extract frontmatter
    match = re.match(r'^---\n(.*?)\n---', content, re.DOTALL)
    if not match:
        return False, "Invalid frontmatter format"

    frontmatter_text = match.group(1)

    # Parse YAML frontmatter
    try:
        frontmatter = yaml.safe_load(frontmatter_text)
        if not isinstance(frontmatter, dict):
            return False, "Frontmatter must be a YAML dictionary"
    except yaml.YAMLError as e:
        return False, f"Invalid YAML in frontmatter: {e}"

    # Check required fields
    if 'name' not in frontmatter:
        return False, "Missing 'name' in frontmatter"
    if 'description' not in frontmatter:
        return False, "Missing 'description' in frontmatter"

    name = frontmatter.get('name', '')
    is_valid, msg = _validate_frontmatter(frontmatter, name)
    if not is_valid:
        return False, msg

    # Validate skill.yaml if present
    skill_yaml = skill_path / 'skill.yaml'
    if skill_yaml.exists():
        try:
            skill_yaml_data = yaml.safe_load(skill_yaml.read_text(encoding="utf-8"))
        except yaml.YAMLError as e:
            return False, f"Invalid YAML in skill.yaml: {e}"
        if not isinstance(skill_yaml_data, dict):
            return False, "skill.yaml must be a YAML dictionary"
        if skill_yaml_data.get('name') != name:
            return False, (
                f"skill.yaml name '{skill_yaml_data.get('name')}' does not match "
                f"SKILL.md frontmatter name '{name}'"
            )
        
        if skill_yaml_data.get('lifecycle') is not None:
            yaml_lifecycle = skill_yaml_data.get('lifecycle')
            if yaml_lifecycle not in LIFECYCLE_STATES:
                return False, (
                    f"skill.yaml lifecycle '{yaml_lifecycle}' is not one of "
                    f"{sorted(LIFECYCLE_STATES)}"
                )
        
        # Validate dependencies exist
        if skill_yaml_data.get('dependencies'):
            deps = skill_yaml_data['dependencies']
            if not isinstance(deps, list):
                return False, "skill.yaml dependencies must be a list"
            missing = [d for d in deps if not (skill_path / d).exists()]
            if missing:
                return False, f"skill.yaml declares missing dependencies: {missing}"
    
    # Check LIFECYCLE.md consistency if present
    lifecycle_md = skill_path / 'LIFECYCLE.md'
    if skill_yaml.exists() and lifecycle_md.exists():
        yaml_lifecycle = skill_yaml_data.get('lifecycle') if skill_yaml_data else None
        try:
            lifecycle_text = lifecycle_md.read_text(encoding="utf-8")
        except OSError as e:
            return False, f"Cannot read LIFECYCLE.md: {e}"
        
        status_match = re.search(r'^status:\s*(\S+)', lifecycle_text, re.MULTILINE)
        if status_match:
            md_status = status_match.group(1)
            if md_status not in LIFECYCLE_STATES:
                return False, (
                    f"LIFECYCLE.md status '{md_status}' is not one of {sorted(LIFECYCLE_STATES)}"
                )
            if yaml_lifecycle and yaml_lifecycle != md_status:
                return False, (
                    f"Lifecycle mismatch: skill.yaml says '{yaml_lifecycle}', "
                    f"LIFECYCLE.md says '{md_status}'"
                )
    
    # Validate PERMISSIONS.md consistency
    permissions_md = skill_path / 'PERMISSIONS.md'
    allowed_tools = frontmatter.get('allowed-tools')
    # allowed-tools is a pre-approval grant, not a capability declaration, so
    # PERMISSIONS.md existing is no reason to require one.
    del permissions_md, allowed_tools
    
    # Validate tests/ directory if present
    tests_dir = skill_path / 'tests'
    if tests_dir.exists():
        known_test_files = {'should_trigger.yaml', 'should_not_trigger.yaml', 'expected_behavior.yaml'}
        present = {f.name for f in tests_dir.iterdir() if f.is_file()}
        if not present & known_test_files:
            return False, (
                f"tests/ directory exists but contains none of {sorted(known_test_files)}"
            )
        for fname in present & known_test_files:
            try:
                data = yaml.safe_load((tests_dir / fname).read_text(encoding="utf-8"))
            except yaml.YAMLError as e:
                return False, f"Invalid YAML in tests/{fname}: {e}"
            if not isinstance(data, list) or len(data) == 0:
                return False, f"tests/{fname} must be a non-empty YAML list"

    return True, "Skill is valid!"


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python quick_validate.py <skill_directory>", file=sys.stderr)
        sys.exit(1)
    
    valid, message = validate_skill(sys.argv[1])
    print(message)
    sys.exit(0 if valid else 1)
