#!/usr/bin/env python3
"""Instance-authoring preflight: refuse to bank an instance whose CODE_PATHS
view can never cover the fix or fit the implementer prompt.

    python3 tools/preflight_instance.py <task-file> <env-file> <repo-at-base>

Exits 0 printing the numbers when the instance is authorable; exits non-zero
printing the specific reason when any of:

  (a) a file matched by SCOPE_PATHS (space-separated globs; the files a fix
      must be allowed to touch) is not matched by any CODE_PATHS glob;
  (b) the summed checkout view size of the CODE_PATHS matches exceeds
      CHECKOUT_CHAR_BUDGET (the implementer prompt would be truncated);
  (c) CODE_PATHS matches zero files in the repo.

The CODE_PATHS/SCOPE_PATHS glob syntax, dot-directory exclusion, de-duplication
and block sizing are the implementer checkout's own — this reuses
`lap.checkout_files` rather than restating them, so the preflight and the lap
can never disagree. The task-text check (literal 'TASK-' markers) is
deliberately out of scope (ponytail: the two wasted laps were both (a)).
"""

import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "..", "src"))

import lap  # noqa: E402

# Never truncate while measuring: checkout_files() stops AT the budget, so a
# huge sentinel returns every matched block and the total is honest.
_NO_BUDGET = 1 << 62


def load_env(path):
    """Parse `export KEY=value` lines; one layer of matching quotes stripped."""
    env = {}
    with open(path) as f:
        for line in f:
            m = re.match(r"\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)=(.*)", line)
            if not m:
                continue
            k, v = m.group(1), m.group(2).strip()
            if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
                v = v[1:-1]
            env[k] = v
    return env


def _view(globs, repo):
    """The exact checkout view for `globs`, built by the lap's own function."""
    saved = lap.CODE_PATHS
    try:
        lap.CODE_PATHS = globs
        return lap.checkout_files(repo, _NO_BUDGET)
    finally:
        lap.CODE_PATHS = saved


def _rels(view):
    # block = "=== rel ===\n<text>"; its first line names the file.
    return [b.split("\n", 1)[0][4:-4] for b in view]


def preflight(task_file, env_file, repo):
    """(exit code, message). `task_file` is accepted for interface stability;
    the only checks are (a)-(c) (see the module docstring)."""
    env = load_env(env_file)
    code_globs = [p.strip() for p in env.get("CODE_PATHS", "*.py").split(",") if p.strip()]
    scope_globs = env.get("SCOPE_PATHS", "").split()
    budget = int(env.get("CHECKOUT_CHAR_BUDGET", "100000"))

    code_view = _view(code_globs, repo)
    covered = set(_rels(code_view))
    if not covered:
        return 1, "FAIL code_paths: no file in %s matches CODE_PATHS=%r" % (repo, code_globs)

    size = sum(len(b) for b in code_view)
    if size > budget:
        return 1, ("FAIL budget: checkout view is %d chars > "
                   "CHECKOUT_CHAR_BUDGET=%d" % (size, budget))

    scope_files = set(_rels(_view(scope_globs, repo))) if scope_globs else set()
    missed = sorted(scope_files - covered)
    if missed:
        return 1, ("FAIL scope: SCOPE_PATHS file(s) not matched by any CODE_PATHS "
                   "glob: %s" % ", ".join(missed))
    return 0, ("ok CODE_PATHS=%d file(s) view=%d/%d chars SCOPE_PATHS=%d file(s)"
               % (len(covered), size, budget, len(scope_files)))


def main(argv):
    if len(argv) != 3:
        sys.stderr.write("usage: preflight_instance.py <task-file> <env-file> <repo-at-base>\n")
        return 2
    code, msg = preflight(*argv)
    print(msg)
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
