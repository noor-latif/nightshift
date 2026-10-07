"""Unit 4 (DEPLOY_MODE) behavior tests driven through run() itself: with
DEPLOY_MODE=none the lap records deploy-skip and never builds/runs a deploy
script or identity readback; with the default the deploy block runs. Everything
around the deploy gate (issue fetch, LLM, merge) is faked — the gate is the
behavior under test."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
import unittest.mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import lap  # noqa: E402


def git(cwd, *args):
    r = subprocess.run(["git"] + list(args), cwd=cwd, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return r.stdout


class FakeLapEnv:
    """Upstream repo + clone-as-PRODUCT_REPO + patched gh/agent/merge/verify."""

    ISSUE = 21

    def __init__(self, deploy_mode):
        self.mode = deploy_mode
        self.base = tempfile.mkdtemp()
        up = os.path.join(self.base, "upstream")
        os.mkdir(up)
        git(up, "init", "-q", "-b", "main")
        with open(os.path.join(up, "app.py"), "w") as f:
            f.write("x = 1\n")
        git(up, "add", "-A")
        git(up, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "init")
        self.repo = os.path.join(self.base, "repo")
        git(self.base, "clone", "-q", up, self.repo)
        git(self.repo, "fetch", "-q", "origin")
        self.worktree = os.path.join(self.repo, ".factory", "worktrees",
                                     "agent-issue-%d" % self.ISSUE)
        # state/evidence + result file write into the tmp base, never real state/
        self.patches = [
            unittest.mock.patch.object(lap, "PRODUCT_REPO", self.repo),
            unittest.mock.patch.object(lap, "CODE_PATHS", ["*.py"]),
            unittest.mock.patch.object(lap, "DEPLOY_MODE", deploy_mode),
            unittest.mock.patch.object(lap, "EVIDENCE_DIR",
                                      os.path.join(self.base, "evidence")),
            unittest.mock.patch.object(lap, "RESULT_PATH",
                                      os.path.join(self.base, "lap-result.json")),
            unittest.mock.patch.object(lap, "HEARTBEAT_PATH",
                                      os.path.join(self.base, "heartbeat")),
            # run_id collision guard: same second → same run_id → same evdir;
            # harmless here (files overwritten), evidence read fresh below
            unittest.mock.patch.object(lap, "issue_data",
                                      lambda issue: {"title": "t", "body": "Acceptance criteria:\nfix"}),
            unittest.mock.patch.object(lap, "_gh", lambda args: ""),
            unittest.mock.patch.object(lap.agent, "chat", self.fake_chat),
            unittest.mock.patch.object(lap.merge, "full_merge",
                                      lambda issue, repo, wt, ev: {"merged": True, "pr": 1,
                                                                  "merge_sha": "abc"}),
            unittest.mock.patch.object(lap.verify, "verify_candidate",
                                      lambda cwd, pid, sdir, issue=None, evidence_dir=None: {"verdict": "pass"}),
        ]

    def fake_chat(self, msgs, model, max_tokens=None, reasoning_effort=None,
                  trace_dir=None, call_id="call", api="openai-completions",
                  max_tokens_field="max_tokens"):
        if model == lap.IMPLEMENTER_MODEL:
            content = json.dumps([{"file": "app.py", "find": "x = 1", "replace": "x = 2"}])
        else:
            content = "VERDICT: accept"
        return {"content": content, "finish_reason": "stop",
                "usage": {"buyer_cost_micro": 1000}}

    def __enter__(self):
        for p in self.patches:
            p.start()
            self.addCleanup_later = None
        return self

    def addCleanup_later(self, _):
        pass

    def __exit__(self, *a):
        for p in reversed(self.patches):
            p.stop()
        return False

    def timeline(self):
        run_ids = sorted(os.listdir(os.path.join(self.base, "evidence")))
        with open(os.path.join(self.base, "evidence", run_ids[-1], "timeline.json")) as f:
            return json.load(f)


class TestDeployModeNone(unittest.TestCase):
    def test_deploy_skipped_with_event_and_no_deploy_build(self):
        with FakeLapEnv("none") as env:
            with unittest.mock.patch.object(
                    lap.deploy, "build_deploy_script",
                    side_effect=AssertionError("deploy must not run")) as bs, \
                 unittest.mock.patch.object(
                    lap.deploy, "identity_readback",
                    side_effect=AssertionError("identity must not run")):
                lap.run(FakeLapEnv.ISSUE)
                self.assertFalse(bs.called)
        events = [e["event"] for e in env.timeline()]
        self.assertIn("deploy-skip", events)
        self.assertNotIn("deploy", events)
        self.assertIn("issue-closed", events)
        with open(os.path.join(env.base, "lap-result.json")) as f:
            self.assertEqual(json.load(f)["outcome"], "success")

    def test_deploy_failure_impossible_in_none_mode(self):
        # the deploy gate failure path (rc != 0) cannot trigger when the
        # block is skipped: no deploy event at all, lap reaches success
        with FakeLapEnv("none") as env:
            lap.run(FakeLapEnv.ISSUE)
        self.assertEqual([e["event"] for e in env.timeline()][-2], "issue-closed")


class TestDeployModeApp(unittest.TestCase):
    def test_app_mode_still_deploys_and_checks_identity(self):
        calls = []
        with FakeLapEnv("app") as env:
            def fake_script(port, product_repo, pid_file):
                calls.append("build")
                return "echo deploy-ok"
            def fake_identity(url, repo):
                calls.append("identity")
                return {"match": True, "head": "x"}
            with unittest.mock.patch.object(lap.deploy, "build_deploy_script",
                                            side_effect=fake_script), \
                 unittest.mock.patch.object(lap.deploy, "identity_readback",
                                            side_effect=fake_identity):
                lap.run(FakeLapEnv.ISSUE)
        events = [e["event"] for e in env.timeline()]
        self.assertIn("deploy", events)
        self.assertNotIn("deploy-skip", events)
        self.assertEqual(calls, ["build", "identity"])
        with open(os.path.join(env.base, "lap-result.json")) as f:
            self.assertEqual(json.load(f)["outcome"], "success")

class TestScenariosDirWiring(unittest.TestCase):
    """Behavioral proof (launch-2 lesson): SCENARIOS_DIR must flow through
    the REAL call paths — lap.run's verify_candidate call and supervisor's
    red_recheck — not merely exist in settings. A dir listing or a settings
    reload is not proof; the recorded argument is."""

    def test_lap_run_passes_env_scenarios_dir_to_verify(self):
        curated = tempfile.mkdtemp(prefix="curated-oracles-")
        with FakeLapEnv("none"):
            with unittest.mock.patch.object(lap, "SCENARIOS_DIR", curated):
                seen = {}

                def recorder(cwd, pid_file, scenarios_dir, issue=None, evidence_dir=None):
                    seen["dir"] = scenarios_dir
                    return {"verdict": "pass"}

                with unittest.mock.patch.object(lap.verify, "verify_candidate",
                                                side_effect=recorder):
                    lap.run(FakeLapEnv.ISSUE)
        self.assertEqual(seen["dir"], curated)

    def test_lap_run_default_scenarios_dir_without_env(self):
        # env unset → the historical relative default (the module attr,
        # resolved at import from settings' env read)
        import settings
        expected = os.path.normpath(settings.SCENARIOS_DIR)
        with FakeLapEnv("none"):
            seen = {}

            def recorder(cwd, pid_file, scenarios_dir, issue=None, evidence_dir=None):
                seen["dir"] = scenarios_dir
                return {"verdict": "pass"}

            with unittest.mock.patch.object(lap.verify, "verify_candidate",
                                            side_effect=recorder):
                lap.run(FakeLapEnv.ISSUE)
        self.assertEqual(os.path.normpath(seen["dir"]), expected)

    def test_supervisor_red_recheck_passes_env_scenarios_dir(self):
        import supervisor
        curated = tempfile.mkdtemp(prefix="curated-oracles-")
        wt = tempfile.mkdtemp(prefix="recheck-wt-")
        seen = {}

        def recorder(cwd, pid_file, scenarios_dir, issue=None, evidence_dir=None):
            seen["dir"] = scenarios_dir
            seen["issue"] = issue
            return {"verdict": "fail"}

        with unittest.mock.patch.object(supervisor, "SCENARIOS_DIR", curated), \
             _patch_lap_worktree(wt), \
             _patch_verify_recorder(recorder):
            verdict, _detail = supervisor.red_recheck(3)
        self.assertEqual(seen["dir"], curated)
        self.assertEqual(seen["issue"], 3)
        self.assertEqual(verdict, "fail")

    def test_supervisor_red_recheck_default_dir(self):
        import supervisor
        import settings
        wt = tempfile.mkdtemp(prefix="recheck-wt-")
        seen = {}

        def recorder(cwd, pid_file, scenarios_dir, issue=None, evidence_dir=None):
            seen["dir"] = scenarios_dir
            return {"verdict": "fail"}

        with _patch_lap_worktree(wt), _patch_verify_recorder(recorder):
            verdict, _detail = supervisor.red_recheck(4)
        self.assertEqual(os.path.normpath(seen["dir"]),
                         os.path.normpath(settings.SCENARIOS_DIR))


class TestAddCostRows(unittest.TestCase):
    """G3 (audit #3): a call with no usage data must still cost a row —
    'if usage:' silently dropped it and published cost tables undercounted."""

    def lap_with_tmp_evidence(self):
        tmp = tempfile.mkdtemp()
        with unittest.mock.patch.object(lap, "EVIDENCE_DIR",
                                        os.path.join(tmp, "evidence")):
            l = lap.Lap(31)
        return l, os.path.join(l.evdir, "cost.json")

    def test_falsy_usage_appends_row_with_missing_usage(self):
        l, cost_path = self.lap_with_tmp_evidence()
        l.add_cost(None, "implementer")
        with open(cost_path) as f:
            data = json.load(f)
        self.assertEqual(len(data["calls"]), 1)
        row = data["calls"][0]
        self.assertEqual(row["role"], "implementer")
        self.assertIsNone(row["usage"])
        self.assertEqual(row["buyer_cost_micro"], 0)
        self.assertTrue(row["missing_usage"])
        self.assertEqual(data["total_usd"], 0)

    def test_null_usage_summed_alongside_real_rows(self):
        l, cost_path = self.lap_with_tmp_evidence()
        with unittest.mock.patch.object(lap, "COST_CEILING_USD", 10.0):
            l.add_cost({"buyer_cost_micro": 1_500_000}, "implementer")
            l.add_cost(None, "reviewer")
        with open(cost_path) as f:
            data = json.load(f)
        self.assertEqual(len(data["calls"]), 2)  # per-call count assertable
        self.assertEqual(data["total_usd"], 1.5)

class TestFailedCallCostUnknown(unittest.TestCase):
    """A failed call (no response at all, so no usage will ever arrive) must
    still cost a row, marked cost_unknown — the billed spend is unknown, not
    silently absent from the published table."""

    def test_failed_call_records_cost_unknown_row(self):
        def failing_chat(messages, model, **kw):
            raise lap.agent.TransientError("stream died mid-body")

        with FakeLapEnv("none") as env:
            with unittest.mock.patch.object(lap.agent, "chat",
                                            side_effect=failing_chat):
                lap.run(FakeLapEnv.ISSUE)
        with open(os.path.join(env.base, "lap-result.json")) as f:
            result = json.load(f)
        self.assertEqual(result["outcome"], "failure")
        self.assertEqual(result["gate"], "gateway")
        run_ids = sorted(os.listdir(os.path.join(env.base, "evidence")))
        with open(os.path.join(env.base, "evidence", run_ids[-1], "cost.json")) as f:
            cost = json.load(f)
        self.assertEqual(len(cost["calls"]), 1)  # the failed call is not absent
        self.assertEqual(cost["calls"][0]["role"], "implementer")
        self.assertTrue(cost["calls"][0]["cost_unknown"])
        self.assertEqual(cost["total_usd"], 0)


class TestPromptViewSanity(unittest.TestCase):
    def test_implausibly_small_billed_prompt_is_durable_instrument_observation(self):
        rendered = "=== app.py ===\nx = 1\n" + ("x" * 80000)

        def cheap_chat(messages, model, max_tokens=None, reasoning_effort=None,
                       trace_dir=None, call_id="call", api="openai-completions",
                       max_tokens_field="max_tokens"):
            if model == lap.IMPLEMENTER_MODEL:
                content = json.dumps([{"file": "app.py", "find": "x = 1", "replace": "x = 2"}])
            else:
                content = "VERDICT: accept"
            return {"content": content, "finish_reason": "stop",
                    "usage": {"buyer_cost_micro": 1000, "prompt_tokens": 300}}

        with FakeLapEnv("none") as env:
            with unittest.mock.patch.object(lap, "checkout_files",
                                            return_value=[rendered]), \
                 unittest.mock.patch.object(lap.agent, "chat",
                                            side_effect=cheap_chat):
                lap.run(FakeLapEnv.ISSUE)
        run_ids = sorted(os.listdir(os.path.join(env.base, "evidence")))
        with open(os.path.join(env.base, "evidence", run_ids[-1], "verdict.json")) as f:
            verdict = json.load(f)
        self.assertEqual(verdict["attribution"], "instrument-anomaly")
        observation = verdict["observations"][0]
        self.assertEqual(observation["type"], "prompt-size-vs-view")
        self.assertEqual(observation["prompt_tokens"], 300)
        self.assertIn("prompt-size-vs-view discrepancy", observation["message"])
        with open(os.path.join(env.base, "lap-result.json")) as f:
            result = json.load(f)
        self.assertEqual(result["observations"][0]["type"], "prompt-size-vs-view")

    def test_consistent_billed_prompt_is_clean(self):
        self.assertIsNone(lap.prompt_view_discrepancy(
            "x" * 80000, {"prompt_tokens": 20000}))


class TestCostCeilingGate(unittest.TestCase):
    """G7: COST_CEILING_USD was a dead constant — the whitepaper's '$0.01
    ceiling' never ran. Exceeding it must end the lap gate='cost' with a
    verdict.json, not continue silently."""

    def test_ceiling_exceeded_lap_fails_gate_cost(self):
        with FakeLapEnv("none") as env:
            # fake implementer call costs 1000 micro = $0.001; a $0.0005
            # ceiling is exceeded on the first add_cost
            with unittest.mock.patch.object(lap, "COST_CEILING_USD", 0.0005):
                lap.run(FakeLapEnv.ISSUE)
        with open(os.path.join(env.base, "lap-result.json")) as f:
            result = json.load(f)
        self.assertEqual(result["outcome"], "failure")
        self.assertIn("exceeds ceiling", result["error"])
        run_ids = sorted(os.listdir(os.path.join(env.base, "evidence")))
        with open(os.path.join(env.base, "evidence", run_ids[-1], "verdict.json")) as f:
            verdict = json.load(f)
        self.assertEqual(verdict["gate"], "cost")
        self.assertEqual(verdict["verdict"], "fail")

    def test_ceiling_not_reached_lap_succeeds(self):
        # the default $0.01 ceiling vs one $0.001 call: no gate trip
        with FakeLapEnv("none") as env:
            lap.run(FakeLapEnv.ISSUE)
        with open(os.path.join(env.base, "lap-result.json")) as f:
            self.assertEqual(json.load(f)["outcome"], "success")


class TestMergeEvidencePassThrough(unittest.TestCase):
    """Audit gap #4: full_merge must receive the REAL verify evidence —
    the hardcoded {\"verdict\": \"pass\"} made merge.py's gate_green green
    by construction."""

    def test_full_merge_receives_verify_evidence(self):
        real_evidence = {"verdict": "pass", "checks": [{"status": "pass"}],
                         "marker": "distinctive"}
        seen = {}

        def recorder(cwd, pid_file, scenarios_dir, issue=None, evidence_dir=None):
            return real_evidence

        def merge_recorder(issue, repo, wt, ev):
            seen["evidence"] = ev
            return {"merged": True, "pr": 1, "merge_sha": "abc"}

        with FakeLapEnv("none"):
            with unittest.mock.patch.object(lap.verify, "verify_candidate",
                                            side_effect=recorder), \
                 unittest.mock.patch.object(lap.merge, "full_merge",
                                           side_effect=merge_recorder):
                lap.run(FakeLapEnv.ISSUE)
        self.assertEqual(seen["evidence"], real_evidence)


def _patch_lap_worktree(wt):
    import lap as lapmod
    return unittest.mock.patch.object(lapmod, "worktree_for",
                                     lambda issue, prefix="recheck": wt)


def _patch_verify_recorder(recorder):
    import verify
    return unittest.mock.patch.object(verify, "verify_candidate",
                                     side_effect=recorder)

class TestReviewVerdictParsing(unittest.TestCase):
    """P3: the verdict line carries three classes, and the per-criterion table
    is derived from the evidence lines the prompt orders BEFORE each judgment."""

    def test_all_three_classes_parse(self):
        for cls in ("accept", "reject", "abstain"):
            self.assertEqual(lap.review_verdict("prose\nVERDICT: %s\n" % cls), cls)

    def test_case_insensitive_and_unparseable_is_none(self):
        self.assertEqual(lap.review_verdict("VERDICT:  ABSTAIN"), "abstain")
        self.assertIsNone(lap.review_verdict("no verdict line here"))

    def test_first_match_wins_the_echoed_instruction_hazard_is_unchanged(self):
        # Design §3.4: re.search returns the FIRST match, so a review echoing
        # the instruction line captures the echo's class rather than the final
        # line's. Pre-existing, deliberately unchanged by P3 (owner's call to
        # harden) — pinned here so any change to it is a deliberate one.
        text = "Last line must be VERDICT: accept|reject|abstain\n\nVERDICT: reject"
        self.assertEqual(lap.review_verdict(text), "accept")

    def test_review_table_pairs_evidence_with_judgment(self):
        text = ("EVIDENCE: x = 2\nJUDGMENT: PASS\n"
                "EVIDENCE: none\nJUDGMENT: UNVERIFIABLE\n")
        table = lap.review_table(text, "abstain")
        self.assertEqual(table["verdict_class"], "abstain")
        self.assertEqual(table["criteria"],
                         [{"evidence": "x = 2", "judgment": "PASS"},
                          {"evidence": "none", "judgment": "UNVERIFIABLE"}])
        self.assertEqual(table["evidence_none_count"], 1)

    def test_review_table_keeps_colons_inside_a_verbatim_quote(self):
        text = "EVIDENCE: body = {\"error\": \"not found\"}\nJUDGMENT: PASS\n"
        table = lap.review_table(text, "accept")
        self.assertEqual(table["criteria"][0]["evidence"],
                         'body = {"error": "not found"}')

    def test_review_table_parses_inline_pair(self):
        # R3 of the p3-matrix rerun emitted the pair on one line (em-dash
        # separator) and the two-line grammar missed all four rows.
        text = 'EVIDENCE: `if self.path != "/paste":` — JUDGMENT: FAIL\n'
        table = lap.review_table(text, "reject")
        self.assertEqual(table["criteria"],
                         [{"evidence": '`if self.path != "/paste":`',
                           "judgment": "FAIL"}])

    def test_review_table_parses_inline_pair_with_spaced_hyphen(self):
        text = "EVIDENCE: x = 2 - JUDGMENT: pass\n"
        table = lap.review_table(text, "accept")
        self.assertEqual(table["criteria"],
                         [{"evidence": "x = 2", "judgment": "PASS"}])

    def test_review_table_mixed_two_line_and_inline_rows(self):
        text = ("EVIDENCE: `path = urllib.parse.urlsplit(self.path).path`\n"
                "JUDGMENT: PASS\n"
                "\n"
                "EVIDENCE: `self._send_json(400, {...})` — JUDGMENT: FAIL\n"
                "\n"
                "EVIDENCE: none\n"
                "JUDGMENT: UNVERIFIABLE\n")
        table = lap.review_table(text, "abstain")
        self.assertEqual([c["judgment"] for c in table["criteria"]],
                         ["PASS", "FAIL", "UNVERIFIABLE"])
        self.assertEqual(table["criteria"][1]["evidence"],
                         "`self._send_json(400, {...})`")
        self.assertEqual(table["evidence_none_count"], 1)

    def test_review_table_two_line_pair_is_not_double_parsed_as_inline(self):
        text = ("EVIDENCE: a = 1 - b = 2\n"   # a dash, but no inline judgment
                "JUDGMENT: PASS\n")
        table = lap.review_table(text, "accept")
        self.assertEqual(table["criteria"],
                         [{"evidence": "a = 1 - b = 2", "judgment": "PASS"}])

    def test_review_table_inline_none_still_counts_evidence_none(self):
        table = lap.review_table("EVIDENCE: none — JUDGMENT: UNVERIFIABLE\n",
                                 "abstain")
        self.assertEqual(table["criteria"],
                         [{"evidence": "none", "judgment": "UNVERIFIABLE"}])
        self.assertEqual(table["evidence_none_count"], 1)

    def test_review_table_excludes_echoed_prompt_template(self):
        # A review echoing the prompt's template must not turn the template
        # into a row, and must not swallow the real rows around it.
        text = ("For each criterion emit exactly two lines:\n"
                "\n"
                "EVIDENCE: <one verbatim quote, copied character-for-character "
                "from the diff or\n"
                "from the current file contents above, that decides this "
                "criterion> — or\n"
                "literally `EVIDENCE: none` when no text in the provided "
                "material decides it.\n"
                "JUDGMENT: PASS | FAIL | UNVERIFIABLE\n"
                "\n"
                "EVIDENCE: none — JUDGMENT: UNVERIFIABLE\n")
        table = lap.review_table(text, "abstain")
        self.assertEqual(table["criteria"],
                         [{"evidence": "none", "judgment": "UNVERIFIABLE"}])
        self.assertEqual(table["evidence_none_count"], 1)

    def test_review_table_parses_the_real_r3_shape(self):
        text = ('EVIDENCE: `if self.path != "/paste":` — JUDGMENT: FAIL\n'
                'EVIDENCE: `path = urllib.parse.urlsplit(self.path).path` — '
                'JUDGMENT: PASS\n'
                'EVIDENCE: `self._send_json(400, {"error": "invalid JSON '
                'body"})` — JUDGMENT: FAIL\n'
                'EVIDENCE: `status, body = self.request("POST", "/paste", '
                '{"content": "factory smoke test"})` — JUDGMENT: PASS\n'
                "VERDICT: reject\n")
        table = lap.review_table(text, "reject")
        self.assertEqual(len(table["criteria"]), 4)
        self.assertEqual([c["judgment"] for c in table["criteria"]],
                         ["FAIL", "PASS", "FAIL", "PASS"])
        self.assertEqual(table["evidence_none_count"], 0)


class TestLocalReviewSnapshot(unittest.TestCase):
    def test_snapshot_survives_cleanup_without_merge_or_close(self):
        with FakeLapEnv("none") as env, \
             unittest.mock.patch.object(lap, "MERGE_MODE", "review"), \
             unittest.mock.patch.object(lap.merge, "full_merge", side_effect=AssertionError("must not merge")), \
             unittest.mock.patch.object(lap, "_gh", side_effect=AssertionError("must not close")):
            lap.run(env.ISSUE)
            with open(os.path.join(env.base, "lap-result.json")) as f:
                result = json.load(f)
            self.assertEqual(result["outcome"], "awaiting-review")
            with open(os.path.join(result["evidence_dir"], "merge.json")) as f:
                snapshot = json.load(f)
            self.assertFalse(os.path.exists(env.worktree))
            self.assertEqual(git(env.repo, "show", snapshot["ref"] + ":app.py"), "x = 2\n")
            self.assertFalse(snapshot["pushed"])
            self.assertFalse(snapshot["merged"])

    def test_rejected_candidate_retained_with_ref_and_record(self):
        # reviewer rejects: the candidate must stay discoverable after
        # worktree cleanup — a rejected/<run-id> ref plus verdict + sha in
        # the run's artifacts, not only the bare agent branch.
        def rejecting_chat(messages, model, **kw):
            if model == lap.IMPLEMENTER_MODEL:
                content = json.dumps([{"file": "app.py", "find": "x = 1",
                                       "replace": "x = 2"}])
            else:
                content = "VERDICT: reject"
            return {"content": content, "finish_reason": "stop",
                    "usage": {"buyer_cost_micro": 1000}}

        with FakeLapEnv("none") as env, \
             unittest.mock.patch.object(lap, "MERGE_MODE", "review"), \
             unittest.mock.patch.object(lap.agent, "chat", side_effect=rejecting_chat), \
             unittest.mock.patch.object(lap.merge, "full_merge", side_effect=AssertionError("must not merge")), \
             unittest.mock.patch.object(lap, "_gh", side_effect=AssertionError("must not close")):
            lap.run(env.ISSUE)
        with open(os.path.join(env.base, "lap-result.json")) as f:
            result = json.load(f)
        self.assertEqual(result["outcome"], "failure")
        self.assertEqual(result["gate"], "review")
        rejected = result["rejected_candidate"]
        self.assertEqual(rejected["verdict"], "reject")
        self.assertFalse(os.path.exists(env.worktree))
        self.assertEqual(git(env.repo, "rev-parse", rejected["ref"]).strip(),
                         rejected["commit"])
        self.assertEqual(git(env.repo, "show", rejected["ref"] + ":app.py"), "x = 2\n")
        with open(os.path.join(result["evidence_dir"], "rejected.json")) as f:
            self.assertEqual(json.load(f)["commit"], rejected["commit"])

    def test_abstained_candidate_is_terminal_escalation_not_reject_or_retry(self):
        # P3: abstain is its own terminal class — no merge, no verify, no
        # close; the candidate is retained under the reject retention
        # namespace, and the verdict class is recorded as abstain (never
        # accept, and never collapsed into "fail").
        def abstaining_chat(messages, model, **kw):
            if model == lap.IMPLEMENTER_MODEL:
                content = json.dumps([{"file": "app.py", "find": "x = 1",
                                       "replace": "x = 2"}])
            else:
                content = ("EVIDENCE: none\nJUDGMENT: UNVERIFIABLE\n"
                           "VERDICT: abstain")
            return {"content": content, "finish_reason": "stop",
                    "usage": {"buyer_cost_micro": 1000}}

        with FakeLapEnv("none") as env, \
             unittest.mock.patch.object(lap, "MERGE_MODE", "review"), \
             unittest.mock.patch.object(lap.agent, "chat", side_effect=abstaining_chat), \
             unittest.mock.patch.object(lap.merge, "full_merge", side_effect=AssertionError("must not merge")), \
             unittest.mock.patch.object(lap.verify, "verify_candidate", side_effect=AssertionError("must not verify")), \
             unittest.mock.patch.object(lap, "_gh", side_effect=AssertionError("must not close")):
            lap.run(env.ISSUE)
        with open(os.path.join(env.base, "lap-result.json")) as f:
            result = json.load(f)
        self.assertEqual(result["outcome"], "abstain")
        self.assertEqual(result["gate"], "review")
        abstained = result["abstained_candidate"]
        self.assertEqual(abstained["verdict"], "abstain")
        self.assertFalse(os.path.exists(env.worktree))
        self.assertEqual(git(env.repo, "show", abstained["ref"] + ":app.py"), "x = 2\n")
        evdir = result["evidence_dir"]
        with open(os.path.join(evdir, "abstained.json")) as f:
            self.assertEqual(json.load(f)["verdict"], "abstain")
        with open(os.path.join(evdir, "verdict.json")) as f:
            self.assertEqual(json.load(f)["verdict"], "abstain")  # not "fail"
        with open(os.path.join(evdir, "review-verdicts.json")) as f:
            self.assertEqual(json.load(f)["verdict_class"], "abstain")
        events = [e["event"] for e in env.timeline()]
        self.assertIn("review-abstain", events)
        self.assertNotIn("review-accept", events)
        self.assertNotIn("review-reject", events)

    def test_bad_enhancement_baseline_prevents_model_call(self):
        with FakeLapEnv("none") as env, \
             unittest.mock.patch.object(lap, "TASK_KIND", "enhancement"), \
             unittest.mock.patch.object(lap.verify, "verify_candidate", return_value={"verdict": "HOLD"}), \
             unittest.mock.patch.object(lap.agent, "chat", side_effect=AssertionError("must not call model")):
            lap.run(env.ISSUE)
            with open(os.path.join(env.base, "lap-result.json")) as f:
                result = json.load(f)
            self.assertEqual(result["gate"], "baseline")
            self.assertEqual(result["outcome"], "failure")

    def test_verify_source_mutation_cannot_be_reported_reviewable(self):
        def changing_verify(cwd, pid, sdir, issue=None, evidence_dir=None):
            with open(os.path.join(cwd, "app.py"), "w") as f:
                f.write("x = 3\n")
            return {"verdict": "pass"}
        with FakeLapEnv("none") as env, \
             unittest.mock.patch.object(lap, "MERGE_MODE", "review"), \
             unittest.mock.patch.object(lap.verify, "verify_candidate", side_effect=changing_verify):
            lap.run(env.ISSUE)
            with open(os.path.join(env.base, "lap-result.json")) as f:
                result = json.load(f)
            self.assertEqual(result["gate"], "verify-source")
            self.assertEqual(result["outcome"], "failure")

class TestWorktreePreAssignCleanup(unittest.TestCase):
    """L-016: run() pre-assigns the deterministic worktree path so its finally
    reaps it even when worktree_for raises before assignment. The skipped
    finally is how the launch-5 crash loop started: the registered trap
    survived every crash and every retry hit it again."""

    def test_run_reaps_registered_trap_when_worktree_for_raises(self):
        with FakeLapEnv("none") as env:
            os.makedirs(os.path.dirname(env.worktree), exist_ok=True)
            git(env.repo, "worktree", "add", env.worktree, "-B", "agent/issue-21",
                "origin/main")
            self.assertIn(env.worktree, git(env.repo, "worktree", "list", "--porcelain"))
            with unittest.mock.patch.object(
                    lap, "worktree_for",
                    side_effect=RuntimeError("worktree add failed: is already used by worktree")):
                lap.run(FakeLapEnv.ISSUE)
            with open(os.path.join(env.base, "lap-result.json")) as f:
                result = json.load(f)
            self.assertEqual(result["outcome"], "crash")
            # the pre-assigned path was reaped despite worktree_for raising
            self.assertNotIn(env.worktree,
                             git(env.repo, "worktree", "list", "--porcelain"))

if __name__ == "__main__":
    unittest.main()
