#!/usr/bin/env python3
"""nightshift-echelon — the free regression bank for the kernel.

Design: RESEARCH-CODING-METRICS_2026-10-08.md §3 "Regression gating for the
kernel" — a locked case set, per-slice gating, no paid calls. Five slices:

  1. stored verdicts — review_verdict() (src/lap.py) over the FROZEN snapshot
     in tools/echelon_bank/ (one .txt per locked review, named by sanitized
     relative path); expected verdicts locked in tools/echelon_bank.json
  2. self-bank oracles — the F5/G9 oracles, run against the tip under test,
     PLUS a known-red control: the F5 oracle against the PRE-FIX tree
     (cfd7ad4b, the parent of the b566cd06 fix) must exit non-zero — pins
     discrimination, not just the fix
  3. unit suite — unittest discover, in that same checkout; the count is
     floored at the locked suite_tests (a suite that loses tests never greens)
  4. cost honesty — the newest cost.json carries the completeness contract

Slices 2 and 3 run in a throwaway jj workspace at the tip, discarded after
(so the suite and the oracles see the tip's files, never a dirty working copy).

First run locks: copies the current matching reviews into tools/echelon_bank/
and writes tools/echelon_bank.json with their verdicts keyed by slug. Later
runs read ONLY tools/echelon_bank/ — live evidence dirs can never move the
needle, so a new lap's review.txt cannot false-RED the bank. Adding to the
bank is an explicit re-lock: delete tools/echelon_bank.json AND
tools/echelon_bank/, then rerun (see SELFHOST-LAPS_2026-10-09.md baseline
section). Exit 0 iff every slice is green.
"""

import argparse
import datetime
import glob
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
BANK = os.path.join(HERE, "echelon_bank.json")
SNAP = os.path.join(HERE, "echelon_bank")
ORACLE_DIR = os.path.expanduser("~/repos/self-bank/oracles")
ORACLES = ("oracle_self_f5.sh", "oracle_self_g9.sh")
# The pre-fix tree for the known-red control: parent of the b566cd06 fix
# (change unytzmplwkny). Hardcoded; the change-id suffix form is fragile.
PRE_FIX = "cfd7ad4bb4b62959a5a46c561bbee7c518c583a0"
REVIEW_GLOBS = (
    os.path.join(ROOT, "state", "evidence", "*", "review.txt"),
    os.path.expanduser("~/repos/factory-docs/p3-matrix-rerun/*.review.txt"),
)


def run(argv, cwd=ROOT, timeout=1800):
    return subprocess.run(argv, cwd=cwd, text=True, capture_output=True,
                          timeout=timeout)


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


def lock_bank(commit):
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
                   "commit": commit, "suite_tests": 324, "verdicts": verdicts},
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
    """Slices 2+3: oracles at the tip, the known-red F5 control at the pre-fix
    tree, and the unit suite with its test count."""
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
        pre = tempfile.mkdtemp(prefix="echelon-prered-")
        pref = os.path.join(pre, os.path.basename(pre))
        add2 = run(["jj", "workspace", "add", "-r", PRE_FIX, pref])
        if add2.returncode != 0:
            raise RuntimeError("known-red workspace failed: %s"
                               % (add2.stderr or add2.stdout).strip())
        try:
            known_red = run(["bash", os.path.join(ORACLE_DIR, "oracle_self_f5.sh")],
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


def main(argv=None):
    parser = argparse.ArgumentParser(description="nightshift-echelon regression bank")
    parser.add_argument("-o", "--out", metavar="FILE",
                        help="append this run's metrics as one JSON line to FILE")
    args = parser.parse_args(argv)

    commit = measured_commit()
    date = datetime.date.today().isoformat()

    locked = None
    locked_this_run = False
    if os.path.exists(BANK):
        with open(BANK, encoding="utf-8") as fh:
            locked = json.load(fh)
    else:
        lock_bank(commit)
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

    oracles, known_red, suite_tests, suite_ok, suite_tail = suite_slices()
    oracles_green = sum(1 for _, code in oracles if code == 0)
    known_red_ok = known_red != 0
    floor = locked["suite_tests"]
    floor_ok = suite_tests >= floor
    cost_ok, cost_path = cost_contract()

    matches = sum(1 for key, verdict in now.items() if locked["verdicts"].get(key) == verdict)
    total = len(now)
    stability = "%d/%d" % (matches, total)
    green = (total > 0 and matches == total and not drift
             and oracles_green == len(ORACLES) and known_red_ok
             and floor_ok and suite_ok and cost_ok)

    print("ECHELON verdict_stability=%s" % stability)
    print("ECHELON known_red=%s" % ("ok" if known_red_ok else "broken"))
    print("ECHELON oracles_green=%d/%d" % (oracles_green, len(ORACLES)))
    print("ECHELON suite_tests=%d" % suite_tests)
    if not floor_ok:
        print("ECHELON suite_floor=FELL (%d < %d)" % (suite_tests, floor))
    else:
        print("ECHELON suite_floor=ok")
    print("ECHELON suite_ok=%s" % str(suite_ok).lower())
    print("ECHELON cost_contract=%s" % str(cost_ok).lower())
    print("ECHELON locked_this_run=%s" % str(locked_this_run).lower())
    for key, was, is_now in drift:
        print("ECHELON DRIFT verdict[%s]: locked=%s now=%s" % (key, was, is_now))
    if not green:
        for name, code in oracles:
            if code:
                print("ECHELON FAIL oracle %s exit=%d" % (name, code))
        if not known_red_ok:
            print("ECHELON FAIL known-red control: F5 oracle exited 0 on pre-fix tree")
        if not floor_ok:
            print("ECHELON FAIL suite floor")
        if not suite_ok:
            print("ECHELON FAIL suite: %s" % " ".join(suite_tail))
        if not cost_ok:
            print("ECHELON FAIL cost.json incomplete: %s" % (cost_path or "none found"))
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
                "drift": [key for key, _, _ in drift]}, sort_keys=True) + "\n")

    return 0 if green else 1


if __name__ == "__main__":
    sys.exit(main())
