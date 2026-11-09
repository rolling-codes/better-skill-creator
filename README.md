# Better Skill Creator

[![Release v3.7.3](https://img.shields.io/badge/release-v3.7.3-blue.svg)](https://github.com/rolling-codes/better-skill-creator/releases/tag/v3.7.3)
[![Claude Code Skill](https://img.shields.io/badge/Claude%20Code-Skill-blueviolet.svg)](https://claude.ai/code)
[![Python 3.12+](https://img.shields.io/badge/Python-3.12%2B-green.svg)](#requirements)
[![License](https://img.shields.io/badge/license-Apache%202.0-green.svg)](LICENSE)

Better Skill Creator helps you build Claude Code skills and measure two things: whether Claude loads them at the right time and how well they perform once loaded. It adds structured design analysis, independent review, and evidence gates to Anthropic's skill-building workflow.

## Contents by question

| Question | Where to read |
|---|---|
| What is this for, and how does it build a skill? | [How it works](#how-it-works) · [What makes it different](#what-makes-it-different) |
| How do I install it and run my first check? | [Quick start](#quick-start) · [Setup](SETUP.md) |
| Why can the same skill behave differently across Claude models? | [Model behavior and evidence](docs/MODEL_BEHAVIOR.md) |
| How should I write for a specific model or tier? | [Model guidance](skills/skill-creator/references/model-guidance.md) |
| Which Claude Code features does the evaluator rely on? | [Verified Claude Code contracts](skills/skill-creator/references/claude-code-contracts.md) |
| How do I design and validate a skill? | [Design a skill](docs/USER_GUIDE.md#design-and-build-a-skill) · [Validate it](docs/USER_GUIDE.md#validate-the-skill) |
| How do I test missed triggers, false triggers, and near misses? | [Trigger tests](docs/USER_GUIDE.md#test-whether-it-triggers) · [Near misses](docs/USER_GUIDE.md#review-neighboring-skill-near-misses) |
| How do I test what the skill actually does? | [Behavior tests](docs/USER_GUIDE.md#test-what-it-does-after-loading) · [Paired baseline grading](docs/USER_GUIDE.md#grade-paired-authoring-runs) |
| How do I compare results across versions or models and tune descriptions? | [Comparison and optimization](docs/USER_GUIDE.md#compare-results-and-improve-descriptions) |
| What evidence do I need before sharing a skill? | [Independent review](docs/USER_GUIDE.md#independent-review-and-completion) · [Packaging](docs/USER_GUIDE.md#package-and-share) |
| Where are the commands and troubleshooting steps? | [Command index](docs/USER_GUIDE.md#feature-and-tool-index) · [Troubleshooting](docs/USER_GUIDE.md#troubleshooting) |
| What shipped, what's planned, and why? | [Release notes](#release-notes) · [Roadmap](#roadmap) · [Decision record](decisions.md) |


## Quick start

1. Install the Claude Code plugin.

   ```bash
   claude plugin marketplace add rolling-codes/better-skill-creator
   claude plugin install skill-creator@skill-creator-local
   ```

2. Ask Claude to create or improve a skill. For the remaining commands, use a checkout of this repository and run from its root. You can install the optional pre-commit hook in that checkout.

   ```bash
   python bsc.py hooks install
   ```

3. Add trigger cases using the [positive](examples/release-notes/tests/should_trigger.yaml) and [negative](examples/release-notes/tests/should_not_trigger.yaml) examples. Validate your skill folder.

   ```bash
   python bsc.py check skills/my-skill
   ```

4. Preview the trigger evaluation and its model-call estimate.

   ```bash
   python bsc.py eval skills/my-skill
   ```

5. After checking your allowance and overage settings, run the live evaluation.

   ```bash
   python bsc.py eval skills/my-skill --live
   ```

## Requirements

- **Claude Code**, installed and authenticated
- **Python 3.12+** and **PyYAML** (`pip install pyyaml`) for the repository commands

## How it works

1. Define the skill's outcome, boundaries, and when Claude should load it.
2. Run the same task with the skill and with a comparable baseline. [Grade the saved outputs](docs/USER_GUIDE.md#grade-paired-authoring-runs) or grade behavior from a saved transcript.
3. Test positive and negative trigger cases separately. The description optimizer selects a candidate on validation cases and measures it on held-out cases.
4. For substantial changes, record independent review before packaging. Run `python bsc.py package skills/my-skill` to build a distributable skill.

## What makes it different

- [Design analysis](skills/skill-creator/references/design-analysis.md) separates what the task requires from what the skill is authorized to do.
- [Independent review](skills/skill-creator/references/independent-review.md) checks outcomes, scope, and structure. A completion reviewer challenges the evidence before the packaging gate accepts it.
- [Model-aware comparisons](docs/USER_GUIDE.md) keep trigger results separate by model and surface failed evaluations separately from missed triggers.

## Roadmap

- Model-assisted near-miss proposals with semantic review. Today, the generator proposes cases from neighboring skills and reviewers approve the labels.
- Repeated trigger and behavior benchmarks across supported model tiers. Today's scheduled canary covers a small trigger suite on Haiku and Sonnet.

See the [roadmap and documentation notes](docs/USER_GUIDE.md#limits-and-documentation-sources).

## Relationship to Anthropic's skill creator

This project builds on [Anthropic's skill-creator](https://github.com/anthropics/skills/tree/main/skills/skill-creator). Earlier releases used the name Skill Architect. See the [project history](CHANGELOG.md).

## When to use it

Use it to draft a skill, debug missed or unwanted triggers, compare versions, or prepare a skill for distribution.

## Repository layout

```
skills/skill-creator/
  SKILL.md       agent workflow
  scripts/       validation, evaluation, and packaging
  references/    schemas and guidance
  agents/        reviewer and evaluator roles
```

## Contributing

Start with a reproducible failure, make a focused change, and add regression coverage.

## Release notes

Current version: v3.7.3. This release hardens secret-file exclusions during packaging and documents the offline paired grading commands. The [release page](https://github.com/rolling-codes/better-skill-creator/releases/tag/v3.7.3) includes the standalone `.skill` and the Claude Code plugin ZIP. See [CHANGELOG.md](CHANGELOG.md) for release history.

## License

See [LICENSE](LICENSE).
