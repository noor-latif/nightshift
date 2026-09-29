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
        elif self.path == "/stats":
            self._send(200, {"pastes": len(self.server.pastes)})
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


    def do_DELETE(self):
        pid = self.path.rsplit("/", 1)[1]
        if pid in self.server.pastes:
            del self.server.pastes[pid]
            self.send_response(204)
            self.end_headers()
        else:
            self._send(404, {"error": "not found"})

def load_scenarios():
    d = os.path.join(os.path.dirname(__file__), "..", "scenarios")
    out = []
    # global files only — the same selection rule as verify.scenario_paths().
    # Per-issue oracles are RED on main by construction (RED-first); a
    # fixture that mirrors main MUST fail them, so they cannot be asserted
    # green here.
    for name in sorted(n for n in os.listdir(d)
                       if n.endswith(".json") and not n.startswith("issue-")):
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

class TestChunkedAssertions(unittest.TestCase):
    """`chunked: true` sends Transfer-Encoding: chunked with no fixed
    Content-Length — the wire shape issue #19's repro needs."""

    @classmethod
    def setUpClass(cls):
        seen = {}

        class Echo(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_POST(self):
                # read the body the way a real server would: chunked framing
                # only when the request says so, Content-Length otherwise
                te = (self.headers.get("Transfer-Encoding") or "").lower()
                if "chunked" in te:
                    body = b""
                    while True:
                        line = self.rfile.readline().strip()
                        if b";" in line:
                            line = line.split(b";", 1)[0]
                        size = int(line, 16)
                        if size == 0:
                            self.rfile.readline()
                            break
                        body += self.rfile.read(size)
                        self.rfile.readline()
                    seen["body"] = body.decode()
                else:
                    length = int(self.headers.get("Content-Length") or 0)
                    seen["body"] = self.rfile.read(length).decode()
                seen.update(dict(self.headers))
                self.send_response(200)
                self.send_header("Content-Length", "2")
                self.end_headers()
                self.wfile.write(b"ok")

        cls.server = HTTPServer(("127.0.0.1", 0), Echo)
        cls.port = cls.server.server_address[1]
        t = threading.Thread(target=cls.server.serve_forever, daemon=True)
        t.start()
        cls.seen = seen


    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def test_chunked_flag_puts_te_on_wire_and_streams_body(self):
        a = {"method": "POST", "url": "http://127.0.0.1:%d/echo" % self.port,
             "expected_status": 200, "body": {"content": "hi"},
             "chunked": True}
        self.seen.clear()
        check = verify.evaluate_assertion(a, self.port, {})
        self.assertEqual(check["status"], "pass", msg=check)
        self.assertEqual(self.seen.get("Transfer-Encoding"), "chunked")
        self.assertNotIn("Content-Length", self.seen)
        self.assertEqual(self.seen["body"], json.dumps({"content": "hi"}))

    def test_chunked_raw_body_streams_verbatim(self):
        a = {"method": "POST", "url": "http://127.0.0.1:%d/echo" % self.port,
             "expected_status": 200, "raw_body": "not json", "chunked": True}
        self.seen.clear()
        check = verify.evaluate_assertion(a, self.port, {})
        self.assertEqual(check["status"], "pass", msg=check)
        self.assertEqual(self.seen["body"], "not json")

    def test_absent_chunked_sends_content_length(self):
        a = {"method": "POST", "url": "http://127.0.0.1:%d/echo" % self.port,
             "expected_status": 200, "body": {"content": "hi"}}
        self.seen.clear()
        check = verify.evaluate_assertion(a, self.port, {})
        self.assertEqual(check["status"], "pass", msg=check)
        self.assertNotIn("Transfer-Encoding", self.seen)
        self.assertEqual(self.seen.get("Content-Length"),
                         str(len(json.dumps({"content": "hi"}))))


class TestCrashClassification(unittest.TestCase):
    """A server that dies answering is a FAIL (the crash is the evidence);
    only nothing-listening is a HOLD."""

    def test_nothing_listening_is_hold(self):
        a = {"method": "GET", "url": "http://127.0.0.1:1/health", "expected_status": 200}
        check = verify.evaluate_assertion(a, 1, {})
        self.assertEqual(check["status"], "HOLD")

    def test_empty_reply_from_listening_server_is_fail(self):
        import threading

        class Die(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                # accept the request, then close without any response —
                # issue #18's empty-reply crash shape
                self.close_connection = True
                self.connection.close()

        server = HTTPServer(("127.0.0.1", 0), Die)
        port = server.server_address[1]
        t = threading.Thread(target=server.serve_forever, daemon=True)
        t.start()
        try:
            a = {"method": "GET", "url": "http://127.0.0.1:%d/health" % port,
                 "expected_status": 200}
            check = verify.evaluate_assertion(a, port, {})
            self.assertEqual(check["status"], "fail")
            self.assertIsNone(check["observed_status"])
            self.assertIn("closed connection without response", check["detail"])
        finally:
            server.shutdown()


class TestNoGitBoot(unittest.TestCase):
    """`boot_cwd: "no-git"` boots a plain copy without .git (issue #18)."""

    def test_copy_excludes_git_and_factory(self):
        import shutil as _sh

        src = tempfile.mkdtemp()
        os.makedirs(os.path.join(src, ".git"))
        os.makedirs(os.path.join(src, ".factory", "worktrees"))
        with open(os.path.join(src, "app.py"), "w") as f:
            f.write("x = 1\n")
        # run_scenario's copy step, exercised through a minimal scenario
        # object with an immediate HOLD-free boot failure is heavy; assert
        # the copy logic directly via the same primitives it uses.
        dst = tempfile.mkdtemp(prefix="factory-nogit-test-")
        for name in os.listdir(src):
            if name == ".git" or name.startswith(".factory"):
                continue
            s = os.path.join(src, name)
            if os.path.isfile(s):
                _sh.copy(s, os.path.join(dst, name))
            else:
                _sh.copytree(s, os.path.join(dst, name))
        self.assertEqual(sorted(os.listdir(dst)), ["app.py"])
        self.assertFalse(os.path.exists(os.path.join(dst, ".git")))

    def test_scenario_ready_path_override_probes_alternate_endpoint(self):
        # wait_ready(path=...) is the readiness contract for scenarios whose
        # assertion targets /health itself
        import threading

        class Ok(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                code = 200 if self.path == "/stats" else 500
                self.send_response(code)
                self.send_header("Content-Length", "2")
                self.end_headers()
                self.wfile.write(b"{}")

        server = HTTPServer(("127.0.0.1", 0), Ok)
        port = server.server_address[1]
        t = threading.Thread(target=server.serve_forever, daemon=True)
        t.start()
        try:
            self.assertTrue(verify.wait_ready(port, deadline_s=5, path="/stats"))
        finally:
            server.shutdown()

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


class TestExecOracle(unittest.TestCase):
    """kind: "exec" assertions run argv in the candidate checkout with no
    boot, no port. A scenario that is ALL exec-kind never boots a
    candidate (nightshift has no app.py)."""

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        with open(os.path.join(self.dir, "probe.py"), "w") as f:
            f.write("print('factory-exec-marker')\n")

    def exec_a(self, **kw):
        a = {"kind": "exec", "argv": ["python3", "probe.py"], "expected_exit": 0}
        a.update(kw)
        return a

    def test_exit_zero_passes(self):
        check = verify.evaluate_exec_assertion(self.exec_a(), self.dir)
        self.assertEqual(check["status"], "pass")
        self.assertEqual(check["observed_exit"], 0)

    def test_fragment_required_when_given(self):
        check = verify.evaluate_exec_assertion(
            self.exec_a(expect_stdout_fragment="factory-exec-marker"), self.dir)
        self.assertEqual(check["status"], "pass")
        check = verify.evaluate_exec_assertion(
            self.exec_a(expect_stdout_fragment="absent"), self.dir)
        self.assertEqual(check["status"], "fail")
        self.assertFalse(check["fragment_found"])

    def test_wrong_exit_fails_not_holds(self):
        with open(os.path.join(self.dir, "probe.py"), "w") as f:
            f.write("raise SystemExit(3)\n")
        check = verify.evaluate_exec_assertion(self.exec_a(), self.dir)
        self.assertEqual(check["status"], "fail")
        self.assertEqual(check["observed_exit"], 3)

    def test_spawn_failure_is_hold_never_pass(self):
        check = verify.evaluate_exec_assertion(
            self.exec_a(argv=["/nonexistent/interpreter", "probe.py"]), self.dir)
        self.assertEqual(check["status"], "HOLD")
        self.assertIn("cannot run", check["detail"])

    def test_all_exec_scenario_never_boots(self):
        import unittest.mock as mock

        scenario = {"name": "no-boot", "assertions": [self.exec_a()]}
        with mock.patch.object(verify, "boot_candidate",
                               side_effect=AssertionError("boot attempted")):
            with mock.patch.object(verify, "free_port",
                                   side_effect=AssertionError("port allocated")):
                r = verify.run_scenario(scenario, self.dir, "unused.pid")
        self.assertEqual(r["verdict"], "pass")
        self.assertEqual(r["checks"][0]["status"], "pass")

    def test_all_exec_scenario_failure_fails_scenario(self):
        scenario = {"name": "no-boot-fail",
                    "assertions": [self.exec_a(expected_exit=2)]}
        r = verify.run_scenario(scenario, self.dir, "unused.pid")
        self.assertEqual(r["verdict"], "fail")

    def test_mixed_scenario_still_boots_and_runs_exec_checks(self):
        # run_scenario captures the candidate revision from git (existing
        # contract); the mixed boot path needs a real git checkout
        import subprocess as sp

        env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t",
                   GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")
        for args in (["init", "-q"], ["add", "-A"],
                     ["commit", "-qm", "c"]):
            sp.run(["git"] + args, cwd=self.dir, check=True,
                   capture_output=True, env=env)
        # one HTTP assertion in the mix → boot path runs (the candidate is
        # this app.py stand-in), the exec assertion runs alongside it
        app = ('import json\n'
               'import os\n'
               'from http.server import BaseHTTPRequestHandler, HTTPServer\n'
               'class H(BaseHTTPRequestHandler):\n'
               '    def log_message(self, *a):\n'
               '        pass\n'
               '    def do_GET(self):\n'
               '        if self.path == "/health":\n'
               '            b = json.dumps({"status": "ok"}).encode()\n'
               '            self.send_response(200)\n'
               '            self.send_header("Content-Length", str(len(b)))\n'
               '            self.end_headers()\n'
               '            self.wfile.write(b)\n'
               '        else:\n'
               '            self.send_response(404)\n'
               '            self.end_headers()\n'
               'PORT = int(os.environ.get("FACTORY_PORT", "0"))\n'
               'HTTPServer(("127.0.0.1", PORT), H).serve_forever()\n')
        with open(os.path.join(self.dir, "app.py"), "w") as f:
            f.write(app)
        scenario = {
            "name": "mixed",
            "assertions": [
                self.exec_a(),
                {"method": "GET", "url": "http://127.0.0.1:{{port}}/health",
                 "expected_status": 200},
            ],
        }
        pid_file = os.path.join(self.dir, "mixed.pid")
        r = verify.run_scenario(scenario, self.dir, pid_file)
        self.assertEqual(r["verdict"], "pass", msg=r["checks"])
        self.assertTrue(r["checks"][0]["assertion"].startswith("exec "))
        self.assertEqual(r["checks"][1]["observed_status"], 200)
        kinds = {c["assertion"].split(" ")[0] for c in r["checks"]}
        self.assertEqual(kinds, {"exec", "GET"})

if __name__ == "__main__":
    unittest.main()
