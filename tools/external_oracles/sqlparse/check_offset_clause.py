#!/usr/bin/env python3
"""Lap 4001 oracle — sqlparse #842: with `reindent_aligned=True` the SQL:2008
`OFFSET ... FETCH NEXT n ROWS ONLY` paging clause must stay on one line.

Property-based, never golden-output: the checker computes nothing about the
fix's indentation arithmetic, so any alignment that keeps the clause together
passes (clause on its own line, or appended to the ORDER BY line — the issue
allows either). What it does pin:

  * the clause text sits in exactly one line, and that line is the ORDER BY
    line or the line right after it, and is the last line;
  * no clause keyword is left orphaned on a line of its own;
  * the lines before the clause do not move;
  * no token is dropped, added, duplicated or reordered (whitespace- and
    case-insensitive) — this is what stops a "fix" that lines the clause up
    by swallowing part of it;
  * the two control cases (LIMIT, JOIN ... ON / AND) keep their base output.

Usage: check_offset_clause.py <cases.json>   (cwd MUST be the candidate worktree)
Exit 0 = PASS, 1 = FAIL, 2 = harness error.
"""

import json
import os
import sys

sys.path.insert(0, os.getcwd())  # the worktree's package, never an installed copy

try:
    import sqlparse  # noqa: E402
except ImportError as exc:  # a harness problem, not a candidate defect
    print("harness error: cannot import sqlparse from %s (%s)" % (os.getcwd(), exc))
    sys.exit(2)


def check_case(case):
    """Return the list of failure strings for one case ([] = pass)."""
    sql = case["sql"]
    out = sqlparse.format(sql, **case["options"])
    lines = out.split("\n")
    fails = []

    # Content guard first: whitespace- and case-insensitive token sequence.
    if "".join(out.split()).lower() != "".join(sql.split()).lower():
        fails.append("content changed:\n    in : %r\n    out: %r" % (sql, out))

    if case["kind"] == "exact_lines":
        if lines != case["expect_lines"]:
            fails.append("lines %r != expected %r" % (lines, case["expect_lines"]))
        return fails

    prefix = case["prefix_lines"]
    if lines[:len(prefix)] != prefix:
        fails.append("leading lines %r != %r" % (lines[:len(prefix)], prefix))

    for orphan in case["orphan_forbidden"]:
        if any(line.strip() == orphan for line in lines):
            fails.append("%r is left orphaned on its own line: %r" % (orphan, lines))

    clause = case["clause"]
    owners = [i for i, line in enumerate(lines) if clause in line]
    if len(owners) != 1:
        fails.append("clause %r is not contained in exactly one line (found in %d): %r"
                     % (clause, len(owners), lines))
    else:
        if owners[0] != len(lines) - 1:
            fails.append("clause is not the last line: %r" % (lines,))
        order = [i for i, line in enumerate(lines)
                 if line.lstrip().startswith(case["order_line_prefix"])]
        if len(order) != 1:
            fails.append("expected exactly one line starting with %r, found %d: %r"
                         % (case["order_line_prefix"], len(order), lines))
        elif owners[0] not in (order[0], order[0] + 1):
            fails.append("clause line %d is neither the %r line (%d) nor the line after it"
                         % (owners[0], case["order_line_prefix"], order[0]))
    return fails


def main(argv):
    if len(argv) != 2:
        print("harness error: usage: %s <cases.json>" % argv[0])
        return 2
    with open(argv[1]) as f:
        data = json.load(f)

    pkg = os.path.realpath(sqlparse.__file__ or "")
    cwd = os.path.realpath(os.getcwd())
    if not pkg.startswith(cwd + os.sep):
        print("harness error: imported sqlparse is %s, outside the worktree %s"
              % (pkg, cwd))
        return 2

    failures = []
    for case in data["cases"]:
        fails = check_case(case)
        print("%-4s %s" % ("ok" if not fails else "FAIL", case["name"]))
        failures += ["%s: %s" % (case["name"], f) for f in fails]

    for f in failures:
        print("FAIL: %s" % f)
    if failures:
        return 1
    print("PASS: %d cases — paging clause intact, controls unchanged"
          % len(data["cases"]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
