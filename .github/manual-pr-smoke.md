# Manual PR trigger smoke

Automatic PR checks use zero model calls. Use **Manual PR trigger smoke** for
an explicit live check of a same-repository PR targeting `main`. It tests the
candidate skill name and description against the four trusted trigger cases
and a discovery control. The maximum is five Haiku calls with no retries.

## Repository setup

1. Create a GitHub Actions environment named `pr-smoke`. Under its deployment
   branch and tag settings, allow only the `main` branch.
2. Add the `PR_SMOKE_CLAUDE_CODE_OAUTH_TOKEN` secret to that environment.
3. Set the environment variable `PR_SMOKE_ENABLED` to `true` when ready to
   allow paid runs. Keep it unset or false to disable calls.

After the workflow lands on `main`, select **Actions → Manual PR trigger smoke
→ Run workflow** and choose `main`. Enter the PR number and the full current
head SHA. Choose `AUTO` to apply the changed-path policy, or `FORCE_RUN` to
override that policy. Both the original actor and any rerun actor need
repository write access. The workflow checks the open PR, its repository,
base branch and head again just before the live check.

The Actions summary and the `manual-pr-smoke-status` artifact record the exact
commit, decision status, and planned, attempted and successfully completed
calls. USD cost covers available case metrics and excludes the discovery
control and any unreported costs. The scheduled and release canary continues
to check both Haiku and Sonnet independently.

The artifact name includes the GitHub run attempt and records the verified
Claude Code CLI version. A GitHub deployment record in
`pr-smoke-spend-ledger` reserves one attempt per PR and head SHA, including
failed or interrupted attempts. The record does not deploy any code. Keep the
reservation records so reruns and duplicate dispatches stay within the cap.
