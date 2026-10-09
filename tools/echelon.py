#!/usr/bin/env python3
"""nightshift-echelon — the free regression bank for the kernel.

Design: RESEARCH-CODING-METRICS_2026-10-08.md §3 "Regression gating for the
kernel" — a locked case set, per-slice gating, no paid calls. Four slices:

  1. stored verdicts — review_verdict() (src/lap.py) over the pinned review.txt
     artifacts; the expected verdicts are locked in tools/echelon_bank.json
  2. self-bank oracles — the F5/G9 oracles, run against the tip under test
  3. unit suite — unittest discover, in that same checkout
  4. cost honesty — the newest cost.json carries the completeness contract

Slices 2 and 3 run in a throwaway jj workspace at the tip, discarded after
(so the suite and the oracles see the tip's files, never a dirty working copy).

First run locks tools/echelon_bank.json from current observations; later runs
diff against it and report drift. Exit 0 iff every slice is green.
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
ORACLE_DIR = os.path.expanduser("~/repos/self-bank/oracles")
ORACLES = ("oracle_self_f5.sh", "oracle_self_g9.sh")
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


def stored_verdicts():
    """Slice 1: current review_verdict() over the pinned review artifacts."""
    sys.path.insert(0, os.path.join(ROOT, "src"))
    spec = importlib.util.spec_from_file_location("lap", os.path.join(ROOT, "src", "lap.py"))
    assert spec and spec.loader
    lap = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(lap)
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


def workspace_slices():
    """Slices 2+3: oracles and the suite, in a throwaway workspace at the tip."""
    tmp = tempfile.mkdtemp(prefix="echelon-ws-")
    wt = os.path.join(tmp, os.path.basename(tmp))
    # -r @: the new working-copy commit's parent is the revision under test
    # (a plain `workspace add` branches off @-, i.e. the pre-change tree).
    add = run(["jj", "workspace", "add", "-r", "@", wt])
    if add.returncode != 0:
        shutil.rmtree(tmp, ignore_errors=True)
        raise RuntimeError("jj workspace add failed: %s" % (add.stderr or add.stdout).strip())
    try:
        oracles = [(name, run(["bash", os.path.join(ORACLE_DIR, name)], cwd=wt,
                              timeout=900).returncode) for name in ORACLES]
        suite = run([sys.executable, "-m", "unittest", "discover", "-s", "tests"],
                    cwd=wt, timeout=1800)
    finally:
        run(["jj", "workspace", "forget", os.path.basename(tmp)])
        shutil.rmtree(tmp, ignore_errors=True)
    out = suite.stdout + suite.stderr
    ran = re.search(r"^Ran (\d+) tests?", out, re.M)
    ok = suite.returncode == 0 and bool(re.search(r"^OK\b", out, re.M))
    return oracles, int(ran.group(1)) if ran else 0, ok, out.strip().splitlines()[-1:] 


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

    now = stored_verdicts()
    locked = None
    if os.path.exists(BANK):
        with open(BANK, encoding="utf-8") as fh:
            locked = json.load(fh)["verdicts"]

    drift = []
    if locked is not None:
        for key in sorted(set(locked) | set(now)):
            if locked.get(key) != now.get(key):
                drift.append((key, locked.get(key, "<absent>"), now.get(key, "<absent>")))

    oracles, suite_tests, suite_ok, suite_tail = workspace_slices()
    oracles_green = sum(1 for _, code in oracles if code == 0)
    cost_ok, cost_path = cost_contract()

    matches = sum(1 for key, verdict in now.items() if locked is None or locked.get(key) == verdict)
    total = len(now)
    stability = "%d/%d" % (matches, total)
    green = (total > 0 and matches == total and oracles_green == len(ORACLES)
             and suite_ok and cost_ok and not drift)

    print("ECHELON verdict_stability=%s" % stability)
    print("ECHELON oracles_green=%d/%d" % (oracles_green, len(ORACLES)))
    print("ECHELON suite_tests=%d" % suite_tests)
    print("ECHELON suite_ok=%s" % str(suite_ok).lower())
    print("ECHELON cost_contract=%s" % str(cost_ok).lower())
    print("ECHELON bank_locked=%s" % str(locked is None).lower())
    for key, was, is_now in drift:
        print("ECHELON DRIFT verdict[%s]: locked=%s now=%s" % (key, was, is_now))
    if not green:
        for name, code in oracles:
            if code:
                print("ECHELON FAIL oracle %s exit=%d" % (name, code))
        if not suite_ok:
            print("ECHELON FAIL suite: %s" % " ".join(suite_tail))
        if not cost_ok:
            print("ECHELON FAIL cost.json incomplete: %s" % (cost_path or "none found"))
    print("ECHELON baseline_commit=%s date=%s" % (commit, date))

    if locked is None:
        with open(BANK, "w", encoding="utf-8") as fh:
            json.dump({"locked_at": "%sT%s" % (date, datetime.datetime.now().strftime("%H:%M:%S")),
                       "commit": commit, "verdicts": now}, fh, indent=1, sort_keys=True)
            fh.write("\n")

    if args.out:
        with open(args.out, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({
                "date": date, "commit": commit, "verdict_stability": stability,
                "oracles_green": "%d/%d" % (oracles_green, len(ORACLES)),
                "suite_tests": suite_tests, "suite_ok": suite_ok,
                "cost_contract": cost_ok, "green": green,
                "drift": [key for key, _, _ in drift]}, sort_keys=True) + "\n")

    return 0 if green else 1


if __name__ == "__main__":
    sys.exit(main())
