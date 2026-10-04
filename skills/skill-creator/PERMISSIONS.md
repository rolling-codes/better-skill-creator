# skill-creator — Permission Boundaries

The summary `allowed-tools` list is declared in `SKILL.md` frontmatter
(that's the field `quick_validate.py` already recognized) — this file adds
the per-script risk breakdown that a flat list can't express, since
skill-creator's risk profile isn't uniform: `quick_validate.py` only reads,
while `run_eval.py` shells out to a live model.

```yaml
risk:
  level: medium
  reasons:
    - "terminal.execute spawns a live Claude subprocess with explicitly supplied provider credentials — a malformed eval prompt set could burn budget or leak context into eval transcripts"
    - "repair tools can rewrite a caller-selected SKILL.md; packaging repairs only a private copy"
    - "package_skill.py writes a new archive from a bounded snapshot that rejects links and excludes sensitive filenames"
```

## Risk rubric

Levels are assigned by this rule, not by feel — apply it to reclassify if
a script's tool list changes:

| Level      | Rule                                                                 |
| ---------- | --------------------------------------------------------------------- |
| **low**    | Only `filesystem.read`, or `filesystem.write`/`filesystem.zip` scoped to files the script itself creates/names — nothing it didn't write can be touched. |
| **medium** | `filesystem.write` to a path supplied by the caller (e.g. an existing `SKILL.md`), OR any `terminal.execute` whose subprocess is bounded (fixed command, no shell interpolation of untrusted input, timeout enforced). |
| **high**   | `network.request` to an unbounded/caller-specified destination, OR `terminal.execute` with unbounded iteration (no max_iterations-style cap) or shell interpolation of untrusted input. |

## Vocabulary

`filesystem.read`, `filesystem.write`, `filesystem.zip`, `terminal.execute` and
`network.request` below are this rubric's capability categories, not Claude Code
tool names. The SKILL.md `allowed-tools` field uses real tool names and only
pre-approves only the read-only analyzers; anything that writes
to a caller-supplied path or spawns Claude subprocesses still goes through the
normal permission prompt.

## Per-script breakdown

| Component                     | Tools needed                          | Risk   |
| ------------------------------ | -------------------------------------- | ------ |
| `quick_validate.py`             | filesystem.read                        | low    |
| `package_skill.py`              | filesystem.read, filesystem.zip        | medium |
| `aggregate_benchmark.py`        | filesystem.read                        | low    |
| `generate_report.py`            | filesystem.read, filesystem.write      | low    |
| `eval-viewer/generate_review.py`| filesystem.read, filesystem.write      | low    |
| `run_eval.py`                   | filesystem.read, terminal.execute      | medium |
| `improve_description.py`        | filesystem.read/write, terminal.execute| medium |
| `run_loop.py`                   | all of the above (orchestrates both)   | medium |

## Audit output (example)

```
skill-creator/scripts/run_loop.py

This skill can modify SKILL.md files and spawn Claude subprocesses
in a loop up to max_iterations times.
Review required before enabling in an unattended/CI context.
```

## Notes

Nothing in skill-creator currently declares `network.*` — `run_eval.py` and
`improve_description.py` reach the model only via the local `claude -p`
subprocess, using an isolated profile and explicit provider credentials rather than making direct HTTP calls. If
that changes (e.g. a future version calls the API directly), add a
`network.request` row here and reassess the risk tier.

## Enforced core boundaries

- Packaging uses `scripts/file_policy.py` to snapshot regular files before validation
  or repair. Both public entry points repair a private copy. The output is created
  exclusively, so an existing archive or symlink is never overwritten. Links,
  junctions, special files, files over 20 MiB, and source trees over 100 MiB are
  rejected. POSIX traversal uses directory descriptors and `O_NOFOLLOW`; on other
  platforms keep the source tree quiescent during packaging.
- Sensitive filenames (`.env*`, private keys, credential files) and local state
  directories are excluded. This filename policy is not a secret-content scanner:
  review the distribution manifest before sharing. Optionally provide
  `package-manifest.json` with `{"files": ["SKILL.md", "references/guide.md"]}` to
  restrict distribution to exact filenames. It cannot re-include forbidden files;
  the manifest and existing review record are retained in the archive.
- Trigger evaluations expose only `Skill`; text optimization/grading exposes no
  tools. Each model subprocess receives a disposable home/configuration directory,
  ignores user/project settings and MCP servers, disables hooks and session
  persistence, and drops unrelated environment variables. These restrictions are
  not a kernel sandbox; the Claude executable and enforced administrator policies
  remain trusted. Use a dedicated OS sandbox/account for hostile executable code.
- Live runs require an explicitly supplied `ANTHROPIC_API_KEY` or
  `CLAUDE_CODE_OAUTH_TOKEN`. Existing interactive login profiles, custom endpoints,
  plugins, and arbitrary environment settings are not copied. Never store tokens
  in skill files or commit them. Unsupported isolation flags fail the run; there
  is no fallback to an unrestricted invocation.
- `scripts/call_budget.py` enforces one shared call allowance (default 20) across
  parallel evaluations, retries, model variants, and optional grading. The optimizer
  includes both proposal and shortening calls in its worst-case estimate. Raise
  `--max-calls` explicitly after approving the estimate. Results record limit,
  attempts used, and remaining calls. This caps process attempts, not dollars or
  the model's token consumption within a single attempt.
