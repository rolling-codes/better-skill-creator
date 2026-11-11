# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [3.7.5] - 2026-11-10

Commands and flags are unchanged.

### Fixed

- A recorded independent-review skip (`activation.required: false` with a
  reason) no longer fails `scripts.validate` or `scripts.review_gate` with
  `review-agent-missing` on a skill that does not ship the toolkit's
  `agents/*.md` files. The skip is still validated for a reason, a source
  binding, and staleness. A skip without a reason does not waive the agent
  check, and a required review still needs the agent files. Reported by
  @chaser940428-pixel.

- **Behavior grading scoped to one case** — `grade_behavior()` now accepts
  `--behavior-case` and passes only the selected case's assertions to the
  judge. Multi-case suites require explicit selection; single-case suites
  auto-select. Duplicate assertion text across different cases is now
  permitted.

- **Grades bound to their evidence** — `evidence_digest()` computes a
  SHA-256 over assertions, output files, and optional transcript.
  `merge_grades()` rejects stale model grades whose digest does not match
  current evidence. Legacy grades without a digest are flagged
  `unverified: true` rather than silently accepted.

- **Blank prompts rejected before dispatch** — `run_eval()` raises
  `ValueError` for blank or whitespace-only prompts before any infra or
  model call. `generate_tests.py` also filters blank prompts before writing
  generated YAML fixtures.

- **Frontmatter identity used consistently** — `grade_behavior()` provenance
  and `bsc eval` now use the `name:` field from `SKILL.md` instead of the
  directory name. Baselines tied to a directory name need their `skill_name`
  field updated to the declared frontmatter name.

- **Infrastructure failure diagnostics preserved** — `_check_infra()` returns
  a full `QueryOutcome` instead of a bare `bool`. Failure reports include
  `infrastructure_error` (e.g. `timeout`, `authentication`, `not_triggered`)
  and `infrastructure_error_detail`. `run_loop` propagates both fields;
  `held_out_score` is `null` when the held-out eval itself hits an infra
  failure.

### Documentation

- `docs/MODEL_BEHAVIOR.md` now covers all four current model tiers (Opus 5.5,
  Sonnet 5.5, Sonnet 5, Haiku 5.5, Fable 5.2) with a tier overview, per-behavior
  tables linked to Anthropic's own pages, and one-run live trigger snapshots per
  alias.

- Adds a Sonnet 5.5 table built from Anthropic's own prompting guide (effort,
  `between_tools` thinking, early stopping and verification, mid-turn messages,
  JSON tasks, tool-call handling). Corrects an earlier claim that no Sonnet 5.5
  guide had been published. Records what two independent evaluators (Artificial
  Analysis and Vals.ai) report about Sonnet 5.5.

### License

- The project is now licensed under **Apache License 2.0** with an Additional
  Terms section requiring that anyone who sells or commercially distributes the
  Work or any Derivative Work must credit **RollingCodes** as the original
  creator with a link to this repository. Free use, modification, and
  redistribution are unaffected.

## [3.7.4] - 2026-11-09

Install v3.7.4 before the next `package` or grade. v3.7.3 can approve a skill
that the packager then rewrites or strips, and it can turn a grade into a
score for work the judge never saw. Commands and flags are unchanged. What
changes is which skills pass, which bytes enter an archive, and which grades
are allowed to count.

Each item below names the issue and the pull request that landed it. Issues
[#102](https://github.com/rolling-codes/better-skill-creator/issues/102)
through
[#108](https://github.com/rolling-codes/better-skill-creator/issues/108)
are the defect reports.
[#113](https://github.com/rolling-codes/better-skill-creator/pull/113)
landed [#102](https://github.com/rolling-codes/better-skill-creator/issues/102),
[#103](https://github.com/rolling-codes/better-skill-creator/issues/103),
[#104](https://github.com/rolling-codes/better-skill-creator/issues/104),
[#106](https://github.com/rolling-codes/better-skill-creator/issues/106),
[#107](https://github.com/rolling-codes/better-skill-creator/issues/107),
and
[#108](https://github.com/rolling-codes/better-skill-creator/issues/108).
[#111](https://github.com/rolling-codes/better-skill-creator/pull/111)
landed
[#105](https://github.com/rolling-codes/better-skill-creator/issues/105).
[#112](https://github.com/rolling-codes/better-skill-creator/pull/112)
landed the package-target half of
[#108](https://github.com/rolling-codes/better-skill-creator/issues/108).
[#99](https://github.com/rolling-codes/better-skill-creator/pull/99)
has no separate issue; it is the grading work found while those defects were
open.
[#109](https://github.com/rolling-codes/better-skill-creator/pull/109)
is the Fable 5.2 documentation.
[#101](https://github.com/rolling-codes/better-skill-creator/pull/101)
adds the offline package preview.
[#110](https://github.com/rolling-codes/better-skill-creator/pull/110)
bumps the GitHub Actions pins.

### What was fixed

- `check` and `package` now agree when `SKILL.md` or `skill.yaml` names a
  secret-like file such as `references/secrets.md`, `credentials`, or a
  `*.key` sample. Both fail and name the pattern. Rename the file to ship it.
  The package report lists every path the policy skips.
  Issue
  [#105](https://github.com/rolling-codes/better-skill-creator/issues/105).
  Pull request
  [#111](https://github.com/rolling-codes/better-skill-creator/pull/111).
- `package` on a missing path, or on a file instead of a skill directory,
  reports the same input error as `check`: the target must be a directory
  that contains `SKILL.md`. A snapshot that no longer contains `SKILL.md`
  uses that same error.
  Issue
  [#108](https://github.com/rolling-codes/better-skill-creator/issues/108).
  Pull requests
  [#112](https://github.com/rolling-codes/better-skill-creator/pull/112)
  and
  [#113](https://github.com/rolling-codes/better-skill-creator/pull/113).
- Info-only runs of `static_analysis`, `semantic_analysis`, `validate`, and
  `repair` exit 0. Exit 2 means warnings. `repair` prints notes as info.
  Issue
  [#107](https://github.com/rolling-codes/better-skill-creator/issues/107).
  Pull request
  [#113](https://github.com/rolling-codes/better-skill-creator/pull/113).
- A fresh scaffold, and any description that still starts with `TODO`, fails
  `check`. A section whose only body is an HTML comment is empty.
  Issue
  [#106](https://github.com/rolling-codes/better-skill-creator/issues/106).
  Pull request
  [#113](https://github.com/rolling-codes/better-skill-creator/pull/113).
- A file is referenced only when the path token matches. `guide.md` stays
  orphaned when the skill names `style-guide.md`. The same boundary applies
  to `utils.py` beside `test_utils.py` and to `scripts.lint` inside
  `scripts.lint_stage`.
  Issue
  [#104](https://github.com/rolling-codes/better-skill-creator/issues/104).
  Pull request
  [#113](https://github.com/rolling-codes/better-skill-creator/pull/113).
- Headings inside fenced examples are not duplicate sections. Duplicate
  headings outside fences are removed from the bottom of the file, and only
  when that line still holds the heading.
  Issue
  [#103](https://github.com/rolling-codes/better-skill-creator/issues/103).
  Pull request
  [#113](https://github.com/rolling-codes/better-skill-creator/pull/113).
- An activation skip covers the source manifest recorded with it. The next
  edit needs a new skip or a review.
  Issue
  [#102](https://github.com/rolling-codes/better-skill-creator/issues/102).
  Pull request
  [#113](https://github.com/rolling-codes/better-skill-creator/pull/113).
- Paired grading and saved-transcript grading are separate steps. A nonempty
  rubric is required before `check`, `merge`, or a benchmark score. Reviewed
  `text_line` checks grade one exact UTF-8 line locally. Preflight can reject
  a plan above `--max-dispatches`.
  Pull request
  [#99](https://github.com/rolling-codes/better-skill-creator/pull/99).

### What bugs were found

- Issue
  [#105](https://github.com/rolling-codes/better-skill-creator/issues/105),
  fixed in
  [#111](https://github.com/rolling-codes/better-skill-creator/pull/111):
  a guide named `references/secrets.md` passed `check` because the file was
  on disk. `package` then deleted it for the secret-name policy and reported
  it as missing. The same trap hits `credentials` and `*.key` samples.
- Issue
  [#108](https://github.com/rolling-codes/better-skill-creator/issues/108),
  fixed in
  [#112](https://github.com/rolling-codes/better-skill-creator/pull/112)
  and
  [#113](https://github.com/rolling-codes/better-skill-creator/pull/113):
  `python bsc.py package nope` and `python bsc.py package path/to/SKILL.md`
  printed a raw `FileNotFoundError` or `NotADirectoryError`, then told the
  author to run `doctor`.
- Issue
  [#107](https://github.com/rolling-codes/better-skill-creator/issues/107),
  fixed in
  [#113](https://github.com/rolling-codes/better-skill-creator/pull/113):
  a skill whose only findings were notes such as `unused-tool` exited 2 from
  `static_analysis`, `semantic_analysis`, and `validate`. `repair` called
  those notes warnings.
- Issue
  [#106](https://github.com/rolling-codes/better-skill-creator/issues/106),
  fixed in
  [#113](https://github.com/rolling-codes/better-skill-creator/pull/113):
  `python -m generators` still produced a skill that passed `check`, scored
  82, and packaged. The description was the `TODO` template, and every
  section body was an HTML comment.
- Issue
  [#104](https://github.com/rolling-codes/better-skill-creator/issues/104),
  fixed in
  [#113](https://github.com/rolling-codes/better-skill-creator/pull/113):
  naming `references/style-guide.md` hid `references/guide.md` from the
  orphan check, because the bare filename was a substring. The same false
  pass hid `utils.py` next to `test_utils.py` and `scripts.lint_stage` next
  to `scripts.lint`.
- Issue
  [#103](https://github.com/rolling-codes/better-skill-creator/issues/103),
  fixed in
  [#113](https://github.com/rolling-codes/better-skill-creator/pull/113):
  two example blocks that both contained `## Summary` were repaired by
  deleting the second heading inside the fence. A second duplicate later in
  the file was deleted at a stale line, so `### Keep me` disappeared and
  `## Notes` stayed duplicated. `package` could still report success.
- Issue
  [#102](https://github.com/rolling-codes/better-skill-creator/issues/102),
  fixed in
  [#113](https://github.com/rolling-codes/better-skill-creator/pull/113):
  `activation.required: false` in `review.yaml` stayed valid after every
  later edit, including edits under `scripts/`. The gate, the test suite, and
  packaging all passed.
- Found in review of
  [#99](https://github.com/rolling-codes/better-skill-creator/pull/99),
  and fixed there: blind transcript grading put the skill name on the
  identity screen. A real `Skill` tool call contains that name, so every
  expectation became `UNDETERMINED` and the judge was never called. Words
  such as `baseline`, `candidate`, and a bare model alias did the same to
  ordinary task text. Files under `dist/` or `runs/`, and files named
  `metrics.json` or `timing.json`, were dropped from the evidence with no
  note.
- Found in review of
  [#99](https://github.com/rolling-codes/better-skill-creator/pull/99),
  and fixed there: a case with no assertions still produced a benchmark row
  at a 0% pass rate.

### Why change now

- Issue
  [#105](https://github.com/rolling-codes/better-skill-creator/issues/105)
  /
  [#111](https://github.com/rolling-codes/better-skill-creator/pull/111):
  re-run `check` on anything you packaged with v3.7.3. Open the archive and
  confirm every referenced file is inside it. If a skill references
  `secrets.*`, `credentials`, or `*.key`, rename the file and update the
  reference before the next package.
- Issue
  [#106](https://github.com/rolling-codes/better-skill-creator/issues/106)
  /
  [#113](https://github.com/rolling-codes/better-skill-creator/pull/113):
  if you generated a skill and have not replaced the `TODO` description,
  `check` will now fail. Replace the description and the HTML-comment
  placeholders before you share it.
- Issue
  [#103](https://github.com/rolling-codes/better-skill-creator/issues/103)
  /
  [#113](https://github.com/rolling-codes/better-skill-creator/pull/113):
  if `package` rewrote `SKILL.md` on v3.7.3, compare the archive with your
  source. Example headings inside fences may have been deleted.
- Issue
  [#102](https://github.com/rolling-codes/better-skill-creator/issues/102)
  /
  [#113](https://github.com/rolling-codes/better-skill-creator/pull/113):
  if a review skip was recorded before this release, record it again against
  the current source or run the review.
- Pull request
  [#99](https://github.com/rolling-codes/better-skill-creator/pull/99):
  re-grade any paired run or transcript you scored on the blind-judging path
  in this development line. A score from an empty rubric, or from a judge
  that did not see the skill call or the output files, is not a result.
- Pull request
  [#109](https://github.com/rolling-codes/better-skill-creator/pull/109):
  model notes for Claude Fable 5.2 (`claude-fable-5-2`), including the
  request patterns that now return 400, are in this release. Use them before
  you pin a skill to that model.

### Added

- Blind judging for residual assertions and optional pairwise comparison.
  Identity-bearing evidence is screened before a judge call.
  Pull request
  [#99](https://github.com/rolling-codes/better-skill-creator/pull/99).
- Offline `text_line` checks for one exact UTF-8 line, beside `json_value`
  and `csv_rows`.
  Pull request
  [#99](https://github.com/rolling-codes/better-skill-creator/pull/99).
- Preflight dispatch counts, per-case reviewed and residual coverage, and
  `--max-dispatches`.
  Pull request
  [#99](https://github.com/rolling-codes/better-skill-creator/pull/99).
- An offline package-preview workflow builds `skill-creator.skill` on pull
  requests that touch the packager.
  Pull request
  [#101](https://github.com/rolling-codes/better-skill-creator/pull/101).

### Documentation

- Model guidance covers Claude Fable 5.2, released 9 November 2026. The
  behavior matrix lists what Anthropic documents and what that means for a
  skill. The model table corrects Haiku 5.5 pricing and adds default effort
  for each model.
  Pull request
  [#109](https://github.com/rolling-codes/better-skill-creator/pull/109).
- `docs/MODEL_BEHAVIOR.md` records the Fable 5.2 behaviors that can change
  results between model versions.
  Pull request
  [#109](https://github.com/rolling-codes/better-skill-creator/pull/109).
- `docs/BLIND_JUDGING.md` explains what a blind judge sees and how to read
  the cost report.
  Pull request
  [#99](https://github.com/rolling-codes/better-skill-creator/pull/99).

### Maintenance

- GitHub Actions dependencies were bumped.
  Pull request
  [#110](https://github.com/rolling-codes/better-skill-creator/pull/110).

### License

- The repository license is Better Skill Creator License 1.1. It does not
  include any other license text. A same-product copy is one of these: a
  release `.skill` or plugin zip, a checkout of this repository, the names
  Better Skill Creator, better-skill-creator, or skill-creator-local, 40 or
  more copied words in a row, 20 or more copied source lines in a row, a
  fork, translation, or other edit, a tree that still shares 70 percent of
  the lines in `SKILL.md` and in 5 files under `scripts/`, or an installer
  that extracts those files. A product that fails every test, with new
  source files and a different name, may be sold.
- The v3.7.4 release includes this license. `LICENSE` is in the plugin zip
  and the source archive. `LICENSE.txt` is in `skill-creator-3.7.4.skill`.

## [3.7.3] - 2026-11-06

A skill is a folder of instructions the model may load. Packaging copies that
folder into a shareable archive. Grading runs one task with the skill and one
baseline, then checks the saved files. This release clears two stalls in that
path. Install commands and flags are unchanged.

### Fixed

- The packager skipped secret filenames only when the spelling matched exactly.
  A trailing space or dot, a leading dot on a key name (`.id_rsa`), an invisible
  character, or a compatibility letter (`İD_RSA`) still entered the archive.
  On Windows the system ignores trailing dots and spaces, so the lookalike can
  be the real secret. Names are folded before the same skip list is applied.
  `.git.` and `dist.` fold into the excluded directories `.git` and `dist`.
  A component that folds into `..` is skipped. Ordinary names such as
  `guide.md` stay. Rename a file only when you meant to ship it and its folded
  name is now excluded. This repository had no file in that set.

### Documentation

- v3.7.2 added offline grading for paired runs, and the guides people copy
  from still listed trigger tests and trigger-result comparison. A plan that
  called `authoring_eval.py` had no command to run. The agent guide and user
  guide now name `python -m scripts.authoring_eval` from `skills/skill-creator/`:
  `preflight` checks the plan, `prepare` reserves a run and does not write
  `eval_metadata.json`, `check` grades reviewed file assertions, and `merge`
  writes `grading.json`. Pass leftover reviewer grades only when `check` still
  has some. Keep a reviewer's earlier grade in `reference-grades.json`, because
  the next merge replaces `grading.json`. That grade's run id and model must
  match the prepared run. This repository had no saved grade to move.
  ([#91](https://github.com/rolling-codes/better-skill-creator/issues/91))

### Changed

- The skill's own review record uses a narrow skip after the schema example
  and the filename filter changed. The previous reports stay in `review.yaml`
  as history. Other skills that still require a review are unchanged.

## [3.7.2] - 2026-11-05

### Added

- Added offline preflight and grading for paired authoring evaluations
  (`scripts/authoring_eval.py`). Reviewed JSON and CSV checks grade saved outputs
  locally; an independent grader covers residual assertions. Each case still needs
  fresh candidate and baseline runs.
  ([#89](https://github.com/rolling-codes/better-skill-creator/pull/89))

### Fixed

- Reject saved evaluation rows with zero successful runs, incomplete executions
  marked as passed, or pass flags that disagree with the recorded trigger threshold.
- Reject out-of-range metrics, contradictory run counts and rates, incomplete
  summaries, and reports with conflicting raw and nested result payloads.
- Require explicit model identities in matrix rows and live baseline preflight.
  Legacy raw single-pair comparisons retain support for unknown model identities.
- Declare the Apache-2.0 license in Python package metadata and link bundled
  release-history pointers to the canonical changelog.

## [3.7.1] - 2026-10-25

### Added

- Added a complete user guide, a v3.7.0 feature overview, and a decision record for maintainers.

### Changed

- Updated repository setup and agent guidance to reflect the published v3.7.0 release.

### Fixed

- Added coverage ensuring the `pyproject.toml` package version stays aligned with the CLI and plugin version.

## [3.7.0] - 2026-10-24

Added reviewed near-miss candidates, model-aware baseline comparisons, and a bounded Haiku/Sonnet
trigger canary. Also aligned release metadata and setup documentation with the supported Python
floor and made the root changelog the single release-history source.

### Added

- Added offline near-miss proposals from adjacent skills, with explicit label review and promotion
  into measured trigger suites. ([#78](https://github.com/rolling-codes/better-skill-creator/pull/78))
- Added model-aligned comparisons for front-end evaluation reports, baseline preflight before live
  calls, and per-model query summaries. ([#78](https://github.com/rolling-codes/better-skill-creator/pull/78))
- Added installed-CLI evaluation-flag checks to doctor without authentication or model calls.
  ([#78](https://github.com/rolling-codes/better-skill-creator/pull/78))
- Added a bounded Haiku/Sonnet trigger canary, with five calls per model and explicit skip/failure
  reporting. ([#78](https://github.com/rolling-codes/better-skill-creator/pull/78))

### Changed

- Kept candidate proposals outside measured suites until reviewed; comparison rejects incomplete
  executions and known threshold mismatches, and warns on missing legacy thresholds and model-alias
  reproducibility. ([#78](https://github.com/rolling-codes/better-skill-creator/pull/78))
- Updated setup instructions for Python 3.12+, Git-resolved hook installation, and the current
  plugin name. ([#79](https://github.com/rolling-codes/better-skill-creator/pull/79))
- Made the root changelog the release-history source and added a root Apache-2.0 license.
  ([#79](https://github.com/rolling-codes/better-skill-creator/pull/79))

### Fixed

- Rejected duplicate-only near-miss promotions before writing, preserving existing output.
  ([#78](https://github.com/rolling-codes/better-skill-creator/pull/78))
- Fixed adjacent-skill metadata defaults and accepted extended-context model identifiers such as
  `sonnet[1m]`. ([#78](https://github.com/rolling-codes/better-skill-creator/pull/78))

## [3.6.0] - 2026-10-21

Verification and failure-handling release. The toolkit now checks more of what it claims, rejects
more of what it should never package or trust, and fails cleanly where it used to crash or lose
work. No new `bsc.py` commands or flags. It also ships the doc-sync review-command validation and
transcript-grading report changes from the bug-prevention work (#74), listed below.

### Added

- **Documented review commands are validated.** `doc_sync` reads every `python -m scripts.review <cmd>`
  in fenced blocks and inline code and rejects a missing, suffixed (`show.md`) or unknown (`run`)
  subcommand. It understands `python`, `python3`, `py` and interpreter flags, `\` and PowerShell
  backtick line continuations, and sentence punctuation after the token; prose outside code is not
  parsed. The check runs against `review.COMMANDS`, the table `scripts.review` itself dispatches
  through, so documentation and CLI cannot drift apart. It already caught a real bug: CLAUDE.md
  documented a `scripts.review run` command that never existed.
- **`reference-escapes-skill` error.** `static_analysis` rejects references that resolve outside the
  skill directory (`../x`, absolute and drive-qualified paths such as `C:/x` on any host, `assets/../..`,
  backslash traversal including inside asset references, `evals/../..`-style paths that start with a
  runtime-output prefix, and paths that cannot be resolved, such as a symlink loop). They existed on
  disk, so they passed as valid, but they are never packaged.
- **Claims must be verified by a test that can verify something.** `claims_check` no longer counts a test
  that is unconditionally skipped or xfailed (including a module-level `pytestmark`, annotated or not),
  that calls `pytest.skip()` directly, or whose body is only `pass`, a docstring, `assert <constant>` or
  `raise NotImplementedError`. A conditional `skipif`, or a `pytest.skip()` inside an `if`, still runs
  on some paths, so it still counts; likewise a module-level skip under a non-constant `if`, while a
  literal-truthy string condition such as `skipif('True')` is unconditional. This is a heuristic gate, not a proof of test strength. A claim
  whose `sources` do not exist inside the skill directory or repo root, or that has an empty source
  entry, is a `claim-source` error; a `removed` claim's historical sources are not checked.
- **`validate_all.sh` runs the repo-level checks CI enforces.** When the target is the toolkit it now
  also runs `source_rules` (strict, as in CI), `doc_sync` and `claims_check`, and it says so when it
  skips them for another skill. It does not run pyright, which CI also runs.
- **Release hygiene test.** `test_release_metadata` requires the top CHANGELOG release to equal
  `VERSION`, alongside the existing version-lockstep check.

### Changed

- **Transcript grading reports are collision-free and atomic.** `skill_test --grade-only
  --grade-transcript` writes `<transcript-filename>.grading.json` beside the transcript (it used to
  overwrite a shared `grading.json`) through a temp file and rename. `behavior_evidence.json`, the file
  `review_gate` reads, keeps its fixed name and is written first, so a report on disk always has fresh
  evidence beside it. Pass `--grade-output` with a path named `grading.json` when `aggregate_benchmark`
  or the viewer must read it. `behavior_manifest_digest` excludes exactly the generated artifacts:
  `grading.json`, `behavior_evidence.json`, and a `*.grading.json` only when it has the `summary` and
  the `provenance` hashes (`transcript_sha256`, `skill_manifest_sha256`) that `grade_behavior` writes, so a
  source file or fixture that merely shares the suffix stays bound. This identifies the tool's own
  output; it is not a signature, so a file built to imitate a report is treated as one.
- **`run_loop` keeps your work when the improve step fails.** A timeout or error while proposing a new
  description now stops with `infrastructure_failed (improve, ...)` and returns the iterations already
  completed, where it used to raise and discard `results.json` and the report.
- **`quick_validate` reports malformed input instead of crashing.** A non-string `lifecycle`, or a
  `tests` path that exists but is a file rather than a directory, is now a validation error.

### Fixed

- **Auto-repair silently deleted unmodelled frontmatter keys** (`argument-hint`,
  `disable-model-invocation`, `context`, ...). Rewriting `SKILL.md` now preserves them.
- **Packaging policy gaps.** `Evals/` shipped on case-insensitive filesystems because the exclusion was
  case-sensitive, and `*.pfx`, `*.p12`, `*.jks`, `*.keystore`, `id_dsa*`, `id_ecdsa*` and
  `.git-credentials` were not treated as secrets.
- **Saved transcripts were not byte-faithful on Windows** (LF was rewritten to CRLF).
- **Eval viewer reset the connection on early 403/415 replies.** It answered without reading the request
  body, so the OS reset the socket: Windows clients saw `ConnectionAbortedError` instead of the status,
  and `test_feedback_rejects_cross_origin_and_non_json` failed in 4 of 25 repeated runs on one Windows machine. The body (at most
  1 MiB) is now consumed first, within a 2-second overall deadline so a slow client cannot hold the
  single-threaded viewer. Replies that are not drained (411, 413, a 404 for another path, and bodies over
  1 MiB) are unchanged and can still race.

### Documentation

- CLAUDE.md: orphaned files are warnings (dead and escaping references are the errors); the review
  lifecycle no longer mentions the nonexistent `review run`; `bsc.py compare` and
  `bsc.py eval --grade-transcript` are documented.
- SKILL.md and `references/benchmark-methodology.md` explain the grading report and evidence names and
  which readers need `grading.json`.
- CHANGELOG: added the missing compare links and an `[Unreleased]` section.

### Known limitations

- `doc_sync` does not scan fenced blocks indented four or more spaces inside list items, and
  `behavior_manifest_digest` ignores every `*.grading.json` at any depth.
- `bsc.py eval --grade-transcript` writes `behavior_evidence.json` under `runs/<id>/`; `review_gate`
  needs `behavior_evidence_path` or a copy to see it (unchanged from earlier releases).
- A hard kill between the temp write and the rename can leave a `*.tmp` file beside a report.
- `claims_check`'s hollow-test detection is a heuristic: a test that asserts something vacuous in a
  subtler way still counts as verifying a claim.
- Reference and claim-source containment is a point-in-time check on a tree nobody is modifying: it does
  not defend against another process swapping a symlink between the check and later use.
- When several transcripts are graded into one directory at once, `behavior_evidence.json` holds the last
  writer's evidence. Each file is complete and carries its own provenance (including the transcript
  hash), so a report and evidence from different runs are distinguishable, but they are not published as
  an atomic pair.

## [3.5.1] - 2026-10-19

Documentation and packaging-metadata patch. Fixes install references left stale by the
repository rename and clarifies the scope-selection matrix. No code changes, no API or
CLI changes, no behavior changes; all `scripts.*` imports and invocations are unchanged.

### Fixed

- **Broken install references after the repo rename to `better-skill-creator`.** Several
  pointers still named the old `rolling-codes/-the-better-skill-creator-skill-`, which no
  longer resolves, so the documented install path failed:
  - `.claude-plugin/plugin.json` `repository` field.
  - `SETUP.md` — the `git clone` URL, the `cd` target, and the `/plugin marketplace add`
    argument (these were non-working install steps).
  - the repository URL inside `CHANGELOG.md`'s existing version-compare links.

### Changed

- **`references/design-analysis.md` — the scope-selection matrix now defines its
  Complexity and Risk criteria.** Previously both were listed only as one-line questions
  with no scale. They now carry explicit *low / moderate / high* definitions lined up with
  the activation criteria in `references/independent-review.md` §"When to run it" (the
  binary full-review-vs-recorded-skip decision), so the matrix and the review gate judge a
  skill the same way instead of drifting into two vocabularies. High complexity ↔ a
  substantial new skill / architecture or scope change / multiple modes; high risk ↔
  handling external systems, permissions, or destructive actions, with authorization
  routed to the existing *Entailment is not permission* section.

  This change was taken through the skill's own full independent review (outcome-analyst,
  scope-adversary, architecture-reviewer, practices-reviewer + completion-adversary). The
  first round caught a blocking defect — an earlier draft cited rubric identifiers
  (`external_mutation`, `permissioned_or_destructive`, an `ACTIVATION_RUBRIC`) that do not
  exist in this repository; they were rewritten to the actual prose criteria before the
  completion-adversary returned **complete**. `skills/skill-creator/review.yaml` records
  the findings, their dispositions, the synthesis, and the passed gate.

## [3.5.0] - 2026-10-17

Bug-prevention phase 1 — gate correctness and source-level defect detectors, porting the
gate-correctness patterns from the sibling longterm-ai project. No breaking changes.

### Added

- `scripts/source_rules.py` — an AST linter over the toolkit's own Python that catches two
  recurring defect *classes* repo-wide: **H-ENCODING** (text `open()`/`read_text()`/`write_text()`
  with no `encoding=`, a latent Windows bug) and **H-SWALLOW** (an `except` body that is only
  `pass`). Deliberately conservative (flags only provably builtin-`open`/`pathlib` receivers) and
  fail-closed; wired into CI with bad/good fixtures.
- `scripts/claims_check.py` + `claims.yaml` — a behavioral-claim registry check: every registered
  claim must resolve to an existing verifier test.
- `scripts/doc_sync.py` — verifies documented commands, flags, modules, and links actually exist.
- `scripts/structured_logging.py` additions supporting the above.
- Review-gate correctness (`scripts/review_gate.py`, `scripts/finding_types.py`): a uniform
  **0/1/2 exit-code contract** (0 = ok, 1 = blocking error, 2 = warnings-only) and a required-key
  check so a placeholder synthesis can no longer satisfy the gate.

### Fixed

- CI now tolerates a warnings-only exit (2) from `doc_sync` and `claims_check` (`|| [ $? -eq 2 ]`),
  matching the `lint`/`static_analysis` steps and the documented contract; only error findings
  (exit 1) block the build.

## [3.4.1] - 2026-10-14

Bug-fix patch for the 3.4.0 release. No breaking changes; no new public API.

### Fixed

- Control query counted in `run_eval`'s call budget; CI canary uses `bsc.py eval` with `haiku`
  alias and `CLAUDE_CODE_OAUTH_TOKEN`; review-gate CI step hardened.
- `bsc.py hooks` uses `git rev-parse --git-path hooks` for worktree/submodule portability.
- `review_gate --release` summary line now correctly prints "failed" when review-skipped is promoted.
- Scoring exception in `validate.py` surfaces as an error `Finding` (exit 1) rather than stderr.
- `CLAUDE.md` corrected; README quick start documents `bsc.py hooks install` and `--model` flag.

## [3.4.0] - 2026-10-06

Adds token-economy and skill-composition guidance. Content-only addition — no engine/script
changes, no breaking changes; all existing CLI invocations and `scripts.*` imports are unchanged.

### Added

- **`references/token-economy.md`**: how to structure a skill or a family of skills to spend the
  context budget deliberately. Covers the three progressive-disclosure levers (metadata is the only
  always-on cost; SKILL.md is a <500-line table of contents; `references/` and `scripts/` cost
  nothing until read/run); one-skill-vs-many composition with a recommended **development track**
  (`scoping-changes → implementing-features → validating-code → reviewing-changes`, each loading
  only for its phase); and naming conventions (gerund skill names, descriptive domain-organized
  file names, forward slashes, a predictable scheme) so files are opened by convention instead of
  discovered by directory scan. Grounded in Anthropic's official Skill authoring best practices
  (linked, not copied); the secondary-source "~40% token reduction" figure is excluded as it is
  not on the primary source.
- Wired into `SKILL.md` — listed in **Reference files** and pointed to from the Progressive
  Disclosure section — and added to `skill.yaml` dependencies (satisfies `static_analysis.py`
  orphan check and `lint.py` reference-wiring completeness).

## [3.3.1] - 2026-10-06

Dogfooding and CI hardening. No new features for authored skills; no breaking changes to
`scripts.*` imports or CLI invocations (the `check` command gains an optional flag).

### Fixed

- **`bsc.py check` failed on the repo's own skill.** `checks()` called `validate_skill()`
  without `claude_code=True`, so the documented `python bsc.py check skills/skill-creator`
  always reported `structure — failed: Unexpected key(s) … model` — the `model:` key is a
  legitimate Claude Code extension. `check` now validates with Claude Code extensions enabled
  by default and accepts a `--strict` flag to validate without them (upload/API compatibility,
  the behavior packaging still uses). The independent-review gate still applies as designed.
- **`runs/` was not git-ignored.** `bsc.py check`/`eval` write timestamped reports under
  `runs/`; those artifacts could be staged into commits by accident. Added `runs/` to
  `.gitignore` beside `dist/` and `*-workspace/`.

### Added

- **CI now enforces the progressive-disclosure invariant.** `.github/workflows/test.yml` runs
  `quick_validate --claude-code` plus `lint` and `static_analysis` (errors-only gating;
  pre-existing script-orphan warnings do not fail CI) on every push and PR, so wiring, orphan,
  and version-drift regressions are caught in CI rather than only by a bypassable local hook.
- Regression test (`tests/test_bsc_check.py`) pinning that `bsc.py check` reports the skill's
  structure valid with Claude Code extensions and rejects the `model:` key under `--strict`.

## [3.3.0] - 2026-10-06

Adds a development-practices guidance pack so skills that write code, fix bugs, run
tests, or author PRs bake in the practices that keep AI-assisted code from repeating
the same bugs. The guidance pack is a content-only addition; this release also includes
the `quick_validate.py` fix described below. No breaking changes; all existing CLI
invocations and `scripts.*` imports are unchanged.

### Added

- **`references/development-practices.md`**: a development-practice counterpart to
  `references/model-guidance.md` (which covers prompt/model patterns). It is grounded in
  this repo's own hard lessons and in a survey of 84 genuine `fix:` commits across the
  author's AI-assisted repositories, which surfaced the recurring failure modes it
  defends against: under-validation at trust boundaries (the largest category), multi-
  location version/manifest drift, cross-platform path/encoding bugs, concurrency/TOCTOU
  races, missing-default guards, hallucinated/unverified API calls, symptom-only fixes,
  and fixes shipped without a regression test. External claims are limited to verified,
  primary-sourced studies (SmartBear/Cisco peer-review data; Google `eng-practices` and
  *Software Engineering at Google* on small changes); unsourced folklore is excluded.
- Wired into `SKILL.md` — listed in **Reference files** and pointed to from the Design
  analysis section when the outcome entails real development work — and added to
  `skill.yaml` dependencies, satisfying the progressive-disclosure invariant
  (`static_analysis.py` orphan check, `lint.py` reference-wiring completeness).

### Fixed

- **Windows: dependency-containment error message** (`quick_validate.py`): the missing/escaping
  dependency list was interpolated via its `repr()` (`{missing}`), which doubles backslashes in
  Windows paths and broke `test_path_containment.py::test_validate_dependency_containment[absolute-outside]`
  on the Windows CI runner. Now joined as a plain string (`', '.join(missing)`). This fix was
  authored during the PR #44 cycle but did not make it into the merge; folded in here. It is also
  the canonical example of the cross-platform section in the new guidance.

## [3.2.1] - 2026-10-04

Post-release hardening from the independent v3.2.0 audit and CodeRabbit security
review. No new features and no breaking changes — all existing CLI invocations and
`scripts.*` imports are unchanged.

### Fixed

- **Gate wiring** (`fix/gate-wiring` — PR #39): `review_gate.py`, pyright, and a
  version-consistency check are now wired into the pre-commit hook. Previously the
  hook ran quick-validate and lint but skipped the review gate and type-checker,
  allowing a commit to pass locally while blocking packaging.
- **Flag-shaped generator args** (`fix(L1+M1)`): generator CLI now rejects arguments
  that look like flags (e.g. `--foo`) passed as positional skill names, promoting the
  finding from a lint warning to an error so it surfaces before packaging.
- **Pyright to 0 errors** (`fix(H4+M9)`): consolidated to a single `pyrightconfig.json`
  at the repo root; all type errors resolved. Previously two configs existed with
  conflicting `pythonVersion` settings, and Pylance/pyright reported unresolved imports.
- **Python 3.8 compatibility**: replaced `dict|None` union syntax with
  `Optional[Dict]` throughout `scripts.*` — the `|` union form requires Python 3.10+
  and silently broke installations on the stated floor of 3.8.
- **Security hardening** (CodeRabbit PR #40): `file_policy.py` enforces path
  containment so packaging cannot read or write outside the skill directory;
  `call_budget.py` caps subprocess call counts per run. 300-line regression test suite
  added.
- **Atomic write cleanup**: temp-file cleanup on failure is now guaranteed; regression
  tests for the H2/C1 failure paths added.
- **Unanchored snapshot metadata**: `file_policy.py` now refreshes file metadata in
  unanchored snapshots; permission docs clarified.

### Docs

- Docstrings added across CLI, generators, execution, packaging, review, and security
  modules.
- PR template added (`.github/PULL_REQUEST_TEMPLATE.md`).
- Release notes updated to reflect the current v3.2.0 state.

## [3.2.0] - 2026-10-03

Validation architecture overhaul, model-aware writing guidance, and silent-failure
fixes. No breaking changes — existing `python -m scripts.lint/static_analysis/review_gate`
invocations continue to work unchanged.

### Added

- **`scripts/validate.py`** — unified validation CLI. Runs `quick_validate` → `lint` →
  `static_analysis` in order, short-circuits on structural errors, and emits a single
  sorted report. Use this as the canonical gate; the individual tools remain available for
  targeted use.
- **`scripts/types.py`** — shared types module. `Finding`, `_cap()`,
  `BLOCKING_SEVERITIES`, `DISPOSITIONS`, and `GATE_STATES` now live here. Eliminates the
  import coupling where every consumer had to import from `static_analysis` or `review`
  just to get a type. Both source modules re-export for backwards compatibility.
- **`scripts/__init__.py`** — package marker. Makes `scripts.*` imports resolvable by
  Pylance/pyright without IDE configuration.
- **`metadata.lint_ignore`** in SKILL.md frontmatter — per-skill rule suppression. A skill
  can now silence specific lint rules locally with a justification comment, instead of
  requiring a global exemption added to `analysis_config.py`.
- **`_check_unknown_ignore` lint rule** — typo guard for `lint_ignore` entries. Warns if
  a rule ID in `lint_ignore` doesn't match any known rule.
- **`_check_eval_files` lint rule** — warns when `evals/evals.json` references a file path
  that doesn't exist on disk. Previously, a missing eval file caused the test to silently
  run without its input.
- **`ReviewRecord.bad_severities()`** — surfaces findings whose severity value is
  misspelled (e.g. `critcal`, `hight`). Previously these silently passed the blocking
  check since the misspelling never matched `BLOCKING_SEVERITIES`.
- **Model-aware writing guidance** — `SKILL.md` "Model-Aware Writing" section, updated
  `agents/grader.md`, and new `references/model-guidance.md` § "Writing for a lower-tier
  target". Covers density calibration by tier, concrete Fable-vs-Haiku examples, the
  `metadata.target_model` field, and grader standard injection.

### Changed

- **`lint()` now runs in three layers** (structural → content → wiring). Wiring rules
  no longer fire when the body is empty or structurally broken, eliminating misleading
  noise like "unwired-dependency" on a skill with no body yet.
- **`review_gate.py`** wires `bad_severities()` as a warning check alongside the existing
  `bad_dispositions` error check.
- **`references/schemas.md`** — new "SKILL.md metadata fields" section documenting
  `schemaVersion`, `target_model`, and `lint_ignore` with examples and known rule IDs.

## [3.1.0] - 2026-10-02

2026 model guidance overhaul and SKILL.md de-specification for Fable 5+
compatibility. No breaking changes.

### Changed

- **`references/model-guidance.md` rewritten** from ~90 lines to ~350 lines.
  Adds adaptive thinking API (`output_config.effort`; `budget_tokens` returns
  HTTP 400 on Claude 4.7+ and is removed), Fable 5.1/Opus 5.5/Sonnet 5.5
  context windows (1M/128K), evidence-backed prompting patterns, agentic
  workflow taxonomy, and prompt injection defenses (session-salted delimiters,
  dual-LLM gatekeeper, compaction-summary trust boundary).
- **`SKILL.md` compressed** from 519 to ~415 lines, applying the Fable 5
  finding that over-specified skill files degrade output. Removed prescriptive
  boilerplate, collapsed the design analysis and compiler pipeline sections to
  pointers, and trimmed the eval step sequence to outcome-focused phases.
- **`references/description-optimization.md`** trimmed to remove exhaustive
  query-writing rules that contradicted Fable 5 guidance; updated model IDs to
  `claude-haiku-4-5-20251001` and `claude-sonnet-5-5`.
- **`references/schemas.md`** `analyzer_model` example updated to
  `claude-fable-5-1`.

## [3.0.1] - 2026-10-02

Live trigger evals run again on current Claude Code. The toolkit resolved the
`claude` CLI through a package layout that recent Claude Code releases no longer
ship, so every live path — `bsc.py eval --live`, `skill_test`, `run_eval` and the
`run_loop` optimizer — failed before it could reach the model.

### Fixed

- **`eval --live` reported `infrastructure_failed` on every query** against a
  current Claude Code install. `claude_process.claude_command` rewrote the Windows
  `.cmd`/`.ps1` shim to `node …/node_modules/@anthropic-ai/claude-code/cli.js`, but
  Claude Code now ships a native `bin/claude.exe` (POSIX: `bin/claude`) and no
  `cli.js`. The missing file raised `FileNotFoundError`, which `run_eval` recorded
  as `SUBPROCESS_CRASH` and surfaced as `infrastructure_failed` — the run never
  made a model call, so no trigger rate could be measured. The resolver now prefers
  the native `bin/claude` binary and falls back to the legacy `node`+`cli.js`
  layout only when the binary is absent.

## [3.0.0] - 2026-10-02

Spec compliance and current-model guidance. Generated skills now upload to
claude.ai and the Skills API, and the toolkit's advice matches how current Claude
models behave. Major bump because skills with a top-level `schemaVersion`, which
earlier versions generated, now fail `quick_validate` until migrated.

### Changed (breaking)

- **`schemaVersion` moved under `metadata`.** claude.ai uploads, the Skills API
  and upstream `package_skill.py` reject any top-level frontmatter key outside
  `name`, `description`, `license`, `compatibility`, `metadata`, `allowed-tools`.
  Generators write `metadata: {schemaVersion: N}`; `quick_validate` rejects the
  top-level key with a fix message; `skill_ir` still reads the legacy location.
  Migrate existing skills with `python -m scripts.migrate_skill <skill> --to 1`.

### Fixed

- **`allowed-tools` used names Claude Code doesn't recognize** (`filesystem.read`,
  `terminal.execute`), so it pre-approved nothing. SKILL.md, the example skill and
  all generators now use real tool names, scoped narrowly. The skill pre-approves
  only read-only analyzers and packaging; anything that writes caller paths or
  spends model budget still prompts.
- **`write_skill_md` dropped `license` and custom `metadata`** on rewrite. Both are
  now carried through.
- **SKILL.md said `package_skill.py` uses a `filesystem.zip` tool.** It uses
  Python's zipfile module.

### Added

- **`invalid-tool-name` lint rule** (replaces `frontmatter-missing-tools`), checked
  by shape so new tools pass without a hand-kept list.
- **`bsc.py eval --models haiku,sonnet,opus`** runs the trigger eval per model,
  reports each separately, and counts `--max-calls` across all of them.
- **`references/model-guidance.md`**: portable frontmatter, `allowed-tools` as a
  security grant, current-model writing guidance, and the official tools that
  overlap this one (`claude plugin eval`, `/claude-api prompt-audit`).
- `allowed-tools` accepts the spec's space- or comma-separated string form.

### Removed

- **Advice to make descriptions "pushy"** to fight undertriggering. Current models
  overtrigger on emphatic language; the description guidance now asks for third
  person, key use case first, and named near misses.
- **Scorer penalty for missing `allowed-tools`**, and the `quick_validate` rule
  that required it whenever PERMISSIONS.md exists. Absence of a pre-approval grant
  is not a defect.

### Known issues

- The `docs`, `python`, `research` and `script` generator archetypes write an
  empty `tests/` directory, so their output fails `quick_validate`. Not addressed
  here.

## [2.1.0] - 2026-09-08

Easier first use and cleaner results. The main addition is `python bsc.py` — a
root-level launcher so users no longer navigate into internal directories. The
`examples/release-notes` starter skill makes `bsc.py new` usable on a fresh
download. Documentation is rewritten around the five commands rather than upstream
comparisons. Grader validation and subprocess edge cases get new regression tests.
Python 3.12 is now the documented baseline; CI runs on Windows and Ubuntu.

### Added

- **`bsc.py` launcher** — `doctor`, `new`, `check`, `eval`, `package` subcommands,
  all resolving paths relative to the caller's working directory, not the script's
  location.
- **`examples/release-notes/`** — complete starter skill (`release-note-draft`) with
  5 positive trigger cases, 5 negative near-miss cases, and 2 authored behavior cases.
  Copied by `bsc.py new NAME --example release-notes`.
- **GitHub Actions CI** — matrix of `ubuntu-latest` and `windows-latest` on Python
  3.12; runs the full test suite plus `bsc.py doctor` as a smoke test.
- **Grader validation unit tests** — edge cases for empty evidence, whitespace-only
  evidence, duplicate expectation text, and unexpected expectation text; all must
  produce exit 1 (grading incomplete), not exit 2 (grading failed).
- **Large-stderr regression test** — confirms `run_single_query` completes in bounded
  time and returns a failed result (not a hang) when the subprocess emits 100 KB of
  stderr.

### Fixed

- **`new` overwrites existing directory.** `target.mkdir(exist_ok=False)` raised a
  bare `FileExistsError` caught by the generic handler with a confusing message.
  Now raises `InputError` with a clear explanation and the full path.

### Changed

- **README rewritten** — purpose, prerequisites, five-minute walkthrough with expected
  outputs, troubleshooting, and attribution. Comparison table and design-rationale
  sections removed (content lives in CHANGELOG and reference docs).
- **Python baseline raised to 3.12** — `doctor` already required 3.12; the badge and
  documentation now match.

## [2.0.3] - 2026-09-07

Reliability patch for the live eval machinery: it now works on Windows, never
scores a failed execution as a pass, and cleans up after itself. No behavior
change to skill *authoring* — only to how the toolkit runs and grades evals.

### Fixed

- **Windows-incompatible eval streaming.** `run_eval.py` polled the subprocess
  pipe with `select.select`, which only works on sockets on Windows, so every
  query errored out to `False`. Replaced with a background reader thread feeding
  a `queue.Queue`; the prompt is now delivered over stdin. Cross-platform.
- **Dropped final output.** The stream reader discarded a trailing line with no
  newline; it is now drained after the process exits.
- **Premature non-trigger.** An unrelated tool event (a tool other than
  `Skill`/`Read`) made a query report "not triggered"; the reader now skips
  unrelated events and keeps reading until a real trigger, a `result`, or a
  clean end.
- **Failed executions counted as passes.** A timed-out / crashed / auth-failed /
  malformed run was indistinguishable from a clean non-trigger, so it satisfied
  negative test cases. Runs now return a categorized `QueryOutcome`
  (`triggered` / `not_triggered` vs `TIMEOUT` / `AUTHENTICATION` /
  `SUBPROCESS_CRASH` / `PARSING`); trigger rate is computed over clean runs only,
  and a failed run can never pass. `run_eval` surfaces `execution_error` per
  query and `infrastructure_failed` in the summary.
- **Optimizing on broken infrastructure.** `run_loop.py` now stops and refuses
  to propose a new description when the eval infrastructure fails.
- **Retry crash.** Backoff used `uuid.uuid4().random()`, which does not exist —
  replaced with `random.random()`.
- **Leaked temp file.** `skill_test.py` wrote the eval-set JSON with
  `delete=False` and never removed it; now cleaned up on every exit path.
- **External targets couldn't be tested.** `skill_test.py` ran the toolkit module
  from the *target* skill dir; it now runs from the toolkit dir and addresses the
  target via `--skill-path`, so a skill without the toolkit's `scripts/` package
  can be tested.
- **Grader gaps.** `skill_test.py` falls back to the bundled `agents/grader.md`
  when the target lacks one, and requires a complete, correctly-typed grading
  response covering every requested expectation (else it fails rather than
  silently under-counting).
- **Dead reference.** `static_analysis.py` no longer flags runtime workspace
  outputs (e.g. `evals/evals.json`) as dead references.

### Changed

- **Consistent exit codes** across `run_eval`, `run_loop`, and `skill_test`:
  `0` = all passed, `1` = execution/input/infrastructure error, `2` = completed
  with failed expectations.
- New shared `scripts/tests_loader.py` normalizes every trigger-test file (bool
  and legacy `triggered`/`not_triggered` labels, `prompt`/`query` aliases),
  rejects malformed entries, and de-duplicates queries.
- Wired the support modules (`structured_logging`, `tests_loader`,
  `skill_md_utils`, `analysis_config`) into SKILL.md and `skill.yaml`; cleared the
  `claude plugin validate` warnings (marketplace description added, non-standard
  `plugin.json` `upstream` field removed — Anthropic attribution stays in the
  description). Added `.vscode/settings.json` mirroring `pyrightconfig.json`.

### Tests

- New regression suites: `test_tests_loader.py`, `test_run_eval_stream.py`
  (controlled fake subprocess — never a live `claude`), `test_skill_test_grader.py`,
  and `test_run_loop_infra.py`. Full suite: 76 passing.

## [2.0.2] - 2026-09-05

Documentation-accuracy patch. Salvages the one portable change from the stale
PR #10 (`fix/variance-check-script-gate`) and drops the rest as obsolete.

### Fixed

- SKILL.md's reference entry for `scripts/dependency_graph.py` now shows it takes
  a skill root directory as its positional argument (`<skill-root>`), matching the
  tool's actual CLI (`skill_path = Path(args[0])`) and the README usage line.

### Notes

- PR #10's other changes — Gate 0 frontmatter-only collection and variance-check
  lint/dependency-graph gating — targeted the retired `skill-architect` layout
  (numbered Gates 0–6, `workflows/variance-check.md`) and have no equivalent in the
  current `skill-creator` fork, so they were dropped rather than force-fitted.

### Validation

- Offline pipeline green: `quick_validate` pass, `lint` 0 errors, `semantic_analysis`
  clean, architecture score 90/100.
- `dependency_graph.py` exercised across a skill root in summary/json/dot formats
  plus the no-arg usage message and bad-path error contract.
- Regression suite: 19/19 passing.

## [2.0.1] - 2026-09-05

Fixes the validation-quality PR review findings and bumps the skill package to
2.0.1.

### Fixed

- Restored `quick_validate.py`'s cross-file lifecycle mismatch failure between
  `skill.yaml` and `LIFECYCLE.md`.
- Replaced newly added PEP 604 union annotations in the changed validation/IR
  utilities with Python 3.8-compatible `typing.Union` forms.
- Hardened `safe_path_exists` with `Path.relative_to()` containment checks so
  sibling path-prefix escapes are rejected.

### Validation

- Added regression tests for the lifecycle mismatch, path containment, and
  Python 3.8 annotation compatibility fixes.

## [2.0.0] - 2026-08-30

Adds an independent multi-agent review system and adversarial completion gate for
complex skill creation and substantial updates. This is a major release because
the review gate now blocks packaging of complex skills that lack a passing
`review.yaml`.

### Added

- Fresh-context review roles for outcome interpretation, adversarial scope,
  architecture/validation, and completion-adversary review.
- `references/independent-review.md` to document adaptive activation,
  independence requirements, synthesis, and the completion gate.
- `scripts/review.py`, `scripts/review_gate.py`, and
  `scripts/stages/review_stage.py` for recording review state and enforcing the
  gate in the package pipeline.
- Behavioral coverage for RPG variant discrimination, log-fix
  entailment-vs-authorization, no-modification constraints, narrow
  description-only edits, simple-skill requests, ambiguous requests, and
  development-log review behavior.

### Changed

- `SKILL.md` now requires independent review for complex skills and substantial
  updates, while allowing narrow edits to record a skip reason.
- `skill.yaml` declares the new reviewer agents, review scripts, and
  independent-review reference so progressive disclosure can discover them.
- Bumped version to 2.0.0 in `.claude-plugin/plugin.json`,
  `skills/skill-creator/skill.yaml`, and the README release badge.

### Fixed

- `PackageStage` now fails closed on error-severity diagnostics before writing a
  `.skill`, preventing callers from bypassing an unresolved review gate.
- Python 3.8 compatibility for scripts that used runtime `list[...]`/`dict[...]`
  annotations.

### Validation

- The v2.0.0 review system was applied to itself: the completion adversary
  returned `verdict: complete`, its three low-severity findings were disposed in
  `review.yaml`, and `review_gate.py` passed.
- Offline validation passed: `quick_validate`, `lint`, `static_analysis`,
  `review_gate`, architecture score 95/100, and 16/16 pipeline tests.
- Live previous-vs-new evaluation over three representative prompts scored 100%
  with-skill vs 41.7% baseline.

## [1.10.0] - 2026-08-30

Makes Design Analysis *adaptive and bounded*. v1.9.0 told the model to work every
angle in order, which invites mechanical checklists and over-scoping — the opposite of
the flat scoping it cured. This release adds focus, a permission guardrail, and a
stopping rule.

### Added

- **Adaptive lenses** (`references/design-analysis.md`): an always-evaluate core
  (outcome, material interpretations, necessary entailments, boundaries & authorization,
  validation) plus evaluate-when-relevant lenses (accessibility, security, performance,
  persistence, creative direction, integration, multi-user, error recovery). The model
  justifies each lens it picks up; an unused lens is focus, not omission.
- **Entailment ≠ permission.** Discovered work is classified required-and-authorized
  (do it), required-but-unauthorized (identify and ask), optional (recommend, never add
  silently), or out-of-scope (exclude). Recorded in a new
  `SkillSpec.authorization_boundaries` field. Prevents multi-angle reasoning from
  becoming uncontrolled or unauthorized scope expansion.
- **Scope-selection matrix** (goal fit, evidence, complexity, reversibility, risk,
  clarification need) to choose among interpretations by reasoning, not listing.
- **Design brief** — new `SkillSpec` fields `chosen_interpretation`,
  `optional_features`, `authorization_boundaries` (existing `interpretations` /
  `open_questions` serve as alternatives-considered / decisive-questions).
- **Contradiction handling** and a **stopping rule** in the doctrine: explicit user
  constraints win and compromises are recorded; the analysis stops once another lens
  wouldn't change the architecture.
- **Adversarial behavioral tests** in `tests/expected_behavior.yaml`: nine prompts that
  check for both under- and over-scoping and for permission boundaries ("diagnose but
  do not modify", "only change the CSS", "make a simple skill, no optional systems").

### Changed

- `scripts/confidence.py` `assess_spec` now flags entailed work with no
  `authorization_boundaries` ("assumed all entailed work is authorized") and multiple
  interpretations with no `chosen_interpretation`.
- Bumped version to 1.10.0 in `.claude-plugin/plugin.json`, `skill.yaml`, and the
  README release badge.

## [1.9.1] - 2026-08-30

Completes the v1.9.0 Design Analysis feature — the scoring was authored but not
fully wired, and the compatibility story needed fixing.

### Fixed

- **`assess_spec` is now reachable.** `scripts/confidence.py`'s CLI only called
  `assess_skill`; the flat-scope scoring in `assess_spec` was dead code. The CLI now
  also assesses `spec.yaml` when present and gates on the lower of the two scores.
- **Back-compatible validation.** v1.9.0 added `outcome`/`entailments` to
  `missing_fields()`, so `spec validate` hard-failed specs authored before those
  fields existed — contradicting the "loads unchanged" claim. `missing_fields()` is
  back to the original core set; a new `missing_design_fields()` reports
  `outcome`/`entailments` as a **non-fatal warning** (exit 2), not an error.
- **Behavioral tests updated.** `tests/expected_behavior.yaml` still encoded the old
  question-first flow. It now covers the design-analysis behavior: RPG variant
  enumeration, log→diagnose→patch→verify entailment expansion, stated assumptions,
  and flexibility-without-vagueness scope control.

### Changed

- Bumped version to 1.9.1 in `.claude-plugin/plugin.json`,
  `skills/skill-creator/skill.yaml`, and the README release badge.

## [1.9.0] - 2026-08-30

Turns the Skill Creator from a request-transcriber into a design-and-reasoning
system. When creating or improving a skill it now scopes the *outcome* from
multiple angles before choosing a structure, instead of converting the literal
wording into a basic instruction file. "Build me an RPG skill" is treated as a
family of very different skills (flat narrative vs. persistent campaign with
world-state and progression); "watch my logs" is scoped as detect → diagnose →
patch → verify, not a log grepper.

### Added

- **Gate 1 reframed to Design Analysis** in `SKILL.md`, backed by a new
  `skills/skill-creator/references/design-analysis.md` doctrine: work an angle
  checklist (real outcome, valid interpretations, modes, cross-cutting
  requirements, entailments, failure points, self-validation), compare, decide
  what's in scope, then architect. Bias flipped from ask-heavy to analyze-first —
  make and *state* assumptions when intent is safe to infer; ask a focused
  question only when two interpretations would produce substantially different
  skills.
- **Design-analysis fields on `SkillSpec`** (`scripts/spec.py`): `outcome`,
  `interpretations`, `modes`, `entailments`, `failure_points`, `validation`,
  `assumptions`, `open_questions`. `outcome` and `entailments` are now required
  for a complete spec.
- **Flat-scope scoring** in `scripts/confidence.py`: an outcome that was never
  expanded into entailments, or unresolved decisive `open_questions`, now lowers
  confidence and is surfaced as an inferred assumption.
- A Red Flags row for the "build the literal request" shortcut.

### Changed

- Bumped version to 1.9.0 in `.claude-plugin/plugin.json`,
  `skills/skill-creator/skill.yaml`, and the README release badge.

## [1.8.1] - 2026-08-30

### Documentation

- Clarified that `scripts/dependency_graph.py` is an optional inspection tool:
  the skill-creator workflow and packaging pipeline do not depend on it, and it
  has no connection to any external graph service. Documentation only, no
  behaviour or wiring change.

### Changed

- Bumped version to 1.8.1 in `.claude-plugin/plugin.json`,
  `skills/skill-creator/skill.yaml`, and the README release badge.

## [1.8.0] - 2026-08-30

Fixed a wiring regression in the v1.2-v1.7 features: `generators/`,
`static_analysis.py`, `lint.py`, `dependency_graph.py`, `migrate_skill.py` and
`generate_report.py` were documented in the README but never referenced in
`SKILL.md`, so under progressive disclosure Claude could not discover them — the
same defect this fork was built to remove, reintroduced a layer up. Also
tightened the linter rules so the regression cannot recur. See
`skills/skill-creator/CHANGELOG.md` for component-level detail.

### Fixed

- Wired all six orphaned features into `SKILL.md` (Reference files section,
  Validation Pipeline, and a scaffolding note for the generators).
- README: static analysis runs via `LintStage`, not a `StaticAnalysisStage`;
  linter check count corrected from eight to nine.
- Python 3.8 compatibility in `package_skill.py` and `skill_test.py`
  (`from __future__ import annotations` for `list[...]` subscripts).
- `tests/test_pipeline.py` no longer hardcodes an absolute `C:/Temp` skill path,
  so the suite runs on any checkout.

### Added

- `static_analysis.py` orphaned-file rule and `lint.py` reference-wiring
  completeness rule, both run in the package pipeline via `LintStage`, so a
  shipped-but-unreferenced file now fails the linter instead of shipping silently.

### Changed

- Bumped version to 1.8.0 in `.claude-plugin/plugin.json`,
  `skills/skill-creator/skill.yaml`, and the README release badge.

## [1.7.0] - 2026-08-26

Version-alignment release. `1.7.0` was chosen to sit above the highest existing
GitHub release tag (`v1.6.0`) so the release marked "Latest" points at the code
actually shipping on `main`. The earlier `v1.0.0`–`v1.6.0` tags were cut from an
earlier packaging of this same project on a since-reinitialized git history, so
they share no commit ancestor with the current tree even though they carry the
same project's version numbers — the content history those numbers refer to is
the set of entries below. Releases 1.2.0 and 1.3.0 were written in the skill
changelog of that earlier packaging and are included here. No functional
changes over 1.4.0.

### Changed

- Bumped version to 1.7.0 in `.claude-plugin/plugin.json`, `skills/skill-creator/skill.yaml`,
  and the README release badge.

## [1.4.0] - 2026-08-26

Tightens SKILL.md and closes the Gate 3 gap the fork advocated but never applied
to itself.

### Added

- **Iron law and Red Flags table** in `SKILL.md`. The README described Gate 3
  (one non-negotiable rule phrased as reasoning, plus a table of rationalizations
  paired with correct behaviour) as the fix for imperative fragility and the
  excuse trap, but the skill itself had neither. The iron law is that a skill is
  never reported as better without a baseline run from the same iteration,
  because with-skill output that looks good on its own does not show the skill
  caused it. The seven table rows are drawn from the shortcuts this loop actually
  invites, most of which SKILL.md previously addressed as scattered one-line
  pleas ("don't stop partway through", "this is the only opportunity to capture
  this data", "please use generate_review.py").
- `references/description-optimization.md` — the trigger-eval and
  description-tuning loop, extracted from `SKILL.md` with a table of contents,
  a pointer back to `references/environments.md` for the no-subprocess case, and
  an entry in both the Reference files section and `skill.yaml` dependencies.

### Changed

- **`SKILL.md` cut from 500 to 446 lines.** The 73-line Description Optimization
  section moved to `references/`, following the same extraction pattern already
  used for environments. Remaining trims were duplicated or ornamental prose: the
  closing recap restated the opening summary, and three short paragraphs were
  merged.
- **`scripts/validate_all.sh` now runs the offline checks it claimed to.** It ran
  `quick_validate.py` and `skill_test.py` only, skipping `lint.py` and
  `static_analysis.py`, and invoked scripts by file path, which breaks the
  `scripts.skill_ir` import for the module-based ones. It now runs all three
  offline checks as modules from inside the skill directory, treats exit 2
  (warnings only) as a pass, skips the live trigger tests with an explicit
  message when the `claude` CLI is absent instead of failing, and returns a
  non-zero exit if any check genuinely failed.

### Fixed

- **Wrong flag documented.** The Reference files section told the model to grade
  expected behaviour with `--transcript`. The actual flag is
  `--grade-transcript <path>`, so the documented invocation would have been
  rejected by the argument parser.

### Note on the Robustness score

Robustness rose from 60 to 90, and the overall score from 92 to 95. Read that
carefully: `scripts/score.py` awards 20 points for the body matching the regex
`red flags?` and 10 for `iron law`, so the metric can be moved by typing two
headings. The content added here is meant to earn the points, but the rubric
would not have noticed the difference. Tightening that rule to require an actual
table with a rationalization column is open work.

---

## [1.3.1] - 2026-08-26

Repository consistency and linter-signal fixes. No change to skill behaviour.

### Fixed

- **Plugin install was broken.** `.claude-plugin/marketplace.json` declared the
  plugin as `skill-architect` in a marketplace named `skill-architect-local`,
  while `.claude-plugin/plugin.json` declared `skill-creator`. The documented
  install command matched neither, so `claude plugin install` failed. Both
  manifests now agree on `skill-creator@skill-creator-local`.
- **Pre-commit hook never ran.** It matched staged paths against
  `skill-creator/`, but the skill lives at `skills/skill-creator/`, so the
  condition was never true. It also invoked `python3 -m scripts.lint` from the
  repo root, where no `scripts` package exists. The hook now resolves the repo
  root via `git rev-parse`, uses the correct path, runs both checks from inside
  the skill directory, and fails loudly if the configured directory is missing.
- **Undeclared PyYAML dependency.** The README claimed standard library only,
  but six modules import `yaml`. Added `requirements.txt` and corrected the
  README and SETUP.md. `quick_validate.py` and `skill_ir.py` now fail with an
  install hint instead of a bare `ModuleNotFoundError`.
- **License conflict.** `plugin.json` declared MIT while `LICENSE.txt` is
  Apache 2.0. `plugin.json` now declares `Apache-2.0`.
- **Version drift.** README badge said 1.0.0, root changelog stopped at 1.1.0,
  `plugin.json` said 1.2.0, `skill.yaml` said 1.3.0. All now agree.
- **SETUP.md described a different project.** It documented `skill-architect`
  install commands and a `/skill-architect` verification step, neither of which
  exist here. Rewritten against the actual plugin.
- **Stage list was incomplete.** `SKILL.md` and the skill changelog both said
  "seven concrete stage wrappers" and then listed six. `DependencyStage` was
  missing.
- **Attribution.** `skill.yaml` credited Anthropic as author while
  `plugin.json` credited RollingCodes. `skill.yaml` now names the fork.

### Changed

- **`unreachable-section` narrowed** (`scripts/static_analysis.py`). It flagged
  any heading not cross-linked, which fired on 23 of ~25 sections of this
  skill's own SKILL.md. A linear procedural document is read top to bottom, so
  the rule now only applies to documents that actually navigate by anchor link
  (three or more), skips `Step N` headings, and considers top-level sections only.
- **`workflow-no-output` narrowed** (`scripts/lint.py`). It matched every
  markdown numbered list, including interview questions and concept
  enumerations. It now only inspects numbered lines inside sections whose
  heading names a process, skips questions, and requires the line to begin with
  an imperative verb.
- **Findings are capped per rule.** New `_cap()` helper in
  `static_analysis.py` shows the first five findings for a rule plus a count of
  the rest, with a note that a rule firing this often is usually too broad. This
  is the same non-discriminating-signal problem `agents/analyzer.md` warns about
  in evals, applied to the linters themselves. Combined effect on this skill:
  static analysis went from 35 findings to 1, lint from 17 to 7.

### Known issues

- `SKILL.md` is 500 lines, exactly on the progressive-disclosure guidance
  boundary rather than comfortably under it. The README claim of 463 lines was
  stale and has been corrected to the true figure.

---

## [1.3.0] - 2026-07-12

Recorded in the skill changelog of the earlier packaging of this project, when
the manual Skill Architect checks were being replaced by a compile pipeline.
Brought into this ledger so that history is not only in the archived repository.

### Added

- `CompilerContext` dataclass — shared mutable state passed through all pipeline
  stages, carrying `skill_spec`, `diagnostics`, `repairs`, `applied_fixes`,
  `score`, and `output_path` (`scripts/compiler_context.py`).
- `RepairProposal` dataclass — a deferred repair closure that separates fix
  planning from filesystem mutation.
- `StageRegistry` — executes registered `PipelineStage` implementations in order,
  with `run_all()` and `run_until()` entry points (`scripts/pipeline.py`).
- `PipelineStage` protocol — structural interface all stage wrappers satisfy.
- Seven concrete pipeline stages in `scripts/stages/`: `LintStage`,
  `SemanticStage`, `DependencyStage`, `RepairStage`, `ApplyRepairsStage`,
  `ScoreStage`, `PackageStage`.
- `RepairStage` builds repair proposals without touching disk;
  `ApplyRepairsStage` is the sole filesystem-writing stage.
- Five regression tests for the compiler pipeline in `tests/test_pipeline.py`.

### Changed

- `package_skill.py` now orchestrates the pipeline via `CompilerContext` and stage
  instances rather than direct function calls; all observable behaviour preserved.
- `.pytest_cache` excluded from packaged `.skill` archives.

### Architecture note

v1.2.0 created skills. v1.3.0 compiles them. The stage and registry model
separates what work happens from what performs it. Later stages, including
review, were added on that same registry.

## [1.2.0] - 2026-07-07

Recorded in the skill changelog of the earlier packaging. These are the tools
that draft a skill from a written intent and score it before packaging.

### Added

- `scripts/spec.py` — pre-generation SkillSpec intent record; writes `spec.yaml`.
- `scripts/confidence.py` — requirement coverage and ambiguity score.
- `scripts/semantic_analysis.py` — contradiction, duplicate-section, and
  inconsistent-terminology checks.
- `scripts/repair.py` — deterministic auto-fix loop for known lint errors.
- `scripts/score.py` — architecture scoring rubric (7 dimensions, 0–100 each).
- `scripts/generate_tests.py` — generates edge-case and malformed-input test scenarios.
- All six scripts wired into the `package_skill.py` compile pipeline.

---

## [1.1.0] - 2026-07-12

Six architectural improvements implemented from the roadmap.

### Added

- **Intermediate Representation** (`scripts/skill_ir.py`) — `Skill` dataclass as
  the canonical in-memory model for a skill. All scripts now parse through
  `Skill.from_path()` rather than each doing their own frontmatter/yaml parsing.
  `scripts/utils.py`'s `parse_skill_md()` delegates here, keeping existing callers
  unchanged.

- **Formal dependency graph** (`scripts/dependency_graph.py`) — `SkillGraph` class
  that builds a directed node graph from `skill.yaml` dependencies and backtick
  references in SKILL.md. Supports cycle detection (DFS), missing-node audit,
  impact analysis (reverse traversal), and export to JSON or Graphviz DOT.
  `python -m scripts.dependency_graph <path> [--format json|dot|summary]`

- **Static analysis** (`scripts/static_analysis.py`) — shared `Finding` datatype
  (severity + rule + message + line) plus five semantic rules: `dead-reference`,
  `missing-asset`, `unused-tool`, `unreachable-section`, `recursive-call`. Wired
  into `package_skill.py` after validation — error-severity findings block packaging.

- **Skill linter** (`scripts/lint.py`) — eight content-quality rules:
  `description-length`, `description-no-trigger`, `description-no-boundary`,
  `token-budget`, `missing-example`, `missing-reference-section`,
  `frontmatter-missing-tools`, `workflow-no-output`. Exit 0 = clean, 1 = errors
  (blocks commit), 2 = warnings only (commit proceeds). Wired into the pre-commit
  hook alongside `quick_validate.py`.

- **Versioned skill schema** (`schemaVersion` frontmatter field,
  `scripts/migrations/`, `scripts/migrate_skill.py`) — `schemaVersion: 1` added
  to `skill.yaml` and accepted by `quick_validate.py`. Migration registry maps
  `(from, to)` pairs to functions; `v1_to_v2.py` is the identity template.
  `python -m scripts.migrate_skill <path> --to <version> [--dry-run]`

- **Plugin architecture** (`generators/`) — `GeneratorRegistry` with pluggable
  `Generator` base class. Three built-in archetypes: `default` (general-purpose),
  `python-skill` (pre-fills terminal/filesystem tools, creates `scripts/main.py`
  stub), `research` (pre-fills WebSearch/WebFetch, creates `references/overview.md`).
  `python -m generators --archetype python-skill --name my-skill --output ./skills/`

- **Pylance config** (`pyrightconfig.json` at repo root, `skills/skill-creator/`) —
  `extraPaths: ["skills/skill-creator"]` so Pylance resolves `scripts.*` and
  `generators.*` imports without false positives.

### Changed

- `skill.yaml` version bumped to `1.1.0`; `schemaVersion: 1` added; 12 new
  dependency entries for all new scripts and generators.
- `scripts/quick_validate.py`: `schemaVersion` added to `ALLOWED_PROPERTIES`.
- `scripts/package_skill.py`: static analysis runs after validation; errors block.
- `scripts/hooks/pre-commit`: `lint.py` runs alongside `quick_validate.py`;
  exit 2 (warnings) allows commit, exit 1 (errors) blocks it.
- `scripts/utils.py`: `parse_skill_md()` delegates to `Skill.from_path()`.

---

## [1.0.0] - 2026-07-12

Initial release of **skill-creator** — a meta-skill for Claude Code that handles
the full lifecycle of building, testing, and iteratively refining other skills.

### Added

- **Eval runner** (`scripts/run_eval.py`) — spawns Claude subprocesses against a
  set of test prompts and measures whether the skill description causes the skill
  to load. Produces per-query trigger rates so you can see exactly which prompts
  are flaky.

- **Optimization loop** (`scripts/run_loop.py`) — iterates on the skill description
  automatically, proposing rewrites after each eval round until trigger accuracy
  reaches a target threshold or a max iteration count is hit.

- **Description improver** (`scripts/improve_description.py`) — targeted rewriter
  for skill descriptions; can be run standalone when you only need to tune the
  triggering surface without a full eval loop.

- **Browser-based eval viewer** (`eval-viewer/generate_review.py` + `viewer.html`)
  — launches a local web UI that shows with-skill vs baseline outputs side by side,
  displays benchmark metrics, and collects structured user feedback. Use `--static`
  for headless environments.

- **Blind A/B comparison agents** (`agents/analyzer.md`, `comparator.md`,
  `grader.md`) — three specialist agents for objective evaluation: the comparator
  runs blind comparisons without knowing which version is which, the grader scores
  assertions in `expected_behavior.yaml`, and the analyzer flags non-discriminating
  evals and high-variance results.

- **Benchmark pipeline** (`scripts/aggregate_benchmark.py`,
  `scripts/generate_report.py`) — aggregates grading results across runs into
  `benchmark.json` with pass rates, token/timing statistics (mean ± stddev), and
  per-version deltas. Generates a human-readable markdown report.

- **Regression test suite** (`tests/should_trigger.yaml`,
  `tests/should_not_trigger.yaml`, `tests/expected_behavior.yaml`) — 10 positive
  and 9 near-miss negative test cases covering the full intent space; expected
  behaviour graded by the grader agent via `--grade-transcript`.

- **Skill packaging** (`scripts/package_skill.py`) — bundles a skill folder into
  a distributable `.skill` zip archive ready for sharing or installation.

- **Quick validator** (`scripts/quick_validate.py`) — read-only structural check
  of `SKILL.md` frontmatter, required fields, and lifecycle consistency. Runs in
  under a second; wired into the pre-commit hook and `validate_all.sh`.

- **JSON schema reference** (`references/schemas.md`) — complete field-by-field
  definitions for `evals.json`, `grading.json`, `history.json`, `benchmark.json`,
  `timing.json`, and `feedback.json`.

- **Environment adaptations** (`references/environments.md`) — instructions for
  using the skill in Claude Code, Claude.ai (no subagents), and Cowork (no browser),
  including how to update an already-installed skill.

- **Apache 2.0 license** — project is now explicitly open-source.

### Removed

- `skill-architect` six-gate pipeline (`skills/skill-architect/`) — replaced by
  the eval-driven `skill-creator` workflow. The six-gate approach (Evidence,
  Adversarial Elicitation, Trigger Contract, Iron Law, Self-Critique, Blast Radius,
  Variance Analysis) was effective for manual audits but lacked automated eval
  infrastructure; `skill-creator` covers the same quality goals with measurable,
  repeatable benchmarks.

[Unreleased]: https://github.com/rolling-codes/better-skill-creator/compare/v3.7.5...HEAD
[3.7.5]: https://github.com/rolling-codes/better-skill-creator/compare/v3.7.4...v3.7.5
[3.7.4]: https://github.com/rolling-codes/better-skill-creator/compare/v3.7.3...v3.7.4
[3.7.3]: https://github.com/rolling-codes/better-skill-creator/compare/v3.7.2...v3.7.3
[3.7.2]: https://github.com/rolling-codes/better-skill-creator/compare/v3.7.1...v3.7.2
[3.7.1]: https://github.com/rolling-codes/better-skill-creator/compare/v3.7.0...v3.7.1
[3.7.0]: https://github.com/rolling-codes/better-skill-creator/compare/v3.6.0...v3.7.0
[3.6.0]: https://github.com/rolling-codes/better-skill-creator/compare/v3.5.1...v3.6.0
[3.5.1]: https://github.com/rolling-codes/better-skill-creator/compare/v3.5.0...v3.5.1
[3.5.0]: https://github.com/rolling-codes/better-skill-creator/compare/v3.4.1...v3.5.0
[3.4.1]: https://github.com/rolling-codes/better-skill-creator/compare/v3.4.0...v3.4.1
[3.4.0]: https://github.com/rolling-codes/better-skill-creator/compare/v3.3.1...v3.4.0
[3.3.1]: https://github.com/rolling-codes/better-skill-creator/compare/v3.3.0...v3.3.1
[3.3.0]: https://github.com/rolling-codes/better-skill-creator/compare/v3.2.1...v3.3.0
[3.2.1]: https://github.com/rolling-codes/better-skill-creator/compare/v3.2.0...v3.2.1
[3.2.0]: https://github.com/rolling-codes/better-skill-creator/compare/v3.1.0...v3.2.0
[3.1.0]: https://github.com/rolling-codes/better-skill-creator/compare/v3.0.1...v3.1.0
[3.0.1]: https://github.com/rolling-codes/better-skill-creator/compare/v3.0.0...v3.0.1
[3.0.0]: https://github.com/rolling-codes/better-skill-creator/compare/v2.1.0...v3.0.0
[2.1.0]: https://github.com/rolling-codes/better-skill-creator/compare/v2.0.3...v2.1.0
[2.0.3]: https://github.com/rolling-codes/better-skill-creator/compare/v2.0.2...v2.0.3
