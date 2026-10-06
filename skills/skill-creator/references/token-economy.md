# Token Economy and Skill Composition

Read this when deciding how to *structure* a skill or a family of skills: what goes in
SKILL.md versus a reference versus a script, whether one skill should become several, and
how to name files so they are found without a search. The goal is to spend the context
budget deliberately. Every token a skill forces into the window competes with the user's
actual conversation; the cheapest token is the one never loaded.

The mechanics below are from Anthropic's official
[Skill authoring best practices](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices)
— re-open the link rather than trusting this snapshot (see
`references/development-practices.md` on perishable facts).

## Contents

- [The three token levers](#the-three-token-levers)
- [One skill or many — composition and the development track](#one-skill-or-many--composition-and-the-development-track)
- [Naming so things are found, not searched](#naming-so-things-are-found-not-searched)
- [Checklist](#checklist)

## The three token levers

Skills load in three levels, and only the first is always paid for:

1. **Metadata (`name` + `description`) — always in context.** Every installed skill's name and
   description sit in the system prompt for the whole session. This is the one unavoidable cost,
   so it is the one to spend most carefully: a tight, specific description is both the trigger
   signal *and* the smallest always-on footprint. Vague padding here is paid on every turn of
   every conversation, triggered or not.
2. **SKILL.md body — loaded only when the skill triggers.** Keep it a lean **table of contents**:
   the workflow and the decisions, with pointers to where detail lives. Official guidance caps it
   at **under 500 lines**; past that, split into references. Being concise still matters even
   though it is not always-on — once loaded, every line competes with conversation history.
3. **Bundled resources — loaded only when actually read.** This is the big lever:

   - **`references/*.md` cost nothing until opened.** A 2,000-line API reference on disk adds zero
     tokens until the moment Claude reads it. So *move* lookup tables, schemas, environment notes,
     and deep background out of SKILL.md into references, and point to them with a one-line "read
     this when…". The pointer costs a line; the payload costs nothing until needed.
   - **`scripts/*` execute without loading their source.** A deterministic or bulky task — parsing,
     validation, bulk transformation — belongs in a script that Claude *runs*. Only the script's
     **output** enters the window, not its source. Inlining the same logic as prose into SKILL.md
     pays for every line on every trigger; a script pays only for what it prints.
   - **Link canonical docs instead of copying them.** A copied spec is both stale-prone (see
     perishable facts) and a standing token cost if it lives in the body. Link it; inline only the
     few lines you truly need inline.

The discipline in one line: **metadata earns the trigger, SKILL.md orchestrates, references and
scripts hold the weight — and weight is free until it is used.**

## One skill or many — composition and the development track

A capability can grow as one skill with many references, or as several focused skills that
compose. The token question decides it: **the model loads the body of every skill that triggers.**
A single mega-skill covering design, implementation, validation, and review loads all of it the
moment any part is relevant. Four focused skills each load only when their own job is at hand.

Split into separate skills when:

- The pieces trigger on **different intents** ("scope a feature" vs "review a diff") — separate
  descriptions fire precisely and load only what the moment needs.
- A piece is **independently useful** or reused across contexts.
- One piece is heavy enough that always carrying it with the others is wasteful.

Keep as one skill with references when:

- The steps are a **single workflow** the user triggers as a unit (the pieces are phases, not
  independent jobs) — splitting would just make them re-trigger each other.
- They share so much context that separate skills would duplicate it.

**The recommended development track** is a composition, not a fusion:

| Skill (gerund name) | Job | Triggers on |
|---|---|---|
| `scoping-changes` | Turn a request into a bounded spec | "what should this do", design questions |
| `implementing-features` | Write the change | "build/add/fix…" |
| `validating-code` | Run the checks the change must pass | "verify / does this pass" |
| `reviewing-changes` | Independent read before merge | "review this / ready to ship?" |

Each carries a tight **trigger and an explicit boundary** ("NOT for…") so they don't
trigger-collide, and each loads only for its phase — the composition's token cost scales with the
task at hand, not with the size of the whole track. Within a single skill, the same principle
applies in miniature: this skill-creator keeps SKILL.md as the spine and puts each concern in its
own `references/` file (design-analysis, model-guidance, development-practices, this one), loaded
only when that concern is live.

## Naming so things are found, not searched

A file the model can *predict* is a file it opens directly; a file it can't is one it finds by
listing and grepping the directory — and every one of those discovery steps is spent tokens. Good
names are a token optimization, not just tidiness.

Official rules, applied here:

- **Skill names: gerund form** (`processing-pdfs`, `testing-code`, `writing-documentation`).
  `name` is lowercase letters/digits/hyphens, ≤64 chars. **Avoid** `helper`, `utils`, `tools`,
  generic nouns (`documents`, `data`), reserved words (`claude-…`, `anthropic-…`), and mixing
  patterns within one collection.
- **File names describe contents:** `form-validation-rules.md`, never `doc2.md` / `file1.md`.
- **Organize by domain, not by type:** `references/finance.md`, `references/sales.md` — not
  `docs/file1.md`. The model navigates the skill like a filesystem; a domain layout lets it jump
  straight to the right file.
- **Forward slashes always** (`references/guide.md`), never backslashes — paths are POSIX in skills
  (this is also the cross-platform rule from `development-practices.md`).

Pick a **predictable scheme and hold to it** so a file can be addressed by convention instead of
discovered:

| Kind | Convention | Example |
|---|---|---|
| Reference doc | `references/<kebab-topic>.md` | `references/token-economy.md` |
| Script | `scripts/<verb>_<noun>.py` | `scripts/validate_skill.py` |
| Agent instructions | `agents/<role>.md` | `agents/scope-adversary.md` |
| Test fixtures | `tests/<suite>.yaml` | `tests/should_trigger.yaml` |

When SKILL.md references a file, name it by this convention so Claude opens it directly — one
`Read` of a known path instead of a directory scan plus a grep.

## Checklist

Structuring a skill or a track:

- [ ] `description` is specific and short — it is the only always-on cost; it earns the trigger.
- [ ] SKILL.md is a <500-line table of contents; detail is pushed to `references/`.
- [ ] Deterministic/bulky logic is a `script` that is run, not prose that is loaded.
- [ ] External specs/stats are linked, not copied into the body.
- [ ] Multi-intent capabilities are split into composed skills; single workflows stay one skill.
- [ ] Every skill in a track has a tight trigger **and** a boundary, so only one loads per task.
- [ ] Names are gerund (skills) and descriptive/domain-organized (files), forward slashes, on a
      predictable scheme so files are opened by convention, not discovered by scan.
