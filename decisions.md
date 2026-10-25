# Project decisions

Updated 25 October 2026. This record explains decisions behind the v3.7.0 implementation, its CI repair, and the completed documentation. It records rationale and consequences; it does not replace the [user guide](docs/USER_GUIDE.md), [changelog](CHANGELOG.md), or executable validation contracts.

## 1. Keep proposed test labels outside the measured suite

**Decision:** Generate adjacent-skill near misses into `tests/candidates/`, then require explicit review before promotion into `tests/generated/`.

**Alternative considered:** Insert automatically generated negative cases directly into trigger evaluations.

**Reason:** Related skill descriptions can overlap. Deterministically combining them does not prove that the target should stay inactive. Treating a proposed negative as truth could reward undertriggering and train the optimizer against incorrect labels.

**Consequence:** The workflow needs a human or independently justified label review. Each case requires `reviewed: true` and an explicit boolean label. Model-assisted semantic verification remains planned rather than implied by this feature.

**Evidence:** `generate_tests.py`, `tests_loader.py`, and the near-miss promotion regression tests.

## 2. Reject a promotion that has nothing new to write

**Decision:** After deduplication against the included suite, raise `TestCaseError` when the accepted set is empty, before opening the destination file.

**Alternative considered:** Write an empty YAML list and return success, or treat the operation as an ordinary successful no-op.

**Reason:** The operation promises to promote cases. Writing an empty file could occupy a new destination or, with replacement enabled, erase earlier promoted cases. Reporting success would conceal the absence of new coverage.

**Consequence:** Callers receive an actionable failure and existing output stays intact. Regression coverage checks both preservation and CLI failure without a success message. Intentional replacement of a nonempty accepted set still requires the explicit replacement flag.

## 3. Preserve separate model comparisons

**Decision:** Align front-end baselines by exact requested model identifier and report comparisons per model.

**Alternatives considered:** Pool all model results into one score, equate aliases to full model IDs, or accept a configured default as an explicit identity.

**Reason:** A pooled score can hide a regression on one model behind a gain on another. Alias resolution can change across runs, and an unnamed configured default does not establish what executed. Reproducibility needs a visible identity contract.

**Consequence:** Missing models and identity mismatches remain visible. Aliases are supported but carry reproducibility warnings; pinned IDs are stronger evidence. Legacy raw-pair comparisons retain their permissive contract and warnings to avoid silently breaking older saved results.

## 4. Validate baseline provenance before live dispatch

**Decision:** Validate metrics, query/label consistency, overlap, skill/model compatibility, execution completeness, and known trigger thresholds before spending live calls on an incompatible baseline.

**Alternative considered:** Run the candidate first and discover comparison problems afterward, or calculate a delta from whatever fields are available.

**Reason:** Invalid measurements do not become comparable because a new candidate was evaluated. Preflight avoids unnecessary calls and prevents incomplete execution from appearing to be a clean negative result or improvement.

**Consequence:** Incompatible inputs fail early. Missing legacy threshold metadata warns rather than inventing a value; known mismatches block comparison. Valid regressions remain valid comparison outcomes. Sample sufficiency fields do not claim a statistical significance test.

## 5. Check CLI capability without using an authenticated model call

**Decision:** Have doctor inspect installed help declarations for required evaluation flags and report transport, timeout, and launch failures explicitly.

**Alternatives considered:** Infer support from a hard-coded version number, accept any prose mentioning a flag, or make a live model call as part of doctor.

**Reason:** Installed distributions and CLI layouts can differ. Declared options are more direct compatibility evidence than a guessed version table, while a live model call would turn a prerequisite check into a metered operation requiring account readiness.

**Consequence:** Doctor can diagnose interface compatibility without spending model budget. It cannot establish authentication, credit, quota, model availability, or successful live evaluation. The runtime-contract reference preserves those evidence boundaries.

## 6. Use a small bounded canary

**Decision:** Run separate Haiku and Sonnet canaries on scheduled/release workflows, with four shared cases and a control per model, five calls each, and explicit skip/failure reports.

**Alternative considered:** Run a broad repeated benchmark across every tier on every PR, or describe the small canary as a comprehensive benchmark.

**Reason:** A canary should catch discovery/runtime failures with a predictable allowance. Broad performance comparisons need more tasks, repetitions, behavioral evidence, and authorization than this small compatibility check provides.

**Consequence:** The canary is affordable and bounded but supports a narrow conclusion. Ordinary PR CI does not make authenticated live calls. Broader benchmarking remains separately scoped work.

## 7. Repair stale review evidence through actual independent review

**Decision:** Obtain fresh outcome, scope, architecture, practices, and completion reports, then bind the record to the current source and rerun the gate.

**Alternatives considered:** Remove the failing live-review assertion, weaken the gate, record a skip for the substantial feature work, or refresh hashes while keeping old approvals.

**Reason:** CI correctly detected that source changed after review. Bypassing that failure would defeat the source-binding invariant and imply that reviewers examined bytes they had not reviewed.

**Consequence:** The gate continues to reject stale evidence. The repaired commit `8f4bb8c` matched all 141 manifest entries and passed the hosted Ubuntu/Windows workflow. Future covered-source changes still require an appropriate renewed review; this repair does not grant approval to later code.

**Evidence:** `review.yaml` and [CI run 40095839453](https://github.com/rolling-codes/better-skill-creator/actions/runs/40095839453). Hashes detect source drift but do not independently authenticate reviewer identity.

## 8. Correct local test conditions instead of changing product behavior

**Decision:** Use an isolated pytest temporary directory and select the Python 3.12 interpreter for local Git Bash checks; report the unavailable symlink privilege separately.

**Alternative considered:** Change unrelated hook/runtime code to satisfy a machine selecting Python 3.15 without PyYAML, or weaken tests to conceal the local restrictions.

**Reason:** The failures had distinct environment causes: inaccessible earlier test directories, a shell interpreter different from the installed supported test environment, and a missing Windows privilege. These did not establish product defects.

**Consequence:** Local evidence is reported with its conditions—928 passed, 28 skipped, one privilege-dependent deselection. Hosted CI separately ran and passed both platform jobs. No general full-suite claim is inferred from a filtered local run.

## 9. Keep implementation in the engine and use the front-end as orchestration

**Decision:** Keep substantive evaluation, comparison, analysis, and packaging logic under `skills/skill-creator/scripts/`; let `bsc.py` dispatch and serialize results.

**Alternative considered:** Duplicate rules in the human-facing CLI or describe engine-only commands as interchangeable front-end options.

**Reason:** One implementation prevents drift between conversational workflows, engine invocations, and the front-end. The actual command contracts differ: for example, front-end packaging protects source through a temporary copy, whereas direct engine packaging can repair in place.

**Consequence:** New logic should extend the engine first and add focused orchestration as needed. Documentation must name the correct working directory and command-specific flags. Existing abstractions do not imply that all possible model-backed stages are implemented.

## 10. Publish complete repository docs with distinct responsibilities

**Decision:** Maintain a full `docs/USER_GUIDE.md`, a focused `docs/WHATS_NEW.md`, the root release ledger, and this rationale record. Link the documents from README/setup and describe v3.7.0 as released only after its tag and GitHub release exist.

**Alternatives considered:** Leave a large draft beside the chat, label branch features as shipped before publication, or overwrite all historical component notes to make them look current.

**Reason:** Users need a stable usage reference, a short explanation of recent changes, and an honest distinction between released and branch-only behavior. Historical records are useful evidence but disagree on dates, model advice, and coverage; rewriting them would erase that context.

**Consequence:** The root changelog is the maintained ledger; shorter component histories remain historical. The v3.7.0 release is dated 24 October 2026, and its docs now distinguish released features from follow-up work. Current behavior is checked against source. Setup uses Python 3.12+ and Git's resolved hook installer. Time-sensitive model claims are framed by their evidence rather than repeated as permanent facts.

## 11. Keep explanatory docs outside the runtime skill tree

**Decision:** Store the guide and change overview under repository-level `docs/`, and rationale in repository-level `decisions.md`.

**Alternative considered:** Put the full human manual under the skill's runtime references and change its dependency links solely to distribute these repository docs.

**Reason:** The manual explains the product to humans and maintainers. It is not an extra workflow resource the model needs to load on every skill-authoring task. Moving it into the skill would expand its package/context surface and invalidate the current source-bound review.

**Consequence:** The existing runtime review can remain current during these repository documentation edits. If a future task adds runtime guidance inside the skill, it must update resource wiring and review evidence as appropriate; this placement is not an exemption for actual skill-source changes.

## 12. Maintain matching agent context

**Decision:** Keep `AGENTS.md` and `CLAUDE.md` synchronized in the active Git checkout and add the same dated work context to the enclosing local workspace's guidance pair.

**Alternative considered:** Record the work only in this conversation or update one agent's instruction file while leaving the other stale.

**Reason:** Future sessions need the actual target runtime, verified repair state, documentation map, and invariants without reconstructing the conversation. The enclosing workspace is not itself the Git checkout, so agents also need an explicit instruction to verify their working directory.

**Consequence:** Shared maintainer instructions are mirrored. They describe evidence at a known commit, not an evergreen claim that CI passes. They retain the distinction between local files and external publication; completing documentation does not itself authorize a new release or deployment.

## Maintaining this record

Add a decision when the alternatives change behavior, compatibility, evidence quality, authorization, or maintenance cost. Include the choice, credible alternatives, reason, consequences, and relevant evidence. If a decision changes, mark it superseded and explain the new choice rather than silently rewriting history. Routine formatting and typo edits do not need individual entries.
