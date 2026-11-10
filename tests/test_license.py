"""The project license forbids resale of the same product and specifies the split."""
import json
from pathlib import Path
import tomllib

ROOT = Path(__file__).resolve().parents[1]


def test_project_license_matches_the_packaged_copy():
    project = (ROOT / "LICENSE").read_text(encoding="utf-8")
    packaged = (ROOT / "skills/skill-creator/LICENSE.txt").read_text(encoding="utf-8")
    assert project == packaged
    for phrase in (
        "You may not sell this project.",
        "You may not publicly reproduce this project.",
        "A work is the same thing as this project when any one of these is true:",
        "A work is an inspired version, which you may publish and sell, only when all",
        "mechanical transformation of this project",
        "different implementation",
        "If you are unsure, treat the work as the same thing",
    ):
        assert phrase in project


def test_upstream_apache_text_stays_available():
    root = (ROOT / "LICENSE-APACHE-2.0").read_text(encoding="utf-8")
    packaged = (ROOT / "skills/skill-creator/LICENSE-APACHE-2.0.txt").read_text(encoding="utf-8")
    assert root == packaged
    assert "Apache License" in root
    assert "Version 2.0, January 2004" in root


def test_license_identifier_is_consistent():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    plugin = json.loads((ROOT / ".claude-plugin/plugin.json").read_text(encoding="utf-8"))
    assert project["license"] == plugin["license"] == "LicenseRef-BSC-No-Resale-1.0"
    assert "LICENSE-APACHE-2.0" in project["license-files"]
