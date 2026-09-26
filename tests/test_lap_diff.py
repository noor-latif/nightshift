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

    def test_headerless_new_file_section_fails_loudly(self):
        # git apply exits 0 but silently drops the header-less section; the
        # gate must fail loudly instead of applying app.py only.
        patch = ("diff --git a/app.py b/app.py\n"
                 "--- a/app.py\n+++ b/app.py\n@@ -1 +1 @@\n-x = 1\n+x = 2\n"
                 "--- /dev/null\n+++ b/paste_empty_content_test.py\n"
                 "def test_x():\n    assert True\n")
        ok, detail, tier = lap.apply_diff(patch, self.dir)
        self.assertFalse(ok)
        self.assertIn("apply_incomplete", detail)
        self.assertIn("paste_empty_content_test.py", detail)
        self.assertEqual(open(os.path.join(self.dir, "app.py")).read(), "x = 2\n")

class TestCheckoutFiles(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()

    def write(self, name, content):
        with open(os.path.join(self.dir, name), "w") as f:
            f.write(content)

    def test_nonstandard_names_included(self):
        self.write("server.py", "s = 1\n")
        self.write("server_test.py", "t = 1\n")
        got = lap.checkout_files(self.dir)
        self.assertEqual(len(got), 2)
        self.assertIn("=== server.py ===", got[0])
        self.assertIn("=== server_test.py ===", got[1])

    def test_dotdirs_and_factory_excluded(self):
        self.write("app.py", "x = 1\n")
        os.makedirs(os.path.join(self.dir, ".factory"))
        with open(os.path.join(self.dir, ".factory", "leak.py"), "w") as f:
            f.write("secret\n")
        got = lap.checkout_files(self.dir)
        self.assertEqual([g for g in got if "app.py" in g], got)
        self.assertNotIn("secret", "".join(got))

    def test_char_cap_stops_at_whole_files_deterministically(self):
        self.write("a.py", "x" * 600)
        self.write("b.py", "y" * 600)
        self.write("c.py", "z" * 600)
        got = lap.checkout_files(self.dir, char_budget=1000)
        self.assertEqual(len(got), 1)
        self.assertIn("a.py", got[0])
        self.assertNotIn("b.py", got[0])

if __name__ == "__main__":
    unittest.main()

    def test_prefixless_diff_accepted_and_normalized(self):
        text = ("```diff\n"
                "diff --git app.py app.py\n"
                "--- app.py\n"
                "+++ app.py\n"
                "@@ -1 +1 @@\n"
                "-x = 1\n"
                "+x = 2\n"
                "```\n")
        out = lap.extract_diff(text)
        self.assertIn("--- a/app.py", out)
        self.assertIn("+++ b/app.py", out)

    def test_prefixless_without_diff_git_line_accepted(self):
        text = ("```\n"
                "--- app.py\n"
                "+++ app.py\n"
                "@@ -1 +1 @@\n"
                "-x = 1\n"
                "+x = 2\n"
                "```\n")
        out = lap.extract_diff(text)
        self.assertIn("+++ b/app.py", out)

    def test_dev_null_left_alone(self):
        text = ("```diff\n"
                "--- /dev/null\n"
                "+++ b/new.py\n"
                "@@ -0,0 +1 @@\n"
                "+x = 1\n"
                "```\n")
        out = lap.extract_diff(text)
        self.assertIn("--- /dev/null", out)

    def test_prose_line_not_treated_as_header(self):
        text = "```\nsome --- dashes and +++ pluses in prose\n```\n"
        self.assertIsNone(lap.extract_diff(text))
