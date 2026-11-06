# Better Skill Creator

[![Release v3.7.3](https://img.shields.io/badge/release-v3.7.3-blue.svg)](https://github.com/rolling-codes/better-skill-creator/releases/tag/v3.7.3)
[![Claude Code Skill](https://img.shields.io/badge/Claude%20Code-Skill-blueviolet.svg)](https://claude.ai/code)
[![Python 3.12+](https://img.shields.io/badge/Python-3.12%2B-green.svg)](#requirements)
[![License](https://img.shields.io/badge/license-Apache%202.0-green.svg)](LICENSE)

Better Skill Creator is an engineering system for helping humans and AI agents create, evaluate, and improve reliable agent skills.

### What's new in v3.7.3

A skill is a folder of instructions. The model decides when to load it and how to follow it. Packaging copies that folder into a file you can share. Grading runs the same task with the skill and with a baseline, then checks the saved files. v3.7.3 clears two places where that work stalled. The [v3.7.3 release notes](https://github.com/rolling-codes/better-skill-creator/releases/tag/v3.7.3) explain the migration in full. [v3.7.2](https://github.com/rolling-codes/better-skill-creator/releases/tag/v3.7.2) is the previous release.

**Packages skip secret names that only look different.** The packager already skipped `.env` and private-key names. It compared the name exactly as written, so `.env ` with a trailing space, `notes.pem.`, `.id_rsa`, or `İD_RSA` still went into the zip. On Windows the system ignores trailing dots and spaces, so those names can be the real secret. The check now folds the name first, then applies the same skip list. Ordinary names such as `guide.md` are unchanged. Rename a file only if you meant to ship it and its folded name is now a secret, `.git`, or `dist`.

**The baseline grading command is written down.** v3.7.2 added `authoring_eval` to grade saved outputs locally. The guides people follow still named trigger tests and trigger-result comparison, so a plan that said "run `authoring_eval.py`" had no command to copy. From `skills/skill-creator/`, `python -m scripts.authoring_eval` checks the plan (`preflight`), reserves a run (`prepare`), grades reviewed file checks (`check`), and writes `grading.json` (`merge`). Write `eval_metadata.json` yourself before `check`. Keep a reviewer's grade in `reference-grades.json`, because `merge` replaces `grading.json`. [Command guide](skills/skill-creator/references/schemas.md#paired-authoring-eval-preflight-and-offline-grading).

Upload these as two different files:

- `skill-creator-3.7.3.skill` is the skill.
- `better-skill-creator-plugin-3.7.3.zip` is the Claude Code plugin.

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

A skill is a folder of instructions. The model decides whether your request matches that folder, how much of it to read, and how to follow it. Better Skill Creator is how you build the folder and check the build. It is not how you perform the task the skill describes.

An earlier version of this project was called Skill Architect. The agent building the skill did the work. Its instructions told it to interview you, then spawn other agents for the checks: one run with the skill and one without, in the same turn; a grader agent that scored the saved outputs against `agents/grader.md`; an analyst agent for patterns the totals hide; and, when you asked whether a new version was actually better, a blind comparator that was not told which output was which. Research that needed outside sources was also spawned as parallel agents. The six checks in that description were the jobs those agents were given, not a form for a person to fill in.

Those jobs are still how a skill gets built. `SKILL.md` still tells the agent to spawn the with-skill run and the baseline together, to grade with the grader agent, and to send independent reviewers at the result. Scripts now do the parts that should not depend on a model remembering to be careful: structure checks, reviewed file assertions, trigger counts, and the gate that keeps a package from shipping while a high finding is open.

| What the agents were told to find | How the agents do it now |
|---|---|
| Did this skill cause the result, or would the model have done it anyway? | The agent spawns a with-skill run and a baseline run in the same turn. The iron law in `SKILL.md` is still: do not call a skill better without that baseline. |
| Can someone tell what it does, when it should load, and what it leaves alone? | The agent writes that into the description. `python bsc.py check` then looks for a trigger and a boundary. A description that only lists features can load for the wrong requests. |
| Is the hard rule written as a reason, and are the excuses for skipping it named? | The skill instructions still carry the iron law and a red-flag table. The agent is told to read the excuse on the left and do the action on the right. |
| What is the most likely way this skill will misfire? | The agent sends reviewers that read the skill from a fresh context. Packaging waits while a high finding is still open. |
| Could a normal request match this skill and a different one? | The agent can ask for near-miss prompts from neighboring skill descriptions. Those prompts stay out of the measured tests until you label them. |
| Does it still behave when the prompt changes, and on more than one model? | The agent runs should-trigger and should-not-trigger prompts, including on more than one model. Description optimization holds some cases back, so the rewrite is not graded only on the examples it just saw. |

### What the agent does

You say what you want. The agent runs this loop and tells you where it is.

1. **Capture the job.** The agent asks what the skill should do, when it should load, and what it must not do, then asks one level deeper about edge cases. [Design analysis](skills/skill-creator/references/design-analysis.md) is that interview. Research that needs outside sources is spawned as other agents when the host allows it.
2. **Write the folder.** `SKILL.md` is the part the model reads first. Longer guides, scripts, and examples stay in files that `SKILL.md` points to. A file that is never mentioned is not loaded. That is why the reference list at the bottom of `SKILL.md` has to name the tools the agent is expected to use.
3. **Check the folder before spending a model call.** The agent runs `python bsc.py check skills/my-skill` for frontmatter, links, and structure.
4. **Spawn both runs in one turn.** One agent does the task with the skill. One does the same task without it, or against the previous version. A result that looks good on its own does not show that the skill caused it.
5. **Grade with an agent, and with a script where the check is mechanical.** The grader agent reads `agents/grader.md` and writes `grading.json`. From `skills/skill-creator/`, `python -m scripts.authoring_eval` grades the file checks already reviewed and leaves the rest for that grader. Keep the grader's notes in `reference-grades.json`, because merge replaces `grading.json`. A saved transcript can also be graded with `python -m scripts.skill_test`. Results are `PASS`, `FAIL`, or `UNDETERMINED`. An incomplete transcript cannot prove that a forbidden action never happened.
6. **See whether it loads.** The agent runs `python bsc.py eval` for how often the description is selected. That is a different question from whether the task output was right. A skill can do the work well and still be a poor skill if the model rarely loads it.
7. **Have another agent look at both sides.** The eval viewer shows the with-skill output and the baseline side by side. The comparator agent reads the outputs without being told which side is which. The analyzer agent looks for checks that pass on both sides and for runs that swing wildly.
8. **Rewrite, then pack.** Description optimization proposes a new triggering description and scores it on held-out prompts. The agent runs `python bsc.py package` to build the `.skill` file. Packaging skips secret filenames, including names that only look different from `.env` or a private key.

A small skill can stop after a check and a couple of paired tasks. A skill that edits files, runs commands, or talks to another system needs the baseline, the trigger tests, and the independent review before you call it finished.


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

```
skills/skill-creator/
  SKILL.md       the agent-facing development process
  scripts/       validators, evals, trigger tests, packaging
  references/    specifications and model guidance
  agents/        independent reviewer roles
```


## Contributing

Good contributions start with a concrete failure and evidence for it, make a targeted change, add regression coverage, and show the change helps without breaking anything else.


## Documentation

- [User guide](docs/USER_GUIDE.md): complete setup, features, workflows, results, troubleshooting, and upgrades.
- [What's new](docs/WHATS_NEW.md): the v3.7.0 feature overview and their practical effects.
- [Decisions](decisions.md): choices, alternatives, tradeoffs, and supporting evidence.
- [Setup](SETUP.md): concise installation and verification.

## Release notes

Current version: v3.7.3. See the root [CHANGELOG.md](CHANGELOG.md) for release history and [GitHub Releases](https://github.com/rolling-codes/better-skill-creator/releases) for published assets. The release uploads the skill and the plugin as different files. Older component summaries remain historical references.


## License

See [LICENSE](LICENSE).
