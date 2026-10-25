# What's new in Better Skill Creator

Updated 25 October 2026. This document summarizes the **published v3.7.0 release**, including PR #78 and the release-organization work in PR #79. It is a feature overview, not a substitute for the [changelog](../CHANGELOG.md), which records version history; the [user guide](USER_GUIDE.md) explains the entire toolkit.

## Reviewable near-miss test cases

You can now generate candidate trigger tests from neighboring skill descriptions. This helps expose ambiguous boundaries: requests related to your skill's topic that should potentially route elsewhere.

From `skills/skill-creator/`:

```bash
python -m scripts.generate_tests /path/to/my-skill --adjacent-skills /path/to/neighbor-skills
```

The command examines immediate child skill directories and writes `tests/candidates/near_misses.yaml`. Candidate files stay outside the measured trigger suite. They contain a proposed label, not an approved ground truth.

Read each prompt, decide whether your skill really should trigger, set `reviewed: true`, and add a boolean `should_trigger`. Promote the reviewed file with:

```bash
python -m scripts.generate_tests /path/to/my-skill --promote-candidates /path/to/reviewed.yaml
```

Accepted cases go to `tests/generated/near_misses.yaml`, which the trigger loader discovers. Promotion rejects missing review markers, invalid labels, and contradictions with the existing suite. It deduplicates repeated queries. If deduplication removes every case, the command raises an error before writing; it cannot silently replace the output with an empty list or report a successful promotion of zero cases.

Generation and promotion refuse existing outputs unless you explicitly use `--replace`. Replacement remains an intentional overwrite operation. Default six-category scenario generation continues to work separately.

Neighbor metadata now follows the supported Claude skill defaults when a name or description is omitted and incorporates `when_to_use` context. Invalid metadata is reported rather than quietly creating unusable proposals.

**Why review remains necessary:** these suggestions are deterministic combinations of descriptions. An adjacent skill can overlap your target, so a proposal may correctly need a positive label. Model-assisted semantic verification remains planned work.

## Compare baselines separately for each model

Comparisons now accept the front-end's model-specific result reports as well as raw evaluation JSON. You can compare saved runs directly:

```bash
python bsc.py compare --candidate /path/to/candidate-results.json --baseline /path/to/baseline-results.json
```

Or preflight a baseline before evaluating a candidate:

```bash
python bsc.py eval skills/my-skill --models haiku,sonnet --baseline /path/to/baseline-results.json
```

The latter command previews without model calls; add `--live` when you intend to execute the evaluation. Preflight rejects an incompatible baseline before live calls begin.

Each model gets its own comparison. The report identifies missing models and preserves useful results from healthy model runs when another model fails. It never pools models into a single apparent improvement. Comparison summaries now report the actual shared-query counts for model matrices as well as raw pairs.

For front-end matrices and live baseline use, model identity means the exact requested identifier. A configured default does not establish a known model, and an alias is not treated as equivalent to a full model ID. Aliases can resolve differently over time; the report warns about this and recommends pinned IDs for reproducible measurements. Raw legacy pair comparisons retain their documented permissive identity handling and warnings.

## Stronger safeguards for evaluation evidence

New comparisons validate more than the presence of a results file:

- Malformed metrics, duplicate queries, conflicting expected labels, incompatible skill names, and zero shared queries are rejected.
- Infrastructure failures and incomplete query executions cannot produce an ordinary improvement comparison.
- New results record the trigger threshold. Known threshold mismatches block comparison; older files missing the metadata produce a warning.
- Per-query deltas are oriented so positive improvement means better behavior for both positive and negative trigger cases.
- A valid comparison can report a regression without misclassifying that result as an infrastructure failure.

The existing legacy `significance_claim` field describes sample sufficiency and is also exposed as `sample_sufficient`. It does not mean that a statistical significance test was performed. Repetition, variability, compatible tasks, and complete measurements still determine how much confidence to place in an observed change.

## Installed CLI capability checks

```bash
python bsc.py doctor
```

Doctor now inspects the installed Claude CLI's help declarations for evaluation flags, including the isolation and output options the engine needs. A mention in descriptive prose is not counted as a declaration of support. Missing flags, timeouts, transport problems, and launch failures are reported as capability-check failures.

This makes version or packaging incompatibilities easier to diagnose before launching a live eval. It performs no model calls and does not verify authentication, billing settings, model access, or available allowance.

Model argument validation now accepts supported extended-context forms such as `sonnet[1m]` and `opus[1m]` and passes them through unchanged. Acceptance of an identifier by this toolkit does not guarantee that the installed CLI or account supports it.

The [runtime-contract reference](../skills/skill-creator/references/claude-code-contracts.md) distinguishes claims supported by documentation, installed CLI observations, offline tests, and authenticated live execution.

## A bounded two-model trigger canary

The scheduled/release CI canary now tests Haiku and Sonnet separately. Each model receives two positive cases, two negative cases, and a discovery control: **five calls per model, ten across the matrix**, with no retries in that configured run.

Reports preserve outcomes and distinguish missing credentials, expectation failures, and infrastructure failures. Missing credentials produce an explicit skip. Ordinary PR runs skip the live canary; green PR checks establish the tested offline contracts, not authenticated model readiness.

This is a small compatibility canary. Broad repeated trigger and behavior benchmarking across all tiers remains separate planned work.

## Release validation

The v3.7.0 release commit `38b5347` passed the hosted Ubuntu and Windows test workflow. The [release commit run](https://github.com/rolling-codes/better-skill-creator/actions/runs/40107979823) and the [latest verification run](https://github.com/rolling-codes/better-skill-creator/actions/runs/40185684538) both completed successfully. This is evidence for the tested revision, not a permanent claim about later changes. The scheduled live canary has separate credential and model-readiness requirements; ordinary PR CI does not establish those.

## Complete documentation and persistent project context

The documentation now has distinct, maintained purposes:

| Document | Use it for |
|---|---|
| [User guide](USER_GUIDE.md) | Installation, every major feature family, complete workflows, results, troubleshooting, and historical upgrade context |
| [What's new](WHATS_NEW.md) | User-facing feature overview for v3.7.0 |
| [Changelog](../CHANGELOG.md) | The maintained release ledger, including post-release work under Unreleased |
| [Decision record](../decisions.md) | Why the current approaches were chosen, alternatives considered, and tradeoffs |
| [Setup](../SETUP.md) | Concise installation and verification steps using the supported Python floor |
| `AGENTS.md` / `CLAUDE.md` | Matching maintainer context, invariants, work history, and validation boundaries |

The user guide is no longer a draft. Setup now specifies Python 3.12+ and uses the front-end hook installer, which resolves Git's actual hook directory. Older component release summaries remain historical references rather than competing current release ledgers.

## Upgrading and trying the changes

Version 3.7.0 is published; no schema migration is required to upgrade from 3.6.0. Update the plugin through Claude Code, or install the checkout's requirements and run doctor when working from source. Reuse existing tests and add reviewed cases where they exercise a real boundary.

Before comparing versions, preserve a compatible baseline and record the requested model and trigger threshold. Before replacing a generated output, inspect what will be overwritten. Before packaging a skill whose covered files changed, obtain current review evidence. See the [user guide](USER_GUIDE.md) for runnable examples and the distinctions between preview, live evaluation, and saved-transcript grading.
