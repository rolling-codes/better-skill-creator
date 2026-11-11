# Contributing to Better Skill Creator

Thank you for contributing. This project is maintained by one person in limited spare time, so a focused, well-scoped contribution makes all the difference.

## Before you start

Open an issue first. Describe the problem you are solving and roughly how you plan to solve it. This avoids wasted work if the approach doesn't fit the project's direction, and it gives me a chance to flag anything that would block a merge.

For small typo fixes or broken-link corrections, you can skip the issue and go straight to a PR.

## What makes a good contribution

- **One thing per PR.** A PR that fixes a single bug or adds a single feature is easy to review and easy to revert if something goes wrong. Bundling unrelated changes slows everything down.
- **Reproduce the problem first.** If you're fixing a bug, include the smallest possible repro case as a test before you touch any other code.
- **Match the existing style.** Read a few nearby files before writing new ones. Naming, structure, and docstring style should feel consistent with what's already there.
- **Cover what you change.** New behaviour needs at least one test. Aim for the minimum test that would catch a regression — not a full suite for a one-line fix.
- **Keep the diff small.** Avoid reformatting lines you aren't changing. Avoid speculative refactoring outside the scope of the fix.

## Running the checks locally

From the repo root:

```bash
pip install -r requirements.txt
cd skills/skill-creator
python -m pytest -q
python -m scripts.source_rules .
python -m scripts.doc_sync .
```

All four should pass before you open a PR. If any fail on `main` already, note that in your PR — don't fix pre-existing failures in the same commit.

## Commit messages

```
<type>: <short description>
```

Types: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`. Keep the subject line under 72 characters. If the why isn't obvious from the code, add a blank line and a short paragraph below.

## Pull request checklist

- [ ] Issue opened and linked (unless it's a trivial fix)
- [ ] Tests added or updated for the change
- [ ] `python -m pytest -q` passes locally
- [ ] `python -m scripts.source_rules .` passes locally
- [ ] PR description explains what changed and why

## What happens after you open a PR

I review contributions when I can. Response time varies — this is a side project and real life takes priority. If you haven't heard back in two weeks, feel free to leave a comment on the PR to bump it. I will not close contributions without explanation.

If a change needs revision, I'll leave specific comments. Once everything looks good I'll merge it myself.

## Code of conduct

Be direct, be kind, assume good faith. That's it.
