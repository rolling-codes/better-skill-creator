# Better Skill Creator Setup

Better Skill Creator is a standalone meta-skill for Claude Code, packaged as a
plugin. The plugin itself is named `skill-creator`, published through a local
marketplace named `skill-creator-local`.

## Requirements

- Claude Code with subprocess access (`claude -p`), needed by `run_eval.py`,
  `run_loop.py`, `improve_description.py` and `skill_test.py --grade-transcript`
- Python 3.8 or newer
- PyYAML, for the validation and packaging scripts

## Install

From a local checkout:

```bash
git clone https://github.com/rolling-codes/better-skill-creator
cd better-skill-creator
pip install -r requirements.txt
claude plugin marketplace add .
claude plugin install skill-creator@skill-creator-local
```

Or from GitHub, inside Claude Code:

```
/plugin marketplace add rolling-codes/better-skill-creator
/plugin install skill-creator
```

Restart Claude Code (or run `/reload-plugins`). Skills register at session start.

## Verify

The skill has no slash command. It loads from its description, so verify it by
asking for something in scope:

```
Help me create a new Claude Code skill for reviewing SQL queries.
```

Claude should consult `skill-creator` and start the intent interview.

To verify the tooling separately, run the validator against the skill itself:

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
touches it is validated and linted first:

```bash
cp skills/skill-creator/scripts/hooks/pre-commit .git/hooks/pre-commit
chmod +x .git/hooks/pre-commit
```

## Note on built skills

Skills you create or audit with this plugin may have their own prerequisites.
Those are the responsibility of the individual skill, not of skill-creator.
