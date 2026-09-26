import json
import os
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import verify  # noqa: E402


class ToyApp(BaseHTTPRequestHandler):
    """In-process stand-in for the toy product: pastes + /health revision."""

    revision = "0" * 40

    def log_message(self, *a):
        pass

    def _send(self, code, body):
        payload = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        self.path = self.path.split("?", 1)[0]  # query strings do not route
        if self.path == "/health":
            self._send(200, {"status": "ok", "revision": self.revision})
        elif self.path.startswith("/paste/"):
            pid = self.path.rsplit("/", 1)[1]
            if pid in self.server.pastes:
                self._send(200, {"id": pid, "content": self.server.pastes[pid]})
            else:
                self._send(404, {"error": "not found"})
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/paste":
            self._send(404, {"error": "not found"})
            return
        hdr = self.headers.get("Content-Length")
        if not hdr or not hdr.strip():
            self._send(411, {"error": "Content-Length required"})
            return
        raw = self.rfile.read(int(hdr)).decode()
        try:
            data = json.loads(raw)
        except ValueError:
            self._send(400, {"error": "malformed"})
            return
        content = data.get("content")
        if not isinstance(content, str) or content == "":
            self._send(400, {"error": "content must be a non-empty string"})
            return
        pid = "a%d" % (len(self.server.pastes) + 1)  # base64url-style: may start with a letter
        self.server.pastes[pid] = data["content"]
        self._send(201, {"id": pid})


def load_scenarios():
    d = os.path.join(os.path.dirname(__file__), "..", "scenarios")
    out = []
    for name in sorted(os.listdir(d)):
        if name.endswith(".json"):
            with open(os.path.join(d, name)) as f:
                data = json.load(f)
            # a file may hold one scenario or a list of scenarios
            out.extend(data if isinstance(data, list) else [data])
    return out


class TestVerifyAgainstFixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("127.0.0.1", 0), ToyApp)
        cls.server.pastes = {}
        cls.t = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.t.start()
        cls.port = cls.server.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def test_all_scenario_assertions_evaluated(self):
        for scenario in load_scenarios():
            saved = {}
            checks = [
                verify.evaluate_assertion(a, self.port, saved,
                                          revision=ToyApp.revision)
                for a in scenario["assertions"]
            ]
            for check in checks:
                self.assertEqual(check["status"], "pass", msg=check)
            self.assertGreater(len(checks), 0)

    def test_round_trip_saves_id(self):
        scenario = next(s for s in load_scenarios() if s["name"] == "paste-round-trip")
        saved = {}
        checks = [verify.evaluate_assertion(a, self.port, saved) for a in scenario["assertions"]]
        self.assertTrue(all(c["status"] == "pass" for c in checks), msg=checks)
        self.assertIn("paste_id", saved)
        # real contract: JSON body {"id": ...}; the saved value is the FULL id
        # (base64url ids may start with a letter — regex-only save broke this
        # by grabbing a digit fragment). Round-trip GET on the saved id passes.
        self.assertTrue(saved["paste_id"].startswith("a"))
        self.assertEqual(checks[1]["status"], "pass")  # GET /paste/<saved id> found it

    def test_save_falls_back_for_non_json_body(self):
        # server answering a bare token instead of JSON: numeric-run fallback
        a = {"method": "GET", "url": "http://127.0.0.1:{{port}}/health",
             "expected_status": 200, "save": "token"}
        saved = {}
        check = verify.evaluate_assertion(a, self.port, saved)
        self.assertEqual(check["status"], "pass")
        self.assertTrue(saved["token"])  # some value saved, no crash

    def test_health_revision_matches_fixture_revision(self):
        scenario = next(s for s in load_scenarios() if s["name"] == "health-revision")
        saved = {}
        checks = [verify.evaluate_assertion(a, self.port, saved, revision=ToyApp.revision)
                  for a in scenario["assertions"]]
        self.assertTrue(all(c["status"] == "pass" for c in checks), msg=checks)
        # and a wrong revision must fail — no constant-literal greenwash
        bad = [verify.evaluate_assertion(a, self.port, {}, revision="wrong-sha")
               for a in scenario["assertions"]]
        self.assertTrue(any(c["status"] == "fail" for c in bad))

    def test_failure_detected_not_greenwashed(self):
        bad = {
            "name": "injected-defect",
            "assertions": [{
                "method": "GET",
                "url": "http://127.0.0.1:{{port}}/paste/does-not-exist",
                "expected_status": 200,  # wrong on purpose
            }],
        }
        check = verify.evaluate_assertion(bad["assertions"][0], self.port, {})
        self.assertEqual(check["status"], "fail")

    def test_unreachable_check_is_hold_never_pass(self):
        # port 1 is never listening
        a = {"method": "GET", "url": "http://127.0.0.1:1/health", "expected_status": 200}
        check = verify.evaluate_assertion(a, 1, {})
        self.assertEqual(check["status"], "HOLD")

    def test_provenance_refuses_env_leak(self):
        import unittest.mock as mock

        tmp = tempfile.mkdtemp()
        with mock.patch.dict(os.environ, {"FACTORY_RUNTIME_CANDIDATE": "x"}):
            with self.assertRaises(verify.Hold):
                verify.check_provenance('{"revision": "abc"}', tmp)

    def test_provenance_mismatch_detected(self):
        tmp = tempfile.mkdtemp()
        import subprocess

        env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t",
                   GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")
        def g(*a):
            subprocess.run(["git", "-C", tmp] + list(a), check=True, capture_output=True, env=env)
        g("init", "-q")
        with open(os.path.join(tmp, "app.py"), "w") as f:
            f.write("x=1\n")
        g("add", ".")
        g("commit", "-qm", "c")
        ok, detail = verify.check_provenance('{"revision": "deadbeef"}', tmp)
        self.assertFalse(ok)  # reported != HEAD
        head = subprocess.run(["git", "-C", tmp, "rev-parse", "HEAD"],
                              capture_output=True, text=True).stdout.strip()
        ok, _ = verify.check_provenance(json.dumps({"revision": head}), tmp)
        self.assertTrue(ok)


class TestHeadersPassThrough(unittest.TestCase):
    """Scenario `headers` must reach the wire verbatim; absent = unchanged."""

    @classmethod
    def setUpClass(cls):
        seen = {}

        class Echo(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                seen.update(dict(self.headers))
                self.send_response(200)
                self.end_headers()

        cls.server = HTTPServer(("127.0.0.1", 0), Echo)
        cls.port = cls.server.server_address[1]
        t = threading.Thread(target=cls.server.serve_forever, daemon=True)
        t.start()
        cls.seen = seen

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def test_headers_reach_server(self):
        a = {"method": "GET", "url": "http://127.0.0.1:%d/echo" % self.port,
             "expected_status": 200, "headers": {"X-Probe": "ping"}}
        self.seen.clear()
        check = verify.evaluate_assertion(a, self.port, {})
        self.assertEqual(check["status"], "pass")
        self.assertEqual(self.seen.get("X-Probe"), "ping")

    def test_content_length_override_sent_verbatim(self):
        # scenario contract: the value must go on the wire exactly as written
        a = {"method": "GET", "url": "http://127.0.0.1:%d/echo" % self.port,
             "expected_status": 200, "headers": {"Content-Length": "999"}}
        self.seen.clear()
        check = verify.evaluate_assertion(a, self.port, {})
        self.assertEqual(check["status"], "pass")
        self.assertEqual(self.seen.get("Content-Length"), "999")

    def test_absent_headers_unchanged(self):
        a = {"method": "GET", "url": "http://127.0.0.1:%d/echo" % self.port,
             "expected_status": 200}
        self.seen.clear()
        check = verify.evaluate_assertion(a, self.port, {})
        self.assertEqual(check["status"], "pass")
        self.assertNotIn("X-Probe", self.seen)

class TestScenarioSelection(unittest.TestCase):
    """issue-<n>.json runs only for its issue; global files always run."""

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        for name in ("toy-product.json", "issue-2.json"):
            with open(os.path.join(self.dir, name), "w") as f:
                f.write("[]")

    def test_issue_file_runs_only_for_its_issue(self):
        import verify
        paths = verify.scenario_paths(self.dir, issue=2)
        self.assertEqual([os.path.basename(p) for p in paths],
                         ["issue-2.json", "toy-product.json"])

    def test_other_issue_skips_foreign_file(self):
        import verify
        paths = verify.scenario_paths(self.dir, issue=3)
        self.assertEqual([os.path.basename(p) for p in paths], ["toy-product.json"])

    def test_no_issue_runs_global_only(self):
        import verify
        paths = verify.scenario_paths(self.dir)
        self.assertEqual([os.path.basename(p) for p in paths], ["toy-product.json"])

    def test_missing_issue_file_is_backward_compatible(self):
        import verify
        paths = verify.scenario_paths(self.dir, issue=9)
        self.assertEqual([os.path.basename(p) for p in paths], ["toy-product.json"])

if __name__ == "__main__":
    unittest.main()
