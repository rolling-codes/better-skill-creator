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

Queries must be realistic: concrete, specific, with the kind of detail a real user would include (file paths, job context, casual phrasing, typos). Mix formal and casual, short and long. Focus on edge cases rather than clear-cut cases — the user will review them anyway.

For **should-trigger** (8–10): different phrasings of the same intent, including cases where the user doesn't name the skill or file type explicitly.

For **should-not-trigger** (8–10): the most valuable are near-misses — queries sharing keywords or concepts with the skill but actually needing something different. Don't use obviously irrelevant negatives ("write a fibonacci function" for a PDF skill tests nothing). 3–5 iterations is typically sufficient to converge.

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

This handles the full optimization loop automatically. It splits the eval set into 60% train and 40% held-out test, evaluates the current description (running each query 3 times to get a reliable trigger rate), then calls Claude to propose improvements based on what failed. It re-evaluates each new description on both train and test, iterating up to 5 times. When it's done, it opens an HTML report in the browser showing the results per iteration and returns JSON with `best_description` — selected by test score rather than train score to avoid overfitting.

### How skill triggering works

Understanding the triggering mechanism helps design better eval queries. Skills appear in Claude's `available_skills` list with their name + description, and Claude decides whether to consult a skill based on that description. The important thing to know is that Claude only consults skills for tasks it can't easily handle on its own — simple, one-step queries like "read this PDF" may not trigger a skill even if the description matches perfectly, because Claude can handle them directly with basic tools. Complex, multi-step, or specialized queries reliably trigger skills when the description matches.

This means your eval queries should be substantive enough that Claude would actually benefit from consulting a skill. Simple queries like "read file X" are poor test cases — they won't trigger skills regardless of description quality.

### Step 4: Apply the result

Take `best_description` from the JSON output and update the skill's SKILL.md frontmatter. Show the user before/after and report the scores.
