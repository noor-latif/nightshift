"""Unit 1: target settings are env-overridable with today's literals as
defaults. The factory must run on itself (nightshift) via env only — no code
edits, no config framework. Import-time reads are the NTFY_TOPIC precedent;
laps run as subprocesses so the launch env applies."""

import importlib
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import settings  # noqa: E402

KEYS = ("PRODUCT_REPO", "GITHUB_REPO", "DEPLOY_MODE", "CODE_PATHS")


class TestSettingsEnvOverrides(unittest.TestCase):
    def setUp(self):
        self.saved = {k: os.environ.get(k) for k in KEYS}
        for k in KEYS:
            os.environ.pop(k, None)

    def tearDown(self):
        for k, v in self.saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        importlib.reload(settings)

    def test_defaults_preserve_toy_behavior(self):
        importlib.reload(settings)
        self.assertEqual(settings.PRODUCT_REPO, "~/factory-lab/toy-product")
        self.assertEqual(settings.GITHUB_REPO, "noor-latif/toy-product")
        self.assertEqual(settings.DEPLOY_MODE, "app")
        self.assertEqual(settings.CODE_PATHS, ["*.py"])

    def test_env_overrides_each_setting(self):
        os.environ["PRODUCT_REPO"] = "~/repos/nightshift"
        os.environ["GITHUB_REPO"] = "noor-latif/nightshift"
        os.environ["DEPLOY_MODE"] = "none"
        os.environ["CODE_PATHS"] = "src/*.py, README.md"
        importlib.reload(settings)
        self.assertEqual(settings.PRODUCT_REPO, "~/repos/nightshift")
        self.assertEqual(settings.GITHUB_REPO, "noor-latif/nightshift")
        self.assertEqual(settings.DEPLOY_MODE, "none")
        self.assertEqual(settings.CODE_PATHS, ["src/*.py", "README.md"])

    def test_code_paths_empty_entries_dropped(self):
        os.environ["CODE_PATHS"] = " src/*.py , ,*.py,"
        importlib.reload(settings)
        self.assertEqual(settings.CODE_PATHS, ["src/*.py", "*.py"])


if __name__ == "__main__":
    unittest.main()
