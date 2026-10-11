"""F9 base-pinning guard at the `worktree_for` level (issue-9803 a1): what
the lap runs must be the DECLARED base.

The 9803 a1 fault: the lap clone's origin was the clone itself (bank recipe),
so `fetch origin main` re-resolved origin/main from the local main branch —
which already contained the gold fix — and the checkout silently advanced past
the pinned defect base. The implementer "resolved" an already-fixed base and
the lap greened vacuously (awaiting-review), caught only by operator audit.

Real git scenarios, no mocks of git itself, no network. Companion coverage at
the run level: an OperationalFault from worktree_for propagates out of run()
and would be classified operational via the except-clause in run() (gate
name carried on the exception)."""

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
    return r.stdout.strip()


class BasePinScenario(unittest.TestCase):
    """Upstream repo (branch main) + clone; the clone is PRODUCT_REPO."""

    ISSUE = 9803

    def setUp(self):
        self.base = tempfile.mkdtemp()
        up = os.path.join(self.base, "upstream")
        os.mkdir(up)
        git(up, "init", "-q", "-b", "main")
        with open(os.path.join(up, "app.py"), "w") as f:
            f.write("x = 1\n")
        git(up, "add", "-A")
        git(up, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "init")
        self.old_sha = git(up, "rev-parse", "HEAD")
        with open(os.path.join(up, "app.py"), "w") as f:
            f.write("x = 2\n")
        git(up, "add", "-A")
        git(up, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "gold fix")
        self.new_sha = git(up, "rev-parse", "HEAD")
        self.repo = os.path.join(self.base, "repo")
        git(self.base, "clone", "-q", up, self.repo)
        self._patches = [
            unittest.mock.patch.object(lap, "PRODUCT_REPO", self.repo),
            unittest.mock.patch.object(lap, "BASE_REF", "origin/main"),
        ]
        for _p in self._patches:
            _p.start()
            self.addCleanup(_p.stop)
        self.path = os.path.join(self.repo, ".factory", "worktrees",
                                 "agent-issue-%d" % self.ISSUE)

    def pin_old(self):
        """The 9803 compensation: pin the base to the pre-fix parent."""
        git(self.repo, "update-ref", "refs/remotes/origin/main", self.old_sha)

    def worktree_head(self):
        return git(self.path, "rev-parse", "HEAD")


class TestBasePinHappy(BasePinScenario):
    """(1) declared base == checkout: passes through unchanged."""

    def test_base_matches_checkout_passes(self):
        self.assertEqual(lap.worktree_for(self.ISSUE), self.path)
        self.assertEqual(self.worktree_head(), self.new_sha)
        self.assertEqual(self.worktree_head(),
                         git(self.repo, "rev-parse", "origin/main"))


class TestBasePinMismatch(BasePinScenario):
    """(2) declared base != checkout: operational failure naming both shas
    and the gate."""

    def test_fetch_advancing_base_ref_fails_operational(self):
        # the local main branch sits at the fix (a real clone of upstream);
        # `fetch origin main` drags origin/main there while the pin names
        # the old rev — the 9803 a1 shape in miniature
        self.pin_old()
        with self.assertRaises(lap.BasePinError) as cm:
            lap.worktree_for(self.ISSUE)
        self.assertIn("declared base %s" % self.old_sha, str(cm.exception))
        self.assertIn("checkout %s" % self.new_sha, str(cm.exception))
        self.assertIn("vacuous-already-fixed risk", str(cm.exception))
        self.assertEqual(cm.exception.gate, "base-pin")

    def test_run_classifies_mismatch_as_operational_gate_base_pin(self):
        # run-level contract: the guard's exception reaches the OperationalFault
        # handler, so the lap ends failure/gate=base-pin — never a scored pass.
        sys.path.insert(0, os.path.dirname(__file__))
        from test_lap_run import FakeLapEnv
        with FakeLapEnv("none") as env, \
             unittest.mock.patch.object(
                 lap, "worktree_for",
                 side_effect=lap.BasePinError(
                     "declared base %s != checkout %s after fetch "
                     "(vacuous-already-fixed risk)" % (self.old_sha, self.new_sha))):
            lap.run(FakeLapEnv.ISSUE)
        with open(os.path.join(env.base, "lap-result.json")) as f:
            result = json.load(f)
        self.assertEqual(result["outcome"], "failure")
        self.assertEqual(result["gate"], "base-pin")
        self.assertIn("declared base", result["error"])
        self.assertIn("vacuous-already-fixed risk", result["error"])


class TestSelfCloneFetchGuard(BasePinScenario):
    """(3) self-referential origin (bank recipe): fetching nothing keeps the
    checkout ref from being re-resolved past the pin."""

    def test_self_clone_fetch_skipped_keeps_pin(self):
        git(self.repo, "remote", "set-url", "origin", ".")
        self.pin_old()
        # the local main branch sits at the fix (a real clone of upstream);
        # WITHOUT the guard `fetch origin main` would drag origin/main there
        self.assertEqual(git(self.repo, "rev-parse", "refs/heads/main"),
                         self.new_sha)
        lap.worktree_for(self.ISSUE)
        self.assertEqual(self.worktree_head(), self.old_sha)
        self.assertEqual(git(self.repo, "rev-parse", "origin/main"), self.old_sha)


if __name__ == "__main__":
    unittest.main()
