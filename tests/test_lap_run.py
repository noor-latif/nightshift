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


if __name__ == "__main__":
    unittest.main()
