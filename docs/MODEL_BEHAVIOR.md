# How we assess model behavior

The same skill description can produce different decisions about when to load the skill. Once loaded, the same instructions can also lead to different tool calls, outputs, or levels of verification. Better Skill Creator uses three kinds of evidence to decide what to test and how to interpret the results.

## What Anthropic has documented

Model behavior can change within a family. Anthropic reports that Sonnet 5 reaches for tools and self-verifies more readily than Sonnet 4.6. It also reports that Sonnet 5 uses tools more often at higher effort in agentic search and coding. The same effort label can correspond to different amounts of thinking across models. These findings give authors concrete reasons to rerun the same skill cases when changing model versions or settings. [Prompting Claude Sonnet 5](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-sonnet-5#tool-use-triggering) · [Anthropic's cross-model effort guidance](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-fable-5-2#calibrate-effort)

### Fable 5.2

Anthropic's Fable 5.2 guidance reports several behaviors that differ from Fable 5.1 and Opus 5.5 on the same instructions. Each one can change what a loaded skill does.

| Behavior Anthropic reports | Why it matters for a skill |
|---|---|
| It follows style, approval, and caution rules closely. In one setup only Fable 5.2 held back routine work that Fable 5.1 and Opus 5.5 still did. | A caution written for an earlier model can now block routine steps. Rerun behavior cases after an upgrade. |
| Instructions to think less do not reduce thinking at `medium` effort and above. Fable 5.1 usually obeyed them. | Lower the effort setting. Record effort with each result. |
| On long multistep tasks it sometimes ends a turn early, more often at `low` and `medium` effort. | A behavior case can fail on completeness at one effort level and pass at another. |
| At `xhigh` and `max` effort it uses subagents to review its own work. Fable 5.1 did not on the same tasks. | Cost and tool-call counts can change with no change to the skill. |
| The same effort label corresponds to a different amount of thinking on each model. The default is `high` on Fable 5.2 and `medium` on Opus 5.5. | An unset effort is a different setting on each model. Set it explicitly when comparing. |

These are Anthropic's results on its own test setups. The percentages in the guide describe those setups. [Prompting Claude Fable 5.2](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-fable-5-2) · [What's new in Claude Fable 5.2](https://platform.claude.com/docs/en/models/fable-5-2/whats-new-fable-5-2) · [Migration guide](https://platform.claude.com/docs/en/models/fable-5-2/migration-guide) · [Skill-writing matrix](../skills/skill-creator/references/model-guidance.md#fable-52-behavior-matrix)

## What published research contributes

Liu et al. found that the position of relevant information affected performance on the long-context retrieval tasks they tested. That motivates a design choice in this project: keep essential instructions in the main skill and link to details the agent can read when needed. Schulhoff et al.'s prompting survey provides a catalog of techniques to try. For a specific skill, treat these patterns as hypotheses and evaluate them on the target model. [Lost in the Middle](https://arxiv.org/abs/2307.03172) · [The Prompt Report](https://arxiv.org/abs/2406.06608)

## What this project observes

- A project issue recorded that review-phrased requests could miss the skill. The description covered writing, evaluation, comparison, and tuning, but omitted independent review. That report motivates testing realistic positive requests alongside plausible near misses. [Issue #60](https://github.com/rolling-codes/better-skill-creator/issues/60)
- The scheduled Haiku and Sonnet canary uses the same four trigger cases and a discovery control for each model. Its artifacts report outcomes per model or explain why a run was skipped. For example, the linked scheduled run published missing-credential statuses for both models. The canary measures a small set of selection cases when credentials are available. [Canary design](../decisions.md#6-use-a-small-bounded-canary) · [Scheduled run and artifacts](https://github.com/rolling-codes/better-skill-creator/actions/runs/42641072399)

## How to check your own skill

Use the same cases and trigger threshold across target models, and record the full model ID and relevant runtime settings where available. Review each model's results separately. For behavior, hold the task, fixtures, and model constant while comparing the skill with a baseline. Repeat runs when deciding whether an observed difference is consistent. Use the tier-specific writing guidance as a starting point for what to test. [Model guidance](../skills/skill-creator/references/model-guidance.md#writing-for-a-lower-tier-target) · [Compare compatible runs](USER_GUIDE.md#compare-compatible-runs) · [Grade paired authoring runs](USER_GUIDE.md#grade-paired-authoring-runs)
