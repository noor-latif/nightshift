"""Selector: pick the next work unit and claim it atomically.

Outcome handling is exhaustive (NEEDLE outcome-classify pattern, re-expressed
in Python): every terminal outcome maps to a defined disposition.
"""

import json
import os
import subprocess
import time

from settings import CLAIMS_DIR, LAP_WALLCLOCK_LIMIT_S, RETRY_BUDGET

OUTCOMES = ("success", "failure", "timeout", "crash", "queue-empty")


def _gh(args, repo, gh="gh"):
    return subprocess.run(
        [gh] + args + ["-R", repo], capture_output=True, text=True, check=True
    ).stdout


def list_open_issues(repo, gh="gh"):
    out = _gh(["issue", "list", "--state", "open", "--json", "number,createdAt"], repo, gh)
    issues = json.loads(out) if out.strip() else []
    # oldest first
    return sorted(issues, key=lambda i: i["createdAt"])


def open_pr_branches(repo, gh="gh"):
    out = _gh(["pr", "list", "--state", "open", "--json", "headRefName"], repo, gh)
    prs = json.loads(out) if out.strip() else []
    return {p["headRefName"] for p in prs}


def claim_path(issues_dir, issue):
    return os.path.join(issues_dir, "issue-%d.json" % issue)


def claim_next(repo, issues_dir=CLAIMS_DIR, now=None, gh="gh", dispositions=None):
    """Claim the oldest open issue with no open PR. Returns the claim dict or None.

    dispositions: durable per-issue map (state["issues"]) — parked issues are
    never re-claimed, so a park survives a supervisor restart.
    """
    dispositions = dispositions or {}
    now = time.time() if now is None else now
    os.makedirs(issues_dir, exist_ok=True)
    pr_branches = open_pr_branches(repo, gh)
    for issue in list_open_issues(repo, gh):
        if dispositions.get(str(issue["number"])) == "parked":
            continue  # park is durable; dispatch must not burn retries again
        if "agent/issue-%d" % issue["number"] in pr_branches:
            continue
        path = claim_path(issues_dir, issue["number"])
        # stale claim breakable with a note (at MAX_CONCURRENT_LAPS=1 the only
        # stale source is a crashed supervisor; O_EXCL claim is the fence)
        if os.path.exists(path):
            if not stale(path, now):
                continue
            break_stale_claim(path, now)
        body = json.dumps({"issue": issue["number"], "claimed_at": now})
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            continue
        with os.fdopen(fd, "w") as f:
            f.write(body)
        return {"issue": issue["number"], "path": path}
    return None


def stale(path, now):
    try:
        with open(path) as f:
            claimed_at = json.load(f)["claimed_at"]
    except Exception:
        # unparseable claim: fall back to mtime
        claimed_at = os.path.getmtime(path)
    return (now - claimed_at) > LAP_WALLCLOCK_LIMIT_S


def break_stale_claim(path, now):
    """Break a stale claim, recording a note. Returns True if broken."""
    try:
        with open(path) as f:
            old = json.load(f)
    except Exception:
        old = {"issue": None, "claimed_at": "unparseable"}
    os.remove(path)
    log = os.path.join(os.path.dirname(path), "broken.log")
    with open(log, "a") as f:
        f.write(json.dumps({"broke": path, "previous": old, "at": now}) + "\n")
    return True


def read_claim(path):
    with open(path) as f:
        return json.load(f)


def handle_outcome(outcome, issue, state, now):
    """Exhaustive outcome → disposition (durable state mutated in place).

    NEEDLE classify shape re-expressed: every terminal outcome has exactly one
    handler; an unknown outcome raises instead of falling through.
    """
    if outcome not in OUTCOMES:
        raise ValueError("unknown outcome: %r" % (outcome,))
    key = str(issue)
    rec = state.setdefault("issues", {}).setdefault(key, {"retries": 0})
    if outcome == "success":
        rec["disposition"] = "merged"
        return "merged"
    if outcome == "queue-empty":
        return "idle"
    if outcome == "timeout":
        rec["disposition"] = "timeout-park"  # never re-dispatch a timed-out lap
        return "timeout-park"
    # failure / crash: retry until budget, then park (Sortie semantics)
    rec["retries"] += 1
    if rec["retries"] > RETRY_BUDGET:
        rec["disposition"] = "parked"
        return "parked"
    rec["disposition"] = "retry"
    return "retry"
