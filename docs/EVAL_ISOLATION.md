# How evaluation runs stay separate

## Trigger tests

Each trigger case and repetition gets its own temporary project and synthetic skill command. Parallel cases have separate skill lists, and the discovery control runs in a separate project before the suite. If the control fails, the evaluator stops before scoring the cases. [Trigger runner](../skills/skill-creator/scripts/run_eval.py)

Each Claude process gets a disposable home and configuration directory. It receives a limited set of runtime variables and explicitly supplied provider credentials. Trigger tests expose only the Skill tool. Text optimization and transcript grading expose no tools. The runner supplies an empty MCP configuration and disables hooks and local Claude session persistence. These controls limit what the CLI inherits and exposes. The Claude executable still runs under the caller's operating-system account. [Process controls](../skills/skill-creator/scripts/claude_process.py) · [Claude CLI reference](https://code.claude.com/docs/en/cli-reference)

## Paired task runs

The authoring workflow gives the candidate and baseline separate agent runs with the same task, fixtures, and model. The baseline gets either the frozen prior skill or no skill. Each side writes to a separate output directory, and each model gets its own workspace. The preparation command refuses to reuse a run directory and records a run ID and model that saved grades must match. Agent dispatch and which files each executor receives are controlled by the authoring workflow and its host. [Paired execution workflow](../skills/skill-creator/SKILL.md#step-1-spawn-all-runs-with-skill-and-baseline-in-the-same-turn) · [Run preparation and grading](USER_GUIDE.md#grade-paired-authoring-runs)

## What leaves the run

Live calls send the inputs needed for the model task to Claude. The front end writes results and reports, and `--save-transcripts` also retains the captured stream. Those files can contain prompts, paths, or model output. Review retained artifacts before sharing them. For distribution archives, see [what gets packaged](SAFE_PACKAGING.md). [Report locations](USER_GUIDE.md#where-reports-go) · [Permissions and credentials](../skills/skill-creator/PERMISSIONS.md#enforced-core-boundaries)
