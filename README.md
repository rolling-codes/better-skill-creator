# Better Skill Creator

[![Release v3.7.0](https://img.shields.io/badge/release-v3.7.0-blue.svg)](https://github.com/rolling-codes/better-skill-creator/releases/tag/v3.7.0)
[![Claude Code Skill](https://img.shields.io/badge/Claude%20Code-Skill-blueviolet.svg)](https://claude.ai/code)
[![Python 3.12+](https://img.shields.io/badge/Python-3.12%2B-green.svg)](#requirements)
[![License](https://img.shields.io/badge/license-Apache%202.0-green.svg)](LICENSE)

Better Skill Creator is an engineering system for helping humans and AI agents create, evaluate, and improve reliable agent skills.

A skill is not a program that runs the same way every time. A model has to decide whether the skill applies, how much of it to load, and how to follow it. A well-written skill can still fail to trigger, trigger when it shouldn't, or behave differently on another model. Better Skill Creator treats those failures as things to measure, not things to hope away.

**The core rule:** do not call a skill better without evidence from a comparable baseline.


## Quick start

1. **Install:**

   ```bash
   claude plugin marketplace add rolling-codes/better-skill-creator
   claude plugin install skill-creator@skill-creator-local
   ```

2. **Install the pre-commit hook** (optional but recommended):

   ```bash
   python bsc.py hooks install
   ```

   Installs into the git repository you run this from, and validates each skill whose files are staged. Type-checking runs when a Python file or `pyrightconfig.json` is part of the commit.

3. **Create or improve a skill** — ask your agent. The skill-creator meta-skill figures out which stage the work is in and moves it forward.

4. **Add trigger tests:** create `skills/my-skill/tests/should_trigger.yaml` with positive cases and `skills/my-skill/tests/should_not_trigger.yaml` with negative cases. Each file is a YAML list with `prompt` and `expected` fields (`true` for positive, `false` for negative). See the [positive](examples/release-notes/tests/should_trigger.yaml) and [negative](examples/release-notes/tests/should_not_trigger.yaml) examples.

5. **Validate:**

   ```bash
   python bsc.py check skills/my-skill
   ```

6. **Preview evaluation** (no model calls):

   ```bash
   python bsc.py eval skills/my-skill
   ```

   Check the call estimate, your account allowance, and paid-overage settings before running live:

   ```bash
   python bsc.py eval skills/my-skill --live
   ```

   Pass `--model haiku` (or `--models haiku,sonnet`) to run against specific model tiers.


## Requirements

- **Python 3.12+**
- **PyYAML** — `pip install pyyaml`
- **Claude Code** — installed and authenticated


## How it works

Every skill moves through the same stages, scaled to how risky the skill is, backed by real tools in `skills/skill-creator/scripts/`:

1. **Understand.** Pin down the outcome the user actually needs (see [design-analysis.md](skills/skill-creator/references/design-analysis.md)).
2. **Design.** Decide when the skill should trigger, when it should not, and what it is allowed to do.
3. **Build.** Write SKILL.md and any references, templates, or scripts.
4. **Validate.** Check frontmatter, file structure, AST, and references for broken wiring with `python bsc.py check skills/my-skill`.
5. **Evaluate Behavior.** Run realistic tasks with the skill and with a baseline. Capture raw JSONL or Markdown transcripts and grade them via `skills/skill-creator/scripts/skill_test.py`. Results are strictly classified as `PASS`, `FAIL`, or `UNDETERMINED`.
6. **Test Triggering.** Run should-trigger and should-not-trigger prompts repeatedly to measure trigger rates across models. Optimize descriptions with `skills/skill-creator/scripts/run_loop.py` using a three-way split (60% train, 20% validation, 20% held-out test).
7. **Independent Review.** Separate reviewer agents (`skills/skill-creator/agents/`) challenge scope, architecture, practices, and outcome evidence.
8. **Adversarial Gate.** The deterministic gate in `skills/skill-creator/scripts/review_gate.py` checks cryptographically bound `behavior_evidence.json` before allowing packaging.

Behavior can be graded from a saved transcript, not just from live runs, so the behavior check still works headlessly — without the full live baseline-and-subagent loop — when that can't run; the skill's own eval workflow documents the exact command.


## What makes it different

**Triggering is tested separately from quality.** A skill can work perfectly once loaded and still be a poor skill if the model rarely loads it. Behavior evals and trigger evals answer different questions, so they are run separately.

**Model behavior is treated as data.** Triggering depends on the description, the other installed skills, the task, and the model. A description that triggers reliably on one model can undertrigger on another. The project keeps records of how supported models tend to route skills, so new work starts from known behavior instead of rediscovering it.

<!-- TODO: add one real example of a description that behaved differently across two models -->

**Independent review.** For substantial skills, separate reviewers check four things from fresh context: whether the skill achieves its outcome, whether it can be misapplied outside its scope, whether its structure is sound, and whether there is real evidence it is finished.

**Entailment is not permission.** An instruction can imply an action is needed without authorizing the agent to take it. Each action a skill might take is classified as required and authorized, required but needing authorization, optional, or out of scope. This matters most for skills that edit files, run commands, or touch external systems.

**Context is a budget.** Skills compete for the model's context. The design asks what belongs in frontmatter, what belongs in SKILL.md, and what should load only when needed. The goal is enough context to do the task correctly, and no more.


## Implemented Architecture vs. Planned Roadmap

### Implemented Engineering Controls
- **Transcript Integrity & Tri-State Grading** (`skills/skill-creator/scripts/skill_test.py`):
  Parses JSONL and Markdown transcripts. Incomplete tool executions, truncated code fences, unclosed tags, or process interruptions trigger `UNDETERMINED` verdicts rather than false `PASS` or silent failures. Negative assertions (*"does not write..."*) are strictly downgraded if transcript completeness cannot be proven.
- **Evidence-Backed Adversarial Completion Gate** (`skills/skill-creator/scripts/review_gate.py`):
  Requires `behavior_evidence.json` bound with SHA-256 digests of the source skill manifest and raw transcript. Missing, malformed, stale, or failing evidence blocks completion claims.
- **Three-Split Held-Out Trigger Optimization** (`skills/skill-creator/scripts/run_loop.py`):
  Stratified partitioning into Train (60%), Validation (20%), and Held-out (20%). Validation and held-out scores are blinded from the improvement prompt. Candidate selection uses validation performance; the held-out set is evaluated exactly once after the loop on the selected best candidate.
- **Baseline Deltas & Statistical Warnings** (`skills/skill-creator/scripts/compare_eval.py`, `bsc.py`):
  Automated per-query and aggregate delta reporting with oriented improvement metrics. Prominently displays caution banners when `--runs < 10` to avoid false confidence from small sample sizes.
- **AST & Documentation Synchronization** (`skills/skill-creator/scripts/doc_sync.py`):
  Automated tests guarantee that CLI flags, modules, and file links in the documentation match parser definitions and filesystem reality.

- **Reviewable Near-Miss Candidates**: Offline proposals from neighboring skill descriptions stay outside measured evals until their labels are explicitly reviewed and promoted.
- **Model-Aware Baseline Comparisons**: Raw eval JSON and front-end reports can be compared by exact model identity, with missing models and invalid inputs reported separately.
- **Bounded Trigger Matrix**: The scheduled/release canary tests Haiku and Sonnet on two positive and two negative cases, with five calls per model and downloadable reports. Missing credentials are reported explicitly.

### Review near-miss cases

From `skills/skill-creator/`, generate proposals from immediate child skills in an adjacent-skills directory:

```bash
python -m scripts.generate_tests <skill-path> --adjacent-skills <adjacent-skills-directory>
python -m scripts.generate_tests <skill-path> --promote-candidates <reviewed-yaml>
```

Proposals go to `tests/candidates/near_misses.yaml` and do not enter evals. Review each prompt, set `reviewed: true`, and add `should_trigger: true` or `false` before promotion. Accepted cases go to `tests/generated/near_misses.yaml`; conflicting labels block the write. Both modes refuse existing output unless `--replace` is supplied. Default scenario generation is unchanged. These are deterministic suggestions, not verified semantic negatives.

### Compare models against a baseline

From the repository root:

```bash
python bsc.py compare --candidate <candidate-results.json> --baseline <baseline-results.json>
python bsc.py eval <skill-path> --models haiku,sonnet --baseline <baseline-results.json>
```

The second command previews inputs without calls; add `--live` for evaluation. Live baselines and comparisons involving front-end reports require exact requested model identifiers; configured-default sentinels are not explicit identities. Aliases and full model IDs are not equated. Aliases can resolve differently over time, so comparisons warn and recommend pinned full model IDs. Documented Claude context suffixes such as `sonnet[1m]` and `opus[1m]` pass through unchanged. Legacy comparisons between two raw eval files retain cross-model warnings and allow unknown identities. Comparisons never pool models. Duplicate queries, malformed metrics, execution failures, contradictory expected labels, and zero-overlap baselines are rejected before live calls. New results record `trigger_threshold`: known mismatches block comparison, while missing legacy metadata produces a warning. A valid comparison may show a regression without being an execution error. The legacy JSON field `significance_claim` indicates sample sufficiency only (also exposed as `sample_sufficient`); no statistical significance test is performed.

`python bsc.py doctor` also checks required eval flags advertised by the installed Claude CLI without authentication or model calls. The [verified Claude Code contracts](skills/skill-creator/references/claude-code-contracts.md) distinguish documentation, installed-CLI, offline-test, and live evidence. Adjacent-skill discovery supports Claude's omitted-name and omitted-description defaults and includes `when_to_use` context.

### Planned Roadmap
- Model-assisted near-miss proposals with semantic review.
- Repeated trigger and behavioral benchmarking across all supported model tiers.


## Relationship to Anthropic's skill creator

Better Skill Creator builds on Anthropic's official `skill-creator`. It does not replace the foundation Anthropic provides; it adds engineering controls around it.

The default Anthropic `skill-creator` already has a meaningful development loop: decide what the skill should do, draft it, create test prompts, run with-skill evaluations, compare results, iterate, evaluate triggering, and optimize the description. Anthropic explicitly identifies the skill description as the primary triggering mechanism.

Better Skill Creator starts from that baseline and asks:

> **What happens when the skill-development process itself becomes the source of failure?**

### Default foundation vs. Better Skill Creator

| Default Anthropic `skill-creator` | Better Skill Creator |
|---|---|
| Drafts and iterates on skills | Adds structured design analysis before implementation |
| Creates realistic test prompts | Adds explicit scope, boundary, and authorization analysis |
| Compares with a no-skill baseline | Makes comparable evidence a quality gate |
| Evaluates task behavior | Adds independent and adversarial review |
| Evaluates triggering | Treats triggering as a model-dependent regression surface |
| Optimizes descriptions | Preserves model-behavior knowledge for future development |
| Provides evaluation scripts | Regression-tests the evaluation infrastructure itself |
| Packages skills | Adds deterministic completion and review gates |
| Provides model guidance | Adds development-practice guidance based on observed failures |
| Validates the skill | Validates the tooling, dependencies, and repository wiring |
| Iterates until satisfied | Uses explicit evidence and completion criteria |

The distinction is **not** that Anthropic has no testing, baselines, or trigger evaluation — it does. The distinction is that Better Skill Creator treats **the entire skill-development system as something that must itself be engineered and tested**.

### Known gaps in the default implementation

The upstream issue tracker documents concrete cases where the default measurement or development infrastructure produced incorrect, misleading, or unusable results:

- **Trigger measurement can be wrong.** Parallel workers sharing a project directory produced 0/12 triggers where serial runs got 10/12. Trigger detection bugs caused real triggers to be recorded as misses, corrupting the description optimizer's signal. One case reported 100% precision and 0% recall for every skill — failing silently.

- **Infrastructure failures can masquerade as results.** A crashed evaluation produced the same `False` value as a legitimate "skill did not trigger" result, meaning an infrastructure failure could count as a passing negative test and influence optimization.

- **The evaluator can contaminate the environment it measures.** Trigger evaluation wrote temporary synthetic command files into the live `.claude/commands/` directory; with parallel workers, concurrent sessions could see those temporary skills.

- **Cross-platform reliability has been a recurring problem.** Multiple independent reports documented the description-optimization loop failing on Windows due to CLI process resolution and use of `select.select()` on subprocess pipes.

- **Benchmark infrastructure has had silent failure modes.** A mismatch between the directory structure `SKILL.md` instructed agents to produce and the structure `aggregate_benchmark.py` expected caused silent benchmark failures.

### What Better Skill Creator does differently

Each failure mode led to a concrete control rather than documentation:

- **Design Analysis** — structured analysis of outcomes, interpretations, entailments, and authorization before selecting a skill structure, preventing transcription of the literal request.
- **Adaptive Lenses + Entailment Is Not Permission** — required, unauthorized, optional, and out-of-scope work treated as distinct states requiring explicit authorization.
- **Independent Multi-Agent Review + Adversarial Completion Gate** — fresh-context reviewers and a deterministic completion gate block packaging when review evidence is missing or findings remain unresolved.
- **Generated Test Discovery + Dependency Path Containment** — generated tests are discovered correctly; dependency paths cannot escape the skill directory.
- **Development Practices Guidance Pack** — recurring engineering failures from 84 real `fix:` commits converted into reusable guidance.
- **Dogfood `bsc.py` + CI Validator Gate** — important validation moved from a locally bypassable workflow into CI; the tool's own skill passes its own validator.

The pattern: **when the development system fails, Better Skill Creator turns that failure into a permanent control**.

### Why this comparison matters

Better Skill Creator treats reliability at multiple levels:

1. **Skill correctness** — does the skill accomplish the intended outcome?
2. **Trigger correctness** — does the model use it when appropriate?
3. **Scope correctness** — does it stay within its authorized boundaries?
4. **Review correctness** — has independent analysis challenged the author's assumptions?
5. **Evaluation correctness** — can the measurement system itself be trusted?
6. **Infrastructure correctness** — are tests, dependencies, and wiring actually correct?
7. **Completion correctness** — is there enough evidence to call it finished?

> **Anthropic's `skill-creator` provides the foundation for creating and evaluating skills; Better Skill Creator builds an engineering system around that foundation so the skills, the development process, and the tooling that measures them can all be designed, tested, reviewed, and improved with evidence.**

The meta-skill remains the center of the system. The validators, evaluators, reviewer agents, references, regression tests, and CI gates exist to make it more capable and more trustworthy.


## When to use it

Use it to create a new skill, improve or debug an existing one, compare versions, tune trigger behavior, or prepare a skill for distribution.

Do not use it to run an existing skill on an ordinary task. It is for building skills, not for doing the work they describe.


## Repository layout

Repo root also holds `bsc.py`, `LICENSE`, `CHANGELOG.md`, `SETUP.md`, `CLAUDE.md`, `.claude-plugin/`, and `examples/release-notes/`. The meta-skill itself lives here:

```
skills/skill-creator/
  SKILL.md       the agent-facing development process
  scripts/       validators, evals, trigger tests, packaging
  references/    specifications and model guidance
  agents/        independent reviewer roles
```


## Contributing

Good contributions start with a concrete failure and evidence for it, make a targeted change, add regression coverage, and show the change helps without breaking anything else.


## Release notes

Current version: v3.7.0. See [CHANGELOG.md](CHANGELOG.md) for details.


## License

See [LICENSE](LICENSE).
