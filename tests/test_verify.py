import importlib.util
import json
import os
import subprocess
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

    def test_run_scenario_boots_a_copy_without_git(self):
        # exercised through run_scenario itself (the production loop), not a
        # re-implementation of its copy step: the booted candidate reports
        # whether a .git directory exists in its own cwd
        src = tempfile.mkdtemp()
        os.makedirs(os.path.join(src, ".git"))
        os.makedirs(os.path.join(src, ".factory", "worktrees"))
        with open(os.path.join(src, "app.py"), "w") as f:
            f.write(
                "import json, os\n"
                "from http.server import BaseHTTPRequestHandler, HTTPServer\n"
                "class H(BaseHTTPRequestHandler):\n"
                "    def do_GET(self):\n"
                "        body = json.dumps({'status': 'ok', 'revision': 'x',\n"
                "                           'has_git': os.path.isdir('.git')}).encode()\n"
                "        self.send_response(200)\n"
                "        self.send_header('Content-Length', str(len(body)))\n"
                "        self.end_headers()\n"
                "        self.wfile.write(body)\n"
                "    def log_message(self, *a):\n"
                "        pass\n"
                "HTTPServer(('127.0.0.1', int(os.environ['FACTORY_PORT'])), H).serve_forever()\n"
            )
        subprocess.run(["git", "init", "-q"], cwd=src, capture_output=True)
        subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t",
                        "commit", "-qm", "init", "--allow-empty"],
                       cwd=src, capture_output=True)
        scenario = {
            "name": "no-git", "boot_cwd": "no-git",
            "assertions": [{"method": "GET",
                            "url": "http://127.0.0.1:{{port}}/health",
                            "expected_status": 200,
                            "expect_body_fragment": '"has_git": false'}],
        }
        pid_file = os.path.join(tempfile.mkdtemp(), "p.pid")
        try:
            result = verify.run_scenario(scenario, src, pid_file)
        finally:
            verify.stop_candidate(pid_file)
        self.assertEqual(result["verdict"], "pass", result)

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

class TestScenarioHoldIsCaptured(unittest.TestCase):
    """K4: a Hold from the scenario ladder is HOLD evidence, never a crash.

    The ladder raises Hold when the harness cannot run the check (scenario
    port range exhausted, candidate never ready). Escaping verify_candidate
    turns a transient resource condition into a lap crash → retry burn →
    false park.
    """

    def test_exhausted_scenario_port_range_returns_hold(self):
        import socket
        from unittest import mock

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        try:
            tmp = tempfile.mkdtemp()
            scenarios = tempfile.mkdtemp()
            with open(os.path.join(scenarios, "global.json"), "w") as f:
                json.dump({"name": "needs-boot", "assertions": [{
                    "method": "GET",
                    "url": "http://127.0.0.1:{{port}}/health",
                    "expected_status": 200,
                }]}, f)
            with mock.patch.object(verify, "SCENARIO_PORT_RANGE", (port, port + 1)), \
                 mock.patch.object(verify, "DEPLOY_MODE", "none"), \
                 mock.patch.object(verify, "run_unit_tests", return_value=(True, "Ran 1 test")):
                evidence = verify.verify_candidate(
                    tmp, os.path.join(tmp, "candidate.pid"), scenarios)
        finally:
            sock.close()
        self.assertEqual(evidence["verdict"], "HOLD")
        self.assertEqual(evidence["scenarios"][0]["verdict"], "HOLD")
        self.assertIn("no free port", evidence["scenarios"][0]["checks"][0]["detail"])

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

class TestNativeBoundary(unittest.TestCase):
    def test_candidate_suite_never_sees_kernel_env(self):
        # 2026-10-09 incident: MERGE_MODE=review leaked from the launch env
        # into a candidate suite that compared it against 'success' and
        # false-REDed. Every candidate-argv execution gets the scrubbed env.
        import unittest.mock as mock

        probe = ("import os\n"
                 "leaked = [k for k in ('MERGE_MODE', 'TASK_KIND', 'DEPLOY_MODE',\n"
                 "                      'FACTORY_NATIVE_CONFIG', 'NTFY_TOPIC',\n"
                 "                      'NIGHTSHIFT_RECIPES_DIR',\n"
                 "                      'SURPLUS_INTELLIGENCE_API_KEY',\n"
                 "                      'IMPLEMENTER_MODEL') if k in os.environ]\n"
                 "if leaked:\n"
                 "    raise SystemExit('leaked: %s' % leaked)\n"
                 "if not os.environ.get('PATH'):\n"
                 "    raise SystemExit('PATH scrubbed')\n"
                 "print('# tests 1')\n")
        suite = [sys.executable, "-c", probe]
        kernel_env = {"MERGE_MODE": "review", "TASK_KIND": "bug",
                      "DEPLOY_MODE": "app", "FACTORY_NATIVE_CONFIG": "{}",
                      "NTFY_TOPIC": "t", "NIGHTSHIFT_RECIPES_DIR": "/tmp/r",
                      "SURPLUS_INTELLIGENCE_API_KEY": "x",
                      "IMPLEMENTER_MODEL": "m"}
        with tempfile.TemporaryDirectory() as cwd:
            with mock.patch.dict(os.environ, kernel_env):
                status, rows = verify._run_native_commands([suite], cwd, suite)
            self.assertEqual(status, "pass", rows[0]["output"])
            # and the denylist is exactly that: PATH/HOME survive the scrub
            scrubbed = verify.candidate_env()
            for k in kernel_env:
                self.assertNotIn(k, scrubbed)
            self.assertTrue(scrubbed.get("PATH"))
            self.assertIn("HOME", scrubbed)

    def test_only_designated_suite_requires_authoritative_positive_total(self):
        # guard argv must stay distinct from every suite argv, or the
        # designated-exactly-once check rejects the fixture (not the contract).
        guard = [sys.executable, "-c", "print('guard: passed\\n# tests 0')"]
        with tempfile.TemporaryDirectory() as cwd:
            for text, expected in (("# pass 0\n# fail 0\n# tests 2", "pass"),
                                   ("# tests 0", "fail"), ("# pass 2", "fail"),
                                   ("# tests nope", "fail"), ("# tests\n2", "fail"),
                                   ("# tests 1\n# tests 2", "fail")):
                suite = [sys.executable, "-c", "print(%r)" % text]
                status, rows = verify._run_native_commands([guard, suite], cwd, suite)
                self.assertEqual(status, expected, rows)
                self.assertEqual(rows[0]["status"], "pass")

    def test_duplicate_suite_argv_is_rejected(self):
        argv = [sys.executable, "-c", "print('# tests 1')"]
        with tempfile.TemporaryDirectory() as cwd:
            with self.assertRaises(ValueError):
                verify._run_native_commands([argv, argv], cwd, argv)
            with self.assertRaises(ValueError):
                verify._run_native_commands([argv], cwd, [sys.executable, "-c", "pass"])

    def test_full_artifacts_and_hold_precedence_through_candidate(self):
        import unittest.mock as mock
        fail = [sys.executable, "-c", "print('x'*10000); raise SystemExit(1)"]
        missing = ["/nonexistent/factory-command"]
        suite = [sys.executable, "-c", "print('# tests 1')"]
        with tempfile.TemporaryDirectory() as cwd:
            for commands in ([fail, missing, suite], [missing, fail, suite]):
                with mock.patch.object(verify, "NATIVE_VERIFY_COMMANDS", commands), \
                     mock.patch.object(verify, "NATIVE_SUITE_COMMAND", suite), \
                     mock.patch.object(verify, "NATIVE_PREPARE_COMMANDS", None):
                    evidence = verify.verify_candidate(cwd, cwd + '/pid', cwd)
                self.assertEqual(evidence["verdict"], "HOLD")
                row = next(r for r in evidence["unit"]["commands"] if r["command"] == fail)
                with open(row["artifacts"]["stdout"]) as f:
                    self.assertEqual(f.read(), "x" * 10000 + "\n")
                self.assertLessEqual(len(row["output"]), 8000)

    def test_timeout_is_hold_with_partial_output(self):
        command = [sys.executable, "-u", "-c", "import time; print('started'); time.sleep(5)"]
        with tempfile.TemporaryDirectory() as cwd:
            status, rows = verify._run_native_commands([command], cwd, timeout_s=0.1)
            self.assertEqual(status, "HOLD")
            self.assertTrue(rows[0]["timed_out"])
            self.assertIn("started", rows[0]["output"])

class TestSuiteRunnerDispatch(unittest.TestCase):
    """suite_runner picks the authoritative-total parser for the suite argv;
    the default stays tap, so an unconfigured suite is byte-identical."""

    def test_pytest_parser_accepts_one_authoritative_summary_only(self):
        cases = (("12 passed in 0.05s\n", 12),
                 ("1 failed, 11 passed in 0.05s\n", 11),
                 ("2 skipped in 0.01s\n", None),          # all-skipped: no passed count
                 ("no tests ran in 0.01s\n", None),       # pytest exit 5 signature
                 ("collected 0 items\n\nno tests ran in 0.01s\n", None),
                 ("12 passed in 0.05s\n3 passed in 1.00s\n", None),  # duplicate total
                 ("3 passed\n", None),                    # no summary line
                 ("", None))
        for text, expected in cases:
            self.assertEqual(verify._pytest_test_count(text), expected, repr(text))

    def test_pytest_parser_binds_the_default_banner_padded_summary(self):
        """pytest's default (non -q) output pads the summary with `=` banners;
        the count must bind from that line (the field-test F1)."""
        cases = (
            ("=" * 18 + " 506 passed, 2 xfailed, 1 xpassed in 1.02s " + "=" * 18 + "\n", 506),
            ("=== 3 failed, 503 passed in 1.0s ===\n", 503),   # red run still binds N
            ("== 12 passed in 0.05s ==\r\n", 12),              # CRLF
            ("====== 1 passed in 0.01s ======\n", 1),
            # the bare `-q` form is unchanged
            ("506 passed, 2 xfailed, 1 xpassed in 1.02s\n", 506),
            # a banner-padded zero-tests signature is still vacuous
            ("=== no tests ran in 0.01s ===\n", None),
            ("=== 2 skipped in 0.01s ===\n", None),
            # two banner-padded summaries are still ambiguous -> unknown
            ("== 3 passed in 1.00s ==\n== 4 passed in 2.00s ==\n", None),
            # a "N passed" outside the summary line cannot manufacture a total
            ("=== 7 passed in 0.00s ===\nwarning: 99 passed\n", 7),
        )
        for text, expected in cases:
            self.assertEqual(verify._pytest_test_count(text), expected, repr(text))

    def test_pytest_banner_padded_summary_through_the_runner(self):
        """A default-output green run passes; a red run binds its count and fails."""
        green = [sys.executable, "-c",
                 "print('=' * 18 + ' 506 passed, 2 xfailed, 1 xpassed in 1.02s ' + '=' * 18)"]
        red = [sys.executable, "-c",
               "print('=== 3 failed, 503 passed in 1.0s ==='); raise SystemExit(1)"]
        with tempfile.TemporaryDirectory() as cwd:
            status, rows = verify._run_native_commands([green], cwd, green,
                                                       runner="pytest")
            self.assertEqual(status, "pass")
            self.assertEqual(rows[0]["test_count"], 506)
            status, rows = verify._run_native_commands([red], cwd, red, runner="pytest")
            self.assertEqual(status, "fail")
            self.assertEqual(rows[0]["test_count"], 503)   # bound, and not vacuous
            self.assertNotIn("vacuous", rows[0])

    def test_default_runner_parses_tap_not_pytest(self):
        suite = [sys.executable, "-c", "print('12 passed in 0.05s')"]
        with tempfile.TemporaryDirectory() as cwd:
            status, rows = verify._run_native_commands([suite], cwd, suite)
            self.assertEqual(status, "fail")
            self.assertIsNone(rows[0]["test_count"])
            self.assertTrue(rows[0]["vacuous"])

    def test_pytest_runner_passes_a_green_summary(self):
        suite = [sys.executable, "-c", "print('12 passed in 0.05s')"]
        with tempfile.TemporaryDirectory() as cwd:
            status, rows = verify._run_native_commands([suite], cwd, suite,
                                                       runner="pytest")
            self.assertEqual(status, "pass")
            self.assertEqual(rows[0]["test_count"], 12)
            self.assertNotIn("vacuous", rows[0])

    def test_pytest_zero_tests_signatures_fail(self):
        # exit 5 ("no tests ran") is already a fail; an all-skipped or
        # zero-collected run exits 0 and must be rejected as vacuous.
        zero_exit = [sys.executable, "-c", "print('no tests ran in 0.01s'); raise SystemExit(5)"]
        green_exit = [sys.executable, "-c", "print('2 skipped in 0.01s')"]
        with tempfile.TemporaryDirectory() as cwd:
            for argv, vacuous in ((zero_exit, False), (green_exit, True)):
                status, rows = verify._run_native_commands([argv], cwd, argv,
                                                           runner="pytest")
                self.assertEqual(status, "fail", argv)
                self.assertIsNone(rows[0]["test_count"], argv)
                self.assertEqual(rows[0].get("vacuous", False), vacuous, argv)

    def test_suite_timeout_applies_to_the_suite_argv_only(self):
        slow_suite = [sys.executable, "-u", "-c", "import time; time.sleep(5)"]
        other = [sys.executable, "-u", "-c", "import time; time.sleep(0.3)"]
        with tempfile.TemporaryDirectory() as cwd:
            status, rows = verify._run_native_commands([slow_suite, other], cwd,
                                                       slow_suite, suite_timeout_s=0.1)
            self.assertEqual(status, "HOLD")
            self.assertTrue(rows[0]["timed_out"])
            self.assertIn("timed out after 0.1s", rows[0]["detail"])
            self.assertEqual(rows[1]["status"], "pass")

@unittest.skipUnless(importlib.util.find_spec("pytest"), "pytest not installed")
class TestPytestEndToEnd(unittest.TestCase):
    """One real pytest run through the gate; skipped where pytest is absent."""

    ARGV = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"]

    def test_green_pytest_suite_is_non_vacuous(self):
        with tempfile.TemporaryDirectory() as cwd:
            with open(os.path.join(cwd, "test_two.py"), "w") as f:
                f.write("def test_a():\n    assert True\n\n"
                        "def test_b():\n    assert True\n")
            status, rows = verify._run_native_commands([self.ARGV], cwd, self.ARGV,
                                                       runner="pytest")
            self.assertEqual(status, "pass", rows[0]["output"])
            self.assertEqual(rows[0]["test_count"], 2)
            self.assertNotIn("vacuous", rows[0])

    def test_empty_pytest_run_is_not_a_pass(self):
        with tempfile.TemporaryDirectory() as cwd:
            status, rows = verify._run_native_commands([self.ARGV], cwd, self.ARGV,
                                                       runner="pytest")
            self.assertEqual(status, "fail", rows[0]["output"])
            self.assertIsNone(rows[0]["test_count"])

if __name__ == "__main__":
    unittest.main()
