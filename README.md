# Better Skill Creator

[![Release v3.4.0](https://img.shields.io/badge/release-v3.4.0-blue.svg)](https://github.com/rolling-codes/better-skill-creator/releases/tag/v3.4.0)
[![Claude Code Skill](https://img.shields.io/badge/Claude%20Code-Skill-blueviolet.svg)](https://claude.ai/code)
[![Python 3.12+](https://img.shields.io/badge/Python-3.12%2B-green.svg)](#requirements)
[![License](https://img.shields.io/badge/license-Apache%202.0-green.svg)](LICENSE.txt)

Better Skill Creator is an engineering system for helping humans and AI agents create, evaluate, and improve reliable agent skills.

A skill is not a program that runs the same way every time. A model has to decide whether the skill applies, how much of it to load, and how to follow it. A well-written skill can still fail to trigger, trigger when it shouldn't, or behave differently on another model. Better Skill Creator treats those failures as things to measure, not things to hope away.

**The core rule:** do not call a skill better without evidence from a comparable baseline.


## Quick start

1. **Install:**

   ```bash
   claude plugin marketplace add rolling-codes/better-skill-creator
   claude plugin install skill-creator@skill-creator-local
   ```

2. **Create or improve a skill** — ask your agent. The skill-creator meta-skill figures out which stage the work is in and moves it forward.

3. **Add trigger tests:** create `skills/my-skill/tests/should_trigger.yaml` with positive cases and `skills/my-skill/tests/should_not_trigger.yaml` with negative cases. Each file is a YAML list with `prompt` and `expected` fields (`true` for positive, `false` for negative). See the [positive](examples/release-notes/tests/should_trigger.yaml) and [negative](examples/release-notes/tests/should_not_trigger.yaml) examples.

4. **Validate:**

   ```bash
   python bsc.py check skills/my-skill
   ```

5. **Preview evaluation** (no model calls):

   ```bash
   python bsc.py eval skills/my-skill
   ```

   Check the call estimate, your account allowance, and paid-overage settings before running live:

   ```bash
   python bsc.py eval skills/my-skill --live
   ```


## Requirements

- **Python 3.12+**
- **PyYAML** — `pip install pyyaml`
- **Claude Code** — installed and authenticated


## How it works

Every skill moves through the same stages, scaled to how risky the skill is.

1. **Understand.** Pin down the outcome the user actually needs.
2. **Design.** Decide when the skill should trigger, when it should not, and what it is allowed to do.
3. **Build.** Write SKILL.md and any references or scripts.
4. **Validate.** Check frontmatter, file structure, and references for broken wiring.
5. **Evaluate.** Run realistic tasks with the skill and with a baseline. For a new skill the baseline is no skill. For an update it is the previous version.
6. **Test triggering.** Run should-trigger and should-not-trigger prompts several times to get a trigger rate, not a single yes or no.
7. **Review.** Independent reviewers look for failures the author missed.
8. **Improve.** Revise from the evidence, then measure again.


## What makes it different

**Triggering is tested separately from quality.** A skill can work perfectly once loaded and still be a poor skill if the model rarely loads it. Behavior evals and trigger evals answer different questions, so they are run separately.

**Model behavior is treated as data.** Triggering depends on the description, the other installed skills, the task, and the model. A description that triggers reliably on one model can undertrigger on another. The project keeps records of how supported models tend to route skills, so new work starts from known behavior instead of rediscovering it.

<!-- TODO: add one real example of a description that behaved differently across two models -->

**Independent review.** For substantial skills, separate reviewers check four things from fresh context: whether the skill achieves its outcome, whether it can be misapplied outside its scope, whether its structure is sound, and whether there is real evidence it is finished.

**Entailment is not permission.** An instruction can imply an action is needed without authorizing the agent to take it. Each action a skill might take is classified as required and authorized, required but needing authorization, optional, or out of scope. This matters most for skills that edit files, run commands, or touch external systems.

**Context is a budget.** Skills compete for the model's context. The design asks what belongs in frontmatter, what belongs in SKILL.md, and what should load only when needed. The goal is enough context to do the task correctly, and no more.


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


## Release notes

Current version: v3.4.0. See [CHANGELOG.md](CHANGELOG.md) for details.


## License

See [LICENSE](LICENSE.txt).
