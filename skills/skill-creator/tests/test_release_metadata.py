"""Release metadata and the development-practices reference stay discoverable."""
import importlib.util
import json
from pathlib import Path
import re

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
SKILL_ROOT = ROOT / "skills" / "skill-creator"
spec = importlib.util.spec_from_file_location("bsc", ROOT / "bsc.py")
assert spec and spec.loader
bsc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bsc)


def test_release_version_agrees_across_manifests_and_readme():
    plugin = json.loads((ROOT / ".claude-plugin/plugin.json").read_text(encoding="utf-8"))
    manifest = yaml.safe_load((SKILL_ROOT / "skill.yaml").read_text(encoding="utf-8"))
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    badge = re.search(
        r"\[!\[Release v([^\]]+)\]\(https://img\.shields\.io/badge/release-v([^-]+)-blue\.svg\)\]"
        r"\(https://github\.com/rolling-codes/better-skill-creator/releases/tag/v([^)]+)\)",
        readme,
    )

    assert badge is not None, "README must expose the release badge and release link"
    assert plugin["version"] == manifest["version"] == bsc.VERSION
    assert badge.groups() == (bsc.VERSION,) * 3


def test_version_flag_reports_release_without_creating_reports(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)

    with pytest.raises(SystemExit) as exc:
        bsc.main(["--version"])

    assert exc.value.code == 0
    captured = capsys.readouterr()
    assert captured.out == bsc.VERSION + "\n"
    assert captured.err == ""
    assert list(tmp_path.iterdir()) == []


def test_development_practices_is_declared_and_linked_from_skill():
    reference = "references/development-practices.md"
    manifest = yaml.safe_load((SKILL_ROOT / "skill.yaml").read_text(encoding="utf-8"))
    skill_md = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
    workflow, heading, reference_section = skill_md.partition("## Reference files")

    assert reference in manifest["dependencies"]
    assert (SKILL_ROOT / reference).read_text(encoding="utf-8").strip()
    assert heading, "SKILL.md must provide the reference index"
    assert f"`{reference}`" in workflow, "Development guidance must be reachable during design"
    assert f"`{reference}`" in reference_section
