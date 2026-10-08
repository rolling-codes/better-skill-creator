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
   ```
   claude plugin marketplace add rolling-codes/better-skill-creator
   claude plugin install skill-creator@skill-creator-local
   ```

2. **Create or improve a skill** — ask your agent. The skill-creator meta-skill figures out which stage the work is in and moves it forward.

3. **Add trigger tests:** create `skills/my-skill/tests/should_trigger.yaml` with positive cases and `skills/my-skill/tests/should_not_trigger.yaml` with negative cases. Each file must contain a YAML list with `prompt` and `expected` fields (`true` for positive cases, `false` for negative cases). See the [positive](examples/release-notes/tests/should_trigger.yaml) and [negative](examples/release-notes/tests/should_not_trigger.yaml) examples and adapt the prompts to your skill.

4. **Validate:**
   ```
   python bsc.py check skills/my-skill
   ```

5. **Preview evaluation** (no model calls):
   ```
   python bsc.py eval skills/my-skill
   ```

   Check the preview's call estimate, your account allowance, and paid-overage settings before running live evaluation:
   ```
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

Better Skill Creator builds on Anthropic's official skill-creator, which already covers drafting, test prompts, baseline comparison, trigger evaluation, and description optimization. This project adds explicit quality gates, reusable model behavior baselines, independent multi-agent review, and scope and authorization analysis.


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

See [LICENSE](skills/skill-creator/LICENSE.txt).
