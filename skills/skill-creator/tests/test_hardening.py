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


def test_secret_lookalike_names_are_excluded():
    """Trailing dots, spaces, hidden-key names, and compatibility letters still match."""
    names = (
        ".env ", "credentials.", ".npmrc.", "notes.pem ", "notes.pem.",
        "file.pem\u200b", "file.pem\ufeff", ".id_rsa", ".id_ed25519.pub",
        "\u0130D_RSA", ".git.", "dist.", ".. ",
    )
    for name in names:
        assert excluded(Path("refs") / name), repr(name)
    assert not excluded(Path("references/guide.md"))
    assert not excluded(Path("references/my.id_rsa"))


def test_matching_secret_pattern_names_the_policy_that_drops_the_file():
    from scripts.file_policy import matching_secret_pattern, secret_exclusion_message

    assert matching_secret_pattern(Path("references/secrets.md")) == "secrets.*"
    assert matching_secret_pattern(Path("references/Secrets.MD")) == "secrets.*"
    assert matching_secret_pattern(Path("references/notes.pem ")) == "*.pem"
    assert matching_secret_pattern(Path("credentials")) == "credentials"
    assert matching_secret_pattern(Path("assets/client.key")) == "*.key"
    assert matching_secret_pattern(Path("references/guide.md")) is None
    message = secret_exclusion_message("references/secrets.md")
    assert message == (
        "`references/secrets.md` is excluded from packages because its name matches "
        "the secret-file pattern `secrets.*`; rename it to ship it."
    )
    assert secret_exclusion_message("https://example.com/secrets.md") is None
    assert secret_exclusion_message("//cdn.example.com/secrets.md") is None
    assert secret_exclusion_message("credentials?download") is not None
    assert secret_exclusion_message("credentials%23setup") is not None
    assert secret_exclusion_message("%2eaws/config") is not None
    assert "credential store" in secret_exclusion_message(".aws/config")
    assert "excluded directory" in secret_exclusion_message("node_modules/pkg/index.js")
    assert secret_exclusion_message(".aws") is not None
    assert secret_exclusion_message(".aws/../notes.md") is None


def test_referenced_secret_filename_is_an_exclusion_error_while_the_file_exists(tmp_path):
    """check sees the file on disk; the failure must name the policy, not a missing path."""
    root = _skill(tmp_path / "probe", """
        name: probe
        description: Probe skill for secret-name reference tests. Use when probing. Not for shipping keys.
        """, textwrap.dedent("""
        # Probe

        ## Reference files

        - `references/secrets.md` — Read when handling credentials.
        - `references/credentials` — sample notes
        - `references/guide.md` — ordinary
        """))
    (root / "references").mkdir()
    (root / "references" / "secrets.md").write_text("how to handle credentials\n", encoding="utf-8")
    (root / "references" / "credentials").write_text("sample\n", encoding="utf-8")
    (root / "references" / "guide.md").write_text("guide\n", encoding="utf-8")
    (root / ".env").write_text("SYNTHETIC-PRIVATE\n", encoding="utf-8")
    findings = analyze(Skill.from_path(root))
    secret = [f for f in findings if f.rule == "secret-name-excluded"]
    messages = {f.message for f in secret}
    assert any(m.startswith("`references/secrets.md` is excluded") and "`secrets.*`" in m for m in messages)
    assert any("`references/credentials`" in m and "`credentials`" in m for m in messages)
    assert "dead-reference" not in {f.rule for f in findings}
    assert "orphaned-file" not in {f.rule for f in findings}
    assert not any(".env" in f.message for f in secret)


def test_stripped_secret_reference_is_still_an_exclusion_not_a_missing_file(tmp_path):
    """package analyses a copy that no longer contains the file. Do not say it was never there."""
    root = _skill(tmp_path / "probe", """
        name: probe
        description: Probe skill for secret-name reference tests. Use when probing. Not for shipping keys.
        """, textwrap.dedent("""
        # Probe

        ## Reference files

        - `references/secrets.md` — Read when handling credentials.
        """))
    findings = analyze(Skill.from_path(root))
    rules = {f.rule for f in findings}
    assert "secret-name-excluded" in rules
    assert "dead-reference" not in rules
    assert "not found on disk" not in " ".join(f.message for f in findings)


def test_skill_yaml_secret_dependency_is_an_exclusion(tmp_path):
    from scripts.quick_validate import validate_skill
    from scripts.stages.dependency_stage import DependencyStage
    from scripts.compiler_context import CompilerContext

    root = _skill(tmp_path / "probe", """
        name: probe
        description: Probe skill for secret-name reference tests. Use when probing. Not for shipping keys.
        """, "\n# Probe\n")
    (root / "references").mkdir()
    (root / "references" / "client.key").write_text("sample key material\n", encoding="utf-8")
    (root / "skill.yaml").write_text(
        "name: probe\ndependencies:\n  - references/client.key\n",
        encoding="utf-8",
    )
    ok, message = validate_skill(root)
    assert ok, message
    findings = analyze(Skill.from_path(root))
    secret = [f for f in findings if f.rule == "secret-name-excluded"]
    assert len(secret) == 1
    assert "`references/client.key`" in secret[0].message
    assert "`*.key`" in secret[0].message
    ctx = CompilerContext.create(root)
    DependencyStage().run(ctx)
    assert "missing-dependency" not in {f.rule for f in ctx.diagnostics}

    (root / "references" / "client.key").unlink()
    ok, message = validate_skill(root)
    assert ok, message
    findings = analyze(Skill.from_path(root))
    assert any(f.rule == "secret-name-excluded" for f in findings)
    assert "dead-reference" not in {f.rule for f in findings}
    ctx = CompilerContext.create(root)
    DependencyStage().run(ctx)
    assert "missing-dependency" not in {f.rule for f in ctx.diagnostics}


def test_secret_like_asset_reference_is_an_exclusion_not_a_missing_asset(tmp_path):
    root = _skill(tmp_path / "probe", """
        name: probe
        description: Probe skill for secret-name reference tests. Use when probing. Not for shipping keys.
        """, "\n# Probe\n\nKeep the sample at assets/license.key.\n")
    findings = analyze(Skill.from_path(root))
    assert any(f.rule == "secret-name-excluded" and "assets/license.key" in f.message for f in findings)
    assert "missing-asset" not in {f.rule for f in findings}


def test_escaping_secret_like_reference_stays_a_containment_error(tmp_path):
    (tmp_path / "outside").mkdir()
    (tmp_path / "outside" / "client.key").write_text("x", encoding="utf-8")
    root = _skill(tmp_path / "probe", """
        name: probe
        description: Probe skill for secret-name reference tests. Use when probing. Not for shipping keys.
        """, "\n# Probe\n\n## Reference files\n\n- `../outside/client.key` — outside\n")
    rules = {f.rule for f in analyze(Skill.from_path(root))}
    assert "reference-escapes-skill" in rules
    assert "secret-name-excluded" not in rules


def test_excluded_paths_lists_policy_skips_without_ordinary_files(tmp_path):
    from scripts.file_policy import excluded_paths

    root = tmp_path / "probe"
    (root / "references").mkdir(parents=True)
    (root / "evals").mkdir()
    (root / ".env").write_text("SYNTHETIC-PRIVATE\n", encoding="utf-8")
    (root / "references" / "secrets.md").write_text("guide\n", encoding="utf-8")
    (root / "references" / "guide.md").write_text("guide\n", encoding="utf-8")
    (root / "evals" / "evals.json").write_text("[]\n", encoding="utf-8")
    cache = root / "__pycache__"
    cache.mkdir()
    (cache / "mod.pyc").write_bytes(b"pyc")
    listed = excluded_paths(root)
    assert ".env" in listed
    assert "references/secrets.md" in listed
    assert "evals/" in listed
    assert "__pycache__/" in listed
    assert "references/guide.md" not in listed
    assert not any("SYNTHETIC" in name for name in listed)


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
