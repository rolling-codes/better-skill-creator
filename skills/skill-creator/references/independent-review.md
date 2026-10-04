# Independent Review & Adversarial Completion

Read this when creating a substantial new skill or making a substantial change. It
removes the primary agent's authority to decide *by itself* that a skill is done. A model
reading its own polished output concludes it worked — the same self-assessment blind spot
the iron law names for evals, applied to completeness. Independent subagents with their
own context windows examine the work before drafting and again before completion.

**Central invariant:** No complex skill is complete until an independently contextualized
adversarial reviewer has attempted to prove it incomplete, and every material finding is
fixed, accepted as a documented limitation, or returned to the user as a decisive
question.

## Contents

- [When to run it (adaptive activation)](#when-to-run-it-adaptive-activation)
- [Independence requirements](#independence-requirements)
- [Pre-draft review](#pre-draft-review)
- [Synthesis without voting](#synthesis-without-voting)
- [Adversarial completion gate](#adversarial-completion-gate)
- [The review record](#the-review-record)

## When to run it (adaptive activation)

Don't spend the full process on spelling fixes, metadata-only edits, or obviously narrow
changes. **Require** it when any of these hold, and **record why** in `review.yaml`
(`activation`):

- Creating a substantial new skill.
- Changing a skill's architecture or scope.
- Adding multiple operating modes.
- Handling external systems, permissions, or destructive actions.
- The request has materially different interpretations.
- Incorrect scoping would make the skill unreliable.
- You are about to describe a complex skill as complete.

If you skip it, record the skip and the reason too — the gate checks that the decision
was made deliberately.

## Independence requirements

Launch the review subagents in the same turn when concurrency permits. Each subagent must:

- Start from a fresh or minimally forked context.
- Receive the original user request, relevant source files, constraints, and observable
  evidence.
- **Not** receive the primary agent's proposed solution, conclusions, suspected problems,
  or preferred answer.
- Analyze independently before seeing another agent's findings.
- Write its own structured report (JSON, per-finding severity).
- Not modify the working tree.

They may share the same files, but their **reasoning contexts must stay isolated**. Do
not call an agent "independent" if it inherits the primary's reasoning or is told what to
conclude. When you spawn each one, hand it only request + files + constraints + evidence
(and, for the scope and architecture reviewers, the scope/architecture under review) —
never your rationale or preferred answer.

## Pre-draft review

Before drafting the skill, spawn three independent reviewers (in one turn):

- `agents/outcome-analyst.md` — the real outcome, material interpretations, modes,
  entailments, safe assumptions, decisive questions, and what "complete" means here.
- `agents/scope-adversary.md` — tries to disprove the scope in **both** directions
  (under-scoping and overengineering), plus authorization overreach and conflicts.
- `agents/architecture-reviewer.md` — whether the proposed structure can deliver the
  outcome (workflow completeness, discoverability, self-validation, permissions,
  recovery, unnecessary complexity).

Collect their JSON reports into `review.yaml` under `independent_findings`.

## Synthesis without voting

Compare the reports against each other and against your own analysis. **Do not use
majority voting** — three shallow agreements don't outweigh one evidenced objection.
Resolve each disagreement using this evidence hierarchy, highest first:

1. The user's explicit request.
2. Existing conversation context.
3. Repository behavior and source files.
4. Tool and environment constraints.
5. Realistic test outcomes.

Produce a **consolidated design decision** recording: accepted findings; rejected
findings with reasons; unresolved conflicts; chosen interpretation; supported and
excluded modes; required entailments; authorization boundaries; validation strategy;
stated assumptions; and any decisive question that must go back to the user. Surface
disagreements — do not erase them. **A subagent recommendation does not grant permission
to expand the task or perform an external mutation**; a suggested feature or action still
has to clear the authorization classification from `references/design-analysis.md`.

## Adversarial completion gate

Do not claim a skill is complete merely because the files exist, validation scripts exit
0, the docs look comprehensive, the output looks polished, one test passes, or you agree
with your own design.

Before declaring completion, spawn a **fresh** `agents/completion-adversary.md` that
receives the original request, the finished skill, the consolidated decision, and the
test/validation results — **not** the implementation history and **not** a list of what
was fixed. It tries to prove the skill is incomplete (unmet outcome, missing mode,
unhandled failure path, unsupported assumption, authorization violation, unwired
resource, hollow test, regression).

Every material (high) finding must be **fixed**, **accepted as a documented limitation**,
or **returned to the user as a decisive question** — recorded in `review.yaml`
(`finding_disposition`). After any material fix, **run the gate again** on the changed
skill. Completion is claimable only when `completion_gate_status: passed` — the gate ran
and no material finding is left undisposed.

## The review record

The whole process is captured in `review.yaml` (see `scripts/review.py`,
`ReviewRecord`), and `scripts/review_gate.py` deterministically enforces it — failing on
missing reports, undisposed high-severity findings, unwired review agents, unresolved
decisive questions, a passed status without a completion-adversary report, or a
completion claim while `completion_gate_status` isn't `passed`. Fields: `activation`,
`independent_findings`, `disagreements`, `consolidated_decision`,
`completion_adversary_report`, `adversarial_findings`, `finding_disposition`,
`completion_gate_status`, `accepted_limitations`, `unresolved_decisive_questions`.

## Source binding and migration

Required reviews now carry `source_manifest`, a map of relative filenames to
SHA-256 content digests. The manifest covers source, test, and eval files; it
excludes `review.yaml` itself, generated caches/builds, VCS state, and sensitive
local files under the shared packaging policy. Added, deleted, or edited covered
files invalidate the review. Auto-repairs also require a new review when they
change covered content.

Start a new record with `python -m scripts.review init <skill-path>`. To deliberately
replace an old record, archive it outside the skill first, then run
`python -m scripts.review restart <skill-path>`. Restart captures current source
and clears old approval and reports; it does not approve the new source. Collect
fresh independent reports and dispositions before marking the gate passed. Do not
refresh only the hashes to make an old approval pass.

Legacy required records without a manifest fail with `review-unbound`. The bundled
historical `review.yaml` is intentionally retained as history and no longer grants
packaging approval for this release; a maintainer must record a fresh review.
Narrow changes can still record an explicit activation skip under the existing
policy. Fingerprints detect staleness, not reviewer authenticity. For untrusted
third-party artifacts, keep approval evidence and release policy outside the
artifact author's control.
