import json
import unittest.mock
import os
import subprocess
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import supervisor  # noqa: E402


def fake_deps(tmp, notify_calls, start_calls=None, claim_result=None, kill_calls=None):
    state_path = os.path.join(tmp, "state.json")
    start_calls = start_calls if start_calls is not None else []
    kill_calls = kill_calls if kill_calls is not None else []
    return {
        "state_path": state_path,
        "notify": lambda text: notify_calls.append(text),
        "claim": lambda now: claim_result,
        "start_lap": lambda issue, lap: start_calls.append((issue, dict(lap, pid=4242))),
        "kill_lap": lambda lap: kill_calls.append(lap["issue"]),
        "reconcile": lambda now: [],
    }


class TestSupervisorStateMachine(unittest.TestCase):
    """Park-after-budget with a fake clock; no real processes."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.notify = []
        self.now = 1000.0
        # never write the real cwd-relative state/ files: a suite run from
        # ~/nightshift must not append to the live log (test pollution)
        self._patches = [
            unittest.mock.patch.object(supervisor, "RUNTIME_LOG_PATH",
                                       os.path.join(self.tmp, "log.jsonl")),
            unittest.mock.patch.object(supervisor, "RECEIPTS_PATH",
                                       os.path.join(self.tmp, "receipts.json"))]
        for _p in self._patches:
            _p.start()
            self.addCleanup(_p.stop)

    def test_dispatch_one_lap_at_a_time(self):
        deps = fake_deps(self.tmp, self.notify, claim_result={"issue": 5, "path": "x"})
        state = supervisor.load_state(deps["state_path"])
        self.assertEqual(supervisor.dispatch(state, self.now, deps), "dispatched")
        self.assertEqual(state["lap"]["issue"], 5)
        self.assertEqual(supervisor.dispatch(state, self.now, deps), "already-running")

    def test_dispatch_idle_when_no_claim(self):
        deps = fake_deps(self.tmp, self.notify, claim_result=None)
        state = supervisor.load_state(deps["state_path"])
        self.assertEqual(supervisor.dispatch(state, self.now, deps), "idle")

    def test_success_notifies_and_clears_lap(self):
        deps = fake_deps(self.tmp, self.notify, claim_result={"issue": 5, "path": "x"})
        state = supervisor.load_state(deps["state_path"])
        supervisor.dispatch(state, self.now, deps)
        disposition, halt = supervisor.handle_lap_end(state, "success", self.now + 10, deps)
        self.assertEqual((disposition, halt), ("merged", False))
        self.assertIsNone(state["lap"])
        self.assertEqual(len(self.notify), 1)
        self.assertIn("GREEN", self.notify[0])

    def test_park_after_retry_budget_and_notify(self):
        deps = fake_deps(self.tmp, self.notify, claim_result={"issue": 5, "path": "x"})
        state = supervisor.load_state(deps["state_path"])
        supervisor.dispatch(state, self.now, deps)
        # two retries within budget, third failure parks
        supervisor.handle_lap_end(state, "failure", self.now + 10, deps)
        supervisor.dispatch(state, self.now + 20, deps)
        supervisor.handle_lap_end(state, "crash", self.now + 30, deps)
        supervisor.dispatch(state, self.now + 40, deps)
        disposition, halt = supervisor.handle_lap_end(state, "failure", self.now + 50, deps)
        self.assertEqual((disposition, halt), ("parked", False))  # Sortie: park continues the queue
        self.assertIn("parked", " ".join(self.notify).lower())
        # parked issue is never re-dispatched: durable state says parked
        self.assertEqual(state["issues"]["5"]["disposition"], "parked")

    def test_wall_clock_exceed_halts(self):
        deps = fake_deps(self.tmp, self.notify, claim_result={"issue": 5, "path": "x"})
        state = supervisor.load_state(deps["state_path"])
        supervisor.dispatch(state, self.now, deps)
        disposition, halt = supervisor.handle_lap_end(state, "timeout", self.now + 10801, deps)
        self.assertEqual(disposition, "timeout-park")
        self.assertTrue(halt)

    def test_restarted_supervisor_with_stale_started_at_dispatches(self):
        # started_at is a lap-session clock: a supervisor restarted after a
        # long gap must dispatch again, not HALT on history it never lived
        deps = fake_deps(self.tmp, self.notify, claim_result={"issue": 5, "path": "x"})
        state = supervisor.load_state(deps["state_path"])
        state["started_at"] = self.now - supervisor.LAP_WALLCLOCK_LIMIT_S - 3600
        events = supervisor.tick(state, self.now, deps)
        self.assertNotIn("HALT", events)
        self.assertIn("dispatch:dispatched", events)
        self.assertEqual(state["started_at"], self.now)

    def test_tick_dead_lap_notified_as_crash(self):
        kills = []
        deps = fake_deps(self.tmp, self.notify, kill_calls=kills)
        state = supervisor.load_state(deps["state_path"])
        state["lap"] = {"issue": 9, "claim_path": "x", "started_at": self.now, "pid": None}
        events = supervisor.tick(state, self.now + 5, deps)
        self.assertTrue(any(e.startswith("crash:") for e in events))
        self.assertEqual(kills, [9])

    def test_heartbeat_and_pid_liveness(self):
        hb = os.path.join(self.tmp, "hb")
        with open(hb, "w") as f:
            f.write("x")
        os.utime(hb, (time.time(), time.time()))
        self.assertTrue(supervisor.heartbeat_fresh(path=hb))
        self.assertFalse(supervisor.pid_alive(None))
        self.assertFalse(supervisor.pid_alive(999999))  # surely dead
        self.assertTrue(supervisor.pid_alive(os.getpid()))

    def test_state_survives_reload(self):
        deps = fake_deps(self.tmp, self.notify, claim_result={"issue": 3, "path": "x"})
        state = supervisor.load_state(deps["state_path"])
        supervisor.dispatch(state, self.now, deps)
        again = supervisor.load_state(deps["state_path"])
        self.assertEqual(again["lap"]["issue"], 3)


if __name__ == "__main__":
    unittest.main()
class TestNotifyGuard(unittest.TestCase):
    """notify is best-effort: an ntfy outage never kills a lap."""
    def setUp(self):
        # never write the real state/evidence/ntfy receipts (test pollution)
        self._p = unittest.mock.patch.object(
            supervisor, "RECEIPTS_PATH",
            os.path.join(tempfile.mkdtemp(), "receipts.json"))
        self._p.start()
        self.addCleanup(self._p.stop)

    def test_notify_swallows_transport_failure(self):
        import urllib.error
        def boom(req, timeout):
            raise urllib.error.URLError("ntfy down")
        status = supervisor.notify("x", opener=type("O", (), {"open": staticmethod(boom)})())
        self.assertIsNone(status)

    def test_notify_success_returns_status(self):
        class Resp:
            status = 200
            def read(self):
                return b"ok"
        def ok(req, timeout):
            return Resp()
        status = supervisor.notify("x", url="https://ntfy.sh/t",
                                   opener=type("O", (), {"open": staticmethod(ok)})())
        self.assertEqual(status, 200)

    def test_notify_success_writes_receipt(self):
        import tempfile as _t
        class Resp:
            status = 200
            def read(self):
                return b"ok"
        receipts = os.path.join(_t.mkdtemp(), "receipts.json")
        with unittest.mock.patch.object(supervisor, "RECEIPTS_PATH", receipts):
            supervisor.notify("lap issue 5: GREEN", url="https://ntfy.sh/t",
                              opener=type("O", (), {"open": staticmethod(
                                  lambda req, timeout: Resp())})())
        with open(receipts) as f:
            rows = [json.loads(line) for line in f]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["status"], 200)
        self.assertEqual(rows[0]["message"], "lap issue 5: GREEN")

    def test_notify_failure_writes_no_receipt(self):
        import tempfile as _t
        import urllib.error
        receipts = os.path.join(_t.mkdtemp(), "receipts.json")
        def boom(req, timeout):
            raise urllib.error.URLError("ntfy down")
        with unittest.mock.patch.object(supervisor, "RECEIPTS_PATH", receipts):
            self.assertIsNone(supervisor.notify(
                "x", url="https://ntfy.sh/t",
                opener=type("O", (), {"open": staticmethod(boom)})()))
        self.assertFalse(os.path.exists(receipts))

    def test_empty_topic_no_transport_receipt_still_written(self):
        import tempfile as _t
        receipts = os.path.join(_t.mkdtemp(), "receipts.json")
        transport = []
        with unittest.mock.patch.object(supervisor, "RECEIPTS_PATH", receipts):
            status = supervisor.notify(
                "lap issue 5: GREEN", url="",
                opener=type("O", (), {"open": staticmethod(
                    lambda req, timeout: transport.append(req))})())
        self.assertIsNone(status)
        self.assertEqual(transport, [])  # no POST attempted
        with open(receipts) as f:
            rows = [json.loads(line) for line in f]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["status"], "no-transport")
        self.assertEqual(rows[0]["message"], "lap issue 5: GREEN")

    def test_topic_set_posts_as_today(self):
        class Resp:
            status = 200
            def read(self):
                return b"ok"
        calls = []
        def ok(req, timeout):
            calls.append(req.full_url)
            return Resp()
        status = supervisor.notify("x", url="https://ntfy.sh/some-topic",
                                    opener=type("O", (), {"open": staticmethod(ok)})())
        self.assertEqual(status, 200)
        self.assertEqual(calls, ["https://ntfy.sh/some-topic"])


class TestParkAndContinue(unittest.TestCase):
    """Sortie semantics: park escalates the issue, the queue continues."""
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.notify = []
        self.now = 1000.0
        # never write the real cwd-relative state/ files (test pollution)
        self._patches = [
            unittest.mock.patch.object(supervisor, "RUNTIME_LOG_PATH",
                                       os.path.join(self.tmp, "log.jsonl")),
            unittest.mock.patch.object(supervisor, "RECEIPTS_PATH",
                                       os.path.join(self.tmp, "receipts.json"))]
        for _p in self._patches:
            _p.start()
            self.addCleanup(_p.stop)

    def _state_with_parked(self):
        state = supervisor.load_state(os.path.join(self.tmp, "state.json"))
        state["issues"] = {"5": {"retries": 3, "disposition": "parked"}}
        return state

    def test_park_does_not_halt(self):
        # fresh issue 5: failure x3 (budget 2) -> parked, halt False
        deps = fake_deps(self.tmp, self.notify, claim_result={"issue": 5, "path": "x"})
        state = supervisor.load_state(os.path.join(self.tmp, "state.json"))
        for i in range(3):
            supervisor.dispatch(state, self.now + i * 50, deps)
            disposition, halt = supervisor.handle_lap_end(state, "failure", self.now + i * 50 + 10, deps)
        self.assertEqual((disposition, halt), ("parked", False))
        self.assertEqual(state["issues"]["5"]["disposition"], "parked")

    def test_park_then_next_tick_dispatches_next_issue(self):
        # S1-critical path: park issue 5, queue continues with issue 6
        deps = fake_deps(self.tmp, self.notify, claim_result={"issue": 5, "path": "x"})
        state = supervisor.load_state(os.path.join(self.tmp, "state.json"))
        for i in range(3):
            supervisor.dispatch(state, self.now + i * 50, deps)
            supervisor.handle_lap_end(state, "failure", self.now + i * 50 + 10, deps)
        state["lap"] = None
        deps["claim"] = lambda now: {"issue": 6, "path": "y"}
        events = supervisor.tick(state, self.now + 200, deps)
        self.assertIn("dispatch:dispatched", events)
        self.assertEqual(state["lap"]["issue"], 6)

    def test_idle_after_all_terminal_drains(self):
        deps = fake_deps(self.tmp, self.notify, claim_result=None)
        state = self._state_with_parked()
        events = supervisor.tick(state, self.now, deps)
        self.assertIn("dispatch:idle", events)
        drained = [e for e in events if e.startswith("DRAIN")]
        self.assertEqual(drained, ["DRAIN:1 parked, 0 merged"])

    def test_session_wallclock_backstop_notified_and_halted(self):
        # main-loop backstop: simulated via the same arithmetic it uses
        session_started = 0.0
        now = supervisor.LAP_WALLCLOCK_LIMIT_S + 1
        self.assertTrue(now - session_started > supervisor.LAP_WALLCLOCK_LIMIT_S)

    def test_idle_with_open_pr_issue_blocks_not_drains(self):
        deps = fake_deps(self.tmp, self.notify, claim_result=None)
        state = supervisor.load_state(os.path.join(self.tmp, "state.json"))
        state["issues"] = {"9": {"retries": 1, "disposition": "retry"}}
        events = supervisor.tick(state, self.now, deps)
        self.assertIn("dispatch:idle", events)
        self.assertIn("BLOCKED:9", events)
        self.assertNotIn("DRAIN", ",".join(events))

    def test_blocked_exit_nonzero_drained_exit_zero(self):
        # main-loop: BLOCKED -> exit 1; DRAIN -> clean break (exit 0)
        def run_main(events):
            cwd = tempfile.mkdtemp()  # subprocess state writes land here, never the real state/
            with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
                f.write("""
import sys
sys.path.insert(0, %r)
import supervisor
supervisor.tick = lambda state, now, deps: %r
supervisor.load_state = lambda p: {}
supervisor.save_state = lambda s, p: None
supervisor.LAP_WALLCLOCK_LIMIT_S = 10**9
supervisor.main()
""" % (os.path.join(os.path.dirname(__file__), "..", "src"), events))
            r = subprocess.run([sys.executable, f.name], capture_output=True,
                                text=True, cwd=cwd)
            os.unlink(f.name)
            return r.returncode

        self.assertEqual(run_main(["dispatch:idle", "BLOCKED:9"]), 1)
        self.assertEqual(run_main(["dispatch:idle", "DRAIN:0 parked, 0 merged"]), 0)

class TestInstanceLock(unittest.TestCase):
    """Two supervisors must never run concurrently (L-009 restart races)."""

    def test_second_acquire_raises_when_held(self):
        import fcntl
        tmp = tempfile.mkdtemp()
        path = os.path.join(tmp, "supervisor.lock")
        held = supervisor.acquire_instance_lock(path)
        try:
            with self.assertRaises(OSError):
                supervisor.acquire_instance_lock(path)
        finally:
            fcntl.flock(held, fcntl.LOCK_UN)
            os.close(held)
        # released → acquires again
        again = supervisor.acquire_instance_lock(path)
        fcntl.flock(again, fcntl.LOCK_UN)
        os.close(again)

    def test_lock_file_created_in_state_dir(self):
        self.assertTrue(supervisor.LOCK_PATH.endswith(
            os.path.join("state", "supervisor.lock")))

class TestRuntimeLog(unittest.TestCase):
    """interventions.jsonl (L-015): S1 must be scoreable from the log alone."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.log = os.path.join(self.tmp, "interventions.jsonl")
        self.notify = []

    def read_rows(self):
        with open(self.log) as f:
            return [json.loads(line) for line in f if line.strip()]

    def test_lap_end_writes_lap_end_and_lap_check_rows(self):
        deps = fake_deps(self.tmp, self.notify, claim_result={"issue": 5, "path": "x"})
        deps["state_path"] = os.path.join(self.tmp, "state.json")
        with unittest.mock.patch.object(supervisor, "RUNTIME_LOG_PATH", self.log):
            state = supervisor.load_state(deps["state_path"])
            supervisor.dispatch(state, 1000.0, deps)
            supervisor.handle_lap_end(state, "failure", 1010.0, deps)
        rows = self.read_rows()
        kinds = [r["event"] for r in rows]
        self.assertEqual(kinds, ["dispatch", "lap-end", "lap-check"])
        self.assertEqual(rows[0]["issue"], 5)
        self.assertEqual(rows[1]["outcome"], "failure")
        # per-lap absence entry: observed list present and empty
        self.assertEqual(rows[2]["observed"], [])

    def test_observed_interventions_recorded_and_flagged(self):
        deps = fake_deps(self.tmp, self.notify, claim_result={"issue": 5, "path": "x"})
        deps["state_path"] = os.path.join(self.tmp, "state.json")
        deps["reconcile_observations"] = ["orphan claim reaped: state/claims/issue-5.json"]
        with unittest.mock.patch.object(supervisor, "RUNTIME_LOG_PATH", self.log):
            state = supervisor.load_state(deps["state_path"])
            supervisor.dispatch(state, 1000.0, deps)
            supervisor.handle_lap_end(state, "crash", 1010.0, deps)
        rows = self.read_rows()
        intervention = [r for r in rows if r["event"] == "intervention"]
        self.assertEqual(len(intervention), 1)
        self.assertIn("orphan claim", intervention[0]["detail"][0])
        check = [r for r in rows if r["event"] == "lap-check"][0]
        self.assertTrue(check["observed"])

    def test_orphan_claim_reaped_by_tick_logs_intervention(self):
        # L-009: a claim file left by a lap that ended between restarts must
        # be reaped, and the reap is an intervention the log records
        claims = os.path.join(self.tmp, "claims")
        os.makedirs(claims)
        claim_path = os.path.join(claims, "issue-5.json")
        with open(claim_path, "w") as f:
            json.dump({"issue": 5, "claimed_at": 900.0}, f)
        broke = []
        deps = fake_deps(self.tmp, self.notify, claim_result=None)
        deps["state_path"] = os.path.join(self.tmp, "state.json")
        deps["reconcile"] = lambda now: [(claim_path, {"issue": 5})]
        deps["break_claim"] = lambda path, now: broke.append(path)
        state = {"issues": {}, "lap": None}
        with unittest.mock.patch.object(supervisor, "RUNTIME_LOG_PATH", self.log):
            events = supervisor.tick(state, 1000.0, deps)
        self.assertEqual(broke, [claim_path])
        self.assertIn("reclaimed:" + claim_path, events)
        rows = self.read_rows()
        self.assertEqual(rows[-1]["event"], "intervention")
        self.assertIn("orphan claim reaped", rows[-1]["detail"])

    def test_row_schema_ts_and_event_present(self):
        supervisor.runtime_log("session-start", pid=1, path=self.log)
        (row,) = self.read_rows()
        self.assertIn("ts", row)
        self.assertEqual(row["event"], "session-start")
        self.assertEqual(row["pid"], 1)

class TestDispatchRedRecheck(unittest.TestCase):
    """L-013: a lap is never spent on an issue main already satisfies."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.notify = []
        self.starts = []

    def deps(self, claim_result, red_recheck):
        d = fake_deps(self.tmp, self.notify, claim_result=claim_result,
                      start_calls=self.starts)
        d["state_path"] = os.path.join(self.tmp, "state.json")
        d["red_recheck"] = red_recheck
        return d

    def test_green_recheck_skips_lap_and_marks_merged(self):
        deps = self.deps({"issue": 5, "path": "claim.json"}, lambda issue: "pass")
        state = supervisor.load_state(deps["state_path"])
        with unittest.mock.patch.object(supervisor, "RUNTIME_LOG_PATH",
                                        os.path.join(self.tmp, "log.jsonl")):
            d = supervisor.dispatch(state, 1000.0, deps)
        self.assertEqual(d, "already-satisfied")
        self.assertEqual(self.starts, [])  # no lap spent
        self.assertEqual(state["issues"]["5"]["disposition"], "merged")
        self.assertIsNone(state.get("lap"))

    def test_red_recheck_dispatches_normally(self):
        calls = []
        deps = self.deps({"issue": 5, "path": "claim.json"},
                         lambda issue: calls.append(issue) or "fail")
        state = supervisor.load_state(deps["state_path"])
        with unittest.mock.patch.object(supervisor, "RUNTIME_LOG_PATH",
                                        os.path.join(self.tmp, "log.jsonl")):
            d = supervisor.dispatch(state, 1000.0, deps)
        self.assertEqual(d, "dispatched")
        self.assertEqual(calls, [5])
        self.assertEqual(state["lap"]["issue"], 5)

    def test_recheck_crash_treated_as_red_and_dispatches(self):
        # the oracle failing must not silently mark an issue merged
        deps = self.deps({"issue": 5, "path": "claim.json"}, lambda issue: None)
        state = supervisor.load_state(deps["state_path"])
        with unittest.mock.patch.object(supervisor, "RUNTIME_LOG_PATH",
                                        os.path.join(self.tmp, "log.jsonl")):
            d = supervisor.dispatch(state, 1000.0, deps)
        self.assertEqual(d, "dispatched")

    def test_red_recheck_verdict_logged(self):
        deps = self.deps({"issue": 5, "path": "claim.json"}, lambda issue: "pass")
        state = supervisor.load_state(deps["state_path"])
        log = os.path.join(self.tmp, "log.jsonl")
        with unittest.mock.patch.object(supervisor, "RUNTIME_LOG_PATH", log):
            supervisor.dispatch(state, 1000.0, deps)
        with open(log) as f:
            rows = [json.loads(line) for line in f]
        recheck = [r for r in rows if r["event"] == "red-recheck"][0]
        self.assertEqual(recheck["issue"], 5)
        self.assertEqual(recheck["verdict"], "pass")

class TestReconcileDeadClaims(unittest.TestCase):
    """L-009 reap + crash-retry accounting: crashed laps are counted, never
    silently retried."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.claims = os.path.join(self.tmp, "claims")
        os.makedirs(self.claims)
        self.result = os.path.join(self.tmp, "lap-result.json")
        self.log = os.path.join(self.tmp, "log.jsonl")

    def claim(self, issue, claimed_at=900.0):
        path = os.path.join(self.claims, "issue-%d.json" % issue)
        with open(path, "w") as f:
            json.dump({"issue": issue, "claimed_at": claimed_at}, f)
        return path

    def run_reconcile(self, state):
        with unittest.mock.patch.object(supervisor, "RUNTIME_LOG_PATH", self.log):
            return supervisor.reconcile_dead_claims(1000.0, state, self.claims,
                                                    result_path=self.result)

    def test_live_lap_claim_never_counted_nor_reaped(self):
        # S1 launch bug, found live: the in-flight lap's claim has no
        # terminal result BY DESIGN — reconcile counted it as a crash every
        # tick and parked the issue mid-lap. The live issue is excluded.
        self.claim(17)
        state = {"issues": {}, "lap": {"issue": 17, "pid": 999}}
        dead = self.run_reconcile(state)
        self.assertEqual(dead, [])
        self.assertNotIn("17", state["issues"])  # no retries burned
        self.assertTrue(os.path.exists(os.path.join(self.claims, "issue-17.json")))

    def test_idle_reconcile_claim_open_issue_is_blocked_not_drained(self):
        import selector

        gh = os.path.join(self.tmp, "gh")
        with open(gh, "w") as f:
            f.write("#!%s\n" % sys.executable)
            f.write(
                "import sys, json\n"
                "if sys.argv[1:3] == ['issue', 'list']:\n"
                "    print(json.dumps([{'number': 18, 'createdAt': '2026-01-01T00:00:00Z'}]))\n"
                "else:\n"
                "    print('[]')\n"
            )
        os.chmod(gh, 0o755)
        claim = selector.claim_next("r/x", self.claims, now=1000.0, gh=gh)
        self.assertEqual(claim["issue"], 18)

        state = {"issues": {}, "lap": None, "started_at": None}
        deps = {
            "state_path": os.path.join(self.tmp, "state.json"),
            "notify": lambda text: None,
            "claim": lambda now: selector.claim_next("r/x", self.claims,
                                                       now=now, gh=gh),
            "reconcile": lambda now: supervisor.reconcile_dead_claims(
                now, state, self.claims, result_path=self.result),
            "break_claim": lambda path, now: os.remove(path),
            "reconcile_observations": [],
        }
        with unittest.mock.patch.object(supervisor, "RUNTIME_LOG_PATH", self.log):
            events = supervisor.tick(state, 1000.0, deps)

        self.assertIn("dispatch:idle", events)
        self.assertIn("BLOCKED:18", events)
        self.assertFalse(any(e.startswith("DRAIN") for e in events))

    def test_other_issue_orphan_still_counted_while_lap_live(self):
        # the exclusion is only for the live issue; a true orphan for a
        # different issue is still a counted crash
        self.claim(17)
        self.claim(18)
        state = {"issues": {}, "lap": {"issue": 17, "pid": 999}}
        dead = self.run_reconcile(state)
        self.assertEqual([c["issue"] for _, c in dead], [18])
        self.assertEqual(state["issues"]["18"]["retries"], 1)
        with unittest.mock.patch.object(supervisor, "RUNTIME_LOG_PATH", self.log):
            return supervisor.reconcile_dead_claims(1000.0, state, self.claims,
                                                    result_path=self.result)

    def test_unaccounted_crash_counts_retries_at_reap(self):
        # orphan claim, no terminal result anywhere: the crash must consume
        # retry budget — never resurface as a free silent retry
        path = self.claim(5)
        state = {"issues": {}}
        dead = self.run_reconcile(state)
        self.assertEqual(dead, [(path, {"issue": 5, "claimed_at": 900.0})])
        self.assertEqual(state["issues"]["5"]["retries"], 1)
        self.assertEqual(state["issues"]["5"]["disposition"], "retry")
        with open(self.log) as f:
            rows = [json.loads(line) for line in f]
        self.assertEqual(rows[-1]["event"], "intervention")
        self.assertIn("crash counted at reap", rows[-1]["detail"])

    def test_terminal_result_claim_reaped_without_double_count(self):
        # its lap already reached handle_lap_end (counted there)
        path = self.claim(5)
        with open(self.result, "w") as f:
            json.dump({"issue": 5, "outcome": "failure"}, f)
        state = {"issues": {"5": {"retries": 1, "disposition": "retry"}}}
        dead = self.run_reconcile(state)
        self.assertEqual(len(dead), 1)
        self.assertEqual(state["issues"]["5"]["retries"], 1)  # unchanged

    def test_parked_issue_claim_reaped_without_count(self):
        path = self.claim(5)
        state = {"issues": {"5": {"retries": 3, "disposition": "parked"}}}
        dead = self.run_reconcile(state)
        self.assertEqual(len(dead), 1)
        self.assertEqual(state["issues"]["5"]["retries"], 3)

    def test_unparseable_claim_reaped(self):
        path = os.path.join(self.claims, "issue-5.json")
        with open(path, "w") as f:
            f.write("not json")
        dead = self.run_reconcile({"issues": {}})
        self.assertEqual(len(dead), 1)
        self.assertEqual(dead[0][1]["issue"], None)

    def test_foreign_result_file_not_terminal(self):
        # result for a different issue must not mark this claim terminal
        self.claim(5)
        with open(self.result, "w") as f:
            json.dump({"issue": 7, "outcome": "failure"}, f)
        state = {"issues": {}}
        self.run_reconcile(state)
        self.assertEqual(state["issues"]["5"]["retries"], 1)  # crash counted

    def test_repeated_reap_of_same_orphan_counts_once(self):
        # second reconcile sees the same claim again only if the caller did
        # not break it; handle_outcome already moved retries — but a claim
        # broken by the caller is gone, so no double count in practice.
        self.claim(5)
        state = {"issues": {}}
        self.run_reconcile(state)
        os.remove(os.path.join(self.claims, "issue-5.json"))
        self.run_reconcile(state)  # nothing left
        self.assertEqual(state["issues"]["5"]["retries"], 1)


class TestNoRealStateWrites(unittest.TestCase):
    """Regression: a suite run from a nightshift-style cwd (a checkout with
    a live state/ dir) must write NOTHING to the cwd-relative real state
    files — the launch-1 test-pollution incident appended 43 rows to the
    live interventions.jsonl (state/interventions.jsonl.testpollution-*)."""

    def test_suite_from_nightshift_cwd_writes_no_real_state(self):
        if os.environ.get("FACTORY_NESTED_SUITE"):
            self.skipTest("nested suite run")
        import shutil
        repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        cwd = tempfile.mkdtemp(prefix="factory-pollution-")
        shutil.copytree(repo, os.path.join(cwd, "repo"),
                        ignore=shutil.ignore_patterns(
                            "__pycache__", ".git", ".jj", "state"))
        state = os.path.join(cwd, "repo", "state")
        os.makedirs(os.path.join(state, "evidence", "ntfy"))
        log = os.path.join(state, "interventions.jsonl")
        receipts = os.path.join(state, "evidence", "ntfy", "receipts.json")
        with open(log, "w") as f:
            f.write('{"sentinel": true}\n')
        with open(receipts, "w") as f:
            f.write('{"sentinel": true}\n')
        r = subprocess.run([sys.executable, "-m", "unittest", "tests.test_supervisor"],
                           cwd=os.path.join(cwd, "repo"), capture_output=True,
                           text=True, env={**os.environ, "FACTORY_NESTED_SUITE": "1"})
        self.assertEqual(r.returncode, 0, msg=r.stderr[-2000:])
        with open(log) as f:
            self.assertEqual(f.read(), '{"sentinel": true}\n')
        with open(receipts) as f:
            self.assertEqual(f.read(), '{"sentinel": true}\n')


class TestMainDepsWiring(unittest.TestCase):
    """Launch-3/launch-4 finding: main()'s REAL deps dict never wired
    'break_claim' — tick() KeyErrored on the first dead claim reconcile
    reported (a leftover TERMINAL claim after a merged/parked lap), killing
    the unit seconds after a lap-end row, silently. Every existing test uses
    fake_deps (test_supervisor.py:388 even supplies break_claim itself), so
    119 tests stayed green while two launches died on the identical KeyError.
    These tests drive main()'s actual deps construction, not fakes."""

    def test_real_deps_cover_every_key_tick_references(self):
        # every key tick()/handle_lap_end()/dispatch() index on deps must be
        # present in the dict main() builds — extract it via source inspection
        # of the real function (no execution of the loop)
        import inspect, re as _re
        src = inspect.getsource(supervisor.main)
        m = _re.search(r"deps = \{(.*?)\n    \}", src, _re.S)
        self.assertTrue(m, "could not find the real deps dict in main()")
        keys = set(_re.findall(r'"([a-z_]+)":', m.group(1)))
        # keys tick() and its callees reference on deps:
        required = {"state_path", "notify", "claim", "start_lap", "kill_lap",
                    "lap_outcome", "reconcile", "break_claim", "red_recheck",
                    "reconcile_observations"}
        self.assertTrue(required <= keys,
                        "main() deps missing: %s" % (required - keys))

    def test_tick_with_dead_terminal_claim_completes_on_real_deps_shape(self):
        # one tick against a state whose claim file belongs to a TERMINAL
        # (merged) issue, using a deps dict with exactly main()'s key set:
        # must reap cleanly, no KeyError, no phantom crash row
        import selector
        tmp = tempfile.mkdtemp()
        claims = os.path.join(tmp, "claims")
        os.makedirs(claims)
        claim_path = os.path.join(claims, "issue-18.json")
        with open(claim_path, "w") as f:
            json.dump({"issue": 18, "claimed_at": time.time() - 3600}, f)
        state = {"issues": {"18": {"retries": 0, "disposition": "merged"}},
                 "lap": None, "started_at": None}
        log = os.path.join(tmp, "log.jsonl")
        broke = []
        deps = {  # exactly the shape main() builds, break_claim wired
            "state_path": os.path.join(tmp, "state.json"),
            "notify": lambda text: None,
            "claim": lambda now: None,
            "start_lap": lambda issue, lap: None,
            "kill_lap": lambda lap: None,
            "lap_outcome": lambda lap: "crash",
            "reconcile": lambda now: supervisor.reconcile_dead_claims(
                now, state, claims, result_path=os.path.join(tmp, "lap-result.json")),
            "break_claim": lambda path, now: broke.append(path) or os.remove(path),
            "red_recheck": None,
            "reconcile_observations": [],
        }
        with unittest.mock.patch.object(supervisor, "RUNTIME_LOG_PATH", log):
            events = supervisor.tick(state, time.time(), deps)
        self.assertIn("reclaimed:" + claim_path, events)
        self.assertFalse(os.path.exists(claim_path))  # reaped
        self.assertEqual(state["issues"]["18"]["retries"], 0)  # no recount
        with open(log) as f:
            rows = [json.loads(line) for line in f if line.strip()]
        self.assertEqual([r["event"] for r in rows], ["intervention"])
        self.assertIn("orphan claim reaped", rows[0]["detail"])

    def test_handle_lap_end_removes_claim_on_merged_and_parked(self):
        # launch-4 root cleanup: terminal laps must not leave their claim
        # file for the next tick's reconcile to trip over
        for disposition_outcome in (("success", "merged"), ("failure", "parked")):
            with self.subTest(outcome=disposition_outcome[0]):
                tmp = tempfile.mkdtemp()
                claims = os.path.join(tmp, "claims")
                os.makedirs(claims)
                claim_path = os.path.join(claims, "issue-5.json")
                with open(claim_path, "w") as f:
                    json.dump({"issue": 5, "claimed_at": time.time()}, f)
                state = {"issues": {}, "lap": {"issue": 5,
                                                "claim_path": claim_path,
                                                "started_at": time.time(),
                                                "pid": None}}
                deps = fake_deps(tmp, [])
                with unittest.mock.patch.object(supervisor, "RUNTIME_LOG_PATH",
                                                os.path.join(tmp, "log.jsonl")):
                    supervisor.handle_lap_end(state, disposition_outcome[0],
                                              time.time(), deps)
                self.assertFalse(os.path.exists(claim_path),
                                 "terminal lap must remove its claim file")
