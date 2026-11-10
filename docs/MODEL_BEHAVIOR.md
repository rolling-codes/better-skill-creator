# How we assess model behavior

The same skill description can produce different decisions about when to load the skill. Once loaded, the same instructions can also lead to different tool calls, outputs, or levels of verification. Better Skill Creator uses three kinds of evidence to decide what to test and how to interpret the results.

## The current tiers at a glance

Anthropic's model overview lists four current tiers. All four have a 1M-token context window and 128K maximum synchronous output. The model ID, default effort, and thinking mode below come from that page. [Models overview](https://platform.claude.com/docs/en/about-claude/models/overview)

| Tier | Model ID | Anthropic's positioning | Default effort | Thinking |
|---|---|---|---|---|
| Fable | `claude-fable-5-2` | Demanding reasoning and long-horizon agentic work | `high` | Adaptive, always on |
| Opus | `claude-opus-5-5` | Long-running agentic coding and knowledge work | `medium` | Adaptive, always on |
| Sonnet | `claude-sonnet-5-5` | The best combination of speed and intelligence | `high` | Adaptive, not always on |
| Haiku | `claude-haiku-5-5` | High-volume, latency-sensitive tasks such as classification, extraction, and routing | `medium` | Adaptive, not always on |

Anthropic says to start with Opus 5.5 for most workloads and to move to Fable 5.2 when evals on Opus 5.5 at higher effort still fall short. The page gives no further guidance on choosing Sonnet or Haiku. The effort default differs by tier, so an unset effort is a different setting on each model.

## What Anthropic has documented

Model behavior can change within a family. Anthropic reports that Sonnet 5 reaches for tools and self-verifies more readily than Sonnet 4.6, and that Opus 5.5 and Haiku 5.5 each have documented behaviors that differ from earlier models in the same family. It also reports that Sonnet 5 uses tools more often at higher effort in agentic search and coding. The same effort label can correspond to different amounts of thinking across models. These findings give authors concrete reasons to rerun the same skill cases when changing model versions or settings. [Prompting Claude Sonnet 5](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-sonnet-5#tool-use-triggering) · [Anthropic's cross-model effort guidance](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-fable-5-2#calibrate-effort)

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

### Opus 5.5

Anthropic's Opus 5.5 guide compares it with Opus 5. Each behavior can change what a loaded skill does. [Prompting Claude Opus 5.5](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-opus-5-5)

| Behavior Anthropic reports | Why it matters for a skill |
|---|---|
| The default effort is `medium`, where Opus 5 defaulted to `high`. At `medium` it matched or beat Opus 5 at `high` on Anthropic's agentic coding tasks, in fewer steps and tokens. | A skill tuned on Opus 5 runs at a different effort when nothing is set. Set effort explicitly in every comparison. |
| At a given effort level it thinks more per turn than Opus 5, especially at `xhigh` and `max`. | Cost and latency can change with no change to the skill. |
| `thinking: {"type": "disabled"}` returns a 400, where Opus 5 accepted it at `high` or below. | A harness that disables thinking fails outright. Start at `low` effort and measure. |
| A text-only turn can end an unattended loop early. Anthropic suggests a task checklist and a continuation message, stopping after two or three. | A behavior case can fail on completeness in an unattended run and pass with a person watching. |
| A reminder after about five quiet tool-calling steps roughly halved the share of tasks with a long silent stretch in Anthropic's agentic coding testing. | Skills that rely on progress messages may need that reminder. |
| An instruction to explore broadly before acting let it complete noticeably more multiapp tasks, with slightly more tool calls. | Exploration steps in a skill can trade tool calls for correctness. |
| Generic style instructions mostly swap one default for another. Naming specific patterns to avoid works better. | Test style rules against the target model. |

### Sonnet 5.5

Anthropic's Sonnet 5.5 guide says existing Sonnet 5 prompts should mostly work unchanged and recommends an Opus model for the hardest long-horizon work. The behaviors below are the ones that can change what a loaded skill does. [Prompting Claude Sonnet 5.5](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-sonnet-5-5)

| Behavior Anthropic reports | Why it matters for a skill |
|---|---|
| Effort levels are recalibrated. The same level does not give the same amount of thinking as on Sonnet 5. The API default is `high`. Anthropic suggests `medium` for well-specified agentic coding and `high` for harder or longer tasks. | Rerun your cases at each effort level instead of carrying over a Sonnet 5 setting. |
| `thinking: {"type": "between_tools"}` is the lowest thinking setting. It is accepted at `high` effort or below and returns a 400 at `xhigh` or `max`. It also returns a 400 if sent with `display`, `budget_tokens`, or `block_binding`. | A harness that sets thinking or effort per request can fail outright. Record the thinking mode with each result. |
| Telling the model to think less does not reliably reduce thinking. With `between_tools`, instructions not to think make internal XML tags more likely in visible output. | Remove "do not think" lines from a skill instead of relying on them. |
| At `low` and `medium` on agentic coding, it sometimes pauses to confirm a plan or asks a question it could answer itself. At `low` it can skip verifying a change. | A behavior case can fail on completeness or verification at one effort level and pass at another. |
| It adds tests, docs, and small supporting files at every effort level, more at higher effort. At `xhigh` and `max` it may start its own review rounds, sometimes with subagents. | Scope limits in a skill matter more on this tier. Cost and tool-call counts can change with effort alone. |
| Anthropic's testing reports that a stop-and-report prompt at `max` effort stopped reviewer subagents and cut session cost by about a third, with no quality change. | This is a vendor-reported result with no linked method. Test it on your own cases before relying on it. |
| On multistep JSON tasks it often answers without thinking, especially at `low` and `medium`. Adding "Think the problem through before you answer." to the end of the system prompt brought accuracy at `high` close to `xhigh`. | Structured-output skills need testing with and without that line. `between_tools` makes the line ineffective. |
| It sometimes answers from training knowledge when a search would catch changed details. Prompt language such as "minimize tool calls" can make this worse. | A skill that discourages tool use can reduce correctness on time-sensitive questions. |
| A genuine mid-task user message can be mistaken for prompt injection when it lands right after a tool result or inside a `tool_result` block. | Deliver user text as its own text block, and keep harness notices separate. |
| It generally checks its work before reporting a change done, but at `low` it sometimes reports done without running a check that exercises the change. Anthropic supplies a verification paragraph that makes skipped checks rare at `low` for a slightly higher cost per task. | Skills for coding agents may need an explicit verify step. |
| It sometimes calls a tool with different letter case or a slightly different parameter name. | A strict tool-name match in a harness can turn a recoverable call into a failure. |
| Progress notes can come back as `thinking` blocks with empty text at the default display setting, so a client that renders only `text` can look silent. | A skill that relies on progress messages needs a harness that shows them. |

These are Anthropic's results on its own test setups. The page links no study, paper, or system card for its "in testing" claims, and it quotes no accuracy percentages for the JSON or chart tasks. It also says there are five breaking API changes when migrating from Sonnet 5 and links the migration guide without listing them here. [What's new](https://platform.claude.com/docs/en/models/sonnet-5-5/whats-new-sonnet-5-5) · [Migration guide](https://platform.claude.com/docs/en/models/sonnet-5-5/migration-guide)

### Sonnet 5

Anthropic's Sonnet 5 guide compares Sonnet 5 mostly with Sonnet 4.6 and predates the Sonnet 5.5 guide above. [Prompting Claude Sonnet 5](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-sonnet-5)

| Behavior Anthropic reports | Why it matters for a skill |
|---|---|
| It is more agentic than Sonnet 4.6 by default and reaches for tools and runs self-verification loops more readily. With thinking disabled it is less likely to use tools. | Tool-call counts and verification can rise with no skill change, and fall when thinking is off. |
| It respects effort levels strictly, especially at `low` and `medium`, and scopes work to what was asked. Anthropic notes some risk of under-thinking at `low`. | A skill that needs thoroughness may need a higher effort setting. |
| It is literal and explicit, particularly at lower effort. It does not silently generalize an instruction to other items. | State scope explicitly in the skill text. |
| Adaptive thinking is on by default, where Sonnet 4.6 ran without thinking. Manual `budget_tokens`, `temperature`, `top_p`, and `top_k` return a 400. | Requests copied from 4.6-era harnesses can fail. |
| A new tokenizer produces roughly 30 percent more tokens for the same text, so `max_tokens` tuned for 4.6 may truncate output. Anthropic says the exact increase depends on content. | Length limits and cost estimates need recalibrating. |
| Telling it to report only high-severity issues can lower measured recall while precision rises. Anthropic calls this a harness effect, not a capability regression. | A review skill's wording can change its measured recall. |

### Haiku 5.5

Anthropic's Haiku 5.5 guide covers behaviors that matter for high-volume skills. [Prompting Claude Haiku 5.5](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-haiku-5-5)

| Behavior Anthropic reports | Why it matters for a skill |
|---|---|
| Thinking is on by default. `thinking: {"type": "disabled"}` works at `low`, `medium`, and `high` but returns a 400 at `xhigh` and `max`. | Effort and thinking settings interact. Record both. |
| At `low` effort, a long coding-agent prompt can make it stop early. Moving from `low` to `medium` roughly halved early stopping and more than doubled output tokens. | A behavior case can pass or fail on completeness because of effort alone. |
| At `low` and `medium` it sometimes reports changes as done without running a check. A verification paragraph raised check frequency, at more tokens. | Skills for coding agents may need an explicit verify step on this tier. |
| With thinking off and a JSON output format, it may skip a needed tool call. A system-prompt line about calling tools first raised the share of complete and correct JSON answers at `low` and `medium`. | Structured-output skills need testing with thinking on and off. |
| A nudge about today's date raised the search rate on questions whose answers had changed, and added searches in only 0 to 3 percent of tries on prompts that needed none. A blanket "search for any present-day factual question" made it search on half of the no-search prompts without improving correctness. | Trigger and tool-use wording can be too broad as well as too narrow. |
| It may ignore user text that arrives inside a `tool_result` block. | Deliver mid-turn guidance as a user text block. |

These are Anthropic's results on its own test setups, and the percentages describe those setups. The Haiku and Opus guides also cover safeguard refusals, which return `stop_reason: "refusal"`. A refusal is a different outcome from a skill not triggering, and an eval should record it separately.

### What is not documented

- No peer-reviewed study of Sonnet 5.5 turned up in a web search on 10 November 2026. The sources found were Anthropic's own pages and third-party benchmark sites, and none of those is peer reviewed. Treat Anthropic's figures as vendor-reported results on its own setups, and treat benchmark sites as unreviewed.
- The overview offers little guidance on choosing between Sonnet and Haiku.
- None of these pages measures how often a skill description triggers. Trigger rates have to come from your own cases, as in the next section.

## What published research contributes

Liu et al. found that the position of relevant information affected performance on the long-context retrieval tasks they tested. That motivates a design choice in this project: keep essential instructions in the main skill and link to details the agent can read when needed. Schulhoff et al.'s prompting survey provides a catalog of techniques to try. For a specific skill, treat these patterns as hypotheses and evaluate them on the target model. [Lost in the Middle](https://arxiv.org/abs/2307.03172) · [The Prompt Report](https://arxiv.org/abs/2406.06608)

## What this project observes

- A project issue recorded that review-phrased requests could miss the skill. The description covered writing, evaluation, comparison, and tuning, but omitted independent review. That report motivates testing realistic positive requests alongside plausible near misses. [Issue #60](https://github.com/rolling-codes/better-skill-creator/issues/60)
- The scheduled Haiku and Sonnet canary uses the same four trigger cases and a discovery control for each model. Its artifacts report outcomes per model or explain why a run was skipped. For example, the linked scheduled run published missing-credential statuses for both models. The canary measures a small set of selection cases when credentials are available. [Canary design](../decisions.md#6-use-a-small-bounded-canary) · [Scheduled run and artifacts](https://github.com/rolling-codes/better-skill-creator/actions/runs/42641072399)

## What this project measured on 10 November 2026

A live trigger run used this repository's own 40 test cases per alias (26 should-trigger and 14 should-not-trigger) through the installed `claude` CLI, 2.1.322, with `--runs 1`. The `haiku`, `sonnet`, and `opus` aliases were passed as given, so the resolved model versions were not recorded.

| Alias | Should-trigger passed | Should-not-trigger passed |
|---|---|---|
| `haiku` | 21 of 26 | 13 of 14 |
| `sonnet` | 24 of 26 | 12 of 14 |
| `opus` | 23 of 26 | 11 of 14 |

Read this as one snapshot, not a performance claim. It is one run per query, so it cannot separate a real difference from run-to-run variation. The run was marked incomplete because one case with an empty query crashed the subprocess on every alias. Behavior grading was not part of the run. Two contradictory prompts ("use skill creator but also don't use it") were missed by all three aliases, and the three misses only Haiku had were realistic requests that do not mention the skill creator by name. Repeat the run with `--runs 10` or more before drawing conclusions.

## How to check your own skill

Use the same cases and trigger threshold across target models, and record the full model ID and relevant runtime settings where available. Review each model's results separately. For behavior, hold the task, fixtures, and model constant while comparing the skill with a baseline. Repeat runs when deciding whether an observed difference is consistent. Use the tier-specific writing guidance as a starting point for what to test. [Model guidance](../skills/skill-creator/references/model-guidance.md#writing-for-a-lower-tier-target) · [Compare compatible runs](USER_GUIDE.md#compare-compatible-runs) · [Grade paired authoring runs](USER_GUIDE.md#grade-paired-authoring-runs)
