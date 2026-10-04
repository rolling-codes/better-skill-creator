# Better Skill Creator

[![Release v3.2.0](https://img.shields.io/badge/release-v3.2.0-blue.svg)](https://github.com/rolling-codes/better-skill-creator/releases/tag/v3.2.0)
[![Claude Code Skill](https://img.shields.io/badge/Claude%20Code-Skill-blueviolet.svg)](https://claude.ai/code)
[![Python 3.12+](https://img.shields.io/badge/Python-3.12%2B-green.svg)](#prerequisites)
[![License](https://img.shields.io/badge/license-Apache%202.0-green.svg)](LICENSE.txt)

A quality-gated toolkit for building Claude Code skills — multi-angle design
analysis, adversarial review, measured description optimization, and a
standalone launcher (`bsc.py`).


---


## What makes it different

Most skills are written by feel: the description is guessed at, instructions
are copy-pasted from examples, and whether it triggers correctly is never
measured. This toolkit adds structure at every step where skills usually fail.


### 1 — Design analysis before authoring

Skill-creator doesn't transcribe your request. It scopes the real outcome
from multiple angles before writing a line of SKILL.md.

`"watch my logs"` is treated as detect → diagnose → patch → verify, not a
log grepper. `"build an RPG skill"` is treated as a family of different skills
(flat narrative vs. persistent campaign with world-state) — not one arbitrary
default. You pick the interpretation before the skill is written.

The framework uses adaptive lenses: a core set always evaluated (outcome,
interpretations, entailments, authorization, validation) plus optional lenses
picked up only when they'd change the architecture (security, persistence,
multi-user, error recovery). An unused lens is focus, not omission.

**Entailment ≠ permission.** Discovered work is classified into four buckets:
required-and-authorized (do it), required-but-unauthorized (ask), optional
(recommend, never add silently), out-of-scope (exclude). This prevents
multi-angle reasoning from becoming unauthorized scope expansion.


### 2 — Independent multi-agent review with adversarial gate

Complex skills go through a fresh-context review before packaging — four
agents, none of which saw the original authoring session:

| Agent | Role |
|---|---|
| Outcome analyst | Did the skill accomplish what was actually needed? |
| Scope adversary | What was silently added or silently omitted? |
| Architecture reviewer | Are the structure and validation sound? |
| Completion adversary | Is this actually done, or just apparently done? |

The completion adversary's verdict gates packaging. High and material findings
must be disposed before a `.skill` archive is produced. The system was applied
to its own v2.0 release: the adversary returned `verdict: complete`; its three
low findings are disposed in `review.yaml`.

Live eval: **100% pass rate with-skill vs 41.7% baseline** on three
representative prompts.


### 3 — Description optimizer with held-out test scoring

A skill's `description` field is what decides whether Claude invokes it at
all. Without measurement, optimizing it is guesswork.

`run_loop` tests each candidate description against 20 real queries — split
60/40 into train and held-out test sets — and picks the winner by test score,
not train score. Including **near-misses** (queries that share keywords but
should not trigger) is critical: without them, `run_loop` can optimize a
description that overtriggers on every related request.

```json
{"query": "draft release notes for v2.3.0", "should_trigger": true},
{"query": "what changed in this PR?",        "should_trigger": false},
{"query": "write commit messages",           "should_trigger": false}
```

Failed executions are never counted as passes — a timed-out or crashed run
gets a categorized `QueryOutcome` (`TIMEOUT` / `AUTHENTICATION` /
`SUBPROCESS_CRASH` / `PARSING`) and is excluded from the trigger rate.


### 4 — Six quality gates before packaging

| Gate | What it catches |
|---|---|
| Structure | Missing frontmatter fields, invalid schema, invalid tool names |
| Lint | Hedged instructions, orphaned references, unwired dependencies |
| Static analysis | Dead links, unreachable files, unused tools |
| Semantic | Vague descriptions, over-specification, trigger ambiguity |
| Dependency | Circular imports, missing scripts |
| Review | Independent adversarial multi-agent review |

All six must pass at error level before `package` completes.


### 5 — 2026 model guidance (Fable 5+)

**Over-specification degrades output.** Anthropic's guidance for Fable 5+:
detailed instruction files consume reasoning budget the model should spend on
the task. Write what done looks like, not how to think:

```
# Degrades output on Fable 5+
Step 1: Run quick_validate with the --strict flag. If it exits 0, proceed to
Step 2. NEVER skip this step. ALWAYS address every warning.

# Works
Validate before eval. Fix blocking issues; warnings are informational.
```

**Hedged language = optional compliance.** `try to`, `if possible`, `you may`,
`consider` — each one silently makes your instruction a suggestion.

**`budget_tokens` removed.** Returns HTTP 400 on Claude 4.7+:

```python
# Before
thinking={"type": "enabled", "budget_tokens": 8000}

# After
thinking={"type": "adaptive"},
output_config={"effort": "high"}  # low | medium | high | xhigh | max
```

**Model routing:**

| Tier | Models | Use for |
|---|---|---|
| Top | Fable 5.1, Opus 5.5 | Architecture, review, planning |
| Mid | Sonnet 5.5 | Default execution |
| Fast | Haiku 4.5 | Eval loops, grading, description optimizer |


---


## Prerequisites

- **Python 3.12 or newer**
- **PyYAML** — `pip install pyyaml`
- **Claude Code** — installed; live runs require an explicit `ANTHROPIC_API_KEY` or
  `CLAUDE_CODE_OAUTH_TOKEN` for an isolated profile (interactive login is not inherited)

Verify everything in one step:

```
python bsc.py doctor
```

Doctor reports each check, explains any failure, and tells you exactly what to
run to fix it. No model calls, no settings changes.


---


## Five-minute walkthrough

**Step 1 — Check your setup:**
```
python bsc.py doctor
```

**Step 2 — Create a starter skill:**
```
python bsc.py new my-skill --example release-notes
```

**Step 3 — Check your skill:**
```
python bsc.py check my-skill
```

**Step 4 — Package it:**
```
python bsc.py package my-skill
```

Core security boundaries and migration instructions: [PERMISSIONS.md](skills/skill-creator/PERMISSIONS.md)
and [review source binding](skills/skill-creator/references/independent-review.md#source-binding-and-migration).
Legacy required reviews must be refreshed before packaging; model call allowances
default to 20 and can be raised explicitly with `--max-calls`.

Each command saves a `results.json` and `report.md` under a timestamped
subdirectory of `runs/`.


---


## Commands

```
python bsc.py doctor                            # verify prerequisites
python bsc.py new NAME --example release-notes  # create a starter skill
python bsc.py check PATH                        # run all six quality gates
python bsc.py eval PATH [--live]                # preview or run trigger eval
python bsc.py package PATH                      # package into a .skill archive
python bsc.py --help                            # full option reference
```

**Exit codes:** `0` = passed · `1` = input/infrastructure error · `2` = checks failed


---


## Expected outputs

| Command | Exit 0 | Exit 1 | Exit 2 |
|---|---|---|---|
| `doctor` | All checks passed | A check failed | — |
| `new` | Skill created | Input error or missing prereq | New skill fails check |
| `check` | All gates passed | Input error | One or more gates failed |
| `eval --live` | All trigger checks passed | Infrastructure failure | Some checks failed |
| `package` | Archive created | Input error | Packaging failed |


---


## Troubleshooting

**PyYAML not found:** `pip install -r requirements.txt`

**Claude not authenticated:** Run `claude --version` to confirm Claude Code is
installed. Local checks (`check`, `package`) don't need Claude. `eval --live`
does.

**Directory already exists (`new`):** Choose a different name — `bsc.py new`
never overwrites an existing directory.

Full setup: [SETUP.md](SETUP.md)


---


## Release history

| Version | Shipped |
|---|---|
| **v3.1.0** | 2026 model guidance overhaul — Fable 5 de-specification, `output_config.effort` replaces `budget_tokens`, evidence-backed writing rules |
| **v3.0.0** | Spec compliance — `schemaVersion` moved under `metadata`, real `allowed-tools` names, live eval transport fixed for current Claude Code |
| **v2.1.0** | `bsc.py` launcher (doctor / new / check / eval / package), `examples/release-notes` starter skill, Windows + Ubuntu CI matrix |
| **v2.0.3** | Eval reliability — Windows-compatible streaming (reader thread, no `select`), categorized `QueryOutcome` so failed runs never score as passes, `run_loop` stops on infra failure |
| **v2.0.0** | Independent multi-agent review + adversarial completion gate — 100% vs 41.7% pass rate with-skill vs baseline on live eval |
| **v1.10.0** | Adaptive lenses + entailment ≠ permission — discovered work requires explicit authorization before execution |
| **v1.9.0** | Design Analysis — scope the real outcome from multiple angles instead of transcribing the literal request |
| **v1.8.0** | Orphan-wiring enforcement — features not referenced in SKILL.md now fail the linter instead of shipping invisibly |

Full details: [CHANGELOG.md](CHANGELOG.md) · [Release notes](skills/skill-creator/RELEASE_NOTES.md)


---


## Attribution

Fork of Anthropic's `skill-creator`. See [CHANGELOG.md](CHANGELOG.md) for
the full history.
