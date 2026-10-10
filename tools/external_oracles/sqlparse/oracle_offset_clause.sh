#!/bin/sh
# Nightshift lap 4001 oracle driver — sqlparse #842
# (`reindent_aligned` splits `OFFSET ... FETCH NEXT n ROWS ONLY`).
#
# Native verify commands carry no env and run with cwd = the candidate
# worktree, so everything here is resolved from $PWD. The lap's prepare step
# (`uv run --group dev pytest tests/`) creates ./.venv inside that worktree and
# uv installs sqlparse EDITABLE, so the checker imports the candidate sources
# (it asserts that, and reports a harness error otherwise).
#
# Exit 0 = PASS (GREEN gate), 1 = FAIL (RED), 2 = harness error.
set -u
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
if [ -x ./.venv/bin/python ]; then
    exec ./.venv/bin/python "$here/check_offset_clause.py" "$here/cases.json"
fi
exec uv run --group dev python "$here/check_offset_clause.py" "$here/cases.json"
