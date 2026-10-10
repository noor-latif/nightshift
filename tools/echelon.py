#!/usr/bin/env python3
"""nightshift-echelon — the free regression bank for the kernel.

Design: RESEARCH-CODING-METRICS_2026-10-08.md §3 "Regression gating for the
kernel" — a locked case set, per-slice gating, no paid calls. Five slices:

  1. stored verdicts — review_verdict() (src/lap.py) over the FROZEN snapshot
     in tools/echelon_bank/ (one .txt per locked review, named by sanitized
     relative path); expected verdicts locked in tools/echelon_bank.json
  2. self-bank oracles — the F5/G9/F6 oracles, run against the tip under
     test, PLUS known-red controls: the F5 oracle against the PRE-FIX tree
     (cfd7ad4b, the parent of the b566cd06 fix) and the F6 oracle against
     its defect-live tree (a478fa35, the parent of the d57fb5af fix) must
     each exit non-zero — pins discrimination, not just the fix
     (`known_red=ok` means ALL red-side controls fired)
  3. unit suite — unittest discover, in that same checkout; the count is
     floored at the locked suite_tests (a suite that loses tests never greens)
  4. cost honesty — the newest cost.json carries the completeness contract
  5. external control — the oracle machinery must discriminate on FOREIGN
     product repos, not only nightshift's own code (see
     EXTERNAL-CONTROL_2026-10-10.md). Two best-effort legs, each degrading
     independently to "absent" (non-gating; only "broken" blocks green):
       - checker self-test (hermetic, always): the committed sqlparse
         checker (tools/external_oracles/sqlparse/) is fed two inline
         fixtures — the buggy reindent output (clause split, ONLY orphaned)
         and the fixed one — and must FAIL the first and PASS the second.
         Catches checker rot with no foreign repo present (<100 ms).
       - external_sqlparse: throwaway worktrees at the bank's base/fix
         commits of the sqlparse repo object, a bare --without-pip venv in
         each (the checker imports the worktree's package from cwd), then
         the committed driver: base must exit 1, fix must exit 0.
       - external_flox: the sealed flox #1619 oracle against the base
         binary; base must exit 1 (GREEN side blocked on an nixlab build).
     The flox oracle dir stays external (referenced by path — copying it in
     would buy nothing since the binary is what's external and it is 321 MB);
     the sqlparse oracle trio IS committed (12 KB, needed for the self-test
     and so the gate survives loss of factory-docs).
     Paths live in the bank's "external" block; each may be overridden per
     run with ECHELON_SQLPARSE_REPO / ECHELON_FLOX_BIN / ECHELON_FLOX_ORACLE
     env vars (degrade testing), and paths are expanduser()'d at runtime.

Slices 2 and 3 run in a throwaway jj workspace at the tip, discarded after
(so the suite and the oracles see the tip's files, never a dirty working copy).

First run locks: copies the current matching reviews into tools/echelon_bank/
and writes tools/echelon_bank.json with their verdicts keyed by slug. Later
runs read ONLY tools/echelon_bank/ — live evidence dirs can never move the
needle, so a new lap's review.txt cannot false-RED the bank. Adding to the
bank is an explicit re-lock: delete tools/echelon_bank.json AND
tools/echelon_bank/, then rerun (see SELFHOST-LAPS_2026-10-09.md baseline
section). With the "external" block present, a re-lock must first verify
the 23 stored verdicts against the freshly computed ones byte-for-byte
(diff the old bank json against the new one's "verdicts" — any difference
means drift: STOP, do not absorb it) and must carry the external block
over. A locked bank WITHOUT the external block is stale/damaged state,
not an old schema: echelon fails closed (exit 1, "bank missing external
block") instead of silently disarming slice 5. Exit 0 iff every slice
is green.
"""

import argparse
import datetime
import glob
import importlib.util
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
BANK = os.path.join(HERE, "echelon_bank.json")
SNAP = os.path.join(HERE, "echelon_bank")
ORACLE_DIR = os.path.expanduser("~/repos/self-bank/oracles")
ORACLES = ("oracle_self_f5.sh", "oracle_self_g9.sh", "oracle_self_f6.sh")
# The pre-fix tree for the known-red control: parent of the b566cd06 fix
# (change unytzmplwkny). Hardcoded; the change-id suffix form is fragile.
PRE_FIX = "cfd7ad4bb4b62959a5a46c561bbee7c518c583a0"
# Known-red tree for the F6 oracle: the tip BEFORE the F6 fix (d57fb5af)
# landed — the defect is live there (bare `skip`, no reason markers).
F6_PRE_FIX = "a478fa35f555ab4653dc24ce64d4690a2f4129e0"
SQLPARSE_ORACLE = os.path.join(HERE, "external_oracles", "sqlparse")
EXTERNAL_TIMEOUT = 180  # per foreign leg; tripped = broken, never silent
# Written into every fresh lock so re-locks stay self-contained (same spirit
# as PRE_FIX); env overrides at run time never touch the stored bank.
DEFAULT_EXTERNAL = {
    "sqlparse_repo_object": "~/repos/sqlparse-lap-4001/repo",
    "sqlparse_base_commit": "60cdc649726bf1bc4f1b336050560b336da715ec",
    "sqlparse_fix_commit": "2ef77ae51b97f94d2d8970861fd3ab6531deb665",
    "flox_bin": "~/repos/flox-target-devsh/debug/flox",
    "flox_oracle_dir": "~/repos/flox-replay-oracle-sealed",
}
REVIEW_GLOBS = (
    os.path.join(ROOT, "state", "evidence", "*", "review.txt"),
    os.path.expanduser("~/repos/factory-docs/p3-matrix-rerun/*.review.txt"),
)


def run(argv, cwd=ROOT, timeout=1800, env=None):
    return subprocess.run(argv, cwd=cwd, text=True, capture_output=True,
                          timeout=timeout, env=env)


def measured_commit():
    """The revision under test: the working-copy commit, else git HEAD."""
    r = run(["jj", "log", "-r", "@", "--no-graph", "-T", "commit_id"])
    if r.returncode == 0 and r.stdout.strip():
        return r.stdout.strip()
    return run(["git", "rev-parse", "HEAD"]).stdout.strip()


def slug_for(relpath):
    """A stable filename for a review's repo-relative path ('/' -> '__')."""
    return relpath.replace("/", "__")


def load_lap():
    sys.path.insert(0, os.path.join(ROOT, "src"))
    spec = importlib.util.spec_from_file_location("lap", os.path.join(ROOT, "src", "lap.py"))
    assert spec and spec.loader
    lap = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(lap)
    return lap


def collect_live():
    """Current review files + verdicts, keyed by ~-relative path."""
    lap = load_lap()
    home = os.path.expanduser("~")
    verdicts = {}
    for pattern in REVIEW_GLOBS:
        for path in sorted(glob.glob(pattern)):
            with open(path, encoding="utf-8", errors="replace") as fh:
                content = fh.read()
            if not content.strip():
                continue  # not a review artifact (e.g. a run that never reviewed)
            verdicts[os.path.relpath(path, home)] = lap.review_verdict(content)
    return verdicts


def lock_bank(commit, suite_tests):
    """First run: snapshot every currently-matching review into tools/echelon_bank/
    and write the lock keyed by slug. Called only when BANK is absent."""
    live = collect_live()
    if not live:
        raise SystemExit("echelon: no review artifacts found to lock")
    os.makedirs(SNAP, exist_ok=True)
    home = os.path.expanduser("~")
    verdicts = {}
    for rel, verdict in live.items():
        slug = slug_for(rel)
        shutil.copyfile(os.path.join(home, rel), os.path.join(SNAP, slug))
        verdicts[slug] = verdict
    with open(BANK, "w", encoding="utf-8") as fh:
        json.dump({"locked_at": "%sT%s" % (datetime.date.today().isoformat(),
                                           datetime.datetime.now().strftime("%H:%M:%S")),
                   "commit": commit, "suite_tests": suite_tests,
                   "external": dict(DEFAULT_EXTERNAL),
                   "verdicts": verdicts},
                  fh, indent=1, sort_keys=True)
        fh.write("\n")


def stored_verdicts():
    """Slice 1: review_verdict() over the frozen snapshot in tools/echelon_bank/."""
    lap = load_lap()
    verdicts = {}
    for path in sorted(glob.glob(os.path.join(SNAP, "*.txt"))):
        with open(path, encoding="utf-8", errors="replace") as fh:
            content = fh.read()
        if not content.strip():
            continue
        verdicts[os.path.basename(path)] = lap.review_verdict(content)
    return verdicts

def suite_slices():
    """Slices 2+3: oracles at the tip, the known-red controls at their
    pre-fix trees, and the unit suite with its test count."""
    tmp = tempfile.mkdtemp(prefix="echelon-ws-")
    wt = os.path.join(tmp, os.path.basename(tmp))
    add = run(["jj", "workspace", "add", "-r", "@", wt])
    if add.returncode != 0:
        shutil.rmtree(tmp, ignore_errors=True)
        raise RuntimeError("jj workspace add failed: %s" % (add.stderr or add.stdout).strip())
    try:
        oracles = [(name, run(["bash", os.path.join(ORACLE_DIR, name)], cwd=wt,
                              timeout=900).returncode) for name in ORACLES]
        suite = run([sys.executable, "-m", "unittest", "discover", "-s", "tests"],
                    cwd=wt, timeout=1800)
        # Known-red controls: each oracle re-run against its defect-live tree
        # must exit non-zero (discrimination, not just the fix).
        red_specs = (("f5", PRE_FIX, "oracle_self_f5.sh"),
                     ("f6", F6_PRE_FIX, "oracle_self_f6.sh"))
        known_red = {}
        for name, rev, oracle in red_specs:
            pre = tempfile.mkdtemp(prefix="echelon-prered-")
            pref = os.path.join(pre, os.path.basename(pre))
            add2 = run(["jj", "workspace", "add", "-r", rev, pref])
            if add2.returncode != 0:
                raise RuntimeError("known-red workspace (%s) failed: %s"
                                   % (name, (add2.stderr or add2.stdout).strip()))
            try:
                known_red[name] = run(["bash", os.path.join(ORACLE_DIR, oracle)],
                                      cwd=pref, timeout=900).returncode
            finally:
                run(["jj", "workspace", "forget", os.path.basename(pre)])
                shutil.rmtree(pre, ignore_errors=True)
    finally:
        run(["jj", "workspace", "forget", os.path.basename(tmp)])
        shutil.rmtree(tmp, ignore_errors=True)
    out = suite.stdout + suite.stderr
    ran = re.search(r"^Ran (\d+) tests?", out, re.M)
    ok = suite.returncode == 0 and bool(re.search(r"^OK\b", out, re.M))
    return oracles, known_red, int(ran.group(1)) if ran else 0, ok, out.strip().splitlines()[-1:]


def cost_contract():
    """Slice 4: the newest evidence run declares its cost accounting complete."""
    for directory in sorted(glob.glob(os.path.join(ROOT, "state", "evidence", "*")),
                            reverse=True):
        path = os.path.join(directory, "cost.json")
        if not os.path.exists(path):
            continue
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError):
            return False, path
        return ("missing_usage_calls" in data and "cost_complete" in data
                and data.get("cost_complete") is True), path
    return False, ""


SELFTEST_SQL = ("SELECT id FROM tbl WHERE id > 0 ORDER BY id ASC "
                "OFFSET 0 ROWS FETCH NEXT 100 ROWS ONLY")
# Both outputs measured from the real sqlparse trees on 2026-10-10: the buggy
# one at base 60cdc64 (issue #842: clause split, ONLY orphaned), the fixed one
# at fix 2ef77ae (clause kept on the line after ORDER BY). The self-test
# replays them through a stub formatter so it needs no sqlparse installed;
# the foreign leg (external_sqlparse) re-proves them against the real repos.
SELFTEST_BUGGY_OUT = ("SELECT id\n  FROM tbl\n WHERE id > 0\n ORDER BY id ASC"
                      "\nOFFSET 0 ROWS FETCH NEXT 100 ROWS\n  ONLY")
SELFTEST_FIXED_OUT = ("SELECT id\n  FROM tbl\n WHERE id > 0\n ORDER BY id ASC"
                      "\nOFFSET 0 ROWS FETCH NEXT 100 ROWS ONLY")
SELFTEST_CASE = {
    "name": "selftest_offset_fetch", "kind": "paging_clause", "sql": SELFTEST_SQL,
    "options": {"keyword_case": "upper", "reindent_aligned": True},
    "clause": "OFFSET 0 ROWS FETCH NEXT 100 ROWS ONLY",
    "prefix_lines": ["SELECT id", "  FROM tbl", " WHERE id > 0"],
    "order_line_prefix": "ORDER BY id ASC",
    "orphan_forbidden": ["ONLY"],
}


def _load_checker_with_output(formatted):
    """Load the committed checker with a stub sqlparse whose format() returns
    `formatted`; return its check_case()."""
    stub = type(sys)("sqlparse_stub")
    stub.format = lambda sql, **kw: formatted
    saved = sys.modules.get("sqlparse")
    sys.modules["sqlparse"] = stub
    try:
        spec = importlib.util.spec_from_file_location(
            "check_offset_clause", os.path.join(SQLPARSE_ORACLE, "check_offset_clause.py"))
        assert spec and spec.loader
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod.check_case
    finally:
        if saved is None:
            sys.modules.pop("sqlparse", None)
        else:
            sys.modules["sqlparse"] = saved


def checker_selftest():
    """Slice 5a, hermetic (<100 ms): feed the committed sqlparse checker the
    measured buggy and fixed reindent outputs; it must FAIL the buggy one
    (clause split, ONLY orphaned) and PASS the fixed one. Catches checker rot
    with zero external dependencies; the foreign leg re-proves the outputs
    against the real repos."""
    check_case = _load_checker_with_output(SELFTEST_BUGGY_OUT)
    buggy = check_case(SELFTEST_CASE)
    check_case = _load_checker_with_output(SELFTEST_FIXED_OUT)
    fixed = check_case(SELFTEST_CASE)
    return (bool(buggy) and not fixed), buggy, fixed


def _bank_path(locked, key, env):
    """A bank external path, env-overridable and ~-expanded; None if unset."""
    raw = os.environ.get(env) or locked.get("external", {}).get(key)
    return os.path.expanduser(raw) if raw else None


def external_sqlparse(locked):
    """Slice 5b: run the committed sqlparse driver in throwaway worktrees at
    the bank's base and fix commits. (absent, None) if the repo object is
    gone; (broken, reason) on any wrong verdict or harness hiccup."""
    repo = _bank_path(locked, "sqlparse_repo_object", "ECHELON_SQLPARSE_REPO")
    base_c = locked.get("external", {}).get("sqlparse_base_commit")
    fix_c = locked.get("external", {}).get("sqlparse_fix_commit")
    if not repo or not base_c or not fix_c or not os.path.isdir(repo):
        return "absent", None
    if shutil.which("git") is None:
        return "broken", "git not found"
    tmp = tempfile.mkdtemp(prefix="echelon-extsql-")
    try:
        cases = os.path.join(SQLPARSE_ORACLE, "cases.json")
        checker = os.path.join(SQLPARSE_ORACLE, "check_offset_clause.py")
        venvs = {}
        for tag, commit in (("base", base_c), ("fix", fix_c)):
            wt = os.path.join(tmp, tag)
            r = run(["git", "-C", repo, "worktree", "add", "--detach", wt, commit],
                    timeout=EXTERNAL_TIMEOUT)
            if r.returncode != 0:
                return "broken", ("worktree %s failed: %s"
                                  % (tag, (r.stderr or r.stdout).strip()[:200]))
            venv = os.path.join(tmp, tag + "-venv")
            if run([sys.executable, "-m", "venv", "--without-pip", venv],
                   timeout=EXTERNAL_TIMEOUT).returncode != 0:
                return "broken", "venv creation failed for %s" % tag
            venvs[tag] = (wt, venv)
        verdicts = {}
        for tag, (wt, venv) in venvs.items():
            py = os.path.join(venv, "bin", "python")
            r = run([py, checker, cases], cwd=wt, timeout=EXTERNAL_TIMEOUT)
            verdicts[tag] = r.returncode
            if r.returncode not in (0, 1):  # 2 = harness error, anything else = tripped
                why = (r.stderr or r.stdout).strip().splitlines()
                return "broken", ("%s harness exit %d: %s"
                                  % (tag, r.returncode,
                                     (why[-1] if why else "timeout/no output")[:200]))
        if verdicts["base"] != 1 or verdicts["fix"] != 0:
            return "broken", "expected base=1 fix=0, got %r" % verdicts
        return "ok", None
    except subprocess.TimeoutExpired:
        return "broken", "leg exceeded %ds timeout" % EXTERNAL_TIMEOUT
    except OSError as exc:
        return "broken", str(exc)[:200]
    finally:
        for tag in ("base", "fix"):
            wt = os.path.join(tmp, tag)
            if os.path.isdir(wt):
                run(["git", "-C", repo, "worktree", "remove", "--force", wt],
                    timeout=60)
        run(["git", "-C", repo, "worktree", "prune"], timeout=60)
        shutil.rmtree(tmp, ignore_errors=True)


def external_flox(locked):
    """Slice 5c: the sealed flox #1619 oracle against the bank's base binary;
    the buggy base must stay RED (exit 1). GREEN side needs an nixlab build
    and is N/A. (absent, None) if the binary or oracle dir is gone."""
    fbin = _bank_path(locked, "flox_bin", "ECHELON_FLOX_BIN")
    odir = _bank_path(locked, "flox_oracle_dir", "ECHELON_FLOX_ORACLE")
    if not fbin or not odir or not os.path.exists(fbin) or not os.path.isdir(odir):
        return "absent", None
    oracle = os.path.join(odir, "oracle_show_align.sh")
    if not os.path.exists(oracle):
        return "absent", None
    try:
        r = run(["bash", oracle], timeout=EXTERNAL_TIMEOUT,
                env=dict(os.environ, FLOX_BIN=fbin))
        if r.returncode != 1:
            why = ((r.stdout or "") + (r.stderr or "")).strip().splitlines()
            return "broken", ("expected exit 1 on buggy base, got %d: %s"
                              % (r.returncode,
                                 (why[-1] if why else "no output")[:200]))
        return "red-ok", None
    except subprocess.TimeoutExpired:
        return "broken", "leg exceeded %ds timeout" % EXTERNAL_TIMEOUT
    except OSError as exc:
        return "broken", str(exc)[:200]


def main(argv=None):
    parser = argparse.ArgumentParser(description="nightshift-echelon regression bank")
    parser.add_argument("-o", "--out", metavar="FILE",
                        help="append this run's metrics as one JSON line to FILE")
    args = parser.parse_args(argv)

    commit = measured_commit()
    date = datetime.date.today().isoformat()

    oracles, known_red, suite_tests, suite_ok, suite_tail = suite_slices()
    oracles_green = sum(1 for _, code in oracles if code == 0)
    known_red_ok = all(code != 0 for code in known_red.values())

    locked = None
    locked_this_run = False
    if os.path.exists(BANK):
        with open(BANK, encoding="utf-8") as fh:
            locked = json.load(fh)
    else:
        lock_bank(commit, suite_tests)
        locked_this_run = True
        with open(BANK, encoding="utf-8") as fh:
            locked = json.load(fh)

    now = stored_verdicts()
    drift = []
    for key in sorted(set(locked["verdicts"]) | set(now)):
        was, is_now = locked["verdicts"].get(key), now.get(key)
        if was != is_now:
            drift.append((key, was if was is not None else "<absent>",
                          is_now if is_now is not None else "<absent>"))

    cost_ok, cost_path = cost_contract()

    floor = locked["suite_tests"]
    floor_ok = suite_tests >= floor

    # Slice 5 arms iff the locked bank carries the external block. A lock
    # WITHOUT it is stale/damaged state (every lock since slice 5 writes one
    # via lock_bank), not an old schema — fail closed, never silently skip.
    missing_external = "external" not in locked
    selftest_ok = buggy = fixed = None
    sqlparse_state = flox_state = "absent"
    sqlparse_why = flox_why = None
    if not missing_external:
        selftest_ok, buggy, fixed = checker_selftest()
        sqlparse_state, sqlparse_why = external_sqlparse(locked)
        flox_state, flox_why = external_flox(locked)

    matches = sum(1 for key, verdict in now.items() if locked["verdicts"].get(key) == verdict)
    total = len(now)
    stability = "%d/%d" % (matches, total)
    green = (not missing_external
             and total > 0 and matches == total and not drift
             and oracles_green == len(ORACLES) and known_red_ok
             and floor_ok and suite_ok and cost_ok
             and (selftest_ok and sqlparse_state != "broken"
                  and flox_state != "broken"))

    print("ECHELON verdict_stability=%s" % stability)
    broken_red = sorted(n for n, c in known_red.items() if c == 0)
    print("ECHELON known_red=%s" % ("ok" if known_red_ok else "broken(%s)" % ",".join(broken_red)))
    print("ECHELON oracles_green=%d/%d" % (oracles_green, len(ORACLES)))
    print("ECHELON suite_tests=%d" % suite_tests)
    if not floor_ok:
        print("ECHELON suite_floor=FELL (%d < %d)" % (suite_tests, floor))
    else:
        print("ECHELON suite_floor=ok")
    print("ECHELON suite_ok=%s" % str(suite_ok).lower())
    print("ECHELON cost_contract=%s" % str(cost_ok).lower())
    if missing_external:
        print("ECHELON FAIL bank missing external block (re-lock per docstring)")
    else:
        print("ECHELON external_sqlparse=%s" % sqlparse_state)
        print("ECHELON external_flox=%s" % flox_state)
        print("ECHELON external_checker_selftest=%s"
              % ("ok" if selftest_ok else "broken"))
    print("ECHELON locked_this_run=%s" % str(locked_this_run).lower())
    for key, was, is_now in drift:
        print("ECHELON DRIFT verdict[%s]: locked=%s now=%s" % (key, was, is_now))
    if not green:
        for name, code in oracles:
            if code:
                print("ECHELON FAIL oracle %s exit=%d" % (name, code))
        if not known_red_ok:
            print("ECHELON FAIL known-red control(s) exited 0 on pre-fix tree: %s"
                  % ",".join(broken_red))
        if not floor_ok:
            print("ECHELON FAIL suite floor")
        if not suite_ok:
            print("ECHELON FAIL suite: %s" % " ".join(suite_tail))
        if not cost_ok:
            print("ECHELON FAIL cost.json incomplete: %s" % (cost_path or "none found"))
        if not missing_external:
            if buggy:
                print("ECHELON FAIL checker selftest: buggy fixture NOT failed: %s"
                      % "; ".join(buggy)[:200])
            if fixed:
                print("ECHELON FAIL checker selftest: fixed fixture failed: %s"
                      % "; ".join(fixed)[:200])
            if sqlparse_state == "broken":
                print("ECHELON FAIL external_sqlparse: %s" % sqlparse_why)
            if flox_state == "broken":
                print("ECHELON FAIL external_flox: %s" % flox_why)
    print("ECHELON baseline_commit=%s date=%s" % (commit, date))

    if args.out:
        with open(args.out, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({
                "date": date, "commit": commit, "verdict_stability": stability,
                "known_red": "ok" if known_red_ok else "broken",
                "oracles_green": "%d/%d" % (oracles_green, len(ORACLES)),
                "suite_tests": suite_tests, "suite_floor": "ok" if floor_ok else "FELL",
                "suite_ok": suite_ok,
                "cost_contract": cost_ok, "green": green,
                "drift": [key for key, _, _ in drift],
                "external": ({
                    "sqlparse": sqlparse_state, "flox": flox_state,
                    "checker_selftest": "ok" if selftest_ok else "broken",
                } if not missing_external else None)}, sort_keys=True) + "\n")

    return 0 if green else 1


if __name__ == "__main__":
    sys.exit(main())
