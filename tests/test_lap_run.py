"""Unit 4 (DEPLOY_MODE) behavior tests driven through run() itself: with
DEPLOY_MODE=none the lap records deploy-skip and never builds/runs a deploy
script or identity readback; with the default the deploy block runs. Everything
around the deploy gate (issue fetch, LLM, merge) is faked — the gate is the
behavior under test."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
import unittest.mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import lap  # noqa: E402


def git(cwd, *args):
    r = subprocess.run(["git"] + list(args), cwd=cwd, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return r.stdout


class FakeLapEnv:
    """Upstream repo + clone-as-PRODUCT_REPO + patched gh/agent/merge/verify."""

    ISSUE = 21

    def __init__(self, deploy_mode):
        self.mode = deploy_mode
        self.base = tempfile.mkdtemp()
        up = os.path.join(self.base, "upstream")
        os.mkdir(up)
        git(up, "init", "-q", "-b", "main")
        with open(os.path.join(up, "app.py"), "w") as f:
            f.write("x = 1\n")
        git(up, "add", "-A")
        git(up, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "init")
        self.repo = os.path.join(self.base, "repo")
        git(self.base, "clone", "-q", up, self.repo)
        git(self.repo, "fetch", "-q", "origin")
        self.worktree = os.path.join(self.repo, ".factory", "worktrees",
                                     "agent-issue-%d" % self.ISSUE)
        # state/evidence + result file write into the tmp base, never real state/
        self.patches = [
            unittest.mock.patch.object(lap, "PRODUCT_REPO", self.repo),
            unittest.mock.patch.object(lap, "CODE_PATHS", ["*.py"]),
            unittest.mock.patch.object(lap, "DEPLOY_MODE", deploy_mode),
            unittest.mock.patch.object(lap, "EVIDENCE_DIR",
                                      os.path.join(self.base, "evidence")),
            unittest.mock.patch.object(lap, "RESULT_PATH",
                                      os.path.join(self.base, "lap-result.json")),
            unittest.mock.patch.object(lap, "HEARTBEAT_PATH",
                                      os.path.join(self.base, "heartbeat")),
            # run_id collision guard: same second → same run_id → same evdir;
            # harmless here (files overwritten), evidence read fresh below
            unittest.mock.patch.object(lap, "issue_data",
                                      lambda issue: {"title": "t", "body": "Acceptance criteria:\nfix"}),
            unittest.mock.patch.object(lap, "_gh", lambda args: ""),
            unittest.mock.patch.object(lap.agent, "chat", self.fake_chat),
            unittest.mock.patch.object(lap.merge, "full_merge",
                                      lambda issue, repo, wt, ev: {"merged": True, "pr": 1,
                                                                  "merge_sha": "abc"}),
            unittest.mock.patch.object(lap.verify, "verify_candidate",
                                      lambda cwd, pid, sdir, issue=None: {"verdict": "pass"}),
        ]

    def fake_chat(self, msgs, model, max_tokens=None, reasoning_effort=None):
        if model == lap.IMPLEMENTER_MODEL:
            content = json.dumps([{"file": "app.py", "find": "x = 1", "replace": "x = 2"}])
        else:
            content = "VERDICT: accept"
        return {"content": content, "finish_reason": "stop",
                "usage": {"buyer_cost_micro": 1000}}

    def __enter__(self):
        for p in self.patches:
            p.start()
            self.addCleanup_later = None
        return self

    def addCleanup_later(self, _):
        pass

    def __exit__(self, *a):
        for p in reversed(self.patches):
            p.stop()
        return False

    def timeline(self):
        run_ids = sorted(os.listdir(os.path.join(self.base, "evidence")))
        with open(os.path.join(self.base, "evidence", run_ids[-1], "timeline.json")) as f:
            return json.load(f)


class TestDeployModeNone(unittest.TestCase):
    def test_deploy_skipped_with_event_and_no_deploy_build(self):
        with FakeLapEnv("none") as env:
            with unittest.mock.patch.object(
                    lap.deploy, "build_deploy_script",
                    side_effect=AssertionError("deploy must not run")) as bs, \
                 unittest.mock.patch.object(
                    lap.deploy, "identity_readback",
                    side_effect=AssertionError("identity must not run")):
                lap.run(FakeLapEnv.ISSUE)
                self.assertFalse(bs.called)
        events = [e["event"] for e in env.timeline()]
        self.assertIn("deploy-skip", events)
        self.assertNotIn("deploy", events)
        self.assertIn("issue-closed", events)
        with open(os.path.join(env.base, "lap-result.json")) as f:
            self.assertEqual(json.load(f)["outcome"], "success")

    def test_deploy_failure_impossible_in_none_mode(self):
        # the deploy gate failure path (rc != 0) cannot trigger when the
        # block is skipped: no deploy event at all, lap reaches success
        with FakeLapEnv("none") as env:
            lap.run(FakeLapEnv.ISSUE)
        self.assertEqual([e["event"] for e in env.timeline()][-2], "issue-closed")


class TestDeployModeApp(unittest.TestCase):
    def test_app_mode_still_deploys_and_checks_identity(self):
        calls = []
        with FakeLapEnv("app") as env:
            def fake_script(port, product_repo, pid_file):
                calls.append("build")
                return "echo deploy-ok"
            def fake_identity(url, repo):
                calls.append("identity")
                return {"match": True, "head": "x"}
            with unittest.mock.patch.object(lap.deploy, "build_deploy_script",
                                            side_effect=fake_script), \
                 unittest.mock.patch.object(lap.deploy, "identity_readback",
                                            side_effect=fake_identity):
                lap.run(FakeLapEnv.ISSUE)
        events = [e["event"] for e in env.timeline()]
        self.assertIn("deploy", events)
        self.assertNotIn("deploy-skip", events)
        self.assertEqual(calls, ["build", "identity"])
        with open(os.path.join(env.base, "lap-result.json")) as f:
            self.assertEqual(json.load(f)["outcome"], "success")

class TestScenariosDirWiring(unittest.TestCase):
    """Behavioral proof (launch-2 lesson): SCENARIOS_DIR must flow through
    the REAL call paths — lap.run's verify_candidate call and supervisor's
    red_recheck — not merely exist in settings. A dir listing or a settings
    reload is not proof; the recorded argument is."""

    def test_lap_run_passes_env_scenarios_dir_to_verify(self):
        curated = tempfile.mkdtemp(prefix="curated-oracles-")
        with FakeLapEnv("none"):
            with unittest.mock.patch.object(lap, "SCENARIOS_DIR", curated):
                seen = {}

                def recorder(cwd, pid_file, scenarios_dir, issue=None):
                    seen["dir"] = scenarios_dir
                    return {"verdict": "pass"}

                with unittest.mock.patch.object(lap.verify, "verify_candidate",
                                                side_effect=recorder):
                    lap.run(FakeLapEnv.ISSUE)
        self.assertEqual(seen["dir"], curated)

    def test_lap_run_default_scenarios_dir_without_env(self):
        # env unset → the historical relative default (the module attr,
        # resolved at import from settings' env read)
        import settings
        expected = os.path.normpath(settings.SCENARIOS_DIR)
        with FakeLapEnv("none"):
            seen = {}

            def recorder(cwd, pid_file, scenarios_dir, issue=None):
                seen["dir"] = scenarios_dir
                return {"verdict": "pass"}

            with unittest.mock.patch.object(lap.verify, "verify_candidate",
                                            side_effect=recorder):
                lap.run(FakeLapEnv.ISSUE)
        self.assertEqual(os.path.normpath(seen["dir"]), expected)

    def test_supervisor_red_recheck_passes_env_scenarios_dir(self):
        import supervisor
        curated = tempfile.mkdtemp(prefix="curated-oracles-")
        wt = tempfile.mkdtemp(prefix="recheck-wt-")
        seen = {}

        def recorder(cwd, pid_file, scenarios_dir, issue=None):
            seen["dir"] = scenarios_dir
            seen["issue"] = issue
            return {"verdict": "fail"}

        with unittest.mock.patch.object(supervisor, "SCENARIOS_DIR", curated), \
             _patch_lap_worktree(wt), \
             _patch_verify_recorder(recorder):
            verdict, _detail = supervisor.red_recheck(3)
        self.assertEqual(seen["dir"], curated)
        self.assertEqual(seen["issue"], 3)
        self.assertEqual(verdict, "fail")

    def test_supervisor_red_recheck_default_dir(self):
        import supervisor
        import settings
        wt = tempfile.mkdtemp(prefix="recheck-wt-")
        seen = {}

        def recorder(cwd, pid_file, scenarios_dir, issue=None):
            seen["dir"] = scenarios_dir
            return {"verdict": "fail"}

        with _patch_lap_worktree(wt), _patch_verify_recorder(recorder):
            verdict, _detail = supervisor.red_recheck(4)
        self.assertEqual(os.path.normpath(seen["dir"]),
                         os.path.normpath(settings.SCENARIOS_DIR))


class TestAddCostRows(unittest.TestCase):
    """G3 (audit #3): a call with no usage data must still cost a row —
    'if usage:' silently dropped it and published cost tables undercounted."""

    def lap_with_tmp_evidence(self):
        tmp = tempfile.mkdtemp()
        with unittest.mock.patch.object(lap, "EVIDENCE_DIR",
                                        os.path.join(tmp, "evidence")):
            l = lap.Lap(31)
        return l, os.path.join(l.evdir, "cost.json")

    def test_falsy_usage_appends_row_with_missing_usage(self):
        l, cost_path = self.lap_with_tmp_evidence()
        l.add_cost(None, "implementer")
        with open(cost_path) as f:
            data = json.load(f)
        self.assertEqual(len(data["calls"]), 1)
        row = data["calls"][0]
        self.assertEqual(row["role"], "implementer")
        self.assertIsNone(row["usage"])
        self.assertEqual(row["buyer_cost_micro"], 0)
        self.assertTrue(row["missing_usage"])
        self.assertEqual(data["total_usd"], 0)

    def test_null_usage_summed_alongside_real_rows(self):
        l, cost_path = self.lap_with_tmp_evidence()
        with unittest.mock.patch.object(lap, "COST_CEILING_USD", 10.0):
            l.add_cost({"buyer_cost_micro": 1_500_000}, "implementer")
            l.add_cost(None, "reviewer")
        with open(cost_path) as f:
            data = json.load(f)
        self.assertEqual(len(data["calls"]), 2)  # per-call count assertable
        self.assertEqual(data["total_usd"], 1.5)


class TestCostCeilingGate(unittest.TestCase):
    """G7: COST_CEILING_USD was a dead constant — the whitepaper's '$0.01
    ceiling' never ran. Exceeding it must end the lap gate='cost' with a
    verdict.json, not continue silently."""

    def test_ceiling_exceeded_lap_fails_gate_cost(self):
        with FakeLapEnv("none") as env:
            # fake implementer call costs 1000 micro = $0.001; a $0.0005
            # ceiling is exceeded on the first add_cost
            with unittest.mock.patch.object(lap, "COST_CEILING_USD", 0.0005):
                lap.run(FakeLapEnv.ISSUE)
        with open(os.path.join(env.base, "lap-result.json")) as f:
            result = json.load(f)
        self.assertEqual(result["outcome"], "failure")
        self.assertIn("exceeds ceiling", result["error"])
        run_ids = sorted(os.listdir(os.path.join(env.base, "evidence")))
        with open(os.path.join(env.base, "evidence", run_ids[-1], "verdict.json")) as f:
            verdict = json.load(f)
        self.assertEqual(verdict["gate"], "cost")
        self.assertEqual(verdict["verdict"], "fail")

    def test_ceiling_not_reached_lap_succeeds(self):
        # the default $0.01 ceiling vs one $0.001 call: no gate trip
        with FakeLapEnv("none") as env:
            lap.run(FakeLapEnv.ISSUE)
        with open(os.path.join(env.base, "lap-result.json")) as f:
            self.assertEqual(json.load(f)["outcome"], "success")


def _patch_lap_worktree(wt):
    import lap as lapmod
    return unittest.mock.patch.object(lapmod, "worktree_for",
                                     lambda issue, prefix="recheck": wt)


def _patch_verify_recorder(recorder):
    import verify
    return unittest.mock.patch.object(verify, "verify_candidate",
                                     side_effect=recorder)

if __name__ == "__main__":
    unittest.main()
