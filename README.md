# Better Skill Creator

[![Release v3.4.0](https://img.shields.io/badge/release-v3.4.0-blue.svg)](https://github.com/rolling-codes/better-skill-creator/releases/tag/v3.4.0)
[![Claude Code Skill](https://img.shields.io/badge/Claude%20Code-Skill-blueviolet.svg)](https://claude.ai/code)
[![Python 3.12+](https://img.shields.io/badge/Python-3.12%2B-green.svg)](#requirements)
[![License](https://img.shields.io/badge/license-Apache%202.0-green.svg)](skills/skill-creator/LICENSE.txt)

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

3. **Add trigger tests:** create `skills/my-skill/tests/should_trigger.yaml` with positive cases and `skills/my-skill/tests/should_not_trigger.yaml` with negative cases. Each file must contain a YAML list with `prompt` and `expected` fields (`true` for positive cases, `false` for negative cases). See the [positive](examples/release-notes/tests/should_trigger.yaml) and [negative](examples/release-notes/tests/should_not_trigger.yaml) examples and adapt the prompts to your skill.

4. **Validate:**

   ```bash
   python bsc.py check skills/my-skill
   ```

5. **Preview evaluation** (no model calls):

   ```bash
   python bsc.py eval skills/my-skill
   ```

   Check the preview's call estimate, your account allowance, and paid-overage settings before running live evaluation:

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

## Relationship to Anthropic's `skill-creator`

Better Skill Creator is an extension of Anthropic's official `skill-creator`. It does not replace the foundation Anthropic provides; it builds additional engineering controls around it.

The default Anthropic `skill-creator` already has a meaningful development loop: decide what the skill should do, draft it, create test prompts, run with-skill evaluations, compare results quantitatively and qualitatively, iterate, expand the test set, evaluate triggering, and optimize the skill description. Anthropic explicitly identifies the skill description as the primary triggering mechanism and notes that Claude currently tends to undertrigger skills.

Better Skill Creator starts from that baseline and asks a further question:

> **What happens when the skill-development process itself becomes the source of failure?**

That is where the project's additional engineering work comes in.

### Default foundation vs. Better Skill Creator

| Default Anthropic `skill-creator` | Better Skill Creator |
|---|---|
| Drafts and iterates on skills | Adds structured design analysis before implementation |
| Creates realistic test prompts | Adds explicit scope, boundary, and authorization analysis |
| Compares with a no-skill baseline | Makes comparable evidence a quality gate |
| Evaluates task behavior | Adds independent and adversarial review |
| Evaluates triggering | Treats triggering as a model-dependent regression surface |
| Optimizes descriptions | Preserves useful model-behavior knowledge for future development |
| Provides evaluation scripts | Regression-tests the evaluation infrastructure itself |
| Packages skills | Adds deterministic completion and review gates |
| Provides model guidance | Adds development-practice guidance based on observed engineering failures |
| Validates the skill | Validates the tooling, generated resources, dependencies, and repository wiring around the skill |
| Iterates until satisfied | Uses explicit evidence and completion criteria to determine when substantial work is ready |

The important distinction is **not** that Anthropic has no testing, baselines, or trigger evaluation. It does.

The distinction is that Better Skill Creator treats **the entire skill-development system as something that must itself be engineered and tested**.

## Evidence that the default implementation has engineering gaps

The strongest evidence comes from Anthropic's own issue tracker.

These are not hypothetical failure modes. They are reports against the default `skill-creator` implementation documenting cases where its measurement or development infrastructure produced incorrect, misleading, or unusable results.

### Trigger measurement can be wrong

Issue #1352 documented that the default parallel trigger evaluator could produce near-zero trigger rates because workers shared the same project command directory. The same evaluation run produced **0/12 triggered in parallel versus 10/12 correct serially**; the issue notes that the default worker count was 10 and that the resulting signal could silently corrupt `run_loop`'s optimization.

Issue #1552 documented two bugs where real skill triggers were recorded as misses. The reported result was that `run_loop.py` could then optimize a description against a **false signal**, even though the skill was actually triggering.

Issue #1721 went further: trigger detection could report **100% precision and 0% recall for every skill**, fail silently, and then allow the optimizer to improve descriptions against the incorrect assumption that positive queries were not triggering.

### Infrastructure failures can masquerade as evaluation results

Issue #1478 documented that a crashed or failed evaluation was represented as the same `False` value as a legitimate "skill did not trigger" result. For negative queries, that meant an infrastructure failure could actually count as a **passing evaluation result** and influence description optimization.

That is a particularly important distinction for Better Skill Creator:

> **A failed measurement is not evidence of a failed skill.**

The measurement system has to distinguish those states.

### The evaluator can interfere with the environment it is measuring

Issue #1260 documented that trigger evaluation wrote temporary synthetic command files into the user's live `.claude/commands/` directory. With parallel workers, concurrent Claude Code sessions could see those temporary skills.

Issue #1552 identified the same shared-project-root problem as part of its trigger-detection failure and proposed isolated temporary project roots as the fix.

The evaluator therefore was not merely measuring a skill in isolation; under some conditions, **the act of measuring it changed the environment in which the measurement occurred**.

### Cross-platform reliability has also been a recurring problem

Issue #1221 reported that the description-optimization loop failed on Windows because of CLI process resolution and use of `select.select()` on subprocess pipes.

Issue #1715 independently reproduced Windows problems and referenced the same trigger-evaluation defects in a separate environment.

Issue #1827, opened later, again reported Windows failures in the description optimizer, along with additional cases where running the optimizer outside the repository or with the skill installed could produce invalid measurements.

### The benchmark infrastructure has had silent failure modes too

Issue #1383 reported multiple problems in the benchmark/evaluation system, including a mismatch between the directory structure the `SKILL.md` instructed agents to produce and the structure `aggregate_benchmark.py` actually expected. The issue explicitly characterized these as **silent benchmark failures**.

That matters because a sophisticated evaluation framework is only as trustworthy as the machinery that consumes its results.

## What Better Skill Creator does differently

The project's PR history shows that these concerns led to concrete engineering controls rather than simply documentation.

**PR #18 — Design Analysis** introduced a structured analysis of outcomes, interpretations, modes, entailments, failure points, validation, assumptions, and open questions before selecting a skill structure. The purpose was to prevent the creator from simply transcribing the user's literal request into instructions.

**PR #20 — Adaptive Lenses + Entailment Is Not Permission** made that analysis adaptive instead of mechanical and introduced explicit authorization boundaries. Required work, unauthorized work, optional work, and out-of-scope work are treated as different states.

**PR #21 — Independent Multi-Agent Review + Adversarial Completion Gate** added fresh-context reviewers and a deterministic completion gate for substantial skills. Packaging can be blocked when required review evidence is missing or material findings remain unresolved.

**PR #44 — Generated Test Discovery + Dependency Path Containment** addressed failures in Better Skill Creator's own validation infrastructure: generated tests were not being discovered, and dependency paths could escape the skill directory. Both behaviors were fixed with regression coverage.

**PR #48 — Development Practices Guidance Pack** converted recurring engineering failures from 84 real `fix:` commits into reusable guidance, so future skills do not have to repeatedly rediscover the same classes of mistakes.

**PR #50 — Dogfood `bsc.py` + CI Validator Gate** caught a case where Better Skill Creator's own documented validation command rejected its own legitimate Claude Code skill configuration. It also moved important validation from a locally bypassable workflow into CI and added regression coverage.

The pattern is deliberate:

> **When the development system fails, Better Skill Creator tries to turn that failure into a permanent control.**

That may mean a validator, regression test, review gate, security boundary, reusable reference, or CI check.

## Why this comparison matters

Anthropic's default `skill-creator` demonstrates that skill development can and should be evaluated empirically. Better Skill Creator agrees with that premise and extends it.

The upstream issue history demonstrates why the extension matters: **evaluation itself can be wrong, incomplete, platform-dependent, environmentally contaminating, or silently misleading.**

Better Skill Creator therefore treats reliability at multiple levels:

1. **Skill correctness** — does the skill accomplish the intended outcome?
2. **Trigger correctness** — does the model use it when appropriate?
3. **Scope correctness** — does it do what it should without silently expanding the task?
4. **Authorization correctness** — does it distinguish what is implied from what is actually permitted?
5. **Review correctness** — has independent analysis challenged the author's assumptions?
6. **Evaluation correctness** — can the measurement system itself be trusted?
7. **Infrastructure correctness** — are tests, dependencies, references, generated resources, and packaging actually wired correctly?
8. **Completion correctness** — is there enough evidence to call the skill finished?

This is also why the project's own model benchmark should remain a separate piece of evidence.

**The model baseline is not yet being presented as proof that Better Skill Creator produces better model outcomes.** That baseline still needs to be refreshed across the current models.

What can already be demonstrated is the engineering difference: the default Anthropic workflow provides the foundation for skill creation and evaluation, while Better Skill Creator adds a set of controls specifically designed around the kinds of failures that the upstream implementation and its issue history have exposed.

### The relationship in one sentence

> **Anthropic's `skill-creator` provides the foundation for creating and evaluating skills; Better Skill Creator builds an engineering system around that foundation so the skills, the development process, and the tooling that measures them can all be designed, tested, reviewed, and improved with evidence.**

The meta-skill remains the center of the system. The validators, evaluators, reviewer agents, references, regression tests, and CI gates exist to make that meta-skill more capable and more trustworthy.

The goal is not simply to generate better `SKILL.md` files.

It is to help **humans and AI agents design, build, evaluate, debug, review, improve, and maintain skills with evidence**.
