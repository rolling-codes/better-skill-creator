# Better Skill Creator Setup

Better Skill Creator is a standalone meta-skill for Claude Code, packaged as a
plugin. The plugin itself is named `skill-creator`, published through a local
marketplace named `skill-creator-local`.

## Requirements

- **Python 3.12+** (supported floor; matches `pyproject.toml` and CI)
- **PyYAML** — `pip install -r requirements.txt` (or `pip install pyyaml`)
- **Claude Code** — installed and authenticated, with subprocess access
  (`claude -p`) for live evals (`run_eval.py`, `run_loop.py`,
  `improve_description.py`, and `skill_test.py --grade-transcript`)

## Install

### From GitHub (recommended)

Inside Claude Code:

```
/plugin marketplace add rolling-codes/better-skill-creator
/plugin install skill-creator@skill-creator-local
```

Or from a shell:

```bash
claude plugin marketplace add rolling-codes/better-skill-creator
claude plugin install skill-creator@skill-creator-local
```

### From a local checkout

```bash
git clone https://github.com/rolling-codes/better-skill-creator
cd better-skill-creator
pip install -r requirements.txt
claude plugin marketplace add .
claude plugin install skill-creator@skill-creator-local
```

Restart Claude Code (or run `/reload-plugins`). Skills register at session start.

## Verify

The skill has no slash command. It loads from its description, so verify it by
asking for something in scope:

```
Help me create a new Claude Code skill for reviewing SQL queries.
```

Claude should consult `skill-creator` and start the intent interview.

To verify the tooling separately, from the repo root:

```bash
python bsc.py doctor
python bsc.py check skills/skill-creator
```

Or run the offline validators from `skills/skill-creator/`:

```bash
cd skills/skill-creator
python3 -m scripts.quick_validate .
python3 -m scripts.lint .
python3 -m scripts.static_analysis .
```

`quick_validate` prints `Skill is valid!` on success. `lint` and
`static_analysis` exit 0 when clean, 2 when they have warnings or notes only,
and 1 when they find an error that should block packaging.

## Optional: pre-commit hook

If you are developing the skill itself, install the hook so every commit that
touches it is validated first:

```bash
python bsc.py hooks install
```

This copies the hook into Git's resolved hooks directory (including worktrees
and submodules). Prefer this over copying `scripts/hooks/pre-commit` by hand.

## Note on built skills

Skills you create or audit with this plugin may have their own prerequisites.
Those are the responsibility of the individual skill, not of skill-creator.
