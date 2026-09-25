import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from merge import (  # noqa: E402
    gate_green,
    post_merge_identity,
    trees_equal,
)

ENV = dict(
    os.environ,
    GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t",
    GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t",
)


def git(cwd, *args):
    return subprocess.run(
        ["git", "-C", cwd, "-c", "commit.gpgsign=false"] + list(args),
        check=True, capture_output=True, text=True, env=ENV,
    ).stdout.strip()


def init_repo():
    tmp = tempfile.mkdtemp()
    subprocess.run(["git", "init", "-q", "-b", "main", tmp], check=True)
    with open(os.path.join(tmp, "f.txt"), "w") as f:
        f.write("a\n")
    git(tmp, "add", ".")
    git(tmp, "commit", "-qm", "A")
    return tmp


def squash_merge_repo():
    """main at A; branch changes file to 'b'; squash-merge into main."""
    tmp = init_repo()
    git(tmp, "checkout", "-qb", "agent/issue-1")
    with open(os.path.join(tmp, "f.txt"), "w") as f:
        f.write("b\n")
    git(tmp, "commit", "-qam", "B")
    head = git(tmp, "rev-parse", "HEAD")
    git(tmp, "checkout", "-q", "main")
    git(tmp, "merge", "--squash", "-q", "agent/issue-1")
    git(tmp, "commit", "-qm", "B (squash)")
    merge = git(tmp, "rev-parse", "main")
    return tmp, head, merge


class TestTreeEquality(unittest.TestCase):
    """Real git fixture: squash merge → empty diff vs head; tamper → must fail."""

    def test_squash_merge_tree_equal_to_head(self):
        tmp, head, merge = squash_merge_repo()
        self.assertTrue(trees_equal(tmp, merge, head))
        self.assertNotEqual(merge, head)  # SHAs differ — SHA equality would be wrong
        post_merge_identity(tmp, merge, head)  # must not raise

    def test_tampered_tree_fails(self):
        tmp, head, merge = squash_merge_repo()
        with open(os.path.join(tmp, "f.txt"), "w") as f:
            f.write("tampered\n")
        git(tmp, "commit", "-qam", "tamper")
        tampered = git(tmp, "rev-parse", "main")
        self.assertFalse(trees_equal(tmp, tampered, head))
        with self.assertRaises(Exception):
            post_merge_identity(tmp, tampered, head)

    def test_gate_requires_green_verdict(self):
        self.assertFalse(gate_green({"verdict": "fail"}))
        self.assertFalse(gate_green({"verdict": "HOLD"}))
        self.assertFalse(gate_green({}))
        self.assertTrue(gate_green({"verdict": "pass"}))


if __name__ == "__main__":
    unittest.main()
