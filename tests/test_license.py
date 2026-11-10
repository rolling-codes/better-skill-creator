"""The project license states counted tests for the same product and for an inspired one."""
import json
from pathlib import Path
import tomllib

ROOT = Path(__file__).resolve().parents[1]


def test_project_license_matches_the_packaged_copy():
    project = (ROOT / "LICENSE").read_text(encoding="utf-8")
    packaged = (ROOT / "skills/skill-creator/LICENSE.txt").read_text(encoding="utf-8")
    assert project == packaged
    for phrase in (
        "Forty or more words in a row",
        "Twenty or more non-blank lines in a row",
        "70 percent of the",
        "15 words or fewer",
        "Test A. Release bytes.",
        "Test G. Wrapper.",
        "You may not sell the repository",
        "You may not post the repository",
        "The v3.7.4 downloads include this file.",
        "Each one\nincludes this file and is under it.",
    ):
        assert phrase in project
    assert "Apache License" not in project
    assert "Version 2.0, January 2004" not in project


def test_repository_does_not_ship_the_apache_license_text():
    assert not (ROOT / "LICENSE-APACHE-2.0").exists()
    assert not (ROOT / "skills/skill-creator/LICENSE-APACHE-2.0.txt").exists()


def test_license_identifier_is_consistent():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    plugin = json.loads((ROOT / ".claude-plugin/plugin.json").read_text(encoding="utf-8"))
    assert project["license"] == plugin["license"] == "LicenseRef-BSC-No-Resale-1.0"
    assert project["license-files"] == ["LICENSE"]
