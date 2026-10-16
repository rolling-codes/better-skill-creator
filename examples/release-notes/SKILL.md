---
name: release-note-draft
description: >-
  Draft structured release notes from git history. Use when the user wants to write
  release notes, a changelog entry, a sprint summary, or wants to know what changed
  since a tag, branch, or previous release — even without the phrase "release notes".
  Not for publishing, tagging, or explaining a single commit in isolation; not for
  general writing that mentions versions.
allowed-tools:
  - Read
  - Bash(git describe *)
  - Bash(git log *)
  - Bash(git diff *)
  - Bash(git show *)
metadata:
  schemaVersion: "1"
---

# Release Note Draft

Turn git history into a structured, human-readable release notes draft.

## Capability

Run `git log` and `git diff` to gather commits between two refs (or from the last tag
to HEAD), group changes into standard categories, and return a Markdown draft for the
user to review. The draft is never published or pushed automatically.

## When to use

- User names a version, tag, or range: "write release notes for v2.1", "what changed
  since v1.0"
- User asks for a work summary: "summarize what changed since last release", "draft a
  changelog entry for this sprint", "what's new since the last tag"
- User wants release notes for a PR: "summarize this PR for the changelog"
- User asks about changes without release-note language: "what went in this week",
  "what changed since the last tag"

## When NOT to use

- User wants to *publish*, *tag*, or *push* a release — ask for explicit confirmation
  before any write action; do not proceed automatically
- User wants to understand what a *single specific commit* does, not summarize it
- User wants a general writing task (email, blog post, document) that mentions a version

## Workflow

1. **Identify the range.** If the user supplied a tag, branch, or SHA range, use it
   directly. If they said "last N commits", use `HEAD~N..HEAD`. If no range is given,
   run `git describe --tags --abbrev=0` to find the last tag and default to `<tag>..HEAD`.
   If there are no tags and no range, use the full log. If `git log` returns nothing,
   tell the user there is no history yet and stop — do not invent changes.
2. **Collect commits.** Run `git log --oneline <range>`. If the range covers more than
   50 commits, report the count and ask whether to summarize or continue.
3. **Inspect significant commits.** For non-trivial subjects, run
   `git show <sha>` to read the full diff and confirm what actually changed.
   Do not rely on the subject line alone.
4. **Group changes** under: **Added**, **Changed**, **Fixed**, **Removed**,
   **Security**. Omit empty categories.
5. **Write bullets** in user-facing language — what changed and why it matters, not
   the raw commit subject.
6. **Return a Markdown draft.** Label it clearly as a draft. List ambiguous or skipped
   commits at the bottom.

## Output format

```markdown
## v2.1.0 — 2026-09-08

### Added
- Users can now filter results by date range.

### Fixed
- CSV exports no longer contain duplicate rows when pagination is active.

---
*Draft — review before publishing. Skipped: abc1234 (merge commit).*
```

## Iron Law

Never invent a change that is not traceable to a commit in the supplied range. If the
history is ambiguous, omit the claim or ask — misleading release notes erode trust
faster than sparse ones.

| Rationalization | Correct behavior |
|---|---|
| "The commit subject says 'fix auth'; I'll add details about what was fixed." | Write only what the commit and its diff confirm. If the diff is unclear, write "Authentication fix (details TBD)" and flag it. |

## Reference files

- `tests/expected_behavior.yaml` — two authored behavior cases (happy path and graceful
  failure); read when uncertain about output format or handling of missing history.
