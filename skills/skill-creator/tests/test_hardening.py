"""Regressions for verified hardening fixes: repair, reference containment, packaging policy, transcripts."""
from __future__ import annotations

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
