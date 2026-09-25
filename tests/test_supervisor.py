import json
import os
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
        self.assertEqual((disposition, halt), ("parked", True))
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
