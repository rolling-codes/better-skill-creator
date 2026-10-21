# Description Optimization

The `description` field in SKILL.md frontmatter is the primary mechanism that
decides whether Claude invokes a skill at all, so it is worth tuning
deliberately rather than by feel. Read this after creating or improving a
skill, when the user asks why a skill is or is not triggering, or before a
release.

Requires subprocess access to `claude -p`. In environments without it (see
`references/environments.md`) this loop cannot run, and you should tune the
description by hand and say so.

## Contents

- Step 1: Generate trigger eval queries
- Step 2: Review with user
- Step 3: Run the optimization loop
- How skill triggering works
- Step 4: Apply the result

---

### Step 1: Generate trigger eval queries

Create 20 eval queries — a mix of should-trigger and should-not-trigger. Save as JSON:

```json
[
  {"query": "the user prompt", "should_trigger": true},
  {"query": "another prompt", "should_trigger": false}
]
```

The queries must be realistic — something a real user would actually type. Not abstract requests, but concrete and specific with the kind of detail users include: file paths, personal job context, column names, company names, URLs, a little backstory. Some might be lowercase, abbreviated, or casually phrased. Mix lengths and focus on edge cases rather than clear-cut cases (the user reviews them before the loop runs).

**Bad:** `"Format this data"`, `"Extract text from PDF"`, `"Create a chart"`

**Good:** `"ok so my boss just sent me this xlsx file (its in my downloads, called something like 'Q4 sales final FINAL v2.xlsx') and she wants me to add a column that shows the profit margin as a percentage. The revenue is in column C and costs are in column D i think"`

For **should-trigger** (8–10): different phrasings of the same intent — some formal, some casual. Include cases where the user doesn't name the skill or file type explicitly, uncommon use cases, and cases where this skill competes with another but should win.

For **should-not-trigger** (8–10): the most valuable are near-misses — queries sharing keywords or concepts with the skill but actually needing something different. Think adjacent domains, ambiguous phrasing where a naive keyword match would trigger but shouldn't, and cases where the query touches something the skill does but in a context where another approach is more appropriate. The key thing to avoid: don't make should-not-trigger queries obviously irrelevant — "write a fibonacci function" as a negative test for a PDF skill is too easy and tests nothing.

### Step 2: Review with user

Present the eval set to the user for review using the HTML template:

1. Read the template from `assets/eval_review.html`
2. Replace the placeholders:
   - `__EVAL_DATA_PLACEHOLDER__` → the JSON array of eval items (no quotes around it — it's a JS variable assignment)
   - `__SKILL_NAME_PLACEHOLDER__` → the skill's name
   - `__SKILL_DESCRIPTION_PLACEHOLDER__` → the skill's current description
3. Write to a temp file (e.g., `/tmp/eval_review_<skill-name>.html`) and open it: `open /tmp/eval_review_<skill-name>.html`

**Headless / remote environments:** if `open` is unavailable, print the output path and
open the file manually. The `~/Downloads` lookup is an example — the actual export path
is printed to stdout; use that path directly.

4. The user can edit queries, toggle should-trigger, add/remove entries, then click "Export Eval Set"
5. The file downloads to `~/Downloads/eval_set.json` — check the Downloads folder for the most recent version in case there are multiple (e.g., `eval_set (1).json`)

This step matters — bad eval queries lead to bad descriptions.

### Step 3: Run the optimization loop

Tell the user: "This will take some time — I'll run the optimization loop in the background and check on it periodically."

Save the eval set to the workspace, then run in the background:

```bash
python -m scripts.run_loop \
  --eval-set <path-to-trigger-eval.json> \
  --skill-path <path-to-skill> \
  --model <model-id-powering-this-session> \
  --max-iterations 5 \
  --verbose
```

Use the model powering the current session — a Haiku-class model for fast iterations, Sonnet-class for final tuning — so the triggering test matches what the user actually experiences.

While it runs, periodically tail the output to give the user updates on which iteration it's on and what the scores look like.

This handles the full optimization loop automatically. It splits the eval set into three stratified sets — 60% train, 20% validation, 20% held-out test — evaluates the current description (running each query 3 times to get a reliable trigger rate), then calls Claude to propose improvements based on what failed on train. Candidate selection uses the validation score, not the held-out score, so the final test set is never seen during optimization. When done, it runs the held-out set exactly once on the selected best candidate, opens an HTML report in the browser, and returns JSON with `best_description` and `held_out_score`.

The held-out result is reported for information. If it is substantially lower than the validation score, the description may have overfit to the validation set — collect more queries and re-run rather than tuning further against the same held-out set.

### How skill triggering works

Understanding the triggering mechanism helps design better eval queries. Skills appear in Claude's `available_skills` list with their name + description, and Claude decides whether to consult a skill based on that description. The important thing to know is that Claude only consults skills for tasks it can't easily handle on its own — simple, one-step queries like "read this PDF" may not trigger a skill even if the description matches perfectly, because Claude can handle them directly with basic tools. Complex, multi-step, or specialized queries reliably trigger skills when the description matches.

This means your eval queries should be substantive enough that Claude would actually benefit from consulting a skill. Simple queries like "read file X" are poor test cases — they won't trigger skills regardless of description quality.

### Step 4: Apply the result

Take `best_description` from the JSON output and update the skill's SKILL.md frontmatter. Show the user before/after and report the scores.
