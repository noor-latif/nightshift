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

KEYS = ("PRODUCT_REPO", "GITHUB_REPO", "DEPLOY_MODE", "CODE_PATHS",
        "CHECKOUT_CHAR_BUDGET", "SCENARIOS_DIR")


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

    def test_checkout_char_budget_default_and_override(self):
        importlib.reload(settings)
        self.assertEqual(settings.CHECKOUT_CHAR_BUDGET, 100_000)
        os.environ["CHECKOUT_CHAR_BUDGET"] = "400000"
        importlib.reload(settings)
        self.assertEqual(settings.CHECKOUT_CHAR_BUDGET, 400_000)

    def test_scenarios_dir_default_and_override(self):
        importlib.reload(settings)
        self.assertEqual(os.path.normpath(settings.SCENARIOS_DIR),
                         os.path.normpath(os.path.join(
                             os.path.dirname(settings.__file__), "..", "scenarios")))
        os.environ["SCENARIOS_DIR"] = "/tmp/deployed-oracles"
        importlib.reload(settings)
        self.assertEqual(settings.SCENARIOS_DIR, "/tmp/deployed-oracles")

    def test_lap_and_supervisor_use_settings_scenarios_dir(self):
        # the module-level import must flow to both call sites: a
        # deployment-curated dir must be honored by lap and red_recheck
        import lap
        import supervisor
        self.assertEqual(lap.SCENARIOS_DIR, settings.SCENARIOS_DIR)
        self.assertEqual(supervisor.SCENARIOS_DIR, settings.SCENARIOS_DIR)


class TestNativeConfigBoundary(unittest.TestCase):
    def test_null_empty_shell_and_missing_suite_rejected(self):
        import json
        import subprocess
        valid_suite = ["node", "--test"]
        cases = [{key: value} for key in ("verify", "prepare", "suite") for value in (None, [])]
        cases += [{"verify": [["node", "--test"]]}, {"verify": "node --test"},
                  {"verify": [[""]]}, {"task_kind": None}, {"merge_mode": None},
                  {"verify": [valid_suite, valid_suite], "suite": valid_suite}]
        for cfg in cases:
            env = dict(os.environ, FACTORY_NATIVE_CONFIG=json.dumps(cfg))
            r = subprocess.run([sys.executable, "-c", "import settings"],
                               cwd=os.path.dirname(settings.__file__), env=env,
                               capture_output=True, text=True)
            self.assertNotEqual(r.returncode, 0, cfg)

class TestNewFilesBoundary(unittest.TestCase):
    """FACTORY_NEW_FILES is a create-surface boundary: glob entries are
    accepted, but the plain-relative-path rules hold for patterns too."""

    def _import(self, value):
        import subprocess
        env = dict(os.environ, FACTORY_NEW_FILES=value)
        return subprocess.run([sys.executable, "-c", "import settings"],
                              cwd=os.path.dirname(settings.__file__), env=env,
                              capture_output=True, text=True)

    def test_glob_entries_accepted(self):
        r = self._import("index.html,styles.css,page.js,assets/*,*")
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_escape_shaped_entries_rejected_even_with_glob_chars(self):
        for bad in ("assets/../*", "../*", "/tmp/*", "~/*", "a\\*.py",
                    "assets//*", "./*.py"):
            self.assertNotEqual(self._import(bad).returncode, 0, bad)

if __name__ == "__main__":
    unittest.main()
