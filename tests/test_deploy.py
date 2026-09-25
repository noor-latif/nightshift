import sys
import os
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from deploy import build_deploy_script  # noqa: E402
from merge import trees_equal  # noqa: E402


class TestDeployScript(unittest.TestCase):
    def setUp(self):
        self.script = build_deploy_script(port=8899, product_repo="~/factory-lab/toy-product",
                                          pid_file="app.pid", ready_timeout=30)

    def test_no_pkill_ever(self):
        self.assertNotIn("pkill", self.script)

    def test_kill_by_pid_file(self):
        self.assertIn("cat app.pid", self.script)
        self.assertIn('kill "$OLDPID"', self.script)

    def test_no_nested_inline_quotes_through_ssh(self):
        # script is a standalone file: no line should embed a nested quote sandwich
        self.assertNotIn("ssh ", self.script)

    def test_fetch_reset_and_start_with_port(self):
        self.assertIn("git fetch origin", self.script)
        self.assertIn("git reset --hard origin/main", self.script)
        self.assertIn("FACTORY_PORT=8899 nohup python3 app.py", self.script)
        self.assertIn("echo $! > app.pid", self.script)

    def test_readiness_bounded_ending_in_health(self):
        self.assertIn("curl -sf http://127.0.0.1:8899/health", self.script)
        self.assertIn("NOT READY", self.script)
        self.assertIn("exit 1", self.script)


if __name__ == "__main__":
    unittest.main()
