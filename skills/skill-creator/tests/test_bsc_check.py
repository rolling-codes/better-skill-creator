"""`bsc.py check` must validate a Claude Code skill (with model:) as itself.

Regression guard for the dogfood bug where checks() called validate_skill() without
claude_code=True, so `python bsc.py check skills/skill-creator` always reported
'structure — failed: Unexpected key(s) ... model' on the repo's own skill.
"""
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SKILL_PATH = ROOT / "skills" / "skill-creator"

spec = importlib.util.spec_from_file_location("bsc", ROOT / "bsc.py")
assert spec and spec.loader
bsc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bsc)


def _structure_row(rows):
    assert rows and rows[0]["check"] == "structure"
    return rows[0]


def test_check_accepts_claude_code_skill():
    """Default check (claude_code=True) validates the skill's structure as valid."""
    row = _structure_row(bsc.checks(SKILL_PATH, claude_code=True))
    assert row["status"] == "passed", row["message"]


def test_strict_check_accepts_skill_without_model_key():
    """--strict (claude_code=False) passes now that model: has moved to metadata.target_model."""
    row = _structure_row(bsc.checks(SKILL_PATH, claude_code=False))
    assert row["status"] == "passed", row["message"]


def _report(runs):
    return json.loads(next(runs.glob("*/results.json")).read_text(encoding="utf-8"))


def test_check_next_action_distinguishes_warnings_from_errors(tmp_path):
    runs = tmp_path / "runs"
    code = bsc.main(["check", str(ROOT / "examples/release-notes"), "--runs-dir", str(runs)])
    result = _report(runs)
    assert code == result["exit_code"] == 0
    assert result["next_action"] == "Warnings found. Inspect them, then package or preview eval."

    bad = tmp_path / "bad-skill"
    bad.mkdir()
    (bad / "SKILL.md").write_text(
        '---\nname: ""\ndescription: present\n---\n# Bad\n\nBody.\n',
        encoding="utf-8",
    )
    bad_runs = tmp_path / "bad-runs"
    assert bsc.main(["check", str(bad), "--runs-dir", str(bad_runs)]) == 2
    assert _report(bad_runs)["next_action"] == (
        "Fix error findings, inspect warnings, then package or preview eval."
    )


def test_check_next_action_for_a_clean_skill(tmp_path):
    description = (
        "Drafts short notes from a request. Use when the user asks for a note or a summary. "
        "Not for sending email or publishing the result."
    )
    skill = tmp_path / "my-skill"
    skill.mkdir()
    (skill / "SKILL.md").write_text(
        f"---\nname: my-skill\ndescription: {description}\n---\n# Notes\n\nWrite the note.\n",
        encoding="utf-8",
    )
    runs = tmp_path / "runs"
    assert bsc.main(["check", str(skill), "--runs-dir", str(runs)]) == 0
    assert _report(runs)["next_action"] == "No blocking findings. Package the skill or preview an eval."


def _example_skill(tmp_path):
    import shutil
    skill = tmp_path / "release-note-draft"
    shutil.copytree(ROOT / "examples/release-notes", skill)
    return skill


def _static_messages(result):
    messages = []
    for row in result["checks"]:
        if row["check"] != "static":
            continue
        messages.extend(item["message"] for item in row.get("findings") or [])
    return messages


def test_check_and_package_agree_when_a_referenced_file_has_a_secret_like_name(tmp_path):
    """Issue 105: the file is on disk. Both commands must say the policy dropped it."""
    skill = _example_skill(tmp_path)
    (skill / "references").mkdir()
    (skill / "references" / "secrets.md").write_text("How to handle credentials.\n", encoding="utf-8")
    text = (skill / "SKILL.md").read_text(encoding="utf-8")
    text += "\n- `references/secrets.md` — Read when handling credentials.\n"
    (skill / "SKILL.md").write_text(text, encoding="utf-8")
    expected = (
        "`references/secrets.md` is excluded from packages because its name matches "
        "the secret-file pattern `secrets.*`; rename it to ship it."
    )

    check_runs = tmp_path / "check-runs"
    assert bsc.main(["check", str(skill), "--runs-dir", str(check_runs)]) == 2
    check = _report(check_runs)
    assert check["status"] == "failed"
    assert expected in _static_messages(check)
    assert "not found on disk" not in " ".join(_static_messages(check))

    package_runs = tmp_path / "package-runs"
    dist = tmp_path / "dist"
    assert bsc.main(["package", str(skill), "--output", str(dist), "--runs-dir", str(package_runs)]) == 2
    packaged = _report(package_runs)
    assert packaged["status"] == "failed"
    assert expected in _static_messages(packaged)
    assert "not found on disk" not in " ".join(_static_messages(packaged))
    assert "references/secrets.md" in packaged["excluded_files"]
    assert not list(dist.glob("*.skill"))
    report = next(package_runs.glob("*/report.md")).read_text(encoding="utf-8")
    assert "Files excluded by packaging policy" in report
    assert "`references/secrets.md`" in report


def test_package_report_lists_an_unreferenced_secret_and_still_ships(tmp_path):
    skill = _example_skill(tmp_path)
    (skill / ".env").write_text("SYNTHETIC-PRIVATE\n", encoding="utf-8")
    runs = tmp_path / "runs"
    dist = tmp_path / "dist"
    assert bsc.main(["package", str(skill), "--output", str(dist), "--runs-dir", str(runs)]) == 0
    result = _report(runs)
    assert ".env" in result["excluded_files"]
    assert "secret-name-excluded" not in json.dumps(result["checks"])
    archive = dist / "release-note-draft.skill"
    assert archive.is_file()
    import zipfile
    with zipfile.ZipFile(archive) as zf:
        assert not any(name.endswith("/.env") or name.endswith(".env") for name in zf.namelist())
        assert not any(b"SYNTHETIC-PRIVATE" in zf.read(name) for name in zf.namelist())


def test_package_reports_a_secret_like_skill_yaml_dependency(tmp_path):
    skill = _example_skill(tmp_path)
    (skill / "references").mkdir()
    (skill / "references" / "client.key").write_text("sample\n", encoding="utf-8")
    (skill / "skill.yaml").write_text(
        "name: release-note-draft\ndependencies:\n  - references/client.key\n",
        encoding="utf-8",
    )
    runs = tmp_path / "runs"
    assert bsc.main(["check", str(skill), "--runs-dir", str(runs)]) == 2
    messages = _static_messages(_report(runs))
    assert any("references/client.key" in message and "`*.key`" in message for message in messages)
    assert not any("not found" in message for message in messages)

    package_runs = tmp_path / "package-runs"
    assert bsc.main(["package", str(skill), "--output", str(tmp_path / "dist"), "--runs-dir", str(package_runs)]) == 2
    packaged = _static_messages(_report(package_runs))
    assert any("references/client.key" in message and "`*.key`" in message for message in packaged)
    assert not any("not found" in message or "missing" in message for message in packaged)


def test_failure_report_does_not_double_the_period(tmp_path, monkeypatch):
    runs = tmp_path / "runs"
    missing = tmp_path / "missing-skill"
    assert bsc.main(["check", str(missing), "--runs-dir", str(runs)]) == 1
    result = _report(runs)
    assert result["next_action"] == (
        "InputError: Target must be a skill directory containing SKILL.md. "
        "Correct this issue and retry."
    )

    skill = tmp_path / "present"
    skill.mkdir()
    (skill / "SKILL.md").write_text("placeholder\n", encoding="utf-8")

    def boom(*_args, **_kwargs):
        raise RuntimeError("disk full")

    monkeypatch.setattr(bsc, "checks", boom)
    bare = tmp_path / "bare-runs"
    assert bsc.main(["check", str(skill), "--runs-dir", str(bare)]) == 1
    assert _report(bare)["next_action"] == (
        "RuntimeError: disk full. Correct this issue and retry; use doctor for environment problems."
    )


def test_package_rejects_a_missing_or_non_directory_target(tmp_path):
    """Issue 108: package uses the same input error as check, not a raw exception."""
    expected = (
        "InputError: Target must be a skill directory containing SKILL.md. "
        "Correct this issue and retry."
    )
    missing = tmp_path / "nope"
    missing_runs = tmp_path / "missing-runs"
    assert bsc.main(["package", str(missing), "--output", str(tmp_path / "dist-a"), "--runs-dir", str(missing_runs)]) == 1
    missing_result = _report(missing_runs)
    assert missing_result["status"] == "incomplete"
    assert missing_result["next_action"] == expected
    assert "FileNotFoundError" not in missing_result["next_action"]
    assert "doctor" not in missing_result["next_action"]

    skill_file = tmp_path / "SKILL.md"
    skill_file.write_text("---\nname: x\n---\n", encoding="utf-8")
    file_runs = tmp_path / "file-runs"
    assert bsc.main(["package", str(skill_file), "--output", str(tmp_path / "dist-b"), "--runs-dir", str(file_runs)]) == 1
    file_result = _report(file_runs)
    assert file_result["next_action"] == expected
    assert "NotADirectoryError" not in file_result["next_action"]
