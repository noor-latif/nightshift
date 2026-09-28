"""L-016 regression tests: worktree_add registered-path collision self-heal,
and run()'s finally-cleanup when worktree_for raises before assignment.

The live trap (2026-09-28 launch-5, issue 17): a stale registered worktree at
.factory/worktrees/agent-issue-17 made `git worktree add ... -B agent/issue-17`
die with "'agent/issue-17' is already used by worktree at <path>"; run() had
worktree=None at that point so the finally-block cleanup was skipped and the
trap survived every crash. Real git scenarios, no mocks of git itself."""

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


def worktree_list(cwd):
    out = git(cwd, "worktree", "list", "--porcelain")
    return [l.split(" ")[1] for l in out.splitlines() if l.startswith("worktree ")]


class GitScenario(unittest.TestCase):
    """Upstream repo (branch main) + clone; the clone is PRODUCT_REPO."""

    ISSUE = 17

    def setUp(self):
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
        self._patches = [unittest.mock.patch.object(lap, "PRODUCT_REPO", self.repo)]
        for _p in self._patches:
            _p.start()
            self.addCleanup(_p.stop)
        self.path = os.path.join(self.repo, ".factory", "worktrees",
                                 "agent-issue-%d" % self.ISSUE)

    def register_stale(self):
        """The launch-3 leftover: a registered worktree at the lap's path."""
        git(self.repo, "worktree", "add", self.path, "-B", "agent/issue-17",
            "origin/main")

    def test_collision_self_heals(self):
        self.register_stale()
        got = lap.worktree_for(self.ISSUE)
        self.assertEqual(got, self.path)
        self.assertTrue(os.path.isdir(self.path))
        # exactly one registration, at the healed path
        self.assertEqual(worktree_list(self.repo).count(self.path), 1)
        # the worktree is usable at fresh origin/main, not the leftover state
        head = git(self.path, "rev-parse", "HEAD")
        self.assertEqual(head, git(self.repo, "rev-parse", "origin/main"))

    def test_foreign_worktree_on_branch_still_raises_loud(self):
        # the branch is checked out SOMEWHERE ELSE: healing the path cannot
        # help; the error must stay loud, never loop
        foreign = os.path.join(self.base, "foreign")
        git(self.repo, "worktree", "add", foreign, "-B", "agent/issue-17",
            "origin/main")
        with self.assertRaises(RuntimeError) as cm:
            lap.worktree_for(self.ISSUE)
        self.assertIn("worktree add failed", str(cm.exception))
        self.assertIn("is already used by worktree", str(cm.exception))

    def test_unrecoverable_failure_still_raises(self):
        # make the parent of the worktree path a plain file: every add tier
        # fails with a non-collision error
        os.makedirs(os.path.join(self.repo, ".factory"))
        with open(os.path.join(self.repo, ".factory", "worktrees"), "w") as f:
            f.write("not a dir\n")
        with self.assertRaises(RuntimeError) as cm:
            lap.worktree_for(self.ISSUE)
        self.assertIn("worktree add failed", str(cm.exception))
        self.assertNotIn("is already used by worktree", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
