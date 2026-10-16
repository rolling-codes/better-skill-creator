#!/usr/bin/env bash
# Run every check this skill has: structural validation, linting, static
# analysis, then the live trigger-test suite.
#
# Usage: scripts/validate_all.sh [path/to/skill-folder]
#
# The offline checks live in this toolkit (the directory that contains the
# scripts package). They are run from there and pointed at the skill path, so
# the same script can validate skill-creator and any other skill folder.
# skill_test.py shells out to a live `claude -p` subprocess per query, so it
# is slow and needs Claude Code; that is why the pre-commit hook runs only the
# offline checks and this script is what you run before a release.
set -uo pipefail

SKILL_PATH="$(cd "${1:-.}" && pwd)"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOOLKIT="$(cd "$SCRIPT_DIR/.." && pwd)"

if command -v python3 >/dev/null 2>&1; then
    PY=python3
elif command -v python >/dev/null 2>&1; then
    PY=python
else
    echo "python3 is not on PATH" >&2
    exit 1
fi

fail=0

run_module() {
    local label="$1"; shift
    echo "== ${label} =="
    ( cd "$TOOLKIT" && "$PY" -m "$@" "$SKILL_PATH" )
    local rc=$?
    # 0 = clean, 2 = warnings/notes only. Anything else is a real failure.
    if [ $rc -ne 0 ] && [ $rc -ne 2 ]; then
        fail=1
    fi
    echo
}

run_module "quick_validate.py" scripts.quick_validate
run_module "lint.py"           scripts.lint
run_module "static_analysis.py" scripts.static_analysis
run_module "review_gate.py"    scripts.review_gate

echo "== skill_test.py =="
if command -v claude >/dev/null 2>&1; then
    # Run as a module from the toolkit. Invoking the file by path puts scripts/
    # on sys.path and used to shadow the stdlib types module.
    ( cd "$TOOLKIT" && "$PY" -m scripts.skill_test "$SKILL_PATH" ) || fail=1
else
    echo "SKIPPED: the \`claude\` CLI is not on PATH, so trigger tests cannot run."
fi

exit $fail
