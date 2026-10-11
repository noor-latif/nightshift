"""Unit 1: the instance-authoring preflight refuses an instance the implementer
could never pass — SCOPE_PATHS unreachable by CODE_PATHS, a checkout view over
CHECKOUT_CHAR_BUDGET, or a CODE_PATHS glob matching nothing. Temp-dir repos, no
network, no git, no model call."""

import contextlib
import io
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))

import preflight_instance  # noqa: E402


def _write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(text)


def _run(env_lines, repo):
    """Build the task/env files in a temp dir, run main(), return (code, out)."""
    with tempfile.TemporaryDirectory() as tmp:
        task = os.path.join(tmp, "task.json")
        envf = os.path.join(tmp, "env.sh")
        _write(task, '{"title": "t", "body": "b"}')
        _write(envf, "".join("export %s\n" % line for line in env_lines))
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = preflight_instance.main([task, envf, repo])
        return code, out.getvalue()


class TestPreflightInstance(unittest.TestCase):
    def test_scope_miss_fails_named(self):
        with tempfile.TemporaryDirectory() as repo:
            _write(os.path.join(repo, "app.py"), "x = 1\n")
            _write(os.path.join(repo, "pkg", "mod.py"), "y = 2\n")
            code, out = _run(['CODE_PATHS="*.py"', 'SCOPE_PATHS="pkg/mod.py"'], repo)
            self.assertNotEqual(code, 0)
            self.assertIn("FAIL scope", out)
            self.assertIn("pkg/mod.py", out)

    def test_budget_exceeded_fails(self):
        with tempfile.TemporaryDirectory() as repo:
            _write(os.path.join(repo, "big.py"), "x = 1\n" * 2000)
            code, out = _run(['CODE_PATHS="*.py"', "CHECKOUT_CHAR_BUDGET=1000"], repo)
            self.assertNotEqual(code, 0)
            self.assertIn("FAIL budget", out)

    def test_happy_path_exits_zero(self):
        with tempfile.TemporaryDirectory() as repo:
            _write(os.path.join(repo, "a.py"), "a = 1\n")
            _write(os.path.join(repo, "b.py"), "b = 2\n")
            code, out = _run(['CODE_PATHS="*.py"', 'SCOPE_PATHS="a.py"'], repo)
            self.assertEqual(code, 0)
            self.assertTrue(out.startswith("ok "), out)


if __name__ == "__main__":
    unittest.main()
