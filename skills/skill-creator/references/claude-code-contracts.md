# Verified Claude Code contracts

Checked against Anthropic's official documentation on 2026-10-22. The local
verification used Claude Code 2.1.308; this is evidence for that installation,
not a guarantee about future releases.

| Contract | Implementation and verification |
|---|---|
| Claude Code accepts legacy `.claude/commands/` files as skills. | The trigger evaluator retains its synthetic command/control-query discovery mechanism. |
| Skill `name` can be omitted; `description` can fall back to the first nonempty body line. `when_to_use` extends the description. | Adjacent-skill candidate discovery uses these defaults locally; strict portable-skill validators remain unchanged. |
| `sonnet[1m]` and `opus[1m]` are supported model forms. | Model argument validation permits a literal `[1m]` suffix and passes the identifier unchanged to Claude. |
| Family aliases may change the resolved model over time. | Comparisons match requested identifiers and warn on aliases. Pin a full model ID for repeatability; matching an alias does not prove identical resolved models. |
| `--tools` restricts built-ins; `--allowedTools` controls permission prompts. | Eval exposes Skill, pre-approves it, disables configured hooks, and uses strict empty MCP configuration. |

Primary sources:

- [Claude Code skills and frontmatter](https://code.claude.com/docs/en/skills#frontmatter-reference)
- [CLI reference](https://code.claude.com/docs/en/cli-reference)
- [Model aliases and configuration](https://code.claude.com/docs/en/model-config#model-aliases)

## Verification boundaries

`bsc.py doctor` checks the installed version, required evaluation flags advertised
by `--help`, and plugin schemas without model calls. This catches an incompatible
CLI interface; it does not prove authentication, billing, model access, or successful
skill invocation. Tests additionally exercise stream handling through fake processes.

The credentialed control query and canary are the live discovery checks. During
this review neither supported credential environment variable was provided, so
no live invocation was verified and no account login profile was copied.

New eval reports record `trigger_threshold`. Known threshold mismatches block
baseline comparisons before calls; older reports without that metadata remain
readable with an explicit warning. Configured-default sentinels are not explicit
model identities for model-aligned report comparison.
