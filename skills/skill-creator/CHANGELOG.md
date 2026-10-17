# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [3.5.0] - 2026-10-17

Bug-prevention phase 1 — source-level defect detectors and gate correctness, ported from the
longterm-ai gate-correctness work. No breaking changes; `scripts.*` imports unchanged.

### Added

- `scripts/source_rules.py` — AST linter over the toolkit's own Python detecting recurring defect
  classes repo-wide: **H-ENCODING** (text file ops without `encoding=`) and **H-SWALLOW**
  (`except` body that is only `pass`). Conservative/fail-closed; CI-wired with good/bad fixtures.
- `scripts/claims_check.py` + `claims.yaml` — behavioral-claim registry; every claim must resolve
  to an existing verifier test.
- `scripts/doc_sync.py` — documented commands/flags/modules/links must exist in the source.
- Review-gate correctness (`scripts/review_gate.py`, `scripts/finding_types.py`): uniform
  **0/1/2 exit-code contract** (0 ok / 1 blocking error / 2 warnings-only) and a required-key check
  (`CONSOLIDATED_REQUIRED_KEYS`) so a placeholder synthesis cannot satisfy the gate.

### Fixed

- CI tolerates a warnings-only exit (2) from `doc_sync`/`claims_check` (`|| [ $? -eq 2 ]`), matching
  the `lint`/`static_analysis` steps; only error findings (exit 1) block the build.

## [3.4.1] - 2026-10-14

### Fixed
- Control query now counted in `run_eval`'s call budget (+1); charged to the caller's shared
  `CallBudget` instead of a private one — prevents silent under-counting of model calls.
- `bsc.py hooks install` and `doctor` use `git rev-parse --git-path hooks` to resolve the
  correct hook directory in git worktrees and submodules.
- `review_gate --release` now prints "failed" (not "skipped") when the `review-skipped`
  info finding is promoted to an error.
- Scoring exception in `validate.py` appends an error `Finding` instead of printing to
  stderr, so the gate returns exit 1 rather than silently passing.
- Canary CI job updated to use `bsc.py eval` with the `haiku` model alias and
  `CLAUDE_CODE_OAUTH_TOKEN`; `review_gate` CI step hardened (no `|| [ $? -eq 2 ]` escape).
- `bsc.py hooks` subcommand excluded from the path-argument loop (no longer requires a
  skill path that it doesn't use).
- `CLAUDE.md` corrected: CI runs separate scripts, not the unified `validate.py` gate.
- Test portability: README block-count assertion updated; `test_bsc_hooks.py` skips
  execute-bit check and submodule layout on Windows.

## [3.4.0] - 2026-10-14

### Changed
- Added token-economy and skill-composition guidance in `references/token-economy.md`.

### Added
- A must-trigger control query rejects evaluations when skills are not discoverable.
- `bsc.py hooks install` installs the pre-commit hook; `doctor` checks its presence.
- A daily trigger canary exercises Claude Code with Haiku and a
  15-call limit.

## [3.3.0] - 2026-10-06

### Added
- `references/development-practices.md` provides guidance for skills that write code,
  fix bugs, run tests, or author PRs, and is wired into `SKILL.md` and `skill.yaml`.

### Fixed
- Dependency-containment diagnostics preserve Windows paths without doubled backslashes.

## [3.2.0] - 2026-10-04

### Added
- `scripts/validate.py` — unified validation CLI replacing three separate tool invocations
- `scripts/types.py` — shared types eliminating import coupling across validation modules
- `metadata.lint_ignore` — per-skill rule suppression with typo guards
- Review gate wired into pre-commit hook
- Pyright integrated into validation (zero errors, zero warnings across 69 files)
- Version-consistency check catching drift between plugin and skill metadata
- Model-aware writing guidance: `target_model` field, tier-specific density calibration

## [3.1.0] - 2026-10-02

### Changed
- `budget_tokens` removed — use `output_config.effort` instead (returns HTTP 400 on Claude 4.7+)
- `references/model-guidance.md` expanded from 90 to 350 lines with 2026 model guidance
- SKILL.md compressed from 519 to ~415 lines, removing prescriptive boilerplate
- Model routing guidance updated for Fable 5.1 / Opus 5.5 / Sonnet 5.5 / Haiku 4.5

### Fixed
- Hedged language (`try to`, `if possible`, `consider`) now flagged as producing optional compliance

## [3.0.1] - 2026-10-02

### Fixed
- `eval --live` now reaches the model — resolves native `bin/claude` binary instead of removed `cli.js`
- Affects all live paths: `bsc.py eval --live`, `skill_test`, `run_eval`, `run_loop`

## [3.0.0] - 2026-10-02

Breaking changes to skill schema.

### Added
- `scripts/migrate_skill.py` migration path for existing skills: `python -m scripts.migrate_skill /path/to/skill --to 1`

### Changed
- `schemaVersion` moved under `metadata` — top-level `schemaVersion` now rejected by `quick_validate`
- Tool names in `allowed-tools` must be real Claude tool names (invalid names now flagged by lint)
- Scorer no longer rewards pre-approval grants

### Fixed
- `allowed-tools` pre-approves correctly
- `write_skill_md` preserves `license` and custom `metadata` on rewrite
- Documentation corrected to match actual runtime behavior

## [2.1.0] - 2026-09-08

### Added
- `bsc.py` launcher with `doctor`, `new`, `check`, `eval`, `package` subcommands
- `examples/release-notes/` starter skill with positive/negative trigger cases
- GitHub Actions CI matrix (Ubuntu + Windows, Python 3.12)

### Changed
- Python 3.12 documented as the baseline

## [2.0.3] - 2026-09-07

### Fixed
- Windows-compatible streaming (reader thread replacing `select`)
- Failed executions categorized so they never score as passes
- Eval infrastructure failure now stops the optimizer instead of continuing

## [2.0.2] - 2026-09-05

Documentation-accuracy patch salvaging the one portable change from the stale
PR #10 (`fix/variance-check-script-gate`).

### Fixed

- The `scripts/dependency_graph.py` reference entry in SKILL.md now states it takes
  a skill root directory as its positional argument (`<skill-root>`), matching the
  actual CLI (`skill_path = Path(args[0])`, usage `python -m scripts.dependency_graph
  <skill-path>`) and the README.

### Notes

- The remainder of PR #10 (Gate 0 frontmatter-only collection; variance-check running
  lint + dependency_graph after edits) applied to the retired `skill-architect`
  layout. This fork has no numbered gates and no variance-check mode, and
  `dependency_graph.py` is intentionally optional here, so those changes were dropped.

### Validation

- `quick_validate` pass, `lint` 0 errors, `semantic_analysis` clean, score 90/100.
- `dependency_graph.py` run over a skill root in summary/json/dot plus no-arg and
  bad-path contracts; regression suite 19/19.

## [2.0.1] - 2026-09-05

Fixes the PR review findings from the validation-quality branch and keeps the
new validation helpers compatible with the documented Python 3.8 minimum.

### Fixed

- `quick_validate.py` again fails when `skill.yaml` declares one lifecycle and
  `LIFECYCLE.md` declares a different `status:`.
- Replaced the newly added PEP 604 union annotations in `quick_validate.py`,
  `skill_ir.py`, and `utils.py` with Python 3.8-compatible `typing.Union`
  annotations.
- `safe_path_exists` now uses `Path.relative_to()` for containment, preventing
  sibling directories with the same textual prefix from passing the check.
- Restored the full angle-bracket validation diagnostic text.

### Validation

- Added regression coverage for lifecycle mismatch rejection, path-prefix escape
  rejection, and avoiding PEP 604 unions in the changed modules.

## [2.0.0] - 2026-08-30

Adds an independent multi-agent review system and adversarial completion gate for
complex skill creation and substantial updates. Major bump: the review gate now
blocks packaging of a complex skill that lacks a passing `review.yaml`, which
changes the packaging contract for substantial skill work.

### Added

- `agents/outcome-analyst.md`, `agents/scope-adversary.md`,
  `agents/architecture-reviewer.md`, and `agents/completion-adversary.md` define
  the required fresh-context review roles.
- `references/independent-review.md` documents adaptive activation, independence
  requirements, synthesis without voting, and the completion gate.
- `scripts/review.py` adds a `ReviewRecord` IR stored in `review.yaml` for
  independent findings, disagreements, adversarial findings, dispositions,
  completion-gate status, accepted limitations, and unresolved decisive questions.
- `scripts/review_gate.py` deterministically detects missing required reports,
  undisposed high/material findings, invalid dispositions, unwired review agents,
  and completion claims before the gate has passed.
- `scripts/stages/review_stage.py` wires the review gate into the package
  pipeline.

### Changed

- `SKILL.md` now requires the review process for complex skills and substantial
  updates, while allowing narrow edits to record a skip reason.
- `skill.yaml` declares all new reviewer agents, review scripts, and the
  independent-review reference so progressive disclosure can discover them.
- `tests/expected_behavior.yaml` now includes the exact RPG, log-fix,
  no-modification, description-only, simple-skill, ambiguous-request, and
  development-log prompts from the v1.11 evaluation matrix.

### Fixed

- Added unit coverage for `SkillSpec` design-analysis scoring and review-gate
  behavior so the new system is validated by behavior, not just by shipped files.
- `PackageStage` now fails closed on error-severity diagnostics (e.g. an
  unresolved review gate) before writing the `.skill`, so the completion gate
  cannot be bypassed by a caller invoking `StageRegistry.run_all` directly rather
  than the `package_skill.py` driver; `review_stage.py`'s docstring corrected to
  locate the enforcement in both layers.
- Python 3.8 compatibility: added `from __future__ import annotations` to
  `aggregate_benchmark.py`, `generate_report.py`, `improve_description.py`,
  `run_eval.py`, `run_loop.py`, and `utils.py`, which used `list[...]`/`dict[...]`
  runtime annotations that raise `TypeError` on the project's stated minimum
  (Python 3.8).

### Validation

- The review system was applied to this release itself. A fresh-context
  completion adversary attempted to prove the skill incomplete and returned
  `verdict: complete`; its three low-severity findings are recorded and disposed
  in `review.yaml` (two fixed — the development-log case and the `PackageStage`
  guard above; one accepted limitation — offline validation cannot prove real
  subagent independence). `review_gate.py` passes and `completion_gate_status` is
  `passed`.
- Live previous-vs-new evaluation over three representative prompts (RPG variant
  discrimination, log-fix entailment-vs-authorization, no-modification constraint),
  with-skill vs no-skill baseline, same model: pass rate 100% vs 41.7%
  (delta +0.58), at +39s and +19k tokens per run. The lift concentrates on the
  ambiguous prompts; the already-constrained prompt was least discriminating.

## [1.10.0] - 2026-08-30

Makes the Design Analysis stage adaptive and bounded, and adds the
entailment-is-not-permission guardrail.

### Added

- `references/design-analysis.md` restructured: adaptive lenses (always-evaluate core
  vs evaluate-when-relevant, justify each), an "Entailment is not permission" section
  with the four-way work classification, a scope-selection matrix, a design-brief
  template, contradiction handling (explicit user constraints win), and a stopping rule.
  Added a table of contents.
- `SkillSpec` (`scripts/spec.py`): `chosen_interpretation`, `optional_features`,
  `authorization_boundaries`. `to_dict`/`from_yaml` round-trip them; `coverage()` counts
  the meaningful ones; existing specs load unchanged.
- `scripts/confidence.py` `assess_spec`: raises an assumption when entailments exist but
  `authorization_boundaries` is empty (entailed work not classified for authorization),
  and a missing-info flag when `interpretations` has more than one entry but
  `chosen_interpretation` is empty.
- `tests/expected_behavior.yaml`: nine adversarial prompts asserting decisions —
  RPG variant discrimination (build / one-shot / persistent-with-ranks),
  entailment-vs-permission ("watch these logs and tell me what crashes",
  "diagnose but do not modify anything"), authorization boundaries
  ("only change the CSS; don't touch the backend"), and over-scoping guard
  ("make a simple skill, do not add optional systems").

### Changed

- `SKILL.md` Design analysis section rewritten to the adaptive-lens split with the
  entailment≠permission rule and the stopping rule; added a Red Flags row for treating
  entailment as authorization.

## [1.9.1] - 2026-08-30

Wires up and back-fills the v1.9.0 Design Analysis feature.

### Fixed

- `scripts/confidence.py` CLI now invokes `assess_spec` when a `spec.yaml` is present
  (previously it only ran `assess_skill`, leaving the flat-scope scoring unreachable
  from `python -m scripts.confidence`). It gates on the lower of the skill and spec
  scores.
- `scripts/spec.py`: `missing_fields()` reverted to the original core set so specs
  written before the design-analysis fields still validate; `outcome`/`entailments`
  moved to a new `missing_design_fields()` that `spec validate` reports as a warning
  (exit 2), not a hard failure (exit 1).
- `tests/expected_behavior.yaml`: replaced the question-first assertions with
  design-analysis behavior — variant enumeration ("Build me an RPG skill"), entailment
  expansion ("watch my logs" → detect → diagnose → patch → verify), stated assumptions,
  and tight-Boundary scope control.

## [1.9.0] - 2026-08-30

Adds a multi-angle **Design Analysis** scoping stage so the skill-creator designs
for the full problem space instead of transcribing the literal request.

### Added

- `references/design-analysis.md` — the scoping doctrine: an angle checklist (real
  outcome, valid interpretations, modes/use-cases, cross-cutting requirements,
  entailments, failure points, self-validation, infer-vs-clarify, flexibility
  without vagueness), a compare→decide→architect step, an ask-vs-assume rule, and
  two worked examples (a dev/logs skill and an RPG skill).
- `SkillSpec` (`scripts/spec.py`) gains `outcome`, `interpretations`, `modes`,
  `entailments`, `failure_points`, `validation`, `assumptions`, and
  `open_questions`. `missing_fields()` now requires `outcome` and `entailments`;
  `coverage()` counts the new fields (except `open_questions`, where empty is the
  goal). `to_dict`/`from_yaml` round-trip them; existing specs load unchanged.
- `assess_spec` (`scripts/confidence.py`) scores the design analysis: a stated
  outcome with no entailments is flagged as flat scope ("assumed the literal
  request is the whole job"), and unresolved decisive `open_questions` lower
  confidence.

### Changed

- `SKILL.md` Gate 1 / intent capture is now "Design analysis: scope the outcome
  from multiple angles," pointing at `references/design-analysis.md`. Bias flipped
  from ask-first to analyze-first with stated assumptions. Added a Red Flags row
  for the "build the literal request" shortcut.

## [1.8.1] - 2026-08-30

### Documentation

- `scripts/dependency_graph.py` is now documented as optional in both SKILL.md
  and the README: the workflow and packaging pipeline do not depend on it, and
  it reads only the skill's own files (no external graph service). No code change.

## [1.8.0] - 2026-08-30

Fixes the wiring regression this fork was created to prevent. The features added
across v1.2-v1.7 shipped in the repo but were never referenced in `SKILL.md`, so
progressive disclosure kept them invisible: Claude running the skill never
scaffolded with the generators, never invoked the linter or static analyzer, and
never migrated schemas. Neither of the fork's own wiring checkers caught it —
`static_analysis` only flagged references pointing at missing files, and `lint`
only checked that a Reference files section existed, not that it was complete.

(Entries 1.4.0 through 1.7.0 were tracked only in the repository-root
`CHANGELOG.md`; this file resumes the component-level history here.)

### Added

- **Orphaned-file rule** in `scripts/static_analysis.py` (`orphaned-file`): flags
  any file under `scripts/`, `agents/`, `references/`, or `generators/` that is
  never referenced in `SKILL.md`. This is the reverse of the existing
  dead-reference rule and runs in the package pipeline through `LintStage`.
- **Reference-wiring completeness rule** in `scripts/lint.py`
  (`unwired-dependency`): flags any `skill.yaml` dependency not linked from
  `SKILL.md`. Raises the linter from eight checks to nine.
- Shared `_is_referenced` / `_reference_forms` helpers matching the three ways
  `SKILL.md` names a script (path, `python -m` module, bare filename). Only
  nested directory references (e.g. `scripts/stages/`) cover their children, so a
  bare `scripts/` in ordinary prose cannot mask a real orphan.

### Fixed

- Wired the six orphaned features (`generators/`, `static_analysis.py`,
  `lint.py`, `dependency_graph.py`, `migrate_skill.py`, `generate_report.py`)
  into the `SKILL.md` Reference files section, Validation Pipeline, and a new
  "Scaffolding a skeleton" note.
- `README.md`: corrected the claim that static analysis runs as a
  `StaticAnalysisStage` (it runs inside `LintStage`) and the linter check count.
- Python 3.8 support: added `from __future__ import annotations` to
  `package_skill.py` and `skill_test.py`, whose `list[...]` annotations would
  raise at import on 3.8. Corrected `package_skill.py`'s stale `python utils/...`
  usage strings.
- `tests/test_pipeline.py`: resolve the skill path from `__file__` instead of a
  hardcoded `C:/Temp/bsc-update` path that made the suite pass only on one
  machine; fixed the `StubFallback` stage signature to match the `PipelineStage`
  protocol.

## [1.3.0] - 2026-07-12

### Added
- `CompilerContext` dataclass — shared mutable IR passed through all pipeline stages,
  carrying `skill_spec`, `diagnostics`, `repairs`, `applied_fixes`, `score`, and
  `output_path` (`scripts/compiler_context.py`)
- `RepairProposal` dataclass — a deferred repair closure that separates fix planning
  from filesystem mutation
- `StageRegistry` — executes registered `PipelineStage` implementations in order,
  with `run_all()` and `run_until()` entry points (`scripts/pipeline.py`)
- `PipelineStage` Protocol — structural interface all stage wrappers satisfy
- Seven concrete pipeline stages in `scripts/stages/`: `LintStage`, `SemanticStage`,
  `DependencyStage`, `RepairStage`, `ApplyRepairsStage`, `ScoreStage`, `PackageStage`
- `RepairStage` builds repair proposals without touching disk; `ApplyRepairsStage`
  is the sole filesystem-writing stage — enforces the proposal/apply split
- Five regression tests for the compiler pipeline in `tests/test_pipeline.py`

### Changed
- `package_skill.py` now orchestrates the pipeline via `CompilerContext` and stage
  instances rather than direct function calls; all observable behaviour preserved
- `.pytest_cache` excluded from packaged `.skill` archives

### Architecture note
v1.2.0 created skills. v1.3.0 compiles them. The stage/registry model decouples
*what* work happens from *who* performs it — future LLM-backed stages slot in by
replacing a stage's `run()` body; the registry and orchestrator are unchanged.

## [1.2.0] - 2026-07-07

### Added
- `scripts/spec.py` — pre-generation SkillSpec intent IR; writes `spec.yaml`
- `scripts/confidence.py` — requirement coverage + ambiguity score
- `scripts/semantic_analysis.py` — contradiction, duplicate-section, and
  inconsistent-terminology checks
- `scripts/repair.py` — deterministic auto-fix loop for known lint errors
- `scripts/score.py` — architecture scoring rubric (7 dimensions, 0–100 each)
- `scripts/generate_tests.py` — generates edge-case and malformed-input test scenarios
- All six scripts wired into `package_skill.py` compile pipeline
