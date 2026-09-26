"""Supervisor: synchronous tick loop (Batty shape) with ntfy notify inline.

Liveness is out-of-process: heartbeat file written by the lap + pid probe.
Failure model is durable JSON state (Sortie park semantics).
"""

import json
import os
import signal
import subprocess
import sys
import time
import urllib.request

from settings import (
    EVIDENCE_DIR,
    GITHUB_REPO,
    HEARTBEAT_PATH,
    HEARTBEAT_TTL_S,
    LAP_WALLCLOCK_LIMIT_S,
    NTFY_URL,
    STATE_DIR,
)

RESULT_PATH = os.path.join(STATE_DIR, "lap-result.json")


def notify(text, title="nightshift", url=NTFY_URL, opener=None):
    """One ntfy POST per terminal state. Inline by design, not a module."""
    data = json.dumps({"topic": url.rstrip("/").rsplit("/", 1)[-1],
                       "title": title, "message": text}).encode()
    req = urllib.request.Request(url, data=data, method="POST")
    open_fn = opener.open if opener else urllib.request.urlopen
    resp = open_fn(req, timeout=10)
    resp.read()
    return resp.status


def pid_alive(pid):
    if pid is None or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # exists, owned by someone else


def heartbeat_fresh(now=None, path=HEARTBEAT_PATH, ttl=HEARTBEAT_TTL_S):
    now = time.time() if now is None else now
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return False
    return (now - mtime) < ttl


def lap_healthy(lap, now=None, hb_path=HEARTBEAT_PATH):
    """Liveness = heartbeat fresh AND recorded pid alive. Never the status row."""
    now = time.time() if now is None else now
    return heartbeat_fresh(now, hb_path) and pid_alive(lap.get("pid"))


def load_state(path):
    try:
        with open(path) as f:
            return json.load(f)
    except FileNotFoundError:
        return {"issues": {}, "lap": None, "started_at": None}


def save_state(state, path):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f, indent=1)
    os.replace(tmp, path)


def dispatch(state, now, deps):
    """Start at most one lap. Returns disposition string."""
    if state.get("lap"):
        return "already-running"
    claim = deps["claim"](now)
    if not claim:
        return "idle"
    state["lap"] = {
        "issue": claim["issue"],
        "claim_path": claim["path"],
        "started_at": now,
        "pid": None,
    }
    # wallclock guard measures the current lap session, not all history:
    # refresh so a supervisor restarted hours later dispatches instead of HALT
    state["started_at"] = now
    deps["start_lap"](claim["issue"], state["lap"])
    save_state(state, deps["state_path"])
    return "dispatched"


def handle_lap_end(state, outcome, now, deps):
    """Terminal lap end: park/retry per selector, notify, maybe HALT."""
    from selector import handle_outcome

    lap = state["lap"]
    issue = lap["issue"]
    if outcome in ("crash", "timeout"):
        deps["kill_lap"](lap)
    disposition = handle_outcome(outcome, issue, state, now)
    if disposition == "retry":
        # release the claim so the retry can re-acquire the same issue
        try:
            os.remove(lap["claim_path"])
        except OSError:
            pass
    notify_fn = deps["notify"]
    if outcome == "success":
        notify_fn("lap issue %d: GREEN" % issue)
    else:
        notify_fn("lap issue %d: %s (%s)" % (issue, outcome.upper(), disposition))
    state["lap"] = None
    save_state(state, deps["state_path"])
    # STOP contract: halt on budget exhaustion (park) or wall-clock exceed
    halt = disposition in ("parked", "timeout-park") or (now - (state.get("started_at") or now)) > LAP_WALLCLOCK_LIMIT_S
    return disposition, halt


def tick(state, now, deps):
    """One supervisor tick: health-check → reconcile → dispatch → tail."""
    events = []
    lap = state.get("lap")

    if lap:
        if lap_healthy(lap, now):
            if (now - lap["started_at"]) > LAP_WALLCLOCK_LIMIT_S:
                # wall-clock exceed: stop the lap, notify-and-halt
                disposition, halt = handle_lap_end(state, "timeout", now, deps)
                events.append("timeout:" + disposition)
                if halt:
                    events.append("HALT")
                    return events
            # else: healthy and within budget → let it run
        else:
            # a dead lap may have finished cleanly: the result file says so
            get_outcome = deps.get("lap_outcome")
            outcome = get_outcome(lap) if get_outcome else "crash"
            disposition, halt = handle_lap_end(state, outcome, now, deps)
            events.append("%s:%s" % (outcome, disposition))
            if halt:
                events.append("HALT")
                return events
    else:
        d = dispatch(state, now, deps)
        if d not in ("already-running",):
            events.append("dispatch:" + d)

    # reconcile: reap claims for issues with no live lap (supervisor restart)
    for path, claim in deps.get("reconcile", lambda now: [])(now):
        if not state.get("lap") or state["lap"].get("issue") != claim["issue"]:
            deps["break_claim"](path, now)
            events.append("reclaimed:%s" % path)

    save_state(state, deps["state_path"])
    return events


def main():
    """Real loop: claim -> dispatch -> watch -> park/retry per selector budget."""
    from selector import OUTCOMES, claim_next

    state_path = os.path.join(STATE_DIR, "state.json")
    os.makedirs(STATE_DIR, exist_ok=True)

    def start_lap(issue, lap):
        logf = open(os.path.join(STATE_DIR, "lap-%d.log" % issue), "a")
        proc = subprocess.Popen([sys.executable, "src/lap.py", str(issue)],
                                stdout=logf, stderr=subprocess.STDOUT)
        lap["pid"] = proc.pid

    def kill_lap(lap):
        pid = lap.get("pid")
        if pid:
            try:
                os.kill(pid, signal.SIGTERM)
            except OSError:
                pass

    def lap_outcome(lap):
        """A dead lap's terminal outcome comes from its result file.

        Missing/unparseable/foreign result = crash. A child that died after
        writing 'timeout' parks (never re-dispatched) per selector.
        """
        try:
            with open(RESULT_PATH) as f:
                r = json.load(f)
        except (OSError, ValueError):
            return "crash"
        if r.get("issue") != lap["issue"] or r.get("outcome") not in OUTCOMES:
            return "crash"
        return r["outcome"]

    box = {}
    deps = {
        "state_path": state_path,
        "notify": notify,
        "claim": lambda now: claim_next(
            GITHUB_REPO,
            issues_dir=os.path.join(STATE_DIR, "claims"),
            dispositions=(box.get("state") or {}).get("issues", {}),
        ),
        "start_lap": start_lap,
        "kill_lap": kill_lap,
        "lap_outcome": lap_outcome,
        "reconcile": lambda now: [],
    }
    while True:
        state = load_state(state_path)
        box["state"] = state
        events = tick(state, time.time(), deps)
        if "HALT" in events:
            notify("supervisor HALT: " + ",".join(events))
            break
        time.sleep(5)


if __name__ == "__main__":
    main()
