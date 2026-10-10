# Comparative Benchmark Methodology

**Status: specification.** This document defines how to compare skill conditions fairly and
reproducibly. It does not authorize live trials. No comparative claim ("BSC beats upstream")
may be made until real evidence collected under this methodology supports it.

This methodology reuses the existing benchmark subsystem — `scripts/aggregate_benchmark.py`,
`agents/grader.md`, `agents/comparator.md`, `agents/analyzer.md`, the schemas in
`references/schemas.md`, and `eval-viewer/viewer.html`. Phase 2 adds specification, a gap
analysis, and methodology tests only.

---

## 1. Hypotheses

Two questions are kept strictly separate:

- **H1 — Construction quality:** Does Better Skill Creator (BSC) produce a *valid, well-formed*
  skill artifact more reliably than the alternatives? Measured on the artifact itself
  (`bsc.py check`, lint, structural validators) — no model execution needed.
- **H2 — Downstream task performance:** Does a BSC-built skill help an agent *do a task better*
  than (a) no skill and (b) a skill built by Anthropic's official skill-creator? Measured by
  executing eval tasks under each condition and grading the outputs.

A valid artifact (H1) is **not** evidence of better outcomes (H2). Report them separately.

---

## 2. Conditions

| Condition | Skill provided to the executing agent | How it is produced |
|---|---|---|
| **A — no-skill** | none | same prompt, no skill path |
| **B — upstream** | skill built by Anthropic's official skill-creator | produced once, frozen, snapshotted into the benchmark workspace |
| **C — BSC** | skill built by Better Skill Creator | produced once, frozen, snapshotted |

Each condition's skill is **frozen** (hash-pinned via `scripts/file_policy.source_manifest`)
before any measurement run, so no mid-benchmark edits can contaminate results.

---

## 3. Tasks and skill categories

Reuse `examples/release-notes` as the first task and add categories covering distinct skill
shapes (document generation, data extraction/transform, procedural/tool-driven). Each task
provides:

- a prompt (identical across all three conditions),
- optional input files (identical across conditions),
- an `expectations[]` list of verifiable statements (the grading rubric),
- an `expected_output` description.

Use the `evals.json` schema in `references/schemas.md`. Tasks must be solvable without the
skill (so condition A is meaningful) but plausibly *easier/better* with one.

---

## 4. Metrics and direction

| Metric | Direction | Source | Available today? |
|---|---|---|---|
| Trigger pass-rate | higher better | `run_eval` summary → `compare_eval` | **Yes, automated** |
| Expectation pass-rate | higher better | grader → `grading.json.summary.pass_rate` | **Yes** — `grade_behavior` now derives `summary` |
| Blind rubric score (1–10) | higher better | `agents/comparator.md` → `comparison.json` | Manual workflow only |
| Wall-clock time | lower better | Claude `result` event `duration_ms` | **Captured when present** (result event) |
| Tokens / cost | lower better | Claude `result` event `usage`/`total_cost_usd` | **Captured when present** (result event) |
| Tool calls | lower better (ties on quality) | executor `metrics.json` | Manual workflow only |

For every reported metric, state its direction explicitly. Do not let a reader infer that a
larger number is better — e.g. more tokens is worse, more expectation passes is better. The
per-query `improvement` field added to `compare_eval.py` follows this rule (positive = better,
with NO-TRIGGER queries sign-flipped).

---

## 5. Scoring and aggregation

Reuse the `benchmark.json` schema and `scripts/aggregate_benchmark.py`:

- **per-run** → one `grading.json` (expectations + summary + optional timing/metrics)
- **per-eval** → runs grouped under `eval-N/<condition>/run-K/`
- **per-condition** → `aggregate_results()` computes mean ± stddev (sample stddev, n−1) for
  each metric, plus a `delta` between the first two configurations.
- **runs-per-config ≥ 3.** No improvement claim is made on fewer than 3 valid runs per shared
  comparison point (mirrors `compare_eval._MIN_RUNS_FOR_CLAIM`).

`calculate_stats` excludes unmeasured values (`None`) and reports a measured count `n`
alongside `mean/stddev/min/max`. A missing measurement is dropped from the mean rather than
counted as a zero, so a partially-instrumented condition is not silently dragged toward 0.
`n == 0` means "not measured"; `n > 0` with `mean == 0` is a real measured zero. Per-run
serialization keeps unmeasured metrics as JSON `null` (never 0) so the viewer — which excludes
missing via `!= null` and recomputes its own per-config averages — stays consistent with the
authoritative `run_summary` stats and cannot re-introduce the missing-as-zero bias downstream.
Each metric carries its own `n`: a run may record duration while lacking token or tool-call
measurements, so interpret `n` per metric, not per run.

---

## 6. Controls and comparability

- Identical prompt, input files, executor model, and call budget across all three conditions.
- **Blind grading:** route quality judgment through `agents/comparator.md` (judge A/B without
  knowing which condition produced which output) to remove pro-skill bias.
- Document unavoidable workflow differences (e.g. BSC and upstream emit different skill shapes)
  rather than hiding them.
- **Never compare incompatible runs silently.** Before aggregating, apply the compatibility
  gate pattern from `scripts/compare_eval.validate_compatibility` (same task set, no
  infrastructure failures, overlapping evals). Mismatches are errors, not warnings.

---

## 7. Repetition and incomplete runs

- ≥ 3 runs per configuration per eval.
- A run whose `grading.json` is missing or malformed is **excluded and reported**, never
  counted as a zero that would distort the mean (`load_run_results` already skips and warns).
- An eval with any infrastructure failure in any condition is marked incomplete and excluded
  from aggregate claims, with the exclusion stated in the report.

---

## 8. Decision criteria and uncertainty

- Report every metric as `mean ± stddev` over valid runs, with n (valid run count) shown.
- An "improvement" claim for H2 requires: ≥ 3 valid runs per condition, a positive oriented
  delta, **and** the delta exceeding the combined stddev band (not within noise).
- If runs are too few or variance too high, the report states "no claim supported," not a
  weaker-but-stated improvement.
- Flaky evals (high variance across runs) are surfaced by the analyzer (`agents/analyzer.md`),
  not averaged away.

---

## 9. Report template

The benchmark report separates, in this order:

1. **Outcomes** — H1 (construction validity) and H2 (task performance) tables, per condition.
2. **Cost** — tokens/cost and wall-clock time per condition, with direction noted.
3. **Uncertainty** — stddev bands, valid-run counts, flagged flaky evals.
4. **Limitations** — unmeasured metrics, workflow differences, sample-size caveats, and any
   condition that could not be run.

No executive summary may assert a winner that the Uncertainty section does not support.

---

## Gap analysis — instrumentation status

The harness existed; its **metric inputs lacked a reproducible automated producer.** Phase 3
closed the three recoverable gaps (offline, no live calls). Current status:

| Metric | Consumer | Producer | Status |
|---|---|---|---|
| trigger pass-rate | `compare_eval.py` | `run_eval` summary | **Automated** |
| `summary.pass_rate` | `aggregate_benchmark.py:136` | `grade_behavior()` now derives `summary` from validated `expectations[]` | **Automated (Step 2)** |
| tokens / cost / `duration_ms` | `aggregate_benchmark.py:144,151` | `run_eval` now captures `total_cost_usd`/`usage`/`duration_ms` from the `result` event into row+summary `metrics` | **Captured when present (Step 1)** |
| `execution_metrics.total_tool_calls` | `aggregate_benchmark.py:157` | executor `metrics.json`, manual workflow only | **Still manual** |
| model configuration | pairing guard | not recorded per-run yet | **Unverified → warning (see below)** |

**Caveats:** cost/usage/duration are captured only when the Claude `result` event carries them;
a run that short-circuits on an early trigger detection will have `metrics = None` (honest
"not measured", never a fabricated 0). Tool-call counts still require the operator-driven
subagent workflow. The pairing guard enforces task-set, condition, run-count, and rubric
equality as hard errors; **model** comparability is a *warning* until a `model` field is
recorded per run, at which point the guard upgrades a mismatch to an error.

**Pairing is balance, not one-to-one matching.** The guard checks that each condition covers
the same evals with equal per-eval run *counts* — the balance that unpaired, per-condition mean
aggregation requires. It does not match replicate *k* of one condition to replicate *k* of
another, because runs are independent replicates with no shared seed or replicate identifier.
Paired analysis (e.g. same input seed across conditions) would require introducing a replicate
id and is out of current scope; until then, do not interpret equal counts as paired
observations.

### Implemented in Phase 3

1. **Cost/usage/duration capture** — `run_eval.py` `run_single_query` reads the `result` event's
   `total_cost_usd`, `usage`, and `duration_ms`; `_aggregate_results` sums present values over
   ok runs into per-row and summary `metrics` (None when unmeasured). No new model calls.
2. **Programmatic `summary.pass_rate`** — `skill_test.grade_behavior` computes
   `summary = {passed, failed, total, pass_rate}` from validated rows and writes it into
   `grading.json`, so the automated path produces what `aggregate_benchmark.py` consumes.
3. **Pairing guard** — `aggregate_benchmark.validate_benchmark_pairing(results,
   expected_conditions=…)` returns `(errors, warnings)` and rejects comparisons across
   mismatched task sets, missing/extra conditions, unequal per-eval run counts, and differing
   rubric (expectation-text) sets; model mismatch is enforced once models are recorded.

### Methodology tests (offline, no live calls)

Covered by `tests/test_run_eval_stream.py` (metric capture + aggregation; None vs 0),
`tests/test_skill_test_grader.py` (derived `summary.pass_rate`), and
`tests/test_aggregate_benchmark.py` (regression→negative/improvement→positive delta, missing
grading excluded, and one failing fixture per pairing-guard dimension plus an aligned pass).

### Still required before live trials

- Record executor/analyzer `model` per run so the pairing guard's model dimension becomes a
  hard error rather than a warning.
- Decide whether tool-call counts are in scope; if so, add a producer for `execution_metrics`.
- Only then run paid trials, with conditions frozen + hash-pinned.
