# Blind judging and evaluation cost

For a paired authoring evaluation, copy the original task into the case metadata as `prompt`. Use the same rubric and judge settings on both completed runs. Run the local check first. The blind judge takes only residual assertions and screened evidence. Supply the candidate and prior skill names with repeated `--producer` flags, including any aliases used in the evidence. These terms stay local. Add `--transcript` when the rubric needs process evidence. [Commands](USER_GUIDE.md#grade-paired-authoring-runs)

Model judges run with fresh CLI context and no tools. They receive the task, rubric, and screened text evidence. The framework excludes known provenance and cost files, strips recognized runtime metadata from JSONL events, and keeps run IDs and execution models in the local report. The original transcript still determines completeness. Style and wording may allow a judge to infer authorship. For saved transcript grading, put any skill-specific grading criteria in `tests/expected_behavior.yaml`. The blind CLI uses its built-in instructions in place of skill-supplied grader prompts.

If known identity clues occur in meaningful evidence, the framework marks the affected judgment undetermined and records it for human review. Binary and inaccessible evidence also go to human review because the current judge has no restricted artifact inspection tools. Preserve original files for that review. Resolve those judgments before claiming a measured improvement. Legacy model grades without blinding metadata have unknown blinding status.

Pairwise comparison is optional. The compare command shuffles A/B presentation and saves the mapping locally. Its default is one call. Use `--swap-audit` when you authorize a second call in reverse order. Disagreement is inconclusive.

Preflight counts planned agent dispatches. Reports can also include `attempt_usage` rows for individual Claude CLI attempts, grouped by stage. A null usage value means the attempt supplied no measurements. Missing cache and cost fields mean the CLI did not report them. Execution metrics supplied by the authoring host remain separate from CLI attempts. These fields do not establish the billed total.

The optimizer stops when a rewrite repeats an already evaluated description. It still runs the held-out check in three-way mode. `--compact-history` opts into a smaller rewrite prompt. The full prompt remains the default pending a budgeted quality comparison.
