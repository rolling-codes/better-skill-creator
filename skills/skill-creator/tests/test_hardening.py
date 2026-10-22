"""Regressions for verified hardening fixes: repair, reference containment, packaging policy, transcripts."""
from __future__ import annotations

import json
import sys
import textwrap
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.claude_process import run_process
from scripts.file_policy import excluded
from scripts.skill_ir import Skill
from scripts.static_analysis import analyze


def _skill(root: Path, frontmatter: str, body: str) -> Path:
    root.mkdir(parents=True)
    (root / "SKILL.md").write_text(f"---\n{textwrap.dedent(frontmatter).strip()}\n---\n{body}", encoding="utf-8")
    return root


def test_rewriting_skill_md_keeps_frontmatter_keys_the_toolkit_does_not_model(tmp_path):
    """repair rewrites SKILL.md in place; argument-hint/context/etc. must not be silently deleted."""
    root = _skill(tmp_path / "s", """
        name: probe
        description: Probe skill for rewrite tests.
        argument-hint: "[file]"
        disable-model-invocation: true
        context: fork
        """, "\n# Probe\n")
    skill = Skill.from_path(root)
    skill.description = "Changed by a repair."
    skill.write_skill_md()

    text = (root / "SKILL.md").read_text(encoding="utf-8")
    frontmatter = yaml.safe_load(text.split("---")[1])
    assert frontmatter["description"] == "Changed by a repair."
    assert frontmatter["argument-hint"] == "[file]"
    assert frontmatter["disable-model-invocation"] is True
    assert frontmatter["context"] == "fork"
    assert list(frontmatter)[:2] == ["name", "description"]


def test_reference_that_escapes_the_skill_directory_is_an_error(tmp_path):
    """A `../outside` reference exists on disk but is never packaged, so it must not pass as valid."""
    (tmp_path / "outside").mkdir()
    (tmp_path / "outside" / "secret.md").write_text("x", encoding="utf-8")
    root = _skill(tmp_path / "s", """
        name: probe
        description: Probe skill for containment tests.
        """, "\n# Probe\n\n## Reference files\n\n- `../outside/secret.md` — outside\n- `references/real.md` — inside\n")
    (root / "references").mkdir()
    (root / "references" / "real.md").write_text("ok", encoding="utf-8")

    errors = {f.rule: f for f in analyze(Skill.from_path(root)) if f.severity == "error"}
    assert "reference-escapes-skill" in errors
    assert "../outside/secret.md" in errors["reference-escapes-skill"].message
    assert "dead-reference" not in errors  # the in-skill reference resolves


def test_asset_reference_that_climbs_out_is_an_error(tmp_path):
    (tmp_path / "x.png").write_text("x", encoding="utf-8")
    root = _skill(tmp_path / "s", """
        name: probe
        description: Probe skill for containment tests.
        """, "\n# Probe\n\nUse assets/../../x.png here.\n")
    assert "reference-escapes-skill" in {f.rule for f in analyze(Skill.from_path(root))}


def test_evals_exclusion_is_case_insensitive_but_review_still_includes_it():
    assert excluded(Path("evals/x.md")) and excluded(Path("Evals/x.md")) and excluded(Path("EVALS/x.md"))
    assert not excluded(Path("Evals/x.md"), review=True)


def test_more_credential_file_types_are_never_packaged():
    for name in ("cert.pfx", "cert.p12", "store.jks", "app.keystore", "id_dsa", "id_ecdsa.pub", ".git-credentials"):
        assert excluded(Path("refs") / name), name
    assert not excluded(Path("references/guide.md"))


def test_saved_transcript_is_byte_faithful(tmp_path):
    """Text-mode newline translation on Windows turned \n into \r\n in the saved transcript."""
    transcript = tmp_path / "t.jsonl"
    # bytes([...]) avoids embedded quotes, which Windows command-line parsing mangles.
    script = "import sys; sys.stdout.buffer.write(bytes([123, 10, 125, 10]))"
    run_process([sys.executable, "-c", script], "", cwd=tmp_path, timeout=30, transcript=transcript)
    assert transcript.read_bytes() == b"{\n}\n"


# --------------------------------------------------------------------------- #
# quick_validate: malformed input is a validation error, never a traceback
# --------------------------------------------------------------------------- #
def _valid_skill(root: Path) -> Path:
    return _skill(root, """
        name: probe
        description: Probe skill for validation tests. Use when probing validation behaviour.
        """, "\n# Probe\n")


def test_non_string_lifecycle_is_a_validation_error_not_a_crash(tmp_path):
    from scripts.quick_validate import validate_skill

    root = _valid_skill(tmp_path / "s")
    (root / "skill.yaml").write_text("name: probe\nlifecycle: [a]\n", encoding="utf-8")
    ok, message = validate_skill(root)
    assert ok is False
    assert "lifecycle" in message


def test_tests_path_that_is_a_file_is_a_validation_error_not_a_crash(tmp_path):
    from scripts.quick_validate import validate_skill

    root = _valid_skill(tmp_path / "s")
    (root / "tests").write_text("not a directory", encoding="utf-8")
    ok, message = validate_skill(root)
    assert ok is False
    assert "tests" in message


# --------------------------------------------------------------------------- #
# run_loop: a failing improve step keeps the iterations already completed
# --------------------------------------------------------------------------- #
def test_improve_failure_stops_cleanly_and_keeps_completed_iterations(monkeypatch, tmp_path):
    from scripts import run_loop as RL

    eval_set = [{"query": "q1", "should_trigger": True}, {"query": "q2", "should_trigger": False}]
    canned = {
        "results": [
            {"query": "q1", "should_trigger": True, "pass": False, "triggers": 0, "runs": 1, "trigger_rate": 0.0},
            {"query": "q2", "should_trigger": False, "pass": True, "triggers": 0, "runs": 1, "trigger_rate": 0.0},
        ],
        "summary": {"total": 2, "passed": 1, "failed": 1},
    }
    monkeypatch.setattr(RL, "run_eval", lambda **kw: canned)
    monkeypatch.setattr(RL, "parse_skill_md", lambda p: ("demo", "desc", "content"))

    def failing_improve(**kw):
        raise TimeoutError("improver timed out")

    monkeypatch.setattr(RL, "improve_description", failing_improve)

    out = RL.run_loop(
        eval_set=eval_set, skill_path=tmp_path, description_override=None,
        num_workers=1, timeout=5, max_iterations=3, runs_per_query=1,
        trigger_threshold=0.5, holdout=0, model="x", verbose=False,
        live_report_path=None, log_dir=None,
    )

    assert out["exit_reason"].startswith("infrastructure_failed (improve, iteration 1")
    assert "TimeoutError" in out["exit_reason"]
    assert len(out["history"]) == 1, "the completed iteration must not be lost"


def test_runtime_looking_prefix_cannot_smuggle_a_reference_out_of_the_skill(tmp_path):
    """evals/../../x.md starts with a runtime-output prefix but resolves outside the skill."""
    (tmp_path / "outside.md").write_text("x", encoding="utf-8")
    root = _skill(tmp_path / "s", """
        name: probe
        description: Probe skill for containment tests.
        """, "\n# Probe\n\n## Reference files\n\n- `evals/../../outside.md` — escapes\n- `evals/evals.json` — runtime output, fine\n")
    messages = [f.message for f in analyze(Skill.from_path(root)) if f.rule == "reference-escapes-skill"]
    assert len(messages) == 1 and "evals/../../outside.md" in messages[0]


def test_backslash_traversal_is_an_escape_on_every_platform(tmp_path):
    r"""On POSIX `..\outside.md` is a single odd filename; on Windows it climbs out. Treat both as escaping."""
    (tmp_path / "outside.md").write_text("x", encoding="utf-8")
    root = _skill(tmp_path / "s", """
        name: probe
        description: Probe skill for containment tests.
        """, "\n# Probe\n\n## Reference files\n\n- `..\\outside.md` — escapes\n")
    assert "reference-escapes-skill" in {f.rule for f in analyze(Skill.from_path(root))}


# --------------------------------------------------------------------------- #
# Containment edge cases raised in code review
# --------------------------------------------------------------------------- #
def test_asset_reference_with_backslash_traversal_is_checked_in_full(tmp_path):
    r"""The asset pattern used to stop at the first backslash, so assets/..\..\x was checked truncated."""
    (tmp_path / "outside.png").write_text("x", encoding="utf-8")
    root = _skill(tmp_path / "s", """
        name: probe
        description: Probe skill for containment tests.
        """, "\n# Probe\n\nUse assets/..\\..\\outside.png here.\n")
    messages = [f.message for f in analyze(Skill.from_path(root)) if f.rule == "reference-escapes-skill"]
    assert len(messages) == 1 and "assets/..\\..\\outside.png" in messages[0]


import pytest as _pytest  # noqa: E402 - local alias keeps the helper block above import-free


@_pytest.mark.parametrize("ref, expected", [
    ("C:/secret.md", True), ("C:secret.md", True), ("c:\\secret.md", True),
    ("\\\\server\\share\\x.md", True), ("/etc/passwd", True),
    ("references/guide.md", False), ("evals/evals.json", False), ("a/b-c_d.md", False),
])
def test_foreign_platform_absolute_references_are_recognised_on_any_host(ref, expected):
    from scripts.static_analysis import _foreign_absolute

    assert _foreign_absolute(ref) is expected


def test_drive_qualified_reference_escapes_even_when_the_host_would_call_it_inside(tmp_path, monkeypatch):
    """On POSIX `C:/x` parses as relative and could resolve inside the skill. Force the host containment
    check to say 'inside' so only the host-independent shape check can flag it, whatever OS runs this."""
    from scripts import static_analysis as SA

    monkeypatch.setattr(SA, "_inside_skill", lambda *args, **kwargs: True)
    root = _skill(tmp_path / "s", """
        name: probe
        description: Probe skill for containment tests.
        """, "\n# Probe\n\n## Reference files\n\n- `C:/secret.md` — drive path\n")
    assert "reference-escapes-skill" in {f.rule for f in analyze(Skill.from_path(root))}


def test_an_unresolvable_path_is_reported_not_raised(tmp_path, monkeypatch):
    """A symlink loop makes Path.resolve() raise; validation must report it instead of crashing."""
    from scripts.static_analysis import _inside_skill

    def boom(self, *args, **kwargs):
        raise RuntimeError("Symlink loop from 'x'")

    monkeypatch.setattr(Path, "resolve", boom)
    assert _inside_skill(tmp_path, tmp_path / "loop") is False


def test_skill_fields_keep_their_positional_order():
    """New fields go last: Skill(...) is built positionally elsewhere, so inserting one shifts arguments."""
    import dataclasses

    names = [f.name for f in dataclasses.fields(Skill)]
    assert names[-2:] == ["source_text", "raw_frontmatter"]


def test_a_grading_report_with_non_sha256_provenance_is_not_generated(tmp_path):
    """Provenance must carry real sha256 digests, not any string, to be excluded from the evidence digest."""
    from scripts.file_policy import _is_generated_grading_artifact

    def report(digest):
        return json.dumps({"summary": {}, "provenance": {"transcript_sha256": digest, "skill_manifest_sha256": digest}})

    (tmp_path / "good.grading.json").write_text(report("a" * 64), encoding="utf-8")
    (tmp_path / "fake.grading.json").write_text(report("a"), encoding="utf-8")
    assert _is_generated_grading_artifact(tmp_path, "good.grading.json") is True
    assert _is_generated_grading_artifact(tmp_path, "fake.grading.json") is False
