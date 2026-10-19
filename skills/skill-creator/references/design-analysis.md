# Design Analysis

Read this before drafting or restructuring a skill. It is the reasoning stage that
keeps the skill-creator from turning a user's wording into a shallow instruction file
— and, equally, from turning it into an over-engineered one. The job is to work out
what the request is really for, scope it, and stop.

The literal prompt is almost always one facet of a larger outcome. "Find the crashes
in my logs" is not a request for a log grepper; it is a request for a working app. But
"design for the whole problem space" is not "consider everything" — that produces
mechanical checklists and uncontrolled scope. You evaluate a small always-on core,
reach for other lenses only when they're relevant, keep entailment separate from
permission, and stop once the architecture is settled.

## Contents

- [Adaptive lenses](#adaptive-lenses) — what to always evaluate vs. evaluate when relevant
- [Entailment is not permission](#entailment-is-not-permission) — classify discovered work
- [Scope-selection matrix](#scope-selection-matrix) — choose among interpretations
- [The design brief](#the-design-brief) — what lands in spec.yaml
- [Contradiction handling](#contradiction-handling) — when requirements conflict
- [Stopping rule](#stopping-rule) — when the analysis is done
- [Ask vs. assume](#ask-vs-assume)
- [Worked examples](#worked-examples)

## Adaptive lenses

Do not work a fixed checklist top to bottom. Evaluate the always-on core every time;
reach for the rest only when the request makes them relevant, and **say why you picked
one up**. An unused lens is a sign of focus, not omission — pulling in a lens the
request doesn't need is how multi-angle reasoning turns into scope creep.

**Always evaluate:**

- **Intended outcome** — what the user is actually trying to achieve, in outcome terms.
  If your restatement is just their sentence reworded, you haven't found it yet.
- **Material interpretations** — the genuinely different readings that would produce
  substantially different skills. Name them so you can choose rather than default.
- **Necessary entailments** — what actually has to exist to deliver the outcome (tools,
  files, references, ordered workflow steps). This is where "generate code" becomes
  "inspect logs → diagnose → patch → verify."
- **Boundaries & authorization** — what is in scope, what is out, and which entailed
  work you are actually permitted to do (see the next section).
- **Validation** — how success is checked; how the produced skill tests its own output.

**Evaluate when relevant** (justify each one you pick up):

- **Accessibility** — headless/no-browser, screen-reader, plain-language.
- **Security** — untrusted input, secrets, auth, injection surfaces.
- **Performance** — data size, latency, resource limits.
- **Persistence** — state that must survive across runs or sessions.
- **Creative direction** — tone, format, style, where they materially matter.
- **Integration** — external systems, APIs, MCPs, file formats it must interoperate with.
- **Multi-user behavior** — concurrency, per-user state, permissions between users.
- **Error recovery** — what the skill does when a step fails partway.

If a lens doesn't apply, skip it silently — don't record "N/A" for eight fields.

## Entailment is not permission

This is the guardrail that keeps multi-angle reasoning from becoming uncontrolled
scope expansion. Recognizing that completing a task *entails* patching code, deleting
data, or deploying does **not** authorize doing those things. Discovering the work and
being allowed to do the work are different questions.

Classify every piece of discovered work into exactly one bucket:

- **Required and authorized** — needed for the outcome and within what the user asked
  for or clearly permitted. Do it.
- **Required but unauthorized** — needed for the outcome but touching data, accounts,
  systems, permissions, or external state the user hasn't authorized. **Identify it and
  request approval.** Never fold it in silently.
- **Optional improvement** — would help but isn't necessary. Recommend it; do not add
  it without a yes.
- **Out of scope** — not part of this outcome. Exclude it explicitly (it becomes part
  of the Boundary clause).

When the skill being built is one that *takes actions* (a dev skill that can patch, a
deploy skill), bake the same discipline into it: the produced skill should classify its
own destructive or outward-facing steps as required-but-unauthorized and ask, rather
than acting silently. Record the classification in `authorization_boundaries`.

## Scope-selection matrix

When more than one material interpretation survives, don't just list them — score them
and choose by reasoning:

| Criterion | Question |
|---|---|
| Goal fit | Does it achieve the user's actual outcome? |
| Evidence | What wording or context supports this reading? |
| Complexity | How much architecture does it introduce? |
| Reversibility | Can a wrong assumption be corrected cheaply later? |
| Risk | Could it affect data, accounts, systems, or permissions? |
| Clarification need | Would choosing wrong substantially change the skill? |

**Scoring Complexity and Risk — use the same vocabulary as the review-activation
rubric** ([`independent-review.md`](independent-review.md) §"When to run it"), so a
skill has one risk/complexity classification, not two competing ones:

- **Complexity** is *low* for a typo/metadata/changelog-level reading, *moderate*
  when it adds one trigger clause or one mode, and *high* when it introduces new
  architecture, multiple modes, persistence, or an RPG-scale workflow. High
  complexity is what the rubric calls a `substantial` change.
- **Risk** is *low* when the reading touches nothing outside the skill's own files,
  and *high* the moment it entails an external mutation, a permissioned or
  destructive action, or anything affecting data, accounts, systems, or permissions
  — the rubric hits `external_mutation` and `permissioned_or_destructive`. High risk
  always forces the `substantial` review class and clears authorization first.

High reversibility + low risk + clear evidence → make the call and state the
assumption. Low reversibility or high risk with thin evidence → that's a decisive
question worth one interruption (see [Ask vs. assume](#ask-vs-assume)).

## The design brief

The analysis produces a short brief, captured in `spec.yaml` (`SkillSpec`) so it
persists and `scripts/confidence.py` can flag a flat, unresolved, or
unauthorized-by-omission design:

```
outcome:                 # the real end-state, in outcome terms
chosen_interpretation:   # the reading you're building, and why
alternatives_considered: # -> spec field `interpretations`
supported_modes:         # -> `modes`
required_entailments:    # -> `entailments`
optional_features:       # recommended, not silently added -> `optional_features`
authorization_boundaries:# required-but-unauthorized / out-of-scope calls
failure_points:          # errors, edge cases, limits to guard or test
validation_strategy:     # -> `validation`
assumptions:             # inferred and stated, so the user can veto
decisive_questions:      # -> `open_questions`; the only things that interrupt the user
```

Only **decisive questions** interrupt the user. Everything else is a visible,
correctable assumption — a stated assumption the user can veto beats an interview that
makes them do the design work.

## Contradiction handling

Requirements conflict. Resolve them explicitly rather than silently picking a side, and
**explicit user constraints always win**. Common conflicts:

- Complete outcome vs. a narrow scope the user stated → honor the narrow scope; note
  the rest as out-of-scope recommendations.
- Accessibility vs. strict visual fidelity.
- Automation vs. a step that requires approval.
- Flexibility vs. deterministic output.
- Broad feature support vs. a concise SKILL.md.

When you trade one against the other, **record the compromise** in `assumptions` or the
Boundary clause so it's visible, instead of quietly optimizing for whichever you
happened to reach first.

## Stopping rule

Stop the analysis — don't keep spinning up lenses — once all of these hold:

- The intended outcome is clear.
- Material interpretations have been resolved (chosen, or reduced to one decisive
  question).
- Necessary entailments are identified.
- Authorization boundaries are known.
- Success can be tested.
- Further angles would not materially change the architecture.

If picking up another lens wouldn't change what you build, you're done. This is what
keeps a "make a simple skill" request from turning into a massive design exercise.

## Ask vs. assume

Ask a focused question **only when a material interpretation would produce a
substantially different skill and the matrix can't settle it safely** — typically low
reversibility or real risk with thin evidence. Then ask one sharp question about the
deciding axis, not a battery.

Otherwise make the call and **state the assumption**. Default to inferring; let the
user veto.

## Worked examples

### A development skill

Prompt: *"Make a skill that builds a responsive app and watches my logs."*

- **Outcome:** a working, responsive app whose failures the skill can find and fix.
- **Interpretations:** scaffold-only generator vs. build-observe-self-heal. "Watches"
  points hard at the latter.
- **Entailments:** generate UI → inspect logs → detect syntax errors → diagnose →
  trace root cause → patch → run tests → verify.
- **Lenses picked up (with reason):** *error recovery* (it acts on failures), *security*
  (it reads logs that may contain secrets). Skipped: multi-user, persistence,
  creative — not implied.
- **Entailment ≠ permission:** patching source is required; is it authorized? For a
  local dev loop, yes. **Deploying** the fix is required-but-unauthorized → the produced
  skill must ask before deploy, never auto-deploy.
- **Decision:** build-and-self-heal, both build and iterate modes. *Assumption stated:*
  "treating this as build + self-heal, not scaffold-only, and patching locally but
  asking before any deploy."

### An RPG skill

Prompt: *"Build me an RPG skill."* vs. *"…one-shot, no persistent state."* vs.
*"…persistent police-career RPG with ranks."*

- **Axes:** flat narrative · dynamic simulation · persistent campaign · progression /
  ranks · branching consequences · world-state · resolution system.
- **Matrix in action:** with no other signal, "Build me an RPG skill" has thin evidence
  across a high-complexity/low-reversibility split (flat vs. persistent), so persistence
  is *one decisive question*: "remember state across sessions, or self-contained each
  run?" The two constrained prompts answer it up front — scope flat for the one-shot,
  scope state+ranks+resolution for the police-career campaign, and don't ask.
- **Stopping rule:** once persistence and progression are settled, further lenses
  (creative tone, multi-user) wouldn't change the architecture — stop.
