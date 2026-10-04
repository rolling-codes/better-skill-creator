# lessons/fixes.md — False-Pass Gate Pattern

## The pattern

Quality gates exist in this repo as Python scripts (`review_gate.py`, `quick_validate.py`, `lint.py`) and as a type checker (`pyright`). For most of the project's history these gates were invoked manually or in CI — but the **pre-commit hook only ran `quick_validate` and `lint`**. As a result, commits could and did ship with:

- 31 pyright type errors (H4 + M9, all present since v3.2.0, caught only by the independent audit)
- `review_gate.py` never running automatically despite being the primary review enforcement tool
- Version strings drifting between `plugin.json` and `skill.yaml` undetected

## What shipped because of it

| Finding | Root cause | First caught by |
|---------|-----------|-----------------|
| H4: ~40 Pylance false import errors | Duplicate nested `pyrightconfig.json`; hook never ran pyright | External audit of v3.2.0 |
| M9: 31 latent type errors | None/unbound access, ClassVar annotation conflicts | External audit of v3.2.0 |
| M11: version drift `3.1.0` vs `3.2.0` | Hook never checked version consistency | External audit of v3.2.0 |

## The fix (applied in this PR)

The pre-commit hook at `scripts/hooks/pre-commit` now also runs:

1. **`review_gate.py`** — exits 0 (no review), 2 (warnings), or 1 (blocking errors). Commit blocked on errors.
2. **`pyright`** — runs against the repo root config. Skipped gracefully if pyright is not installed (warns only).
3. **Version consistency check** — extracts the version field from `.claude-plugin/plugin.json` and `skills/skill-creator/skill.yaml`; blocks commit if they differ.

## How to verify the gate fires

```bash
# 1. Install the hook (one-time from repo root):
cp skills/skill-creator/scripts/hooks/pre-commit .git/hooks/pre-commit
chmod +x .git/hooks/pre-commit

# 2. Introduce a deliberate version mismatch and confirm it blocks:
#    Edit plugin.json "version" to "9.9.9", then:
git add .claude-plugin/plugin.json
git commit -m "test" --dry-run 2>&1 | grep "version mismatch"
git restore .claude-plugin/plugin.json

# 3. Introduce a pyright error and confirm it blocks:
#    Add `x: int = "bad"` to any .py file, stage it, and attempt a commit.
```

## Standing rule

Any new validation script added to this repo should be wired into the pre-commit hook in the same PR that introduces it. The two-line addition (`validate_step && exit 1`) takes less time than a one-line audit finding.
