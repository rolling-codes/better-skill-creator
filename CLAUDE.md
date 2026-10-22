# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A Claude Code **plugin** (`.claude-plugin/`) that wraps a single **meta-skill** at
`skills/skill-creator/`. The skill builds, tests, and iteratively improves *other* Claude Code
skills. It is a fork of Anthropic's `skill-creator`. The engine lives under
`skills/skill-creator/scripts/`; the repo root holds the plugin/marketplace manifests, docs, and
`bsc.py` — a thin human-facing CLI front-end over that engine (see Architecture).

## Commands

Dependencies: `pip install -r requirements.txt` (PyYAML; everything else is stdlib). Python 3.12+ is
the supported floor and the type-check target (`pyrightconfig.json`).

**The `bsc.py` front-end runs from the repo root** and is the recommended entry point for humans —
it wires the import root itself, then writes a timestamped JSON + markdown report under `runs/`:

```bash
python bsc.py doctor                    # prerequisite checks (Python, PyYAML, claude CLI); no model calls
python bsc.py new <name> --example release-notes   # scaffold a skill from examples/release-notes
python bsc.py check <skill-dir>         # structure + lint + static + semantic + review + dep-cycle checks
python bsc.py eval  <skill-dir> [--live --models haiku,sonnet,opus]   # trigger eval (needs claude CLI)
python bsc.py eval  <skill-dir> --grade-transcript <transcript>   # trigger eval, THEN grade expected_behavior.yaml (unlike skill_test --grade-only)
python bsc.py compare --candidate <dir> --baseline <dir>   # compare two versions of a skill
python bsc.py package <skill-dir>       # package a .skill into dist/ (packages a copy; never mutates source)
python bsc.py hooks install             # copy pre-commit hook into Git's resolved hooks directory
```

**The `scripts.*` modules are that engine, and run as modules with the CWD set to
`skills/skill-creator/`** (see Import root below). From that directory:

```bash
# Offline validators (fast, no network/model). Exit 0 = clean, 2 = warnings-only, 1 = blocking error.
python -m scripts.quick_validate .      # structural: frontmatter, required fields, lifecycle
python -m scripts.lint .                # content-quality + reference-wiring completeness
python -m scripts.static_analysis .     # dead references, orphaned files, unused tools, etc.
python -m scripts.review_gate .         # gate over review.yaml (see Review gate)
scripts/validate_all.sh .               # all of the above, then live trigger tests if `claude` is on PATH

# Tests (pure-Python; streaming tests use a fake subprocess, never a live `claude`)
python -m pytest tests/
python -m pytest tests/test_run_eval_stream.py::test_timeout    # single test

# Live trigger evals + behaviour grading (require the `claude` CLI + subprocess access)
python -m scripts.skill_test <skill-folder>                     # runs tests/should_(not_)trigger.yaml
python -m scripts.skill_test <skill-folder> --grade-transcript <transcript>              # trigger tests, THEN grade expected_behavior.yaml (grading skipped if triggers error / return code 1)
python -m scripts.skill_test <skill-folder> --grade-only --grade-transcript <transcript>  # grade behaviour only (skips triggers; one grader model call)
python -m scripts.run_loop --eval-set <eval.json> --skill-path <dir> --model <model>  # optimize the description

# Package a skill into a distributable .skill (runs the compiler pipeline; blocks on error findings)
python -m scripts.package_skill .

# From the repo root:
claude plugin validate .                # validate plugin.json + marketplace.json
```

**Exit-code convention across `run_eval` / `run_loop` / `skill_test`:** `0` = all passed, `1` =
execution/input/infrastructure error, `2` = completed but some expectations failed.

## Architecture (the parts that span multiple files)

**Import root.** `skills/skill-creator/scripts/` is a package; code imports siblings as
`from scripts.X import …` and expects the *parent* dir (`skills/skill-creator/`) on the path. Always
invoke as `python -m scripts.X` from `skills/skill-creator/` — running a script by file path breaks
imports. `pyrightconfig.json` (root and skill dir) and `.vscode/settings.json` encode the same root
for editors; `skill_test.py` runs the toolkit module from the toolkit dir while pointing `--skill-path`
at the (possibly external) target skill.

**Progressive-disclosure invariant.** Under Claude Code, a file not referenced from `SKILL.md` is
never loaded — so it effectively does not exist. This is enforced mechanically: dead and escaping
references are **errors** (they block packaging); orphaned files are **warnings** (exit 2), which CI and
packaging tolerate but which still mean Claude never sees the file:
- `static_analysis.py` flags an **orphaned file** (under `scripts/`, `agents/`, `references/` or
  `generators/`, unreferenced in SKILL.md) as a warning, and a **dead reference** (referenced but absent, or resolving outside the skill directory)
  as an error — runtime workspace outputs like
  `evals/evals.json` are exempted via `RUNTIME_OUTPUT_PREFIXES` in `analysis_config.py`.
- `lint.py` enforces the reverse: every `skill.yaml` dependency must be linked from SKILL.md.
- Therefore the SKILL.md **Reference files** section, `skill.yaml` `dependencies`, and the files on
  disk must stay in sync. Keep SKILL.md within the ~500-line budget (environment/optimization docs are
  extracted to `references/`).

**Eval machinery (how "does the description trigger the skill?" is measured).** `run_eval.py` writes a
synthetic command file into the project's `.claude/commands/`, spawns `claude -p` per query (prompt
over **stdin**, output as stream-json read by a background reader thread + queue — do not reintroduce
`select` on the pipe; it is not portable), and classifies each run into a `QueryOutcome`
(`structured_logging.py`): a clean `triggered`/`not_triggered`, or a failure category
(`TIMEOUT`/`AUTHENTICATION`/`SUBPROCESS_CRASH`/`PARSING`). **A failed execution is never counted as a
pass** — trigger rate is computed over clean runs only, and `run_eval` surfaces `execution_error` per
query and `infrastructure_failed` in the summary. `run_loop.py` wraps eval + `improve_description.py`
into an optimization loop that **stops instead of optimizing when infrastructure fails**.
`tests_loader.py` normalizes every trigger-test file (bool or legacy `triggered`/`not_triggered`
labels, `prompt`/`query` aliases; rejects malformed, de-dupes) into the eval set.

**Control-query gate (invariant — do not revert).** `isolation_args()` in `claude_process.py`
intentionally omits `--setting-sources`. Passing `--setting-sources ""` clears project-level config
including `.claude/commands/`, hiding the synthetic command files from the spawned session so no query
ever triggers. Before the main eval loop, `run_eval.py` fires one control prompt that names the skill
description prefix; if it doesn't trigger, the run aborts with `infrastructure_failed: true`.

**Compiler pipeline.** `compiler_context.py` (`CompilerContext`) + `pipeline.py`
(`StageRegistry.run_all`) + `scripts/stages/` run a staged quality gate (lint → semantic → dependency
→ repair → review → score → package) sharing one context. `package_skill.py` drives it and refuses to
package when error-severity findings remain after auto-repair.

**Independent review gate.** For substantial skill work, `review.py` records an independent
multi-agent review + adversarial completion gate in `review.yaml`; `review_gate.py` / `ReviewStage`
deterministically block packaging until high-severity findings are disposed and
`completion_gate_status: passed`. See `references/independent-review.md`. Lifecycle:
`python -m scripts.review restart .` (clears the stale record after source changes), then
conduct the independent review and record each reviewer's report in `review.yaml`; packaging
unblocks when the gate passes. For a genuinely narrow change (docs/metadata), the gate also
accepts an explicit skip — `activation.required: false` with a `reason` — instead of a full
re-review (see the adaptive-activation section of `references/independent-review.md`); never
refresh only the manifest hashes under a required review.
`review_gate.py` always prints one summary line (`Review gate: passed/failed/skipped`); a skip
without a recorded reason is an error. `test_pipeline.py::test_review_stage_is_available_and_runs`
reads the live `review.yaml` — its assertions change after a `restart` (all 4 reports pending).

**`validate.py` is the unified gate.** It runs structural, lint, static-analysis,
review-gate, and score checks, and reports description confidence. CI runs
`quick_validate`, `lint`, `static_analysis`, and `review_gate` as separate checks;
it does not run the unified gate, its score threshold, or description-confidence checks.
The CI review gate blocks main pushes and scheduled runs; PR development can proceed
with a pending review. The pre-commit hook runs structure, lint, and the review
gate in one process (`python -m scripts.validate --commit`), plus pyright when a
Python file or `pyrightconfig.json` is staged.

**`metadata.target_model` takes a tier name**, not a model ID. Valid values: `fable`, `opus`,
`sonnet`, `haiku`. A full model ID (e.g. `claude-opus-4-8`) triggers `invalid-target-model`.

**Front-end vs engine.** `bsc.py` (repo root) is a deliberately thin wrapper: `ROOT` is the repo
root, it inserts `skills/skill-creator/` onto `sys.path` so it can `from scripts.X import …`, then
each subcommand (`doctor`/`new`/`check`/`eval`/`package`) just orchestrates the same `scripts.*`
functions documented above and serializes the result to `runs/<timestamp>-<id>/{results.json,report.md}`.
`package` operates on a temp-dir **copy** (excluding `.git/.venv/__pycache__/.pytest_cache/runs/dist`)
and reports a fingerprint diff of any auto-repairs, so the source tree is never mutated. Keep logic in
`scripts.*`; `bsc.py` should stay a dispatch/serialize shell.

**Scaffolding generators.** `skills/skill-creator/generators/` is a separate package (run from the
toolkit dir as `python -m generators`) with a `GeneratorRegistry` mapping archetypes
(`default`, `python-skill`, `research`) to `Generator` subclasses (`generators/base.py`). Each
`scaffold()` emits a working SKILL.md + skill.yaml stub. `bsc.py new` is the example-based path
(copies `examples/release-notes`); the generators are the archetype-based path. Add an archetype by
subclassing `Generator` and registering it in `generators/__init__.py`.

**Agents** (`agents/*.md`) are subagent instruction files spawned during evals and reviews (grader,
comparator, analyzer, the reviewers, the completion-adversary) — not executable code.

## Releasing

Version lives in **four** places — `.claude-plugin/plugin.json`, `skills/skill-creator/skill.yaml`,
the README badge, and the `VERSION` constant in `bsc.py` — keep them in lockstep (they drift easily;
`bsc.py` has lagged before). `CHANGELOG.md` follows Keep a Changelog. `main` is branch-protected:
land changes via a feature branch → PR. Run `scripts/validate_all.sh` and `claude plugin validate .`
before tagging.
