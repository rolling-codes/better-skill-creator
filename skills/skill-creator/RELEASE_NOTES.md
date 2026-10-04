# Better Skill Creator Release History

## v3.2.0 — 2026-10-04

**Validation architecture overhaul, model-aware writing guidance, and silent-failure fixes.**

### What changed

- **`scripts/validate.py`** — unified validation CLI (replaces three separate tool invocations)
- **`scripts/types.py`** — shared types eliminate import coupling across validation modules
- **`metadata.lint_ignore`** — per-skill rule suppression with typo guards
- **Review gate wired into pre-commit** — validation now enforces the adversarial review gate at commit time
- **Pyright integrated into validation** — zero type errors, zero warnings across 69 files
- **Version-consistency check** — catches drift between plugin metadata and skill metadata
- **Model-aware writing guidance** — target_model field, tier-specific density calibration

### Upgrade

Drop-in. `python bsc.py check <skill-dir>` — score should hold or improve.

**Validation:** `quick_validate` clean · `lint` 0 errors · `static_analysis` no issues · score 84/100

---

## v3.1.0 — 2026-10-02

**2026 model guidance overhaul and SKILL.md de-specification for Fable 5+ compatibility.**

### Key changes

- **`budget_tokens` removed** — use `output_config.effort` instead (returns HTTP 400 on Claude 4.7+)
- **Over-specification degrades output** — `references/model-guidance.md` expanded from 90 to 350 lines
- **Hedged language = optional compliance** — audit for `try to`, `if possible`, `consider`, etc.
- **SKILL.md compressed** from 519 to ~415 lines — removed prescriptive boilerplate
- **Model routing guidance** — Fable 5.1 / Opus 5.5 (top), Sonnet 5.5 (mid), Haiku 4.5 (fast)

### Upgrade

Drop-in. No breaking changes.

---

## v3.0.1 — 2026-10-02

**Live trigger evals run again on current Claude Code.**

### Fix

- **`eval --live` now reaches the model** — resolves native `bin/claude` binary instead of removed `cli.js`
- Affects all live paths: `bsc.py eval --live`, `skill_test`, `run_eval`, `run_loop`

### Upgrade notes

- Skills created with v2.1.0 that have a top-level `schemaVersion` must move it under `metadata`
- From `skills/skill-creator/`, run: `python -m scripts.migrate_skill /path/to/skill --to 1`

---

## v3.0.0 — 2026-10-02

**Spec compliance and current-model guidance. Major bump: breaking changes to skill schema.**

### Breaking changes

- **`schemaVersion` moved under `metadata`** — top-level `schemaVersion` now rejected by `quick_validate`
- **Tool names corrected** — use real Claude tool names in `allowed-tools` (not older placeholder names)
- **Migration required** — existing skills need schema update via `scripts/migrate_skill.py`

### What's fixed

- `allowed-tools` now pre-approves correctly
- `write_skill_md` preserves `license` and custom `metadata` on rewrite
- Documentation corrected to match the actual runtime behavior

### Upgrade notes

Run this from `skills/skill-creator/` for each existing skill:

```bash
python -m scripts.migrate_skill /path/to/skill --to 1
```

---

## v2.1.0 — 2026-09-08

**Easier first use and cleaner results.**

- `bsc.py` launcher (`doctor`, `new`, `check`, `eval`, `package`)
- `examples/release-notes/` starter skill with positive/negative trigger cases
- GitHub Actions CI matrix (Ubuntu + Windows, Python 3.12)
- Python 3.12 now the documented baseline

---

## v2.0.3 — 2026-09-07

**Reliability patch for live eval machinery.**

- Windows-compatible streaming (reader thread, no `select`)
- Failed executions categorized so they never score as passes
- Eval infrastructure failure now stops the optimizer instead of continuing

---

## v2.0.2 — 2026-09-05

**Documentation-accuracy patch.**

- Corrected `scripts/dependency_graph.py` usage documentation

---

## v2.0.1 — 2026-09-05

**Validation-quality PR fixes.**

- Lifecycle consistency validation restored
- Python 3.8 compatibility restored (removed PEP 604 unions)
- Path containment hardened

---

## v2.0.0 — 2026-08-30

**Independent multi-agent review system and adversarial completion gate.**

- Fresh-context review roles: outcome analyst, scope adversary, architecture reviewer, completion adversary
- `review.yaml` records independent findings and gate status
- Completion gate blocks packaging of unresolved complex skills
- Live evaluation: **100% pass rate with-skill vs 41.7% baseline**

---

## v1.10.0 — 2026-08-30

**Adaptive Design Analysis and entailment-≠-permission guardrail.**

- Adaptive lenses (always-evaluate core + optional lenses)
- Authorization boundaries classification
- Scope-selection matrix

---

## v1.9.1 — 2026-08-30

**Wired v1.9.0 Design Analysis feature.**

- `assess_spec` now reachable via CLI
- Back-compatible validation so older specs still load
- Behavioral tests updated

---

## v1.9.0 — 2026-08-30

**Design Analysis scoping stage.**

- Multi-angle outcome analysis before writing
- Design-analysis fields on `SkillSpec`
- Flat-scope scoring and unresolved-questions detection

---

## v1.8.1 — 2026-08-30

**Documentation: `dependency_graph.py` is optional.**

---

## v1.8.0 — 2026-08-30

**Fixed wiring regressions: orphaned features now referenced in SKILL.md.**

- Wired `generators/`, `static_analysis.py`, `lint.py`, `dependency_graph.py`, `migrate_skill.py`, `generate_report.py`
- New orphaned-file rule
- New reference-wiring completeness rule

---

## v1.7.0 — 2026-08-26

**Version alignment release.**

- Aligned repo history and release tag semantics for the current mainline

---

## v1.4.0 — 2026-08-26

**Tightened SKILL.md and closed Gate 3 gap.**

- Added Iron Law and Red Flags table
- Extracted `references/description-optimization.md`

---

## v1.3.1 — 2026-08-26

**Repository consistency and linter-signal fixes.**

- Fixed plugin install compatibility
- Fixed pre-commit hook path resolution
- Fixed PyYAML dependency declaration
- Fixed license mismatch and version drift

---

## v1.1.0 — 2026-07-12

**Six architectural improvements.**

- Intermediate Representation (`skill_ir.py`)
- Formal dependency graph (`dependency_graph.py`)
- Static analysis rules
- Skill linter (eight content-quality checks)
- Versioned skill schema
- Plugin architecture (`generators/`)

---

## v1.0.0 — 2026-07-12

**Initial release.**

- Eval runner (`run_eval.py`)
- Optimization loop (`run_loop.py`)
- Description improver (`improve_description.py`)
- Browser-based eval viewer
- Blind A/B comparison agents
- Benchmark pipeline
- Regression test suite
- Skill packaging (`package_skill.py`)
- Quick validator (`quick_validate.py`)
