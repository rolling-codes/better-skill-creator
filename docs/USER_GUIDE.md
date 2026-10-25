# Better Skill Creator: user guide

**User documentation · Updated 24 October 2026**

This guide describes the implementation shipped in **v3.7.0** (release commit `38b5347`), including PRs #78 and #79. It was completed on 25 October 2026. See the [release notes](https://github.com/rolling-codes/better-skill-creator/releases/tag/v3.7.0) and [root changelog](../CHANGELOG.md) for the release record.

It consolidates the [root changelog](../CHANGELOG.md), [component changelog](../skills/skill-creator/CHANGELOG.md), [bundled release history](../skills/skill-creator/RELEASE_NOTES.md), existing guides, and current implementation. Where older notes disagree with current code, this guide follows the code. See [Release history and upgrade notes](#release-history-and-upgrade-notes) for the historical context.

## Contents

- [What Better Skill Creator does](#what-better-skill-creator-does)
- [Install and get started](#install-and-get-started)
- [Design and build a skill](#design-and-build-a-skill)
- [Validate the skill](#validate-the-skill)
- [Test whether it triggers](#test-whether-it-triggers)
- [Test what it does after loading](#test-what-it-does-after-loading)
- [Compare results and improve descriptions](#compare-results-and-improve-descriptions)
- [Review results with a human](#review-results-with-a-human)
- [Independent review and completion](#independent-review-and-completion)
- [Package and share](#package-and-share)
- [Feature and tool index](#feature-and-tool-index)
- [Troubleshooting](#troubleshooting)
- [Release history and upgrade notes](#release-history-and-upgrade-notes)
- [Limits and documentation sources](#limits-and-documentation-sources)

## What Better Skill Creator does

Better Skill Creator is a Claude Code plugin containing a **meta-skill**: a skill that helps you create, test, review, and improve other skills. It builds on Anthropic's skill-creator workflow and adds deterministic checks, review records, evaluation controls, and packaging safeguards.

A skill combines a description that helps the model select it, instructions for doing the task, and optional scripts, references, or assets. It can fail in several distinct ways:

| Question | How the toolkit helps answer it |
|---|---|
| Did we design the right workflow? | Design analysis and an optional structured specification |
| Are the files and instructions internally consistent? | Structural validation, lint, static and semantic analysis |
| Does the model load the skill for the right requests? | Positive and negative trigger evaluations |
| Does it perform the task well after loading? | Task evaluations, transcript grading, and baseline comparisons |
| Has anyone challenged the author's assumptions? | Independent reviewers and an adversarial completion gate |
| Is the distribution current and safe to assemble? | Source-bound review evidence and a guarded packaging pipeline |

These checks answer different questions. A high architecture score does not prove good task performance. A successful trigger does not prove correct behavior. An attractive output does not establish improvement over a baseline.

Use the plugin when creating a skill, debugging its scope or triggering, comparing versions, or preparing it for distribution. To perform an ordinary task with an existing skill, use that skill directly.

### Two ways to work

**Conversational workflow:** ask Claude Code to create or improve a skill. The meta-skill guides the design, drafting, evaluation, and review process. Example: “Create a skill that reviews SQL queries and explains performance risks without changing the database.”

**Command-line workflow:** use `bsc.py` from a repository checkout for setup checks, scaffolding, validation, trigger evaluation, comparison, and packaging. The front-end writes a JSON result and a Markdown report for each operation.

The conversational skill supplies judgment and coordination. The Python tools perform bounded operations; running one does not automatically execute the entire authoring workflow.

### Working in different environments

The full workflow targets Claude Code with subprocess access. In a host without subagents, manual task runs and human feedback can still improve a draft, but they do not provide the same independent comparison or review evidence. Without the Claude CLI, skip live trigger evaluation and description optimization. Without a browser, export the viewer as static HTML or present artifacts directly. Python-based analysis and packaging depend on filesystem access and the relevant prerequisites rather than a particular chat interface.

When updating an installed skill, preserve its name and work in a writable copy if the installation is read-only. The [environment guide](../skills/skill-creator/references/environments.md) describes these adaptations; use available capabilities rather than assuming every host provides the full workflow.

## Install and get started

### Prerequisites

- Python **3.12 or newer** is the supported floor and CI target baseline.
- Install the checkout's Python dependencies from `requirements.txt`.
- Claude Code is required for plugin use and model-backed evaluation. It must be authenticated before live model work.
- Git is needed for repository operations and hook installation. Shell scripts require Bash; the Python front-end is the simpler starting point on Windows.

Installing the plugin registers the skill. Running `python bsc.py ...` also requires the repository checkout; a plugin installation does not create a global `bsc` command.

### Install from a checkout

```bash
git clone https://github.com/rolling-codes/better-skill-creator
cd better-skill-creator
python -m pip install -r requirements.txt
claude plugin marketplace add .
claude plugin install skill-creator@skill-creator-local
```

Reload the plugins or restart Claude Code so the skill is available in a new session. You can also register the GitHub marketplace directly using the installation commands in the [README](../README.md).

### Check the environment

Run from the repository root:

```bash
python bsc.py doctor
```

Doctor checks Python, PyYAML, Claude CLI availability, advertised evaluation flags, plugin manifests, and the repository's pre-commit hook. It does **not** make model calls or establish that authentication, account allowances, or paid-overage settings are ready for live evaluation. Some unavailable optional checks are reported as skipped.

### Try a complete starter

```bash
python bsc.py new my-skill --example release-notes --output skills
python bsc.py check skills/my-skill
python bsc.py eval skills/my-skill
```

The first command copies the release-notes example into a new directory. It includes authored trigger and behavior cases. It refuses an existing destination. Edit the copied description, instructions, examples, and tests to fit your task; renaming the scaffold does not customize its workflow.

The final command previews trigger evaluation without model calls. Add `--live` only when you intend to run the model-backed evaluation.

### Where reports go

Front-end commands normally create `runs/<timestamp>-<id>/results.json` and `report.md`, with additional artifacts depending on the operation. Each subcommand accepts `--runs-dir` to change the report location. Read the status, findings, skipped checks, and next action; a report file can describe an unsuccessful operation too.

## Design and build a skill

### Start from the outcome

The design process asks what should be true when the task is finished. It considers materially different interpretations, necessary steps, failure cases, output validation, and authorization boundaries. It should reuse context from a conversation or development log when available.

For example, “watch my logs” might mean report errors, diagnose them, propose patches, or apply fixes. Those workflows require different tools and permissions. The process chooses a supported interpretation and asks a focused question when the available context cannot resolve a consequential difference.

Core design questions always apply. Additional lenses—security, persistence, accessibility, recovery, integrations, and others—are used when they affect the task. They are guidance for reasoning, not a requirement to add every possible subsystem.

**Necessary work still needs authorization.** The design distinguishes required and authorized actions, required actions needing permission, optional additions, and excluded actions. A diagnosis skill should not acquire write permissions merely because a repair would be useful.

### Record a specification when useful

An optional `spec.yaml` stores purpose, inputs, outputs, constraints, dependencies, examples, and workflows. It can also record the chosen interpretation, supported modes, entailments, assumptions, validation, failure points, and open questions.

From `skills/skill-creator/`:

```bash
python -m scripts.spec init /path/to/my-skill
python -m scripts.spec validate /path/to/my-skill
python -m scripts.confidence /path/to/my-skill
```

Fill in the specification before validating it. Confidence is a structural assessment of coverage and ambiguity, not a measured probability that the skill will succeed. Older specs missing design-analysis fields can produce warnings while remaining structurally valid.

### Organize the files

```text
my-skill/
  SKILL.md
  skill.yaml                 # toolkit metadata and dependencies, when used
  spec.yaml                  # optional design brief
  scripts/                   # executable helpers
  references/                # instructions loaded when relevant
  assets/                    # templates and output resources
  tests/
    should_trigger.yaml
    should_not_trigger.yaml
    expected_behavior.yaml
```

`SKILL.md` is the runtime entry point. Its frontmatter describes selection; its body explains the workflow and points to supporting resources. Keep it concise—the guidance aims for roughly 500 lines or fewer—and move detailed material into clearly linked references.

The toolkit checks both missing references and resources that are never wired into `SKILL.md`. Where `skill.yaml` declares dependencies, keep those entries, the runtime links, and the files on disk aligned. Shipping a file is not enough to make it discoverable to the agent.

### Write portable frontmatter

```yaml
---
name: sql-review
description: Reviews SQL queries for correctness and performance risks. Use when the user requests a query review. Not for executing queries or changing a database.
metadata:
  schemaVersion: 1
  target_model: sonnet
---
```

Put custom fields under `metadata`; a top-level `schemaVersion` is a legacy format that strict validation rejects. `metadata.target_model` takes a toolkit tier (`haiku`, `sonnet`, `opus`, or `fable`), not a full model identifier. It guides instruction density; it does not select the model used by an eval command.

The optional `allowed-tools` field is a pre-approval grant. Use real runtime tool names and narrow scopes. Its absence is not itself a defect. Claude Code extensions such as a top-level `model` field are accepted by development checks where supported, but strict upload/package validation can reject them.

The repository's model-writing guidance recommends matching detail to the target tier and avoiding unnecessary instruction density. Treat that as authoring guidance to test on your target runtime, not a guarantee about every model or a permanent list of available models.

### Alternative scaffolding and generated scenarios

The engine offers generator families for general-purpose, Python, and research skills, with aliases listed by the CLI:

```bash
# Run from skills/skill-creator/
python -m generators --list
python -m generators --archetype python-skill --name my-helper --output /path/to/skills
python -m scripts.generate_tests /path/to/my-helper
```

Generators emit starting structures that need customization and validation. Scenario generation writes six groups under `tests/generated/`: happy paths, edge cases, malformed inputs, ambiguous requests, missing files, and unsupported environments. Review the generated prompts and labels for your actual task; they are templates rather than verified semantic judgments. The trigger loader discovers direct `tests/generated/*.yaml` files.

## Validate the skill

### Use the front-end for a practical check

```bash
python bsc.py check skills/my-skill
python bsc.py check skills/my-skill --strict
```

`check` runs structure, lint, static analysis, semantic analysis, applicable independent-review checks, and dependency-cycle detection. It is read-only and makes no model calls. The default accepts supported Claude Code extensions; `--strict` uses the portable frontmatter contract.

| Check | What it can detect |
|---|---|
| Structure | Invalid frontmatter, required fields, lifecycle inconsistencies, and invalid dependencies |
| Lint | Weak or missing selection guidance, content-quality issues, and incomplete resource wiring |
| Static analysis | Dead or escaping references, orphaned resources, and other file-level inconsistencies |
| Semantic analysis | Heuristic duplicate, empty, contradictory, or inconsistent instruction content |
| Dependencies | Cycles and dependency structure; the graph tool also exports summary, JSON, or DOT |
| Review | Missing or stale required reports, unresolved material findings, and invalid completion evidence |

“Semantic analysis” here means deterministic content checks. It is not an independent model proving that the instructions make sense.

### Scores and the unified validator

The engine also exposes `scripts.validate`, `scripts.score`, and `scripts.confidence`. The unified validator runs structure, lint, static and review checks, then reports score and confidence. It differs from `bsc.py check`; the commands are not interchangeable checklists.

The architecture score covers completeness, maintainability, extensibility, clarity, validation, robustness, and testability. These are heuristic signals. They help identify weak structure but cannot replace task evidence. The unified validator treats an overall score below 70 as an error; the packaging driver reports a low-score warning instead of using that same threshold as an independent blocker.

### Repair only what can be corrected mechanically

```bash
# Run from skills/skill-creator/
python -m scripts.repair /path/to/my-skill --dry-run
```

Repair proposes deterministic fixes for supported rules. Without `--dry-run`, it can rewrite source. It cannot decide what a vague skill ought to do. Inspect changes and rerun analysis; source edits can invalidate review evidence.

### Checks for toolkit maintainers

The repository also checks its own engineering claims and documentation:

- `source_rules` catches selected Python defect classes: missing text encodings and silent exception swallowing.
- `doc_sync` checks documented command names, flags, modules, links, and review subcommands in its configured document set.
- `claims_check` links registered behavioral claims to existing, potentially executable verifier tests and rejects some obvious hollow verifiers.
- Release-metadata tests catch version drift across the launcher, manifests, README badge, and top changelog release.

These checks prevent known failure classes. They do not establish that every assertion is meaningful or every documented claim is true.

## Test whether it triggers

### Author positive and negative cases

Put intended requests in `tests/should_trigger.yaml`:

```yaml
- prompt: Review this SQL query for performance risks.
  expected: true
```

Put adjacent requests outside the scope in `tests/should_not_trigger.yaml`:

```yaml
- prompt: Execute this migration against production.
  expected: false
```

The loader accepts both `prompt`/`expected` and `query`/`should_trigger`, plus supported legacy label forms. Prefer explicit booleans in new tests. Duplicate queries are deduplicated; contradictory labels are errors.

### Preview before spending calls

```bash
python bsc.py eval skills/my-skill --models haiku,sonnet --runs 3 --max-calls 100
python bsc.py eval skills/my-skill --models haiku,sonnet --runs 3 --max-calls 100 --live
```

The first command previews. The second runs model processes. The front-end defaults to one worker, one run per query, no retries, a 60-second timeout, a 0.5 trigger threshold, and a 20-call ceiling. Set the budget for the actual suite size, repetitions, model count, control calls, and possible retries. A ceiling does not guarantee that the suite can finish within it.

Use `--save-transcripts` to retain the captured stream for inspection. Read the report's valid-run counts, failures, and incomplete cases as well as its pass rate.

### How the measurement works

The evaluator makes the skill discoverable through a synthetic command file and runs isolated Claude subprocesses. Before the main cases, a control prompt checks that the discovery mechanism works. A failed control aborts the measurement rather than treating every case as a clean non-trigger.

Runs distinguish a clean trigger or non-trigger from timeout, authentication, subprocess, and parsing failures. Trigger rates use clean runs; failed executions cannot satisfy negative expectations. Stop and fix infrastructure before optimizing a description against those results.

`--max-calls` bounds charged model attempts through shared budget controls. It is a call count, not a currency or token limit. Account charging and available models depend on the installed Claude environment.

### Review neighboring-skill near misses

Branch functionality added around PR #78 generates deterministic proposals from neighboring skill descriptions:

```bash
# Run from skills/skill-creator/
python -m scripts.generate_tests /path/to/my-skill --adjacent-skills /path/to/neighbor-skills
python -m scripts.generate_tests /path/to/my-skill --promote-candidates /path/to/reviewed.yaml
```

The generator inspects immediate child skill directories and writes proposals to `tests/candidates/near_misses.yaml`, outside the measured suite. Read each prompt, set `reviewed: true`, and add an explicit boolean `should_trigger` before promotion.

Promotion checks labels and suite conflicts, deduplicates against existing cases, and writes accepted queries to `tests/generated/near_misses.yaml`. If no new cases remain, it fails before writing. Both modes refuse an existing output unless `--replace` is supplied. Replacement is deliberate; keep an earlier copy if you need its cases.

These proposals are not model-verified negatives. A neighboring skill's description can overlap your target's scope, so the reviewer may correctly label a proposal positive.

## Test what it does after loading

Trigger tests answer whether the skill loads. Behavior tests ask whether it follows the intended workflow and produces the right artifacts.

Define behavioral expectations in `tests/expected_behavior.yaml`. Use observable assertions: required output content, prohibited modifications, necessary tool behavior, and failure handling. Avoid assertions that merely look for reassuring words.

The authoring workflow runs realistic tasks with the skill and a comparable baseline. Save the transcript and relevant output artifacts. The grader can then evaluate that saved evidence:

```bash
# Run from skills/skill-creator/
python -m scripts.skill_test /path/to/my-skill --grade-only --grade-transcript /path/to/transcript.md --outputs-dir /path/to/outputs
```

Grading invokes a model even though the transcript is already saved. `--grade-only` skips trigger tests; it does not make grading offline. The front-end also supports `bsc.py eval ... --grade-transcript ...`; inspect its options and report to distinguish grading from trigger execution.

### Understand the verdicts

| Verdict | Meaning |
|---|---|
| `PASS` | The available evidence supports the expectation |
| `FAIL` | The available evidence shows an expectation was not met |
| `UNDETERMINED` | Evidence is incomplete or insufficient to decide |

The transcript checks account for interrupted or incomplete tool activity and truncated formats. Absence of a forbidden action in an incomplete transcript is not sufficient evidence that it never occurred. Grader responses must cover the requested expectations with valid evidence; malformed or incomplete grading is an execution problem.

The grading path writes a report such as `<transcript-filename>.grading.json` and a fixed `behavior_evidence.json`. The evidence binds the transcript and relevant skill source with hashes. Consumers expecting the conventional `grading.json` name—such as the aggregate benchmark workflow—need an explicit `--grade-output` path.

The front-end can write grading evidence under its run directory. The review gate must be pointed to that evidence using the review record's evidence path, or receive it at the expected skill-local location. A successful grading command alone does not make the gate discover the file.

## Compare results and improve descriptions

### Compare compatible runs

```bash
python bsc.py compare --candidate /path/to/candidate-results.json --baseline /path/to/baseline-results.json
python bsc.py eval skills/my-skill --models haiku,sonnet --baseline /path/to/baseline-results.json
```

The second command performs a preview and baseline preflight; add `--live` to evaluate. Save the unmodified prior run as the baseline, then measure the candidate under comparable conditions.

Comparisons report aggregate and per-query changes. Positive oriented improvement means better behavior: increasing triggers helps a positive case, while decreasing triggers helps a negative case. A valid comparison showing a regression is still a valid execution result.

Model-aware front-end reports keep models separate. Exact requested identifiers are matched; aliases are not equated to full IDs, and configured-default sentinels do not establish an explicit identity. Aliases may resolve differently between runs, so pinned model IDs give stronger reproducibility. Legacy raw-to-raw comparisons retain more permissive identity handling and warnings.

Malformed metrics, conflicting labels, incompatible skill identities, no shared queries, and infrastructure failures prevent valid comparison. Incomplete query executions also block it. Known `trigger_threshold` mismatches are errors; missing legacy threshold metadata produces a warning. Partial query overlap is reported rather than hidden.

**Sample sufficiency is not statistical significance.** The legacy `significance_claim` field is also exposed as `sample_sufficient`; the tool does not run a significance test. Small-run warnings, repeated observations, and variance still matter. Historical release percentages are results from particular experiments, not a general promise that this fork beats another skill creator.

### Optimize selection descriptions

From `skills/skill-creator/`:

```bash
python -m scripts.run_loop --eval-set /path/to/eval.json --skill-path /path/to/my-skill --model sonnet --max-calls 100 --results-dir /path/to/optimization-results
```

The optimizer evaluates descriptions and asks a model to propose improvements. It defaults to train/validation/held-out fractions of 60%/20%/20%. The improvement prompt sees training feedback; validation selects the best candidate; the held-out partition is evaluated once after selection. Disabling validation supports the legacy two-way mode.

This protects against selecting a description solely because it fits the same examples used to rewrite it. It does not remove the need for representative cases or enough data in each partition.

Infrastructure failures stop optimization. If the improvement step fails, completed iterations remain available in the results rather than being discarded. The optimizer uses model calls; preview settings and budget before invoking it. See [description optimization](../skills/skill-creator/references/description-optimization.md) for eval-set guidance.

## Review results with a human

The eval viewer displays outputs, prior-iteration feedback, and optional benchmark summaries. Its local server collects feedback in `feedback.json`; static export supports environments where a local browser/server is unsuitable.

From the repository root, for an existing evaluation workspace:

```bash
python skills/skill-creator/eval-viewer/generate_review.py /path/to/workspace --static /path/to/review.html
```

For the interactive viewer, omit `--static`. Use `--previous-workspace` for iteration context and `--benchmark` for an aggregate benchmark file. Static export provides a review artifact rather than the server's direct feedback-save endpoint.

The benchmark aggregator reads the documented eval/configuration/run directory structure and derives means, sample standard deviations, and per-metric measured counts from saved results. Missing measurements remain missing rather than becoming zeros. The grader, blind comparator, and analyzer have different jobs: check assertions, compare outputs without condition labels, and find weak or high-variance evals.

The aggregate benchmark's layout is separate from a front-end `runs/<id>/results.json` report. Use the [schema reference](../skills/skill-creator/references/schemas.md) when preparing benchmark workspaces. The [comparative methodology](../skills/skill-creator/references/benchmark-methodology.md) describes broader construction-quality and downstream-performance experiments; it is not an automated proof of superiority.

## Independent review and completion

Substantial skill creation or changes require fresh-context review. Narrow edits can explicitly record why a full review is unnecessary. The activation decision must be deliberate.

| Reviewer | Primary question |
|---|---|
| Outcome analyst | Does the design address the real requested result? |
| Scope adversary | Is it missing necessary scope or adding unjustified scope? |
| Architecture reviewer | Can the structure and workflow deliver the result? |
| Practices reviewer | Is shipped runnable code engineered correctly? |
| Completion adversary | Can the finished artifact be shown incomplete? |

Initial reviewers inspect independently. Their findings are synthesized using evidence rather than a majority vote. The final completion adversary receives the finished artifact, decision, and validation evidence without the implementation narrative. Material findings must be fixed, accepted as documented limitations, or returned as decisive questions; material fixes require another completion review.

`review.yaml` records activation, reports, synthesis, findings and dispositions, limitations, and completion status. Its source manifest hashes the covered files. Adding, removing, or editing covered source invalidates prior approval.

From `skills/skill-creator/`:

```bash
python -m scripts.review show /path/to/my-skill
python -m scripts.review_gate /path/to/my-skill
```

To restart a stale review, archive the old record outside the skill, then use `python -m scripts.review restart /path/to/my-skill`. Restart captures current source and clears reports; it does not approve the skill. There is no `scripts.review run` command. Reviewer agents must actually be run and their reports recorded.

For evaluation workflows requiring behavior evidence, the gate also checks evidence validity and source/transcript provenance. Hashes detect changed content; they do not authenticate the reviewer or prove that an author-supplied report came from an independent run. Read the record and supporting evidence as well as its status.

## Package and share

```bash
python bsc.py package skills/my-skill --output dist
```

The recommended front-end packages a temporary copy and reports repairs made to that copy. It does not rewrite the source skill. The engine performs structure checks, lint/static and semantic analysis, dependency and review checks, supported repair, reanalysis after changes, scoring, and archive creation. Unresolved error findings block packaging.

Direct engine packaging can apply repairs in place. Use the front-end when you want source preservation.

The file policy excludes selected caches, build outputs, evaluation material, and recognized sensitive-file patterns. It rejects links and unsafe filesystem objects during source snapshots and enforces size bounds. This reduces accidental inclusion; it does not identify every possible secret embedded in an otherwise ordinary file. Inspect the archive before sharing.

Strict packaging can reject frontmatter accepted by a Claude Code development check. Review a resulting package and any repairs; creating a `.skill` archive does not publish it to a marketplace or install it for other users.

An existing archive is not silently overwritten. Choose a different output directory or deliberately handle the earlier artifact before packaging again. The project is licensed under [Apache 2.0](../skills/skill-creator/LICENSE.txt); authored skills and bundled third-party assets need their own appropriate attribution and licensing choices.

### Hooks and CI

`python bsc.py hooks install` installs the hook into the repository you invoke it from, honoring Git worktrees, submodules, and configured hook paths. It validates skills affected by staged files. The commit subset runs structure, lint, and review checks; Python changes or staged `pyrightconfig.json` also trigger type checking. Hooks are local and bypassable, so CI remains necessary.

The current workflow runs tests on Ubuntu and Windows with Python 3.12, offline wiring/source/docs/claims checks, pyright, doctor, and release-notes-example checks. Main and scheduled runs also have an explicit review-gate step. The full test suite includes a live-skill review-record assertion, so stale review evidence can fail PR tests even when that explicit workflow step is skipped.

The scheduled/release trigger canary uses Haiku and Sonnet, two positive and two negative cases, and one control per model: five calls each, ten across the matrix. Missing credentials are reported as a skip. A normal PR run skips this canary, so green PR CI does not establish live-model readiness.

## Feature and tool index

Engine modules below run from `skills/skill-creator/` as `python -m scripts.<module>`, not by executing their file paths. The viewer is a separate file entry point as shown above.

| Feature or tool | Purpose | Model calls / source mutation |
|---|---|---|
| `bsc.py doctor` | Diagnose prerequisites and installed CLI capabilities | No model calls; writes reports |
| `bsc.py new` | Copy the complete release-notes starter | Creates a new directory |
| `generators` | Scaffold general, Python, or research skill families | No model calls; creates files |
| `spec` / `confidence` | Record design intent and assess coverage/ambiguity | No model calls; `spec init` writes a file |
| `skill_ir` | Shared parsed representation of the authored skill | Internal library |
| `bsc.py check` | Practical structure/content/review/dependency checks | No model calls; source read-only |
| `quick_validate` | Structural and portable-frontmatter validation | No model calls; read-only |
| `lint` | Content quality and resource wiring | No model calls; read-only |
| `static_analysis` / `semantic_analysis` | File references and deterministic content consistency | No model calls; read-only |
| `dependency_graph` | Inspect graph, cycles, and change impact; export formats | No model calls; read-only inspection |
| `score` / `validate` | Architecture rubric and unified validation | No model calls; read-only |
| `repair` | Apply supported mechanical corrections | No model calls; can rewrite source |
| `generate_tests` | Generate scenario templates or reviewable adjacent-skill proposals; promote reviewed labels | No model calls; writes selected test outputs |
| `tests_loader` | Normalize and combine authored/generated trigger cases | Internal library |
| `bsc.py eval` / `run_eval` | Preview or measure skill selection | Live eval makes model calls; writes runtime artifacts |
| `skill_test` | Run trigger tests and optionally grade saved behavior evidence | Trigger/grading modes make model calls |
| `compare_eval` / `bsc.py compare` | Validate comparable runs and report oriented deltas | No model calls; writes front-end reports |
| `run_loop` / `improve_description` | Iteratively evaluate and rewrite selection descriptions | Model calls; produces candidate results |
| `aggregate_benchmark` | Aggregate saved grading, timing, and usage measurements | No model calls; writes summaries |
| `generate_report` | Turn optimizer JSON into an HTML report | No model calls; emits HTML |
| Eval viewer | Inspect outputs, benchmarks, and iteration feedback | No model calls; server can save feedback |
| Grader / comparator / analyzer agents | Assertion grading, blind comparison, and eval-quality analysis | Model-backed workflow roles |
| Review agents / `review` / `review_gate` | Independent scrutiny, recorded decisions, deterministic evidence gate | Agents use models; record/gate tools do not |
| `compiler_context` / `pipeline` / `stages` | Share state and execute packaging stages | Internal engine; concrete stages enforce checks |
| `file_policy` / `call_budget` / `claude_process` | Bound source snapshots, model attempts, and subprocess behavior | Infrastructure used by higher-level operations |
| `migrate_skill` | Convert supported skill schema versions | `--dry-run` previews; normal mode rewrites |
| `source_rules` / `doc_sync` / `claims_check` | Check toolkit code practices, docs, and registered verifiers | No model calls; read-only |
| `hooks install` / `validate_all.sh` / CI | Repeat relevant checks locally and in automation | Hooks install writes a hook; `validate_all.sh` can run live trigger tests if Claude is available |

The reference collection covers design analysis, independent review, development practices, token economy and skill composition, model-writing guidance, runtime contracts, schemas, trigger confidence, description optimization, dependency graphs, environment adaptations, and comparative benchmark methodology. These guides explain how to use the tools; they are not additional independently executing features.

## Troubleshooting

| Symptom | Likely next step |
|---|---|
| `No module named scripts` or `generators` | Use `bsc.py` from the root, or change into `skills/skill-creator/` before `python -m ...` |
| PyYAML is missing | Install requirements using the same interpreter that runs the command; Git Bash's `python3` may differ from PowerShell's `python` |
| Doctor passes but live evaluation fails | Check authentication, allowance, CLI compatibility, and the actual error category; doctor is not a live account test |
| Every query fails to trigger | Inspect control-query/discovery failure before editing the description |
| A timeout appears on a negative case | Treat it as failed execution, not successful refusal to trigger |
| `review-stale` | Source changed; archive/restart the record and obtain current independent reports |
| Review gate cannot find grading evidence | Check the evidence path and source/transcript hashes; front-end run outputs are not automatically skill-local |
| `model` passes check but packaging rejects it | Development accepts supported Claude Code extensions; packaging uses the stricter portable contract |
| Promotion has no new cases | All reviewed queries already exist in the included suite; output is preserved and the command fails |
| Comparison rejects a baseline | Inspect skill/model identity, thresholds, labels, overlap, and execution completeness; do not change metrics to force acceptance |
| Scores look good but behavior is weak | Add realistic task assertions and comparable baseline runs; structural scores are not behavioral evidence |
| Viewer has no runs | Confirm the workspace layout and files expected by the viewer schema |
| Local Windows tests fail creating a symlink | Check developer-mode/privilege support; distinguish environment failures from product regressions |

### Read exit codes in context

For validators such as lint/static/review, `0` means no blocking findings, `1` means a blocking error, and `2` generally means warnings only. For trigger evaluation, optimization, and grading, `0` means expectations passed, `1` means input/execution/infrastructure error, and `2` means evaluation completed with failed expectations. Confidence has its own threshold-based contract. Read each command's report; “2” does not mean the same thing everywhere.

## Release history and upgrade notes

This map explains how the current system accumulated its capabilities. It follows the root changelog, supplemented by component-only 1.2.0 and 1.3.0 entries; some component notes use different dates or omit patch releases. Historical score increases, pass rates, model names, and test counts describe those releases' experiments and should not be read as current guarantees.

| Release or work | Contribution and present-day relevance |
|---|---|
| **3.7.0** | Reviewable adjacent-skill proposals, model-aware comparisons, bounded two-model canary, metadata compatibility, CLI capability checks, comparison/provenance guards, and release-documentation cleanup. |
| **3.6.0** | Stronger reference containment, claim-verifier checks, documented-review-command validation, collision-resistant grading reports, preserved optimizer results on improve failure, and packaging/transcript/viewer hardening. |
| **3.5.1** | Corrected repository/install references and clarified scope complexity/risk criteria. |
| **3.5.0** | Added source-rule, documentation-sync, and behavioral-claim checks; strengthened review synthesis and validator exit-code handling. |
| **3.4.1** | Fixed shared control-call accounting, Git hook resolution, release-gate reporting, and score-error handling. |
| **3.4.0** | Added token-economy and skill-composition guidance. Component history also records discovery-control, hooks, and the earlier canary around this period; consult current code for the present behavior. |
| **3.3.1** | Made the front-end check usable on the toolkit's Claude Code metadata, added strict mode, and improved CI wiring checks and report-file hygiene. |
| **3.3.0** | Added development-practices guidance and corrected Windows containment diagnostics. |
| **3.2.1** | Hardened review/hook wiring, generator arguments, typing, packaging containment, call budgets, and repair-write cleanup. |
| **3.2.0** | Introduced unified validation, local lint suppression with typo guards, shared finding types, and target-tier writing guidance. Current code uses `finding_types.py`; historical notes name `types.py`. |
| **3.1.0** | Reworked model-writing guidance and shortened the meta-skill. Reassess time-sensitive model/API advice against the runtime when using it. |
| **3.0.1** | Restored live evaluation compatibility with native Claude CLI layouts. |
| **3.0.0** | Moved `schemaVersion` under `metadata`, corrected tool names and frontmatter rewriting, and added model-specific eval runs. Important migration boundary. |
| **2.1.0** | Added the root CLI, complete release-notes example, and Ubuntu/Windows CI; established Python 3.12 as the documented baseline. |
| **2.0.3** | Made stream handling portable to Windows and separated failed executions from valid non-triggers; stopped optimization on infrastructure failures. |
| **2.0.2** | Corrected dependency-graph usage documentation; did not restore the retired numbered-gate workflow. |
| **2.0.1** | Fixed lifecycle consistency and path containment, with compatibility fixes for the then-supported older Python floor. |
| **2.0.0** | Added independent reviewer roles, `review.yaml`, and blocking completion/package gates for substantial skill work. |
| **1.10.0** | Made design analysis adaptive and bounded; added authorization classifications and a scope-selection decision framework. |
| **1.9.1** | Wired design confidence into the CLI and kept older specifications loadable. |
| **1.9.0** | Added outcome-centered design analysis and structured design fields. |
| **1.8.1** | Clarified that the dependency graph is an optional local inspection tool. |
| **1.8.0** | Connected previously undiscoverable tools to the runtime entry point and added reverse wiring checks. |
| **1.7.0** | Aligned version numbering with the current repository history; not a functional feature release. |
| **1.4.0** | Made baseline evidence an explicit rule, added rationalization/red-flag guidance, and extracted description-optimization instructions. |
| **1.3.1** | Fixed plugin naming/install metadata, hooks, dependencies, license/version consistency, and overly broad lint signals. |
| **1.3.0 — component history** | Added the shared compiler context, stage registry and stage protocol, with repair planning separated from applying changes. The current pipeline also includes review enforcement. |
| **1.2.0 — component history** | Added the specification, confidence, semantic analysis, repair, architecture score, and scenario-generation tools. |
| **1.1.0** | Added the skill IR, dependency graph, static analysis, lint, versioned schemas, and generator registry. |
| **1.0.0** | Established trigger evals, iterative description improvement, human review UI, evaluation agents, benchmark aggregation, validation, and `.skill` packaging; replaced the older skill-architect pipeline. |

### Upgrade an older authored skill

Use Python 3.12+ regardless of historical Python 3.8 compatibility notes. Back up or commit the skill before migration. From the toolkit directory:

```bash
python -m scripts.migrate_skill /path/to/my-skill --to 1 --dry-run
python -m scripts.migrate_skill /path/to/my-skill --to 1
```

Then check frontmatter, actual tool names, declared dependencies, lifecycle metadata, and tests. Rerun validation and obtain current review/evaluation evidence as appropriate. A schema migration does not establish behavioral equivalence.

## Limits and documentation sources

The toolkit implements checks and workflows, not a universal reliability guarantee. Independent-review authenticity still needs human scrutiny. Claim-verifier detection and content analysis are heuristics. Budget counts are not monetary caps. Missing usage fields are not zero consumption. Live readiness and cross-model quality require live evidence.

The current roadmap retains model-assisted near-miss proposals with semantic review and broader repeated trigger/behavior benchmarks across supported tiers. Those should remain clearly separate from deterministic proposals and the small scheduled canary available now.

Use these rules when interpreting or maintaining the documentation:

1. **Setup floor:** Python 3.12+ is the supported minimum. Older release notes about Python 3.8 describe historical compatibility work.
2. **Release sources:** the root changelog is the maintained release ledger. The bundled release history and component changelog are historical sources; their shorter coverage does not mean later features are absent. Read [What’s new](WHATS_NEW.md) for the v3.7.0 feature overview and the changelog for post-release changes.
3. **Historical canary descriptions:** older notes describe different model counts and call limits. The current workflow is authoritative for today's bounded canary.
4. **Front-end versus engine contracts:** retain the distinctions between development/strict validation, grading/trigger execution, score warnings/thresholds, and source-preserving/in-place packaging.
5. **Time-sensitive model guidance:** document tier intent separately from available model IDs and dated API claims; the [runtime-contract reference](../skills/skill-creator/references/claude-code-contracts.md) distinguishes documentation, installed-CLI, offline-test, and live evidence.

This guide lives outside the runtime skill directory. It is explanatory repository documentation, not an additional instruction file automatically loaded by the meta-skill. The [decision record](../decisions.md) explains the tradeoffs behind the current implementation and documentation structure.
