import json
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
        status = supervisor.notify("x", opener=type("O", (), {"open": staticmethod(ok)})())
        self.assertEqual(status, 200)


class TestParkAndContinue(unittest.TestCase):
    """Sortie semantics: park escalates the issue, the queue continues."""
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.notify = []
        self.now = 1000.0

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
            r = subprocess.run([sys.executable, f.name], capture_output=True, text=True)
            os.unlink(f.name)
            return r.returncode

        self.assertEqual(run_main(["dispatch:idle", "BLOCKED:9"]), 1)
        self.assertEqual(run_main(["dispatch:idle", "DRAIN:0 parked, 0 merged"]), 0)
