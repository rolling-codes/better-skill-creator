# Better Skill Creator

**Better Skill Creator is an engineering system for helping humans and AI agents create, evaluate, and improve reliable agent skills.**

A `SKILL.md` is not a deterministic program. An agent has to decide whether a skill applies, decide how much of it to load, interpret its instructions, and execute them correctly. Even a well-written skill can undertrigger, overtrigger, misinterpret its boundaries, or behave differently across models.

Better Skill Creator treats skill development accordingly: **understand the outcome → design and scope → build → validate → evaluate → review → improve → repeat.**

The goal is not simply to make writing skills easier. The goal is to make the resulting skills **more reliable, measurable, and maintainable**.

---

## Why Better Skill Creator exists

Anthropic's official `skill-creator` already provides an important foundation: draft a skill, create realistic test prompts, run with-skill and baseline evaluations, compare results, iterate, and optimize the description for triggering. It also explicitly recognizes that Claude can undertrigger skills and recommends evaluating trigger behavior rather than assuming the description will work.

Better Skill Creator builds on that foundation by making the development process more explicit and more rigorous.

The central difference is **evidence**.

Instead of treating a skill as finished because its instructions look good, Better Skill Creator asks:

- Does it actually produce the intended outcome?
- Does it outperform the appropriate baseline?
- Does it trigger when it should?
- Does it stay inactive when it should not trigger?
- Does its behavior remain reliable across repeated runs?
- How does the target model actually behave?
- Are its boundaries and authorization rules explicit?
- Can independent reviewers find failures the author missed?
- Is there enough evidence to call the skill finished?

---

# The default skill-building workflow

Better Skill Creator provides a default development workflow for agents building skills.

The agent does not need to begin by manually orchestrating every script. The `skill-creator` meta-skill determines where the work currently is and moves the skill through the appropriate stages.

```text
Idea / existing skill
        ↓
Understand the intended outcome
        ↓
Design the skill
        ↓
Define scope, boundaries & authorization
        ↓
Build / revise SKILL.md
        ↓
Validate structure and wiring
        ↓
Evaluate behavior
        ↓
Compare against a baseline
        ↓
Test triggering and composition
        ↓
Independent review
        ↓
Improve from evidence
        ↓
Repeat until the completion gates pass
```

This is the **default methodology**, not a requirement that every skill must use every possible test. The workflow adapts to the task and its risk.

The surrounding scripts and validation infrastructure exist to make the workflow reproducible and measurable.

---

# What makes this different

## 1. Design before instructions

A skill should not begin with a pile of instructions.

The development process first establishes:

- the actual user outcome
- what the agent is expected to accomplish
- what interpretations are possible
- what is required versus optional
- what is authorized
- what is explicitly out of scope
- what evidence will demonstrate success
- what failure modes matter

This prevents a common failure mode: producing a technically detailed skill whose instructions do not actually solve the user's problem.

---

## 2. Outcome-based evaluation

A skill is evaluated on **what it accomplishes**, not merely whether it contains the expected sections.

Better Skill Creator supports behavioral evaluation using realistic tasks, quantitative expectations, qualitative review, and repeated iterations.

For improvements to an existing skill, the relevant comparison is normally the previous version.

For a new skill, the relevant baseline is normally **no skill at all**.

The fundamental rule is:

> **Do not claim that a skill is better without evidence from a comparable baseline.**

This makes improvement measurable instead of subjective.

---

## 3. Model-specific triggering baselines

This is one of the major differences in Better Skill Creator.

Skill triggering is model behavior.

The same skill description does not necessarily produce the same routing behavior on every model. A description that triggers reliably on one model can undertrigger or overtrigger on another.

Better Skill Creator therefore treats model behavior as something to **measure and preserve as evidence**, rather than something to assume.

### Model behavior is part of the development data

The project maintains model-specific guidance and comparisons describing how different models tend to behave when selecting and using skills.

This gives the skill-development process a behavioral reference point:

```text
Skill description
       ↓
Target model
       ↓
Trigger evaluation
       ↓
Observed behavior
       ↓
Baseline / comparison
       ↓
Description or skill revision
```

That matters because triggering is not simply a property of the text.

It is a property of the **skill description + available skills + model + task**.

Anthropic's current tooling does evaluate trigger rates and can run each trigger query multiple times, but its workflow is primarily an optimization loop for the description under test.

Better Skill Creator goes further by treating **known model behavior as reusable development knowledge**.

Instead of rediscovering the same behavior every time a skill is created, the development system can start with what is already known about the target model.

---

## 4. Triggering is tested separately from skill quality

A skill can be excellent once loaded and still be a bad skill if the model rarely loads it when it should.

These are different questions:

```text
          Skill quality
               │
       ┌───────┴────────┐
       ↓                ↓
Can the skill work?   Will it trigger?
       │                │
   behavior eval    trigger eval
```

Better Skill Creator therefore treats triggering as its own evaluation problem.

Trigger evaluations should include both:

- **should-trigger** cases
- **should-not-trigger** cases

Repeated runs provide a trigger rate rather than a single binary observation.

---

## 5. Independent multi-agent review

The author of a skill should not be the only agent deciding whether the skill is finished.

For substantial skills, Better Skill Creator can use independent reviewers focused on different failure modes:

- **Outcome analyst** — does the skill actually achieve the intended result?
- **Scope adversary** — can the skill be misapplied outside its intended boundary?
- **Architecture reviewer** — is the skill structured appropriately?
- **Completion adversary** — is there evidence that the work is actually finished?

Reviewers work from sufficiently fresh context to reduce confirmation bias.

A skill does not automatically pass because the author believes it is complete.

---

## 6. Entailment is not permission

Instructions can imply that an action is necessary without giving the agent authority to perform it.

Better Skill Creator explicitly separates:

| Classification | Meaning |
|---|---|
| **Required + authorized** | The skill should perform it |
| **Required + unauthorized** | The skill needs the result, but must not perform the action without authorization |
| **Optional** | Useful but not necessary |
| **Out of scope** | The skill must not perform it |

This distinction is particularly important for skills that interact with external systems, modify files, execute commands, or perform consequential actions.

---

# A skill is not finished because it looks finished

Better Skill Creator uses quality gates before packaging.

The exact gates depend on the skill, but can include:

### Structural validation

- valid frontmatter
- valid skill name
- valid description
- supported properties
- correct file structure
- valid references
- valid scripts
- no broken wiring

### Behavioral validation

- realistic test prompts
- expected outcomes
- quantitative assertions where appropriate
- qualitative review where judgment is required
- baseline comparison
- repeated evaluation where variance matters

### Trigger validation

- positive trigger cases
- negative trigger cases
- repeated trigger runs
- model-specific observations
- description optimization where appropriate

### Review validation

- independent review
- adversarial scope analysis
- completion review
- authorization review

### Packaging validation

- required files present
- no unintended files included
- references resolve
- final skill passes the applicable gates

---

# Progressive disclosure and token economy

Skills compete for model context.

Better Skill Creator therefore treats context consumption as part of skill design rather than an afterthought.

The development process considers:

- what belongs in frontmatter
- what belongs in `SKILL.md`
- what should be loaded only when needed
- what belongs in references
- what can be delegated to deterministic scripts
- what information should be handed between agents rather than repeatedly reconstructed

The objective is not simply “make the skill shorter.”

It is:

> **Load enough context to perform the task correctly, and no more.**

This makes progressive disclosure a design principle rather than merely a directory convention.

---

# Model-aware skill writing

Different models have different strengths, weaknesses, context behavior, and instruction-following characteristics.

Better Skill Creator therefore includes model-aware guidance rather than assuming that one writing style is optimal everywhere.

The project records practical guidance for supported model tiers and uses that information when designing or reviewing skills.

This does **not** mean hard-coding a skill to one model unnecessarily.

It means acknowledging that:

> **A skill is executed by a model, and the model is part of the system being engineered.**

---

# Development practices matter too

Better skills also depend on the engineering practices used to create them.

The project incorporates guidance for:

- repository research
- implementation planning
- testing
- verification
- safe changes
- debugging
- documentation
- regression prevention
- handoffs between agents

The objective is to make the skill-development process itself reproducible.

---

# What's included

Better Skill Creator combines an agent-facing meta-skill with deterministic supporting infrastructure.

```text
skills/
└── skill-creator/
    ├── SKILL.md
    ├── scripts/
    ├── references/
    └── agents/
```

The `skill-creator` skill is the primary interface.

The supporting system provides things such as:

- structural validators
- skill compilation / IR handling
- behavioral evaluation
- baseline comparison
- trigger evaluation
- description optimization
- independent review
- adversarial review
- completion gates
- regression tests
- packaging
- reporting

The distinction is intentional:

**The agent decides what development work needs to happen.  
The infrastructure makes important parts of that work deterministic and verifiable.**

---

# How it relates to Anthropic's Skill Creator

Better Skill Creator is built on the same general foundation as Anthropic's official skill-development workflow.

Anthropic's current `skill-creator` already includes:

- skill drafting
- realistic test prompts
- with-skill versus baseline runs
- quantitative evaluation
- qualitative review
- iterative improvement
- trigger evaluation
- description optimization
- held-out trigger testing
- packaging guidance

Better Skill Creator does not need to pretend those ideas are new.

Instead, it extends them into a broader engineering methodology.

### The distinction

| Anthropic Skill Creator | Better Skill Creator |
|---|---|
| Create and improve skills | Create, evaluate, improve, and engineer skills |
| Baseline comparisons | Baseline comparisons + reusable model behavior knowledge |
| Trigger evaluation | Trigger evaluation + model-specific behavioral baselines |
| Description optimization | Trigger behavior treated as a first-class engineering concern |
| Evaluation loop | Evaluation loop + explicit quality gates |
| Human evaluation | Independent multi-agent review |
| Skill instructions | Outcome, scope, authorization, and boundaries |
| Progressive disclosure | Progressive disclosure + token-economy design |
| Iterate until satisfied | Iterate from evidence until applicable gates pass |

The goal is not to replace Anthropic's approach.

It is to make the **engineering discipline around skills more explicit, repeatable, and evidence-driven**.

---

# Five-minute walkthrough

### 1. Start with an outcome

Instead of:

> “I want a skill for database work.”

Define:

> “I want an agent to safely diagnose and modify database-backed application behavior while respecting the project's existing architecture and authorization boundaries.”

### 2. Design the skill

Determine:

- what the skill should accomplish
- when it should trigger
- when it should not trigger
- what it is allowed to do
- what it must not do
- what evidence demonstrates success

### 3. Build it

Create the `SKILL.md` and any required references, scripts, or assets.

### 4. Validate it

Run the structural and wiring checks.

### 5. Evaluate it

Run realistic tasks with:

- the skill
- the appropriate baseline
- repeated runs where necessary

### 6. Test triggering

Test both positive and negative cases against the target model.

Use existing model-behavior knowledge as a starting point rather than treating every triggering question as brand new.

### 7. Review independently

Run the applicable reviewers and adversarial checks.

### 8. Improve

Use the evidence to make the next iteration better.

Then repeat.

---

# When to use Better Skill Creator

Use it when you want to:

- create a new agent skill
- improve an existing skill
- diagnose why a skill is failing
- evaluate whether a skill actually improves outcomes
- compare skill versions
- establish or update trigger behavior
- optimize a skill description
- understand how a skill behaves on a target model
- review a skill for scope or authorization problems
- prepare a skill for distribution

---

# When not to use it

Do not use Better Skill Creator merely because you want to **use an existing skill** to complete an ordinary task.

It is for **building and improving skills**, not for replacing the skill being built.

---

# Design principles

Better Skill Creator is built around a few principles:

### Evidence over intuition

If behavior matters, measure it.

### Baselines over isolated results

A result is more meaningful when there is a comparable result to measure it against.

### Model behavior is data

Do not assume every model routes or follows skills identically.

### Triggering is part of skill quality

A skill that works perfectly but never activates when needed is still a poor skill.

### Independent review catches different failures

The author should not be the only judge of completion.

### Authorization is separate from necessity

An instruction can establish that something is needed without granting permission to perform it.

### Deterministic infrastructure should handle deterministic work

Use scripts and validation machinery where reliability benefits from removing unnecessary model judgment.

### Progressive disclosure protects context

Give the model the information it needs at the point it needs it.

### Iterate from evidence

Every significant revision should have a reason grounded in observed behavior.

---

# Current release

**v3.4.0**

The current release focuses on:

- token-economy guidance
- skill-composition guidance
- model-aware development
- development-practice guidance
- stronger validation
- regression protection
- independent review
- behavioral evaluation
- trigger evaluation
- baseline-driven iteration

---

# Project status

Better Skill Creator is an actively developed engineering toolkit and meta-skill.

Its purpose is deliberately broader than a collection of validation scripts:

> **It provides a default way for humans and AI agents to engineer better skills.**

The meta-skill supplies the development methodology.

The evaluation and validation system supplies the evidence.

The model-behavior baselines supply reusable knowledge about how skills actually behave.

Together, they turn skill creation from:

```text
Write SKILL.md
      ↓
Hope the model uses it
```

into:

```text
Understand
   ↓
Design
   ↓
Build
   ↓
Validate
   ↓
Measure
   ↓
Compare
   ↓
Review
   ↓
Improve
   ↓
Measure again
```

That is the core of Better Skill Creator.

---

## Documentation

Start with:

- `skills/skill-creator/SKILL.md` — the agent-facing development process
- `skills/skill-creator/references/` — supporting specifications and guidance
- `skills/skill-creator/agents/` — independent review roles
- `skills/skill-creator/scripts/` — deterministic development and validation infrastructure

---

## Contributing

Contributions should improve the reliability of the skill-development process itself.

When proposing a change, prefer:

1. a concrete failure or limitation
2. evidence demonstrating the problem
3. a targeted change
4. regression coverage
5. verification that the change improves the intended behavior without introducing new failures

---

## License

See `LICENSE`.

---

## Short version

**Better Skill Creator helps humans and AI agents build better skills by treating skills as engineered, measurable systems rather than documents that merely look correct.**

It provides a default workflow for:

**understanding → designing → building → validating → evaluating → comparing → reviewing → improving.**

And because skill behavior depends on the model executing it, Better Skill Creator also treats **model-specific triggering behavior and baselines as development data**, rather than assumptions.

The result is a more rigorous path from:

**“I need a skill.”**

to:

**“I have evidence that this skill works.”**
