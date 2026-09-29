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
    SESSION_WALLCLOCK_LIMIT_S,
    SCENARIOS_DIR,
    STATE_DIR,
)

RESULT_PATH = os.path.join(STATE_DIR, "lap-result.json")
RUNTIME_LOG_PATH = os.path.join(STATE_DIR, "interventions.jsonl")
LOCK_PATH = os.path.join(STATE_DIR, "supervisor.lock")
RECEIPTS_PATH = os.path.join(STATE_DIR, "evidence", "ntfy", "receipts.json")


def acquire_instance_lock(path=LOCK_PATH):
    """Single-instance guard: exclusive flock, held for the process lifetime
    (fd stays open). Two supervisors must never race the same state dir
    (L-009 restart races; BIGGEST_ISSUE_ANALYSIS §5). Returns the held fd or
    raises BlockingIOError.
    """
    import fcntl

    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    fd = os.open(path, os.O_CREAT | os.O_WRONLY)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        os.close(fd)
        raise
    return fd


def runtime_log(event, path=None, **fields):
    """Append one record to the run's append-only event log (L-015).

    This log is the S1 measuring instrument — S1 ("3 consecutive laps with
    zero human interventions") must be scoreable from this file alone, with
    no trust in anyone's memory of the night. Schema, one JSON object per
    line:
      {"ts": "<ISO8601 UTC>", "event": "<kind>", ...event-specific fields}
    Event kinds (closed set, one per line):
      session-start / session-halt / session-blocked / supervisor-restart
        supervisor lifecycle (pid recorded)
      dispatch — a lap was started (issue, run pid)
      lap-end — terminal lap outcome (issue, outcome, disposition, gate)
      lap-check — per-lap intervention audit at lap end: the "observed"
        field lists interventions reconcile detected for this lap; an empty
        list on every lap-check row for 3 consecutive laps is the mechanical
        S1 zero-touch proof. Absence of the file, or a missing lap-check per
        lap, means UNMEASURED, never "no interventions".
      intervention — reconcile reaped a claim-lifecycle artifact (orphan
        claim); a manual state edit is an intervention under the written S1
        text. Detector coverage: the orphan-claim reap class only — no
        pid-mismatch or retry-counter-drift detector is implemented
        (noted 2026-09-29).
      red-recheck — dispatch-time RED re-check verdict (issue, verdict).
    """
    path = path or RUNTIME_LOG_PATH
    row = {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "event": event}
    row.update(fields)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "a") as f:
        f.write(json.dumps(row, default=str) + "\n")

def notify(text, title="nightshift", url=NTFY_URL, opener=None):
    """One ntfy POST per terminal state. Inline by design, not a module.
    Best-effort: a failed notification must never kill a lap. On success the
    receipt is appended to state/evidence/ntfy/receipts.json (S7: a
    notification without a receipt is unobservable).

    Empty url (NTFY_TOPIC unset): no transport — but the receipt is still
    written; receipts are the S7 evidence, the phone channel is optional."""
    if not url:
        try:
            os.makedirs(os.path.dirname(RECEIPTS_PATH), exist_ok=True)
            with open(RECEIPTS_PATH, "a") as f:
                f.write(json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                                        time.gmtime()),
                                    "status": "no-transport", "message": text}) + "\n")
        except OSError:
            pass
        return None
    try:
        data = json.dumps({"topic": url.rstrip("/").rsplit("/", 1)[-1],
                           "title": title, "message": text}).encode()
        req = urllib.request.Request(url, data=data, method="POST")
        open_fn = opener.open if opener else urllib.request.urlopen
        resp = open_fn(req, timeout=10)
        resp.read()
        try:
            os.makedirs(os.path.dirname(RECEIPTS_PATH), exist_ok=True)
            with open(RECEIPTS_PATH, "a") as f:
                f.write(json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                                        time.gmtime()),
                                    "status": resp.status, "message": text}) + "\n")
        except OSError:
            pass  # receipt failure must not kill the lap either
        return resp.status
    except OSError as e:
        print("notify failed: %s" % e, file=sys.stderr, flush=True)
        return None


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
    # L-013: never spend a lap on an already-satisfied issue. Re-prove the
    # repro is RED on fresh main first; GREEN → reconcile as merged + skip.
    recheck = deps.get("red_recheck")
    if recheck:
        verdict = recheck(claim["issue"])
        runtime_log("red-recheck", issue=claim["issue"], verdict=verdict)
        if verdict == "pass":
            state.setdefault("issues", {}).setdefault(str(claim["issue"]), {"retries": 0})
            state["issues"][str(claim["issue"])]["disposition"] = "merged"
            try:
                os.remove(claim["path"])
            except OSError:
                pass
            save_state(state, deps["state_path"])
            return "already-satisfied"
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
    runtime_log("dispatch", issue=claim["issue"], pid=state["lap"].get("pid"))
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
    observed = deps.get("reconcile_observations") or []
    runtime_log("lap-end", issue=issue, outcome=outcome,
                disposition=disposition, gate=lap.get("gate"))
    runtime_log("lap-check", issue=issue, observed=observed)
    if observed:
        runtime_log("intervention", issue=issue, detail=observed)
    if disposition in ("retry", "merged", "parked", "timeout-park"):
        # retry: release so the retry re-acquires the same issue.
        # merged/parked/timeout-park are TERMINAL: the claim file is removed
        # here too — launch-4/launch-2 finding: leaving it made reconcile
        # report a dead claim on the next tick, which tick routed to
        # break_claim (unwired → KeyError → silent unit death right after a
        # lap-end row; this is what actually ended launch-2 and launch-4).
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
    # Sortie semantics: park escalates the issue and releases the queue to
    # continue; halt is reserved for wall-clock exceed (per-lap backstop here,
    # session backstop in main()).
    halt = (now - (state.get("started_at") or now)) > LAP_WALLCLOCK_LIMIT_S
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
            if d == "idle":
                issues = state.get("issues", {})
                blocked = [int(n) for n, r in issues.items()
                           if r.get("disposition") not in ("parked", "timeout-park", "merged")]
                parked = sum(1 for r in issues.values() if r.get("disposition") in ("parked", "timeout-park"))
                merged = sum(1 for r in issues.values() if r.get("disposition") == "merged")
                if blocked:
                    events.append("BLOCKED:%s" % ",".join(map(str, sorted(blocked))))
                else:
                    events.append("DRAIN:%d parked, %d merged" % (parked, merged))

    # reconcile: reap claims for issues with no live lap (supervisor restart)
    observations = deps.get("reconcile_observations") or []
    for path, claim in deps.get("reconcile", lambda now: [])(now):
        if not state.get("lap") or state["lap"].get("issue") != claim["issue"]:
            deps["break_claim"](path, now)
            events.append("reclaimed:%s" % path)
            note = "orphan claim reaped: %s (issue %s)" % (path, claim.get("issue"))
            observations.append(note)
            runtime_log("intervention", detail=note, claim=path)
    save_state(state, deps["state_path"])
    return events

def reconcile_dead_claims(now, state, claims_dir, result_path=RESULT_PATH):
    """L-009 + crash-retry accounting: claim files no live lap owns.

    Two reap classes, counted differently:
    - terminal-result claim (its lap reached handle_lap_end) or durably
      parked/merged issue: reap only — already accounted.
    - orphan claim with NO terminal result (a lap crashed between
      supervisor restarts and nothing ever saw the outcome): reap AND
      count the crash through selector.handle_outcome — the crash must
      consume retry budget, never surface as a free silent retry.
    NEVER touches the live lap's claim: state["lap"]["issue"] is mid-flight
    (its result file is legitimately absent while it runs), and the tick
    health-check path owns that lap's accounting. Found live at S1 launch:
    counting it reaped the in-flight issue 0→parked in three ticks.
    Returns [(path, claim), ...] for the caller to break and log.
    """
    from selector import OUTCOMES, handle_outcome, read_claim

    live_issue = (state.get("lap") or {}).get("issue")
    dead = []
    for name in sorted(os.listdir(claims_dir)):
        if not name.startswith("issue-"):
            continue
        path = os.path.join(claims_dir, name)
        try:
            claim = read_claim(path)
        except Exception:
            dead.append((path, {"issue": None}))
            continue
        issue = claim.get("issue")
        if issue is not None and issue == live_issue:
            continue  # the live lap owns this claim; mid-flight ≠ orphan
        rec = state.get("issues", {}).get(str(issue), {})
        if rec.get("disposition") in ("parked", "timeout-park", "merged"):
            dead.append((path, claim))
            continue
        terminal = False
        if os.path.exists(result_path):
            try:
                with open(result_path) as f:
                    r = json.load(f)
                if r.get("issue") == issue and r.get("outcome") in OUTCOMES:
                    terminal = True
            except (OSError, ValueError):
                pass
        if terminal:
            dead.append((path, claim))
        elif issue is not None:
            # unaccounted crash: count it now, never a free retry
            disposition = handle_outcome("crash", issue, state, now)
            runtime_log("intervention",
                        detail="orphan claim reaped with no terminal result "
                               "(crash counted at reap): %s" % path,
                        issue=issue, disposition=disposition)
            dead.append((path, claim))
    return dead



def main():
    """Real loop: claim -> dispatch -> watch -> park/retry per selector budget."""
    from selector import OUTCOMES, break_stale_claim, claim_next

    state_path = os.path.join(STATE_DIR, "state.json")
    os.makedirs(STATE_DIR, exist_ok=True)
    lock_fd = acquire_instance_lock()
    try:
        os.write(lock_fd, str(os.getpid()).encode())
    except OSError:
        pass  # lock content is diagnostic only; the flock is the guard
    runtime_log("session-start", pid=os.getpid())

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
    observations = []  # per-tick intervention observations, shared with handle_lap_end

    def reconcile_claims(now):
        return reconcile_dead_claims(now, box.get("state") or {},
                                     os.path.join(STATE_DIR, "claims"))

    def red_recheck(issue):
        """L-013: re-run the issue's scenario against fresh origin/main
        BEFORE spending a lap. 'pass' = main already satisfies it (the
        issue is vacated — a lap would be a refactor lap, not work).
        Anything else (fail/hold/crash) = still RED → dispatch.
        """
        import lap as lapmod
        import verify

        worktree = lapmod.worktree_for(issue, prefix="recheck")
        try:
            pid_file = os.path.join("/tmp", "factory-recheck-%d.pid" % issue)
            evidence = verify.verify_candidate(worktree, pid_file, SCENARIOS_DIR, issue=issue)
            return evidence.get("verdict")
        except Exception:
            return None  # recheck itself failed → treat as RED, spend the lap
        finally:
            subprocess.run(["git", "worktree", "remove", "--force", worktree],
                           cwd=os.path.expanduser(lapmod.PRODUCT_REPO), capture_output=True)

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
        "reconcile": reconcile_claims,
        # launch-4 finding: tick() breaks every dead claim reconcile reports,
        # including leftover TERMINAL claims after a merged lap — the dep was
        # never wired, so the first post-success tick died with KeyError
        # 'break_claim' (supervisor.py:278) and the unit failed. Reaping a
        # terminal claim here is reap-only: its disposition is already merged,
        # so nothing is recounted.
        "break_claim": break_stale_claim,
        "red_recheck": red_recheck,
        "reconcile_observations": observations,
    }
    session_started = time.time()
    while True:
        state = load_state(state_path)
        box["state"] = state
        del observations[:]
        now = time.time()
        try:
            events = tick(state, now, deps)
        except Exception as e:  # noqa: BLE001 - launch-2/4 finding: a bookkeeping
            # error must NEVER silently kill an unattended night; the log
            # simply stops otherwise, and the death goes misread. Log + continue.
            runtime_log("tick-error", error=repr(e),
                        traceback=__import__("traceback").format_exc())
            time.sleep(5)
            continue
        if "HALT" in events:
            runtime_log("session-halt", events=events)
            notify("supervisor HALT: " + ",".join(events))
            break
        if any(e.startswith("DRAIN") for e in events):
            runtime_log("session-halt", reason="drained", events=events)
            notify("queue drained: " + next(e[6:] for e in events if e.startswith("DRAIN")))
            break
        if any(e.startswith("BLOCKED") for e in events):
            blocked = next(e[8:] for e in events if e.startswith("BLOCKED"))
            runtime_log("session-blocked", issues=blocked)
            notify("queue blocked: issue %s open PR or live claim" % blocked)
            sys.exit(1)
        if now - session_started > SESSION_WALLCLOCK_LIMIT_S:
            runtime_log("session-halt", reason="session wallclock exceeded")
            notify("supervisor HALT: session wallclock %ds exceeded" % SESSION_WALLCLOCK_LIMIT_S)
            break
        time.sleep(5)


if __name__ == "__main__":
    main()
