---
name: skill-creator
description: Creates and improves agent skills and measures whether a skill beats a
  no-skill baseline. Use when the user wants to write or edit a SKILL.md, run evals or
  benchmarks on a skill, compare skill versions, or tune a description so it triggers
  correctly. Not for using an existing skill to do a task.
allowed-tools:
- Read
- Bash(python -m scripts.quick_validate *)
- Bash(python -m scripts.lint *)
- Bash(python -m scripts.static_analysis *)
- Bash(python -m scripts.semantic_analysis *)
- Bash(python -m scripts.score *)
- Bash(python -m scripts.confidence *)
- Bash(python -m scripts.review_gate *)
model: claude-opus-5-5
metadata:
  schemaVersion: "1"
---

# Skill Creator

A skill for creating new skills and iteratively improving them.

At a high level: decide what the skill should do and roughly how, write a draft, create a few test prompts and run claude-with-access-to-the-skill on them, and help the user evaluate qualitatively and quantitatively — while the runs happen, draft quantitative evals if there aren't any and explain them, and use `eval-viewer/generate_review.py` to show results and metrics. Then rewrite from the user's feedback (and any glaring benchmark flaws), repeat until satisfied, and expand the test set to try at larger scale.

Your job is to figure out where the user is in this process and jump in — narrow down a vague "I want a skill for X", write the draft and test cases, run the prompts, and iterate; if they already have a draft, go straight to the eval/iterate loop. Stay flexible (if they say "just vibe with me", do that), and after the skill is done you can run the description improver — a separate script — to optimize triggering.

## Communicating with the user

Users range from non-coders to experienced engineers. Read context cues and match your
phrasing: "evaluation" and "benchmark" are usually fine; only use "JSON" or "assertion"
unexplained when the user clearly knows them. When in doubt, briefly define a term.

---

## The iron law, and the red flags around it

**Iron law: never tell the user a skill is better without a baseline run from the same iteration, because with-skill output that looks good on its own tells you nothing about whether the skill caused it.** A model reading its own polished output will conclude the skill worked, every time. The baseline is the only thing that separates a real improvement from Claude being competent anyway.

Most of the ways this loop fails are not misunderstandings, they are plausible-sounding shortcuts taken under time pressure. If you catch yourself thinking one of the things on the left, the thing on the right is what the situation actually calls for.

| Rationalization | What to do instead |
|---|---|
| "The baseline is obviously going to be worse, I can skip it." | Spawn with-skill and baseline in the same turn. If the baseline wins, that is the single most useful result you can get. |
| "I'll collect the timing numbers once everything finishes." | `total_tokens` and `duration_ms` arrive only in the task notification. Write `timing.json` as each run completes or the data is gone. |
| "I'll just summarize the results for the user, the viewer is a detour." | Run `eval-viewer/generate_review.py`. Your summary is filtered through your own judgment of your own work, which is exactly what the review step exists to check. |
| "This assertion is a bit subjective but a number is better than nothing." | Drop it and evaluate that dimension qualitatively. An assertion that passes for both configurations measures nothing and inflates the pass rate. |
| "The fix worked on eval-2, that is enough." | Two or three examples cannot show generalization. Ask what the fix does on a prompt you have not tried. |
| "There is a testing skill available, I'll use that instead." | Use this loop. `/skill-test` and similar do not produce the baseline pairing or the workspace layout the viewer and aggregation scripts expect. |
| "The score is 68, close enough to 70." | Fix it first. The threshold exists because the gap between 68 and 70 is usually one unwired reference or one missing test file, which is cheap now and expensive later. |
| "The user literally asked for X, so I'll build X." | The literal request is usually one facet of the outcome. Work the angles in `references/design-analysis.md`, build for the problem space, and state the assumptions you made — breadth still needs a tight Boundary (Gate 2), not vagueness. |
| "Completing this entails patching/deploying, so I'll do it." | Entailment is not authorization. Discovering that work is needed doesn't permit it — classify it required-but-unauthorized and ask, and never fold a permissioned or destructive action into the build silently. |
| "The files exist and validation passed, so the skill is complete." | Passing scripts and polished output are not completeness. For a complex skill, run `agents/completion-adversary.md` on the finished result with fresh context and let it try to prove the skill incomplete; only `completion_gate_status: passed` counts as done. |
| "A reviewer suggested this feature, so I'll add it." | A subagent recommendation is not authorization. Run it through the same required/authorized classification — recommendations can be declined, and they never justify expanding scope or performing an external mutation. |

---

## Creating a skill

### Design analysis: scope the outcome from multiple angles

Don't convert the user's wording into an instruction file. "Find the crashes in my logs" is really "keep my app working" — design for the whole problem space, not the sentence. If the conversation already contains the workflow to capture, mine it first (tools used, step sequence, corrections made, input/output formats observed).

Use **adaptive lenses** — read `references/design-analysis.md` for the full doctrine. Always evaluate: the real outcome, material interpretations (and which you chose), entailments (tools/files/steps the outcome needs), boundaries & authorization, and validation. Reach for other lenses (security, performance, multi-user, etc.) only when the request makes them relevant.

**Entailment is not permission.** Classify each piece of work: required-and-authorized (do it), required-but-unauthorized (ask), optional (recommend, never add silently), out-of-scope (exclude). Record in `authorization_boundaries`.

When the outcome entails real development work — writing code, fixing bugs, running tests, authoring commits/PRs — read `references/development-practices.md` and build its practices into the skill so it doesn't ship the recurring AI-assisted bugs (unvalidated boundaries, hallucinated APIs, symptom-only fixes, fixes without regression tests).

Analyze first, ask only at decisive forks — when a material interpretation would produce a substantially different skill and you can't safely infer intent. From the analysis, answer the four things a draft needs: what the skill enables, when it triggers (specific phrases and contexts), its output format, and whether it needs test cases. Check available MCPs and research in parallel via subagents so you arrive with context instead of making the user fill gaps.

### Independent review & adversarial completion (complex skills)

You don't get to decide by yourself that a complex skill is done — a model reading its
own output always concludes it worked. For a substantial new skill or change (new
architecture/scope, multiple modes, external/permissioned/destructive actions,
materially different interpretations, or when you're about to call it complete), run the
process in `references/independent-review.md` and record why you activated or skipped it.
Before drafting, spawn `agents/outcome-analyst.md`, `agents/scope-adversary.md`, and
`agents/architecture-reviewer.md` in one turn with fresh context — give them the request,
files, constraints, and evidence, **never** your proposed solution — then synthesise
**without majority voting** (resolve by evidence: request > conversation > source >
constraints > tests). Before declaring completion, spawn a fresh
`agents/completion-adversary.md` with the finished skill, the decision, and the test
results but **not** the implementation history, and let it try to prove the skill
incomplete; fix, document as a limitation, or return each material finding, and re-run
after fixes. `review.yaml` records it and `scripts/review_gate.py` enforces it; a
subagent recommendation does not authorize expanding scope or an external mutation.
These reviews are the verification step: don't stack extra self-checks or spawn more
subagents on top of them, since current models already verify and delegate readily.

### Write the SKILL.md

Based on the user interview, fill in these components:

- **name**: Skill identifier
- **description**: When to trigger, what it does, written in third person ("Drafts release notes...") because it is injected into the system prompt. This is the primary triggering mechanism: put the key use case first (Claude Code truncates description plus `when_to_use` at 1,536 characters in the skill listing), name the concrete phrases and contexts that should trigger it, and name near misses that should not. Avoid "pushy" or ALL-CAPS trigger language; current models follow the description closely and overtrigger on it. Measure triggering with the description optimizer rather than guessing.
- **allowed-tools** (optional): real Claude Code tool names, scoped as narrowly as the skill allows (`Read`, `Bash(git log *)`). It pre-approves those tools without a prompt, so treat it as a security grant: never pre-approve writes to caller paths, destructive commands, or anything that spends model budget.
- **metadata** (optional): put custom keys here, including `schemaVersion` and `target_model` (the tier this skill will primarily run on — one of `haiku`, `sonnet`, `opus`, `fable`; omit to mean "any"). Any other top-level key makes claude.ai uploads and the Skills API reject the skill; see `references/model-guidance.md`.
- **compatibility**: Required tools, dependencies (optional, rarely needed)
- **the rest of the skill :)**

### Model-Aware Writing

During the design interview, ask: "What model will this skill primarily run on?" Store the answer as `metadata.target_model`. Default to `sonnet` when unknown or unspecified.

**Calibrate instruction density to the target tier.** Higher-tier models writing for lower tiers over-specify by default — adding nuance and caveats that add cognitive load the target model expends resolving instead of executing. (Background: `references/model-guidance.md` §Critical: over-specification and §Writing for a lower-tier target.)

| Target | Posture |
|---|---|
| `fable` | Outcome statement only. One sentence per behavior. The model self-corrects. |
| `opus` | Outcome + scope boundary. Edge cases only when genuinely ambiguous. |
| `sonnet` | Outcome + explicit scope + enumerate the non-obvious cases. Phase labels on multi-step skills. |
| `haiku` | Full scaffolding: XML structure, step enumeration, named output formats. Repetition is load-bearing here, not noise. |

**Concrete contrast** — same task ("summarize and list action items"), two targets:

*Fable:* `Summarize the document and list action items.`

*Haiku:*
```xml
<task>
  <step id="1">Read {file_path} completely.</step>
  <step id="2">Write a 3–5 sentence summary covering the main topic and key conclusions.</step>
  <step id="3">List every sentence containing an imperative verb as a checkbox: `- [ ] {sentence}`</step>
  <output>Save to {output_path} with headings: ## Summary, ## Action Items</output>
</task>
```

**Calibration test (use this before finalizing):** For each instruction block, ask: "Would removing the last qualifying clause change what the model does?" If no — remove it. Apply until the answer is yes or the block is one sentence.

**Fallback when `target_model` is absent:** treat as `sonnet`. Do not ask again if the user already said "any" or "doesn't matter."

**When spawning the grader:** include `target_model: <value>` in the grader subagent's spawn prompt so it grades to the right tier's standard.

### Skill Writing Guide

#### Anatomy of a Skill

```
skill-name/
├── SKILL.md (required)
│   ├── YAML frontmatter (name, description required)
│   └── Markdown instructions
└── Bundled Resources (optional)
    ├── scripts/    - Executable code for deterministic/repetitive tasks
    ├── references/ - Docs loaded into context as needed
    └── assets/     - Files used in output (templates, icons, fonts)
```

#### Progressive Disclosure

Skills use a three-level loading system:
1. **Metadata** (name + description) - Always in context (~100 words)
2. **SKILL.md body** - In context whenever skill triggers (<500 lines ideal)
3. **Bundled resources** - As needed (unlimited, scripts can execute without loading)

**Key patterns:**
- Keep SKILL.md under 500 lines; if approaching this limit, add an additional layer of hierarchy with clear pointers about where to go next.
- Reference files clearly from SKILL.md with guidance on when to read them
- For large reference files (>300 lines), include a table of contents

**Domain organization**: When a skill supports multiple domains/frameworks, organize by variant:
```
cloud-deploy/
├── SKILL.md (workflow + selection)
└── references/
    ├── aws.md
    ├── gcp.md
    └── azure.md
```
Claude reads only the relevant reference file.

#### Writing Patterns

Prefer using the imperative form in instructions.

**Defining output formats** - You can do it like this:
```markdown
## Report structure
ALWAYS use this exact template:
# [Title]
## Executive summary
## Key findings
## Recommendations
```

### Writing Style

Explain the why, not just the rule. Use theory of mind and make the skill general rather than narrow to specific examples. Start with a draft, then read it with fresh eyes.

A few evidence-backed patterns worth internalizing (see `references/model-guidance.md` for sources):

- **Positive framing beats prohibition.** "Don't do X" activates X. "Do Y instead" routes to the right behavior. Reserve prohibitions for categorical constraints where the positive form is genuinely awkward.
- **Hedged language = hedged compliance.** "Try to be concise" makes conciseness optional. Write "Be concise: max 3 sentences" if you mean it. "If possible", "you may", "try to" all signal optionality to the model.
- **Place critical constraints first and last.** Models attend most strongly to the beginning and end of context. One brief restatement of the most important behavioral rule near the end of the SKILL.md is not redundant — it is position-aware.
- **Explicit over implicit.** "Enumerate [A, B, C]" is deterministic. "Handle relevant requests" is resolved differently every invocation. For scope boundaries especially: name the cases, don't describe the category.
- **Example order matters.** The last example is weighted most heavily due to recency bias. Put your strongest, most representative example last. The example teaches the output schema, so its structure must exactly match what you want back.
- **Label phases in multi-step skills.** Explicit phase markers ("Phase 1: Research", "Phase 2: Draft") let the model apply different behavioral modes within one invocation, which outperforms a flat instruction block for complex sequential skills.

### Validation Pipeline

After drafting, run the compiler pipeline before iterating with the user:

```bash
cd skills/skill-creator
python -m scripts.confidence <skill-path>          # coverage + ambiguity
python -m scripts.semantic_analysis <skill-path>   # contradictions, duplicates
python -m scripts.lint <skill-path>                # content quality + reference-wiring completeness
python -m scripts.static_analysis <skill-path>     # wiring: dead refs, orphaned files, unused tools
python -m scripts.repair <skill-path>              # auto-fix known errors
python -m scripts.score <skill-path>               # quality rubric (7 dimensions)
```

Or it all runs automatically as part of `package_skill.py`. Fix any score below 70
before sharing the skill with the user.

To generate structured edge-case and environment test scenarios:
```bash
python -m scripts.generate_tests <skill-path>      # writes to tests/generated/
```

### Test Cases

After writing the skill draft, come up with 2-3 realistic test prompts — the kind of thing a real user would actually say. Share them with the user: [you don't have to use this exact language] "Here are a few test cases I'd like to try. Do these look right, or do you want to add more?" Then run them.

Save test cases to `evals/evals.json`. Don't write assertions yet — just the prompts. You'll draft assertions in the next step while the runs are in progress.

```json
{
  "skill_name": "example-skill",
  "evals": [
    {
      "id": 1,
      "prompt": "User's task prompt",
      "expected_output": "Description of expected result",
      "files": []
    }
  ]
}
```

See `references/schemas.md` for the full schema (including the `assertions` field, which you'll add later).

## Running and evaluating test cases

Run the eval on every model the skill targets — guidance sufficient for Opus can be too thin for Haiku (`python bsc.py eval <skill> --live --models haiku,sonnet,opus`). Don't use `/skill-test`; it doesn't produce the baseline pairing or workspace layout this loop expects.

Put results in `<skill-name>-workspace/` as a sibling to the skill directory, organized by iteration (`iteration-1/`, `iteration-2/`, etc.) and test case (`eval-0/`, `eval-1/`, etc.). Create directories as you go.

### Step 1: Spawn all runs (with-skill AND baseline) in the same turn

For each test case, spawn two subagents in the same turn — one with the skill, one without. Don't spawn with-skill first and come back for baselines later.

**With-skill run:**

```
Execute this task:
- Skill path: <path-to-skill>
- Task: <eval prompt>
- Input files: <eval files if any, or "none">
- Save outputs to: <workspace>/iteration-<N>/eval-<ID>/with_skill/outputs/
- Outputs to save: <what the user cares about — e.g., "the .docx file", "the final CSV">
- target_model: <value from skill's metadata.target_model, or "sonnet" if absent>
```

**Baseline run** (same prompt, baseline depends on context):
- **Creating a new skill**: no skill at all. Same prompt, no skill path, save to `without_skill/outputs/`.
- **Improving an existing skill**: the old version. Snapshot it first (`cp -r <skill-path> <workspace>/skill-snapshot/`), then point the baseline at the snapshot. Save to `old_skill/outputs/`.

Write an `eval_metadata.json` for each test case. Give each eval a descriptive name — not just "eval-0":

```json
{
  "eval_id": 0,
  "eval_name": "descriptive-name-here",
  "prompt": "The user's task prompt",
  "assertions": []
}
```

### Step 2: While runs are in progress, draft assertions

Draft quantitative assertions for each test case and explain them to the user. Good assertions are objectively verifiable; subjective dimensions (writing style, design quality) are better evaluated qualitatively. Update `eval_metadata.json` and `evals/evals.json` with the assertions.

### Step 3: As runs complete, capture timing data

Each task notification includes `total_tokens` and `duration_ms`. Save immediately to `timing.json` — this is the only opportunity, it won't be available later:

```json
{"total_tokens": 84852, "duration_ms": 23332, "total_duration_seconds": 23.3}
```

### Step 4: Grade, aggregate, and launch the viewer

Once all runs are done:

1. **Grade each run** — spawn a grader subagent reading `agents/grader.md`. Save to `grading.json`. The `expectations` array must use fields `text`, `passed`, and `evidence` (the viewer requires these exact names). Use scripts for programmatic assertions — faster and reusable.

2. **Aggregate into benchmark** — from the skill-creator directory:
   ```bash
   python -m scripts.aggregate_benchmark <workspace>/iteration-N --skill-name <name>
   ```
   Put each `with_skill` version before its baseline. See `references/schemas.md` for the benchmark.json schema.

3. **Do an analyst pass** — surface patterns the aggregate stats hide. See `agents/analyzer.md` for what to look for: non-discriminating assertions (always pass in both configs), high-variance evals (possibly flaky), time/token tradeoffs.

4. **Launch the viewer:**
   ```bash
   nohup python <skill-creator-path>/eval-viewer/generate_review.py \
     <workspace>/iteration-N \
     --skill-name "my-skill" \
     --benchmark <workspace>/iteration-N/benchmark.json \
     > /dev/null 2>&1 &
   VIEWER_PID=$!
   ```
   For iteration 2+, add `--previous-workspace <workspace>/iteration-<N-1>`.
   In headless environments, use `--static <output_path>` for a standalone HTML file.

5. Tell the user: "I've opened the results in your browser — 'Outputs' tab for per-case feedback, 'Benchmark' for the quantitative comparison. Let me know when you're done."

### Step 5: Read the feedback

Read `feedback.json`. Empty `feedback` fields mean the user was satisfied. Focus improvements on test cases with specific complaints.

Kill the viewer when done: `kill $VIEWER_PID 2>/dev/null`

---

## Improving the skill

This is the heart of the loop. You've run the test cases, the user has reviewed the results, and now you need to make the skill better based on their feedback.

### How to think about improvements

1. **Generalize from the feedback.** A skill is meant to run across countless prompts, but you and the user are iterating on only a few examples because it's fast. If the skill works only for those examples it's useless — so avoid fiddly overfitting and constrictive MUSTs; for a stubborn issue, try a different metaphor or pattern of working. It's cheap to try.

2. **Keep the prompt lean.** Remove what isn't pulling its weight. Read the transcripts, not just the outputs — if the skill is making the model waste time, cut the part causing that and see what happens.

3. **Explain the why.** Explain the reasoning behind everything you ask the model to do — today's LLMs have good theory of mind and go beyond rote instructions when given a good harness. Understand what the user actually needs behind terse or frustrated feedback and transmit that into the instructions.

4. **Look for repeated work across test cases.** If all the test runs independently wrote a similar helper (a `create_docx.py`, a `build_chart.py`), that's a signal to bundle it: write it once in `scripts/` and tell the skill to use it, so future invocations don't reinvent it.

Your thinking time is not the blocker here, so take your time. Write a draft revision, then look at it again with fresh eyes and improve it, working from what the user actually needs rather than what they literally typed.

### The iteration loop

After improving the skill:

1. Apply your improvements to the skill
2. Rerun all test cases into a new `iteration-<N+1>/` directory, including baseline runs. If you're creating a new skill, the baseline is always `without_skill` (no skill) — that stays the same across iterations. If you're improving an existing skill, use your judgment on what makes sense as the baseline: the original version the user came in with, or the previous iteration.
3. Launch the reviewer with `--previous-workspace` pointing at the previous iteration
4. Wait for the user to review and tell you they're done
5. Read the new feedback, improve again, repeat

Keep going until:
- The user says they're happy
- The feedback is all empty (everything looks good)
- You're not making meaningful progress

---

## Advanced: Blind comparison

For situations where you want a more rigorous comparison between two versions of a skill (e.g., the user asks "is the new version actually better?"), there's a blind comparison system. Read `agents/comparator.md` and `agents/analyzer.md` for the details. The basic idea is: give two outputs to an independent agent without telling it which is which, and let it judge quality. Then analyze why the winner won.

This is optional, requires subagents, and most users won't need it. The human review loop is usually sufficient.

---

## Description Optimization

The `description` field decides whether Claude invokes the skill at all, so
after creating or improving a skill, offer to optimize it for triggering
accuracy. There is a full automated loop for this (generate trigger evals,
review them with the user, run `scripts/run_loop.py` — or `scripts/improve_description.py`
for a one-off rewrite — apply the winning description). Read
`references/description-optimization.md` before starting it.

---

### Package and Present (only if `present_files` tool is available)

Check whether you have access to the `present_files` tool. If you don't, skip this step. If you do, package the skill and present the .skill file to the user:

```bash
python -m scripts.package_skill <path/to/skill-folder>
```

`package_skill.py` writes the archive with Python's zipfile module. After
packaging, direct the user to the resulting `.skill` file path so they can install it.

---

## Environment adaptations (Claude.ai, Cowork)

The core loop is the same everywhere, but Claude.ai has no subagents and Cowork has no browser, so several mechanics change (how test cases run, how the viewer is delivered, whether description optimization is possible). If you are in Claude.ai or Cowork, read `references/environments.md` before running test cases — it also covers updating an existing installed skill, which applies in every environment.

---

## Reference files

- `scripts/file_policy.py`, `scripts/call_budget.py`, and `scripts/claude_process.py` enforce packaging, model isolation, and call limits; see `PERMISSIONS.md` for limits and authentication requirements.

**Agents** (read when spawning the relevant subagent):
- `agents/grader.md`, `agents/comparator.md`, `agents/analyzer.md`
- `agents/outcome-analyst.md`, `agents/scope-adversary.md`, `agents/architecture-reviewer.md`, `agents/completion-adversary.md`

**References** (read on demand):
- `references/design-analysis.md` — multi-angle scoping doctrine; read before drafting
- `references/model-guidance.md` — current model IDs, adaptive thinking API, prompting patterns, agentic skill patterns, prompt injection defenses; read before writing frontmatter or after a model upgrade
- `references/independent-review.md` — independent review + adversarial completion gate
- `references/schemas.md` — JSON schemas for evals.json, grading.json, benchmark.json, etc.
- `references/environments.md` — Claude.ai and Cowork adaptations
- `references/description-optimization.md` — trigger-eval and description-tuning loop
- `references/trigger-confidence.md` — interpreting flaky trigger results
- `references/dependency-graph.md` — script dependency map; read before refactoring
- `references/development-practices.md` — optimal software-development practice for dev skills (root-cause fixes + regression tests, boundary validation, verified-API calls, cross-platform, concurrency, PR authoring); read when the skill writes code, fixes bugs, runs tests, or opens PRs

**For internal development of this skill** (compiler pipeline scripts, governance, migration tools): see `scripts/` and `PERMISSIONS.md` directly — the file structure is self-documenting.

---

Place these steps on your TodoList if you have one, so the eval viewer step doesn't get skipped.
