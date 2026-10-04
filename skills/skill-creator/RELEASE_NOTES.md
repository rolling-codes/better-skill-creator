# Better Skill Creator 3.2.0

2026 model guidance overhaul. No breaking changes.


---


## Over-specification degrades output on Fable 5+

Trim rigid step sequences, ALL-CAPS rules, and exhaustive checklists from your
SKILL.md. Tell the model what done looks like, not how to think:

```
# Before
Step 1: Run quick_validate with the --strict flag. If it exits 0, proceed to Step 2.
NEVER skip this step. ALWAYS address every warning before moving on.

# After
Validate before eval. Fix blocking issues; warnings are informational.
```

skill-creator's own SKILL.md was trimmed from 519 → ~415 lines.


---


## `budget_tokens` removed

Returns HTTP 400 on Claude 4.7+. Use `output_config.effort` instead:

```python
# Before
thinking={"type": "enabled", "budget_tokens": 8000}

# After
thinking={"type": "adaptive"},
output_config={"effort": "high"}  # low | medium | high | xhigh | max
```


---


## Hedged language = optional compliance

```
"Try to be concise."      →  suggestion, not a rule
"If possible, use tables" →  suggestion, not a rule

"Be concise."             →  rule
"Use tables."             →  rule
```

Audit for: `try to`, `if possible`, `where relevant`, `you may`, `consider`, `when appropriate`.


---


## Description optimizer: include near-misses

Add 8–10 queries that share keywords but should *not* trigger your skill. They
prevent `run_loop` from optimizing a description that overtriggers:

```json
{"query": "draft release notes for v2.3.0", "should_trigger": true},
{"query": "what changed in this PR?",        "should_trigger": false},
{"query": "write commit messages",           "should_trigger": false}
```


---


## Prompt injection: session-salted delimiters

```python
import secrets, re
salt = secrets.token_hex(4)
tag  = f"ext_{salt}"

def wrap(content: str) -> str:
    clean = re.sub(rf"</?{re.escape(tag)}>", "", content, flags=re.IGNORECASE)
    return f"<{tag}>{clean}</{tag}>"
```

Consistent XML role formatting drops injection success from 61% → 10%.


---


## Model routing

| Tier | Models | Use for |
|---|---|---|
| Top | Fable 5.1, Opus 5.5 | Architecture, review, planning |
| Mid | Sonnet 5.5 | Default execution |
| Fast | Haiku 4.5 | Eval loops, grading, description optimizer |

Context windows: Fable 5.1 / Opus 5.5 / Sonnet 5.5 = 1M / 128K output. Haiku 4.5 = 200K / 64K.


---


## Upgrade

Drop-in. `python bsc.py check <skill-dir>` — score should hold or improve.

`quick_validate` clean · `lint` 0 errors · `static_analysis` no issues · score 84/100

---

# Better Skill Creator 3.0.1 Release Notes

Patch release. Live trigger evals could not run against a current Claude Code
install; this restores them.

## Fix

- **`eval --live` failed before reaching the model.** Recent Claude Code releases
  ship a native `bin/claude.exe` (POSIX: `bin/claude`) and no longer include the
  `cli.js` entry point. `claude_process.claude_command` still rewrote the Windows
  `.cmd`/`.ps1` shim to `node …/cli.js`, so the lookup raised `FileNotFoundError`,
  which `run_eval` recorded as `SUBPROCESS_CRASH` and reported as
  `infrastructure_failed` on every query — no model call was ever made, so no
  trigger rate could be measured. The resolver now prefers the native binary and
  falls back to the legacy `node`+`cli.js` layout only when it is absent. The fix
  is shared by every live path: `bsc.py eval --live`, `skill_test`, `run_eval`,
  and the `run_loop` description optimizer.

## Validation

- Offline pipeline green: `quick_validate` (valid), `lint` (0 errors, 0 warnings),
  `static_analysis` (no issues); `claude plugin validate .` passes.
- Test suite 92/92.
- Live evals now reach the model instead of failing closed:
  `infrastructure_failed` goes from `true` (19/19 errored, pre-fix) to `false`
  (0 errored, post-fix) on the skill's own trigger suite.

## Upgrade notes

- Skills created with v2.1.0 that have a top-level `schemaVersion` must move it
  under `metadata`; `quick_validate` now rejects the top-level key. From the
  repository's `skills/skill-creator/` directory, run
  `python -m scripts.migrate_skill /path/to/skill --to 1` (replace `1` with the
  skill's existing schema version). This preserves the version and writes it as
  a string under `metadata`. Skills already using this layout need no migration.

---

# Better Skill Creator 2.0.2 Release Notes

This patch release corrects one documentation inaccuracy and records why the rest
of PR #10 was dropped.

## Fixes

- The SKILL.md reference entry for `scripts/dependency_graph.py` now shows it takes
  a skill root directory as its positional argument (`<skill-root>`), matching the
  tool's actual CLI and the README usage line.

## Dropped from PR #10

- PR #10 (`fix/variance-check-script-gate`) was authored against the retired
  `skill-architect` layout. Its Gate 0 frontmatter-only collection and its
  variance-check lint/dependency-graph gating have no equivalent in this
  `skill-creator` fork (no numbered gates, no variance-check mode,
  `dependency_graph.py` intentionally optional), so only the doc fix above carried
  over.

## Validation

- Offline pipeline green (`quick_validate`, `lint` 0 errors, `semantic_analysis`,
  score 90/100); `dependency_graph.py` exercised across a skill root in
  summary/json/dot plus the no-arg and bad-path contracts; regression suite 19/19.

---

# Better Skill Creator 2.0.1 Release Notes

This patch release fixes the validation-quality PR review findings.

## Fixes

- Restores cross-file lifecycle consistency validation between `skill.yaml` and
  `LIFECYCLE.md`.
- Replaces newly introduced PEP 604 union annotations in the changed validation
  and IR utilities with Python 3.8-compatible `typing.Union` forms.
- Hardens `safe_path_exists` so resolved sibling paths that merely share a text
  prefix with the base directory are rejected.

## Validation

- Added regression tests for lifecycle mismatch rejection, path-prefix traversal
  rejection, and avoiding PEP 604 unions in the changed modules.

---

# Better Skill Creator 2.0.0 Release Notes

This release adds an independent multi-agent review and adversarial completion
gate for complex skill creation and substantial skill updates.

## Highlights

- Complex skill work now routes through three fresh-context pre-draft reviewers:
  outcome interpretation, adversarial scope, and architecture/validation.
- Completion now requires a fresh completion adversary to try to prove the skill
  incomplete before it can be called done.
- `review.yaml` records activation, independent findings, disagreements,
  synthesis decisions, adversarial findings, dispositions, accepted limitations,
  unresolved decisive questions, and gate status.
- `scripts/review_gate.py` enforces the record deterministically and is wired into
  the package pipeline and full validation script.
- The behavioral checklist now includes the requested RPG, log-fixing,
  no-modification, narrow description-only, simple-skill, and ambiguous-request
  cases.

## Validation & evaluation

This release was held to its own gate. A fresh-context completion adversary tried
to prove the skill incomplete and returned `verdict: complete`; its three
low-severity findings are recorded and disposed in `review.yaml` (development-log
eval case added, `PackageStage` hardened to fail closed on review errors, and one
accepted limitation — offline validation cannot prove real subagent independence).
The full offline pipeline is green (`quick_validate`, `lint`, `static_analysis`,
`review_gate`), architecture score 95/100, and 16/16 pipeline tests pass.

A live previous-vs-new evaluation compared the skill against a no-skill baseline
(same model) over three representative prompts — RPG variant discrimination,
log-fix entailment-vs-authorization, and a no-modification constraint:

| Metric | With skill | Baseline | Delta |
|--------|-----------|----------|-------|
| Pass rate | 100% | 41.7% | +0.58 |
| Time | 104.7s | 65.2s | +39.4s |
| Tokens | 56,073 | 36,921 | +19,152 |

The skill's lift concentrates on ambiguous, underspecified prompts (it forces
variant enumeration and explicit entailment-vs-authorization reasoning); on an
already-constrained prompt the baseline nearly matches, so that case is the least
discriminating. The design-analysis pass costs additional time and tokens.

## Upgrade Notes

- Existing older specs remain compatible. `spec.yaml` continues to represent
  pre-generation intent; review/audit state lives in `review.yaml`.
- Narrow changes may skip the full multi-agent process, but the skip reason should
  be recorded. Substantial changes must pass the review gate before release.
