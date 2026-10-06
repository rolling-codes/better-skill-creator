# Development Practices

Read this when the skill you are building or improving does real software development —
writes code, fixes bugs, runs tests, or authors commits and PRs. It is the development-practice
counterpart to `model-guidance.md`: that file is about writing *prompts*; this one is about
writing *software*. The point is not to lecture the model on general programming. It is to make
the produced dev skill bake in the practices that keep AI-assisted code from shipping the same
handful of bugs over and over — so build these into the skill's workflow and checklists, not
just into your own head.

Every section names the failure mode it defends against. The frequencies in parentheses come
from a survey of 84 genuine `fix:` commits across the author's AI-assisted repositories
(EasyCord, LSPDFRManager, better-skill-creator, and others) — these are not hypotheticals, they
are the bugs that actually recurred.

## Contents

- [Understand before you change](#understand-before-you-change)
- [Fix the root cause, not the symptom](#fix-the-root-cause-not-the-symptom)
- [Every fix leaves a regression test](#every-fix-leaves-a-regression-test)
- [Validate at trust boundaries](#validate-at-trust-boundaries)
- [Don't call APIs you haven't verified](#dont-call-apis-you-havent-verified)
- [Cross-platform correctness](#cross-platform-correctness)
- [Concurrency and TOCTOU](#concurrency-and-toctou)
- [Guard missing and optional state](#guard-missing-and-optional-state)
- [One value, one place; small changes](#one-value-one-place-small-changes)
- [Treat facts as perishable — cite a re-checkable source](#treat-facts-as-perishable--cite-a-re-checkable-source)
- [The blind spots: what "done" hides](#the-blind-spots-what-done-hides)
- [Self-review before you push](#self-review-before-you-push)
- [Authoring the PR](#authoring-the-pr)
- [Pre-done checklist](#pre-done-checklist)

## Understand before you change

Read the whole flow the change touches before you touch it — the function, its callers, the
data that reaches it. The smallest diff in the wrong place is not a small change; it is a second
bug on top of the first. Laziness that skips comprehension to ship a short diff is the dangerous
kind: it looks efficient and ships a confident wrong fix.

Before writing, climb the reuse ladder: does this need to exist at all (speculative = skip it);
is there already a helper, type, or pattern in this codebase that does it; does the stdlib or an
already-installed dependency cover it; can it be one line. The first solution that works *once
you actually understand the problem* is the right one.

## Fix the root cause, not the symptom

A bug report names a symptom. The fix belongs at the root. Before you edit the one path the
ticket names, grep every caller of the function you are about to change — the lazy fix and the
correct fix are the same fix: **one guard at the shared chokepoint is a smaller diff than a
guard in every caller, and it is the only version that doesn't leave the sibling callers still
broken.** When a produced dev skill patches code, make "find where all callers route through"
an explicit step, not an afterthought.

## Every fix leaves a regression test

This is the practice that turns a fixed bug into a *non-recurring* bug, and it is the one AI-
assisted work skips most. Repeatedly in the survey a fix shipped, the bug came back, and a later
commit had to "harden X **and add regression tests**." Pay the test the first time.

The loop, in order:

1. **Reproduce** — a failing test that fails for the reason the bug exists, not an incidental one.
2. **Root-cause fix** — at the chokepoint (previous section).
3. **Green** — the new test passes, the existing suite still passes.
4. **Keep the test** — it is the guarantee the bug cannot silently return.

A fix without a test is a bug scheduled to return. Keep the check minimal — one runnable
assertion that fails if the logic breaks (see this repo's `tests/test_security_boundaries.py`,
which pins each hardening fix with a focused regression test). No frameworks or fixtures the
change doesn't need; YAGNI applies to tests too.

## Validate at trust boundaries

**The single largest fix category (12 of 84).** AI-generated code is optimistic: it assumes
inputs are well-formed, paths stay inside the sandbox, and archives are benign. Treat every
system boundary as hostile.

- **Paths:** never trust a path from config, user input, or an archive. Resolve and contain it —
  `(root / candidate).resolve().relative_to(root.resolve())` rejects `../../escape` and absolute
  paths; a bare `exists()` check passes them straight through. (This repo's `_dep_safe()` in
  `scripts/quick_validate.py` and `file_policy.py` are the canonical form.)
- **Archives:** a zip entry named `../../etc/passwd` is zip-slip — validate each extracted path
  against the destination root before writing. ("zip slip" was a real fix here.)
- **Parsing:** reject malformed input loudly instead of best-effort guessing. "Skip malformed"
  and "add validation for overwrite edge cases" both came from real review findings — fail fast
  with a clear message at the boundary rather than propagating half-parsed state inward.

## Don't call APIs you haven't verified

AI's most distinctive own-goal: calling a method, flag, or field that does not exist because it
*sounds* like it should. The survey's sharpest example — code called `timeout_members` (plausible,
nonexistent) when the real API was `moderate_members`. Confident, wrong, and invisible until
runtime.

Before calling into a library or platform API you did not just read, confirm the signature
exists — check the installed version's docs or source, not your memory of how similar APIs look.
When a produced skill generates code against an external API, have it verify symbols against the
actual installed version rather than assuming.

## Cross-platform correctness

**8 of 84.** If a skill runs on both Windows and POSIX, the gap bites. The recurring ones:

- **Path separators in output:** Python's list/`repr()` formatting doubles backslashes —
  `f"{paths}"` renders `C:\foo` as `C:\\foo`. Join explicitly: `", ".join(paths)`. (This was a
  live Windows CI failure in this repo.)
- **Normalize for comparison:** normalize disk paths to POSIX form before comparing or storing
  (`Path.as_posix()`), as `dependency_graph.py` had to.
- **Be explicit:** pass `encoding="utf-8"` on every text read/write (don't inherit the platform
  default); never hardcode `/` or `\` — use `pathlib` / `os.path.join`.
- **Type/version floor:** if the project declares a Python floor, honor it. PEP 604 `X | Y`
  unions are 3.10+ only; on a 3.8 floor use `Optional[X]` / `Union[X, Y]`. Pin one type-checker
  config, not two with conflicting `pythonVersion`. (Both were real fixes here.)

Run CI on the matrix you claim to support — a Windows + Ubuntu matrix catches these before merge.

## Concurrency and TOCTOU

**8 of 84, and the subtlest.** AI code gets the happy path right and the interleaving wrong.

- **Check-then-act is a race.** Between `if not exists` and `create`, another actor acts. Prefer
  atomic operations, or a lock scoped to the exact resource. "tags TOCTOU" and a "db timeout race"
  were both real fixes.
- **Scope locks tightly.** A global lock is correct but kills throughput; a per-resource lock is
  what you usually want. If you take the cheap global lock deliberately, say so and name the
  upgrade path in a comment.
- **Bound every wait.** Unbounded waits hang; make timeouts configurable, and treat a timeout as
  a handled outcome, not a crash. ("bound startup guild-sync with a configurable timeout" was the
  fix for exactly this.)

## Guard missing and optional state

**5 of 84.** A missing optional key should fall back to a sensible default — it must not silently
disable the feature or throw. The canonical bug here: a missing `"enabled"` config key *disabled*
a whole subsystem instead of defaulting to on. Read optional state with an explicit default
(`cfg.get("enabled", default)`), and when a value is genuinely required, fail at startup with a
message that names what's missing — not with a `KeyError` three layers deep at runtime.

## One value, one place; small changes

**Multi-location drift is the #2 fix category (10 of 84):** version numbers out of lockstep,
stale dependency counts, a changelog contradicting itself, a feature added but never wired into
the manifest. The defense is structural: keep a fact in exactly one place, or add a check that
enforces agreement across the places it must live (this repo's version-consistency pre-commit
check exists because the four version locations drifted). If you can't single-source it, test it.

Keep changes small — it is the highest-leverage review practice there is, and it is measured:

- SmartBear's study of ~2,500 reviews over 3.2M lines of code at Cisco found defect discovery is
  strongest at **200–400 lines reviewed per session** and collapses past a rate of ~500 LOC/hour;
  a review in that range yields **70–90% defect discovery**. (SmartBear, *Best Practices for Peer
  Code Review* / Cisco case study — [PDF](https://static1.smartbear.co/support/media/resources/cc/book/code-review-cisco-case-study.pdf).)
- Google's engineering practices put a typical change at **~100 lines** and call 1000 "too large":
  small changes are reviewed faster and more thoroughly, because reviewers burn out on large
  diffs and skim. ([google/eng-practices — small CLs](https://github.com/google/eng-practices/blob/master/review/developer/small-cls.md);
  *Software Engineering at Google*, ch. 9 — [abseil.io](https://abseil.io/resources/swe-book/html/ch09.html).)

The links are not decoration: these numbers are a snapshot, and the practice of citing a
source you can re-open is itself the subject of the next section. A produced dev skill should
prefer many small, self-contained commits/PRs over one large one.

## Treat facts as perishable — cite a re-checkable source

Every concrete fact a skill or its docs encodes — a version number, an API shape, a CLI flag,
a price, a model ID, a benchmark figure — is a snapshot of the world on the day it was written.
The world moves; the snapshot does not. A guidance file that states "the API takes `budget_tokens`"
with no link becomes confidently wrong the day the API renames it, and nothing in the file tells
the reader it has gone stale.

The defense is the link. **Citing a source is not an academic nicety — it is the mechanism by
which a stale fact gets caught and corrected.** When you encode a perishable fact:

- **Link the authoritative source** next to the claim, so a reader can re-open it and check
  whether the fact still holds instead of trusting your snapshot. (That is why the stats above
  carry URLs, not just names.)
- **Prefer linking canonical docs over copying them.** A copied paragraph drifts from its origin
  silently; a link stays honest. Inline only the part you need, and point to the rest.
- **Date the volatile claims.** "As of 2026-10, …" tells a future reader exactly how much to trust
  it, and `model-guidance.md` in this repo exists precisely because model facts needed re-dating
  after an upgrade.
- **Re-verify against the source, not your memory**, before relying on a version-specific or
  API-specific fact — the same discipline as *Don't call APIs you haven't verified*, applied to
  prose instead of code.

A produced skill that bakes in a current fact without a source link has built in an expiry date
with no warning label.

## The blind spots: what "done" hides

The per-bug categories above are what AIs get *wrong*. These are what AIs don't *consider at all*
— the systematic omissions of a model that treats "it ran once" as "it is finished."

Start with the root one. **A model reading its own output always concludes it worked.** "Done"
after a single happy-path run is the default failure, and it is why this repo has an entire
independent-review and adversarial-completion gate (`references/independent-review.md`): the skill
does not get to certify itself complete. For a full-scale dev skill, completion means an
independent check tried to prove it *incomplete* and failed — not that the author felt satisfied.

Then the omissions that a happy-path run never surfaces — each one has bitten this repo's own
projects:

| Blind spot | What the AI skips | Anchor (real fix / repo tool) |
|---|---|---|
| **Backward compatibility & migration** | Renames a signature, schema, or config key and ignores existing callers and saved on-disk state | `scripts/migrate_skill.py`, `scripts/migrations/` exist for exactly this |
| **Reversibility / rollback** | No way to undo a destructive change; no backup before overwrite; irreversible migration | "backup retention" fix |
| **Resource lifecycle & cleanup** | Leaked file handles, temp dirs, subprocesses, locks; partial writes left on failure | "harden atomic write cleanup", "process-group / partial-directory cleanup" fixes |
| **Idempotency** | Re-running an installer / migration / patch double-applies instead of no-op-ing | "duplicate/skip patch logging in xmlpatcher" fix |
| **Observability** | Swallows errors; a crash leaves no log; messages name the failure but not the fix | "add startup crash logging", "surface task exceptions" fixes |
| **Environment assumptions** | Assumes network, admin rights, a tool on PATH, a locale/timezone — instead of detecting and degrading | `require_admin`, the claude-CLI resolver fix (wrong assumed binary layout) |
| **Secrets & config hygiene** | Hardcodes a key; doesn't validate required secrets exist at startup | global security rule — env/secret-manager only |
| **Dependency restraint** | Adds a dependency for a few lines of logic; doesn't pin or lock | the reuse ladder — stdlib / existing dep first |

A produced dev skill should treat these as part of "done," not as follow-up tickets filed after
the bug report arrives.

## Self-review before you push

The survey is full of commits like "address six CodeRabbit findings" and "resolve three code-
review bot findings post-vX" — rework that a five-minute self-pass would have caught before the
push. Make the pre-push pass part of the skill's workflow:

- Read your own diff top to bottom as if reviewing someone else's.
- Run the linters/validators and the test suite locally until green — don't let CI be your first
  reviewer.
- A red CI check is usually a missing regression test, not just a broken build — add the test.

## Authoring the PR

- **Show, don't describe.** This is the one AIs get wrong most: a PR body that lists file names and
  vague bullets ("updated the validator", "improved error handling") is not reviewable — the
  reviewer still has to reverse-engineer what actually changed. Show the change: the key hunks or a
  before→after, the content samples that prove the new behavior, the message a user now sees. Name
  *what* moved and paste the *evidence*, not just the filename. (This repo shipped
  `pr-description: show, don't describe` and "require content samples in what changed, not just
  names" as fixes — the lesson is earned.)
- **Lead with the problem and the why** — the diff already shows the how. Say what was broken or
  missing and what the change makes true.
- **Link the issue:** `Closes #N` so the merge closes it automatically.
- **Include a test plan:** the commands you ran and what you expect, so the reviewer can repeat it.
- **Review the full commit range**, not just the latest commit — `git diff <base>...HEAD` is the
  unit under review.
- **When the remote branch moved under you** (a bot or collaborator pushed), rebase your work onto
  the new tip rather than force-overwriting their commits.

## Pre-done checklist

Before a dev change — or a skill that makes dev changes — is "done":

- [ ] Traced the whole flow; fix is at the shared root, not one symptom path.
- [ ] A regression test reproduces the bug and now passes; the full suite is green.
- [ ] Every external input, path, and archive entry is validated and contained.
- [ ] Every external API symbol called was confirmed to exist in the installed version.
- [ ] Paths, encodings, and type syntax are correct on every platform/version claimed.
- [ ] Check-then-act replaced with atomic ops or tightly-scoped locks; waits are bounded.
- [ ] Missing optional state falls back to a default; required state fails loudly at startup.
- [ ] Facts live in one place (or a check enforces agreement); the diff is small.
- [ ] Every perishable fact (version, API, stat) carries a re-checkable source link.
- [ ] Completion was checked by trying to prove it *incomplete*, not by self-satisfaction.
- [ ] Backward-compat / migration and a rollback path considered for breaking or destructive change.
- [ ] Resources (handles, temp dirs, subprocesses, locks) cleaned up on every path; re-runs idempotent.
- [ ] Errors are surfaced and logged with actionable messages, not swallowed.
- [ ] Self-reviewed, linted, and tested locally before push.
- [ ] PR shows the change (hunks / before→after / content samples), says why, links the issue, carries a test plan.
