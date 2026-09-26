import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import lap  # noqa: E402

def git(cwd, *args):
    r = subprocess.run(["git"] + list(args), cwd=cwd, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return r.stdout

class TestExtractDiff(unittest.TestCase):
    def test_multi_fence_concatenates(self):
        text = ("Let me implement this.\n"
                "```diff\n"
                "diff --git a/app.py b/app.py\n"
                "--- a/app.py\n"
                "+++ b/app.py\n"
                "@@ -1 +1 @@\n"
                "-x = 1\n"
                "+x = 2\n"
                "```\n"
                "Now the test:\n"
                "```\n"
                "diff --git a/app_test.py b/app_test.py\n"
                "--- a/app_test.py\n"
                "+++ b/app_test.py\n"
                "@@ -1 +1 @@\n"
                "-assert x == 1\n"
                "+assert x == 2\n"
                "```\n"
                "Done.")
        out = lap.extract_diff(text)
        self.assertIn("a/app.py", out)
        self.assertIn("a/app_test.py", out)

    def test_prose_fences_ignored(self):
        text = ("Here is how:\n```\ndiff --git is a git command.\n```\n"
                "```diff\ndiff --git a/a b/a\n--- a/a\n+++ b/a\n@@ -1 +1 @@\n-a\n+b\n```\n")
        out = lap.extract_diff(text)
        self.assertNotIn("git command", out)
        self.assertIn("+++ b/a", out)

    def test_bare_diff_fallback(self):
        text = "Sure.\ndiff --git a/a b/a\n--- a/a\n+++ b/a\n@@ -1 +1 @@\n-a\n+b\n"
        out = lap.extract_diff(text)
        self.assertIn("--- a/a", out)

    def test_none_when_no_diff(self):
        self.assertIsNone(lap.extract_diff("I could not do it."))

class TestApplyDiff(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        git(self.dir, "init", "-q")
        with open(os.path.join(self.dir, "app.py"), "w") as f:
            f.write("x = 1\n")
        git(self.dir, "add", "-A")
        git(self.dir, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "init")

    def test_plain_tier(self):
        patch = ("diff --git a/app.py b/app.py\n"
                 "--- a/app.py\n+++ b/app.py\n@@ -1 +1 @@\n-x = 1\n+x = 2\n")
        ok, detail, tier = lap.apply_diff(patch, self.dir)
        self.assertTrue(ok)
        self.assertEqual(tier, "plain")
        self.assertEqual(open(os.path.join(self.dir, "app.py")).read(), "x = 2\n")

    def test_miscounted_headers_need_recount(self):
        patch = ("diff --git a/app.py b/app.py\n"
                 "--- a/app.py\n+++ b/app.py\n@@ -1,5 +1,2 @@\n-x = 1\n+x = 2\n")
        ok, detail, tier = lap.apply_diff(patch, self.dir)
        self.assertTrue(ok)
        self.assertEqual(tier, "recount")
        self.assertEqual(open(os.path.join(self.dir, "app.py")).read(), "x = 2\n")

    def test_failure_returns_tier_and_stderr(self):
        patch = ("diff --git a/app.py b/app.py\n"
                 "--- a/app.py\n+++ b/app.py\n@@ -1 +1 @@\n-x = 9\n+x = 2\n")
        ok, detail, tier = lap.apply_diff(patch, self.dir)
        self.assertFalse(ok)
        self.assertEqual(tier, "recount-C1")
        self.assertTrue(detail)

if __name__ == "__main__":
    unittest.main()
