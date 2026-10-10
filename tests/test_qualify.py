"""Unit tests for the qualify pass (src/qualify.py).

Hermetic and fast: synthetic git repos in temp dirs, no network, no model call,
no nix. The one thing these tests pin hardest is the property the design makes
load-bearing — a deterministic run and every no-go path make ZERO model calls.
"""

import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import qualify  # noqa: E402

GIT_ID = ["-c", "user.email=t@t", "-c", "user.name=t"]


def _load(path):
    with open(path) as f:
        return json.load(f)


def _read_text(path):
    with open(path) as f:
        return f.read()


def _bytes(path):
    with open(path, "rb") as f:
        return f.read()


def _write(path, text, mode=None):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(text)
    if mode:
        os.chmod(path, mode)
    return path


def _git(repo, *args):
    return subprocess.run(["git"] + list(args), cwd=repo, capture_output=True,
                          text=True, check=True).stdout.strip()


def _make_repo(root, files=None, commits=1):
    """A real git repo with a real HEAD. Returns (path, head_sha)."""
    os.makedirs(root, exist_ok=True)
    subprocess.run(["git", "init", "-q", "-b", "main", root], check=True)
    for name, text in (files or {"README.md": "# repo\n"}).items():
        _write(os.path.join(root, name), text)
    subprocess.run(["git"] + GIT_ID + ["add", "-A"], cwd=root, capture_output=True, check=True)
    for i in range(commits):
        subprocess.run(["git"] + GIT_ID + ["commit", "-q", "--allow-empty",
                                           "-m", "c%d" % i],
                       cwd=root, capture_output=True, check=True)
    return root, _git(root, "rev-parse", "HEAD")


SUITE_SH = """#!/usr/bin/env bash
# synthetic TAP suite: one test per '# test' line, red on a probe line.
# cwd-relative on purpose: the harness runs every argv with cwd = repo root.
# On failure it names the failing test the way a real TAP runner does, so the
# collection-liveness probe has something to see in the output.
f="tests/probe.txt"
n=$(grep -c '^# test' "$f" 2>/dev/null || echo 0)
if grep -q '^# test probe-fail' "$f" 2>/dev/null; then
  echo "not ok $n - probe-fail"
  echo "# tests $n"
  exit 1
fi
echo "# tests $n"
exit 0
"""


class QualifyCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="qualify-test-")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def repo(self, name="repo", files=None, commits=1):
        return _make_repo(os.path.join(self.tmp, name), files, commits)

    def evdir(self, name="ev"):
        d = os.path.join(self.tmp, name)
        os.makedirs(d, exist_ok=True)
        return d

    def suite_repo(self):
        """A repo whose suite emits a real TAP total and can be made red.
        Returns the path only (unlike `repo()`, which also returns HEAD)."""
        suite = os.path.join(self.tmp, "suite.sh")
        _write(suite, SUITE_SH, 0o755)
        return self.repo(files={"README.md": "# repo\n",
                                "tests/probe.txt": "# test a\n# test b\n# test c\n"})[0]

    def seed(self, repo, suite=None, **over):
        s = {
            "origin": "example/repo",
            "prepare": [{"argv": ["true"]}],
            "verify": [{"argv": [suite], "timeout_s": 60}],
            "suite_index": 0,
            "suite_runner": "tap",
            "suite_timeout_s": 60,
        }
        s.update(over)
        return s


# --------------------------------------------------------------------------
# D12/G7 — provenance
# --------------------------------------------------------------------------

class TestProvenance(QualifyCase):
    def test_quote_ok_exact_line(self):
        repo, _ = self.repo(files={"README.md": "one\ntwo\nthree\n"})
        self.assertTrue(qualify._quote_ok(repo, {"file": "README.md", "line": 2,
                                                 "text": "two"}))

    def test_quote_ok_line_out_of_range(self):
        repo, _ = self.repo(files={"README.md": "one\ntwo\n"})
        self.assertFalse(qualify._quote_ok(repo, {"file": "README.md", "line": 99,
                                                  "text": "two"}))
        self.assertFalse(qualify._quote_ok(repo, {"file": "README.md", "line": 0,
                                                  "text": "one"}))

    def test_quote_ok_missing_file(self):
        repo, _ = self.repo()
        self.assertFalse(qualify._quote_ok(repo, {"file": "nope.md", "line": 1,
                                                  "text": "x"}))

    def test_quote_ok_substring_absent_from_that_line(self):
        repo, _ = self.repo(files={"README.md": "one\ntwo\n"})
        self.assertFalse(qualify._quote_ok(repo, {"file": "README.md", "line": 1,
                                                  "text": "two"}))

    def test_dryrun_ok_matching_exit(self):
        ev = self.evdir()
        receipt = qualify.write_receipt(ev, "r0", {"argv": ["x"], "exit": 0})
        self.assertTrue(qualify._dryrun_ok(ev, {"kind": "dryrun", "exit": 0,
                                                "evidence": receipt}))

    def test_dryrun_ok_missing_receipt(self):
        ev = self.evdir()
        self.assertFalse(qualify._dryrun_ok(ev, {"kind": "dryrun", "exit": 0,
                                                 "evidence": os.path.join(ev, "gone.json")}))

    def test_dryrun_ok_exit_mismatch(self):
        ev = self.evdir()
        receipt = qualify.write_receipt(ev, "r1", {"argv": ["x"], "exit": 0})
        self.assertFalse(qualify._dryrun_ok(ev, {"kind": "dryrun", "exit": 1,
                                                 "evidence": receipt}))

    def test_operator_source_needs_absolute_first_token(self):
        repo, _ = self.repo()
        ok, why = qualify._source_ok(repo, self.evdir(), {"kind": "operator"}, ["nix", "develop"])
        self.assertFalse(ok)
        self.assertIn("absolute", why)

    def test_operator_source_must_live_outside_the_repo(self):
        repo, _ = self.repo()
        inside = os.path.join(repo, "oracle.sh")
        ok, why = qualify._source_ok(repo, self.evdir(), {"kind": "operator"}, [inside])
        self.assertFalse(ok)
        self.assertIn("outside", why)

    def test_operator_source_absolute_outside_ok(self):
        repo, _ = self.repo()
        ok, _ = qualify._source_ok(repo, self.evdir(), {"kind": "operator"},
                                   [os.path.join(self.tmp, "elsewhere", "oracle.sh")])
        self.assertTrue(ok)

    def test_unknown_source_kind_rejected(self):
        repo, _ = self.repo()
        ok, why = qualify._source_ok(repo, self.evdir(), {"kind": "vibes"}, ["true"])
        self.assertFalse(ok)
        self.assertIn("unknown", why)

    def test_provenance_checks_both_the_claim_and_the_receipt(self):
        """F2: when both are recorded, a passing quote with a mismatched
        receipt is not provenance."""
        repo, _ = self.repo(files={"README.md": "run: make test\n"})
        ev = self.evdir()
        receipt = qualify.write_receipt(ev, "r2", {"argv": ["x"], "exit": 0})
        quote = {"kind": "quote", "file": "README.md", "line": 1,
                 "text": "run: make test"}
        entries = [("prepare", {"source": dict(quote),
                                "dryrun": {"kind": "dryrun", "exit": 0,
                                           "evidence": receipt}}),
                   ("prepare", {"source": dict(quote),
                                "dryrun": {"kind": "dryrun", "exit": 1,
                                           "evidence": receipt}})]
        prov = qualify.check_provenance(repo, ev, entries)
        self.assertEqual([r["ok"] for r in prov["entries"]], [True, False])
        self.assertFalse(prov["ok"])
        self.assertIn("quote verified", prov["entries"][0]["why"])
        self.assertIn("dryrun receipt exit=0 matches", prov["entries"][0]["why"])


# --------------------------------------------------------------------------
# D1/D2/D3/D4/D5 — static checks
# --------------------------------------------------------------------------

class TestStaticChecks(QualifyCase):
    def test_deep_clone_is_ok(self):
        repo, head = self.repo(commits=3)
        res = qualify.check_chain(repo, head)
        self.assertTrue(res["ok"])
        self.assertFalse(res["clones"][0]["shallow"])

    def test_shallow_clone_is_flagged(self):
        src, head = self.repo(name="src", commits=3)
        dst = os.path.join(self.tmp, "shallow")
        subprocess.run(["git", "clone", "-q", "--depth", "1", "file://" + src, dst],
                       capture_output=True, check=True)
        res = qualify.check_chain(dst, head)
        self.assertFalse(res["ok"])
        self.assertTrue(res["clones"][0]["shallow"])
        # the base commit is present (depth 1 = HEAD) — depth alone is the check
        self.assertTrue(res["clones"][0]["base_resolvable"])

    def test_missing_base_is_flagged(self):
        repo, _ = self.repo()
        self.assertFalse(qualify.check_chain(repo, "0" * 40)["ok"])

    def test_hook_with_relative_gitignored_config_is_poisoned(self):
        repo, _ = self.repo(files={"README.md": "# r\n",
                                   ".gitignore": ".pre-commit-config.yaml\n"})
        _write(os.path.join(repo, ".git", "hooks", "commit-msg"),
               "#!/bin/sh\nARGS=(hook-impl --config=.pre-commit-config.yaml "
               "--hook-type=commit-msg)\nexec pre-commit \"${ARGS[@]}\"\n", 0o755)
        res = qualify.check_hooks(repo)
        self.assertTrue(res["poisoned"])
        self.assertEqual(res["escape"], "PRE_COMMIT_ALLOW_NO_CONFIG=1")
        self.assertTrue(res["hooks"][0]["config_gitignored"])

    def test_hook_with_tracked_config_is_not_poisoned(self):
        repo, _ = self.repo(files={"README.md": "# r\n"})
        _write(os.path.join(repo, ".git", "hooks", "pre-commit"),
               "#!/bin/sh\nexec pre-commit --config=.pre-commit-config.yaml\n", 0o755)
        self.assertFalse(qualify.check_hooks(repo)["poisoned"])

    def test_sample_hooks_are_ignored(self):
        repo, _ = self.repo()
        _write(os.path.join(repo, ".git", "hooks", "pre-commit.sample"),
               "#!/bin/sh\n--config=.pre-commit-config.yaml\n", 0o755)
        self.assertFalse(qualify.check_hooks(repo)["poisoned"])

    def test_fingerprint_and_devshell_clobber(self):
        repo, _ = self.repo(files={
            "README.md": "# r\n", "CONTRIBUTING.md": "# c\n", "flake.nix": "{}\n",
            "shells/default/default.nix":
                'shellHook = pre-commit-check.shellHook + \'\'\n'
                '  define_dev_env_var FLOX_BIN "''${REPO_ROOT}/cli/target/debug/flox";\n'
                "'';\n"})
        fp = qualify.check_fingerprint(repo)
        self.assertIn("flake.nix", fp["build_files"])
        self.assertIn("README.md", fp["docs"])
        self.assertIn("shells/default/default.nix", fp["devshell"])
        dev = qualify.check_devshell(repo, fp)
        self.assertGreaterEqual(dev["clobber_count"], 1)
        self.assertIn("default.nix", dev["clobbers"][0]["file"])

    def test_devshell_files_survive_the_cap(self):
        """The cap must not drop the file the D4 trap has to cite: on flox a
        plain alphabetical [:20] listed modules/ and pkgs/ and cut
        shells/default/default.nix, the one carrying the shellHook."""
        files = {"README.md": "# r\n", "flake.nix": "{}\n",
                 "shells/default/default.nix":
                     'shellHook = pre-commit-check.shellHook + \'\'\n'
                     '  define_dev_env_var FLOX_BIN "${REPO_ROOT}/cli/target/debug/flox";\n'
                     "'';\n"}
        for i in range(30):
            files["pkgs/aaa%02d/default.nix" % i] = "{}\n"
        repo, _ = self.repo(files=files)
        fp = qualify.check_fingerprint(repo)
        self.assertIn("shells/default/default.nix", fp["devshell"])
        self.assertLessEqual(len(fp["devshell"]), qualify.MAX_NIX_FILES)
        dev = qualify.check_devshell(repo, fp)
        self.assertTrue(any(h["file"] == "shells/default/default.nix"
                            for h in dev["shell_hooks"]))
        self.assertIn("FLOX_BIN", [c["name"] for c in dev["clobbers"]])

    def test_build_write_rules(self):
        repo, _ = self.repo(files={"README.md": "# r\n",
                                   ".gitignore": "/cli/target\n/build/*\n"})
        res = qualify.check_build_writes(repo)
        self.assertIn("/cli/target", res["out_dir_rules"])
        self.assertIn("/build/*", res["out_dir_rules"])


# --------------------------------------------------------------------------
# G2/G3/G3b/G4 — the dry-run rung
# --------------------------------------------------------------------------

class TestDryRun(QualifyCase):
    def _run(self, **kw):
        repo = self.suite_repo()
        suite = os.path.join(self.tmp, "suite.sh")
        ev = self.evdir()
        seed = self.seed(repo, suite, **kw.pop("seed_over", {}))
        return repo, qualify.qualify(repo, seed=seed, evdir=ev, **kw)

    def test_candidate_commands_never_see_kernel_env(self):
        # qualify ran candidate-repo argv with the full launch env (four
        # dict(os.environ) sites) — the gateway key and launch-config vars
        # reached prepare/verify/probes. Every ambient-env consumer now goes
        # through verify.candidate_env(); the recipe's OWN declared env
        # (seed["env"]) is trusted operator config and still wins.
        import unittest.mock as mock

        probe = ("#!/usr/bin/env python3\n"
                 "import os, sys\n"
                 "leaked = [k for k in ('SURPLUS_INTELLIGENCE_API_KEY',\n"
                 "                      'MERGE_MODE', 'FACTORY_NATIVE_CONFIG')\n"
                 "          if k in os.environ]\n"
                 "if leaked:\n"
                 "    sys.stderr.write('leaked: %s' % leaked)\n"
                 "    sys.exit(3)\n"
                 "if not os.environ.get('PATH'):\n"
                 "    sys.exit(4)\n"
                 "sys.exit(0)\n")
        repo = self.suite_repo()
        ev = self.evdir()
        seed = self.seed(repo, "suite.sh")
        seed["env"] = {"QUALIFY_PROBE_OK": "1"}  # recipe-declared env still passes through
        probe = probe + ("if not os.environ.get('QUALIFY_PROBE_OK'):\n"
                         "    sys.exit(5)\n")
        bad = _write(os.path.join(self.tmp, "probe.sh"), probe, 0o755)
        seed["verify"] = [{"argv": [bad], "timeout_s": 60, "expect_at_base": "red"}]
        kernel_env = {"SURPLUS_INTELLIGENCE_API_KEY": "x", "MERGE_MODE": "review",
                      "FACTORY_NATIVE_CONFIG": "{}", "QUALIFY_PROBE_OK": "1"}
        with mock.patch.dict(os.environ, kernel_env):
            r = qualify.qualify(repo, seed=seed, evdir=ev)
        receipt = r["verify"][0]["observed_at_base"]
        # exit 3 = the probe saw a kernel var (leak); 4 = PATH scrubbed; 5 =
        # the recipe-declared env did not survive. 3 must NOT happen.
        self.assertEqual(receipt["exit"], 0, receipt)

    def test_full_deterministic_pass_reaches_partial(self):
        repo, r = self._run()
        self.assertEqual(r["status"], "partial")
        for g in ("G1", "G2", "G3", "G4", "G6", "G7", "G8", "G11"):
            self.assertEqual(r["gate"][g], "pass", "%s: %s" % (g, r["gate"]))
        # no installed hooks: the A/B would be vacuous, so G9 skips with the reason
        self.assertEqual(r["gate"]["G9"], "skip(no-hooks)")
        # out of scope for a free run, and honestly recorded as such
        self.assertEqual(r["gate"]["G3b"], "skip(no-probe)")
        self.assertEqual(r["gate"]["G5"], "skip(no-netns)")
        self.assertEqual(r["gate"]["G10"], "skip(no-adapter)")
        self.assertEqual(r["gap"], "G3b,G5,G9,G10")
        self.assertEqual(r["verify"][0]["observed_at_base"]["count"], 3)
        self.assertEqual(r["verify"][0]["source"]["kind"], "dryrun")

    def test_g3_failure_marks_the_gates_it_blocks(self):
        """F6-lite: a skip caused by G3 failing carries the blocked-by marker,
        so a gate-table reader can tell it from an absent --netns/--probe."""
        # no `# tests` total at all: G3 cannot bind, so base_count is None
        red = _write(os.path.join(self.tmp, "red.sh"),
                     "#!/usr/bin/env bash\necho 'boom'\nexit 1\n", 0o755)
        _, r = self._run(probe=True, seed_over={
            "verify": [{"argv": [red], "timeout_s": 60, "expect_at_base": "exit0"}],
            "collection_probe": {"kind": "append_test", "target": "tests/probe.txt",
                                 "snippet": "# test probe-fail"}})
        self.assertEqual(r["gate"]["G3"], "fail")
        for g in ("G4", "G5", "G3b"):
            self.assertEqual(r["gate"][g], "skip(G3)", "%s: %s" % (g, r["gate"]))
        # with G3 green, a skip for an absent input says which input
        _, r2 = self._run()
        self.assertEqual(r2["gate"]["G3"], "pass")
        self.assertEqual(r2["gate"]["G5"], "skip(no-netns)")

    def test_absent_input_skips_carry_reason_markers(self):
        """F6: a skip caused by an absent operator input names the input, so
        the gate table never shows a bare `skip` for an unmeasured gate."""
        # no --netns, no --probe: the two absent-input skips in one pass
        _, r = self._run()
        self.assertEqual(r["gate"]["G5"], "skip(no-netns)")
        self.assertEqual(r["gate"]["G3b"], "skip(no-probe)")
        self.assertEqual(r["gap"], "G3b,G5,G9,G10")
        # --probe given but G3 not green: the blocked-by marker wins, the
        # probe never ran, and the recipe must not claim otherwise
        red = _write(os.path.join(self.tmp, "red.sh"),
                     "#!/usr/bin/env bash\necho 'boom'\nexit 1\n", 0o755)
        _, r2 = self._run(probe=True, seed_over={
            "verify": [{"argv": [red], "timeout_s": 60, "expect_at_base": "exit0"}],
            "collection_probe": {"kind": "append_test", "target": "tests/probe.txt",
                                 "snippet": "# test probe-fail"}})
        self.assertEqual(r2["gate"]["G3"], "fail")
        self.assertEqual(r2["gate"]["G3b"], "skip(G3)")
        # --no-hooks-ab only matters when hooks exist; with hooks present and
        # the flag off, the operator opt-out names itself. A hook-free clone
        # stays skip(no-hooks): the A/B is vacuous regardless of the flag.
        repo3 = self.suite_repo()
        self.assertEqual(qualify.dry_run(repo3, "HEAD", [], [], 0, "tap", 60,
                                         self.evdir("ev4"), {}, hooks_ab=False,
                                         hooks_present=True, hooks_poisoned=True)[0]["G9"],
                         "skip(no-hooks-ab)")
        self.assertEqual(qualify.dry_run(repo3, "HEAD", [], [], 0, "tap", 60,
                                         self.evdir("ev5"), {}, hooks_ab=True,
                                         hooks_present=False)[0]["G9"],
                         "skip(no-hooks)")

    def test_static_and_no_command_paths_tag_their_skips(self):
        """F6: the early-exit gate dicts get the same treatment."""
        repo = self.suite_repo()
        suite = os.path.join(self.tmp, "suite.sh")
        # --no-dry-run: nothing was measured because the operator said so
        r = qualify.qualify(repo, seed=self.seed(repo, suite),
                            evdir=self.evdir(), dry_run_enabled=False)
        self.assertEqual(r["gate"]["G1"], "skip(no-dry-run)")
        self.assertEqual(r["gate"]["G5"], "skip(no-netns)")
        self.assertEqual(r["gate"]["G3b"], "skip(no-probe)")
        self.assertEqual(r["gate"]["G9"], "skip(no-dry-run)")
        # no commands at all: there was nothing to measure with
        r2 = qualify.qualify(repo, seed=self.seed(repo, suite, prepare=[],
                                                  verify=[]),
                             evdir=self.evdir("ev2"))
        self.assertEqual(r2["gate"]["G1"], "skip(no-commands)")
        self.assertEqual(r2["gate"]["G5"], "skip(no-netns)")
        self.assertEqual(r2["gate"]["G3b"], "skip(no-probe)")
        self.assertEqual(r2["gate"]["G9"], "skip(no-hooks)")
        self.assertEqual(r2["gate"]["G10"], "skip(no-adapter)")

    def test_default_path_checks_the_proposed_quote_not_only_the_receipt(self):
        """F2: dry_run must not overwrite `source` with its receipt, or G7's
        quote half never runs on the default (dry-run) path."""
        repo, _ = self.repo(files={"README.md": "run: make test\n",
                                   "tests/probe.txt": "# test a\n"})
        suite = _write(os.path.join(self.tmp, "suite.sh"), SUITE_SH, 0o755)
        seed = self.seed(repo, suite)
        seed["prepare"][0]["source"] = {"kind": "quote", "file": "README.md",
                                        "line": 1, "text": "run: make test"}
        r = qualify.qualify(repo, seed=seed, evdir=self.evdir())
        self.assertEqual(r["gate"]["G7"], "pass", r["checks"]["provenance"])
        why = r["checks"]["provenance"]["entries"][0]["why"]
        self.assertIn("quote verified", why)
        self.assertIn("dryrun receipt exit=0 matches", why)
        entry = r["prepare"][0]
        self.assertEqual(entry["source"]["kind"], "quote")       # the claim survives
        self.assertTrue(os.path.isfile(entry["dryrun"]["evidence"]))  # and the receipt

    def test_default_path_rejects_a_fabricated_quote(self):
        """Q1/Q3: the argv executes (green, then failing) and the quote is
        still checked, so a fabricated citation fails G7 either way."""
        repo, _ = self.repo(files={"README.md": "run: make test\n",
                                   "tests/probe.txt": "# test a\n"})
        suite = _write(os.path.join(self.tmp, "suite.sh"), SUITE_SH, 0o755)
        for argv in (["true"], ["false"]):
            seed = self.seed(repo, suite)
            seed["prepare"][0] = {
                "argv": argv,
                "source": {"kind": "quote", "file": "README.md", "line": 1,
                           "text": "FABRICATED QUOTE THAT APPEARS NOWHERE"}}
            r = qualify.qualify(repo, seed=seed, evdir=self.evdir("ev-" + argv[0]))
            self.assertEqual(r["gate"]["G7"], "fail", argv)
            self.assertEqual(r["prepare"][0]["source"]["kind"], "quote", argv)
            self.assertIn("not byte-identical",
                          r["checks"]["provenance"]["entries"][0]["why"], argv)

    def test_seeded_dryrun_source_is_rebound_to_this_pass_receipt(self):
        """A seeded `dryrun` is re-measured; a seeded quote is not."""
        repo, _ = self.repo(files={"README.md": "run: make test\n",
                                   "tests/probe.txt": "# test a\n"})
        suite = _write(os.path.join(self.tmp, "suite.sh"), SUITE_SH, 0o755)
        seed = self.seed(repo, suite)
        seed["prepare"][0]["source"] = {"kind": "dryrun", "exit": 0,
                                        "evidence": "/gone/away.json"}
        ev = self.evdir()
        r = qualify.qualify(repo, seed=seed, evdir=ev)
        self.assertEqual(r["gate"]["G7"], "pass", r["checks"]["provenance"])
        self.assertEqual(r["prepare"][0]["source"]["evidence"],
                         r["prepare"][0]["dryrun"]["evidence"])
        self.assertTrue(r["prepare"][0]["source"]["evidence"].startswith(ev))

    def test_a_seeds_stale_gap_never_beats_the_measured_gates(self):
        """A re-run recomputes the gate table; the seed's recorded gap
        describes the seed's run, so it must not be copied into the output."""
        repo = self.suite_repo()
        suite = os.path.join(self.tmp, "suite.sh")
        seed = self.seed(repo, suite, gap="G2,G3,G4,G5")
        r = qualify.qualify(repo, seed=seed, evdir=self.evdir())
        self.assertEqual(r["status"], "partial")
        self.assertEqual(r["gap"], "G3b,G5,G9,G10")

    def test_poisoned_hook_escape_is_proven_by_an_ab_commit(self):
        repo, _ = self.repo(files={"README.md": "# r\n",
                                   ".gitignore": ".pre-commit-config.yaml\n",
                                   "tests/probe.txt": "# test a\n"})
        suite = _write(os.path.join(self.tmp, "suite.sh"), SUITE_SH, 0o755)
        # the hook mimics the flox shape: a relative --config it cannot find,
        # unless the escape is set
        _write(os.path.join(repo, ".git", "hooks", "commit-msg"),
               "#!/bin/sh\n# --config=.pre-commit-config.yaml\n"
               "[ -n \"$PRE_COMMIT_ALLOW_NO_CONFIG\" ] || exit 1\nexit 0\n", 0o755)
        seed = self.seed(repo, suite, env={"PRE_COMMIT_ALLOW_NO_CONFIG": "1"})
        r = qualify.qualify(repo, seed=seed, evdir=self.evdir())
        self.assertEqual(r["gate"]["G9"], "pass")
        # with no escape declared there is nothing to prove, and no commit is made
        r2 = qualify.qualify(repo, seed=self.seed(repo, suite), evdir=self.evdir("ev2"))
        self.assertEqual(r2["gate"]["G9"], "skip(no-escape)")

    def test_g9_fails_when_the_escape_does_not_work(self):
        repo, _ = self.repo(files={"README.md": "# r\n",
                                   ".gitignore": ".pre-commit-config.yaml\n",
                                   "tests/probe.txt": "# test a\n"})
        suite = _write(os.path.join(self.tmp, "suite.sh"), SUITE_SH, 0o755)
        _write(os.path.join(repo, ".git", "hooks", "commit-msg"),
               "#!/bin/sh\n# --config=.pre-commit-config.yaml\nexit 1\n", 0o755)
        seed = self.seed(repo, suite, env={"PRE_COMMIT_ALLOW_NO_CONFIG": "1"})
        r = qualify.qualify(repo, seed=seed, evdir=self.evdir())
        self.assertEqual(r["gate"]["G9"], "fail")
        self.assertEqual(r["status"], "partial")   # G9 is a partial-class gate

    def test_g9_records_a_commit_msg_linter_as_a_trap(self):
        """The devshell writes .pre-commit-config.yaml during prepare; the
        commit-msg hook then runs for real and the repo's linter sees the
        kernel's literal message. Informational, not gated — but it must show."""
        repo, _ = self.repo(files={"README.md": "# r\n",
                                   ".gitignore": ".pre-commit-config.yaml\n",
                                   "tests/probe.txt": "# test a\n"})
        suite = _write(os.path.join(self.tmp, "suite.sh"), SUITE_SH, 0o755)
        # prepare generates the config; the hook lints the message when it exists
        gen = _write(os.path.join(self.tmp, "gen.sh"),
                     "#!/bin/sh\nprintf '%s\\n' 'linter' > .pre-commit-config.yaml\n", 0o755)
        _write(os.path.join(repo, ".git", "hooks", "commit-msg"),
               "#!/bin/sh\n# --config=.pre-commit-config.yaml\n"
               "if [ ! -f .pre-commit-config.yaml ]; then\n"
               "  [ -n \"$PRE_COMMIT_ALLOW_NO_CONFIG\" ] && exit 0\n"
               "  echo 'No .pre-commit-config.yaml file was found' >&2\n"
               "  exit 1\n"
               "fi\n"
               "grep -qE '^(feat|fix):' \"$1\" && exit 0\n"
               "echo 'commit validation: failed!' >&2\nexit 14\n", 0o755)
        seed = self.seed(repo, suite, env={"PRE_COMMIT_ALLOW_NO_CONFIG": "1"},
                         prepare=[{"argv": [gen]}])
        r = qualify.qualify(repo, seed=seed, evdir=self.evdir())
        self.assertEqual(r["gate"]["G9"], "pass")     # the escape still does its job
        finding = r["checks"]["hooks"]["commit_msg_linter"]
        self.assertEqual(finding["exit"], 1)          # git normalizes hook failures
        self.assertIn("commit validation: failed!", finding["stderr_tail"])
        self.assertEqual(finding["kernel_message"], "Implement issue N")
        self.assertIn("commit-msg-linter", [t["id"] for t in r["traps"]])

    def test_collection_probe_makes_the_count_live(self):
        repo = self.suite_repo()
        suite = os.path.join(self.tmp, "suite.sh")
        seed = self.seed(repo, suite, collection_probe={
            "kind": "append_test", "target": "tests/probe.txt",
            "snippet": "# test probe-fail"})
        r = qualify.qualify(repo, seed=seed, evdir=self.evdir(), probe=True)
        self.assertEqual(r["gate"]["G3b"], "pass")
        result = r["collection_probe"]["result"]
        self.assertEqual((result["exit"], result["count"], result["base_count"]),
                         (1, 4, 3))
        self.assertEqual(result["count_semantics"], "tests-run")
        self.assertTrue(result["probe_visible"])
        # the probe ran in a throwaway worktree and the repo is untouched
        self.assertEqual(_git(repo, "status", "--porcelain"), "")
        self.assertEqual(len(_git(repo, "worktree", "list").splitlines()), 1)

    def test_collection_probe_accepts_the_proposals_file_key(self):
        """The agent's own name for the probe file (`file`) is accepted, so a
        recorded recipe cannot crash G3b — reachable only once G3 binds."""
        repo = self.suite_repo()
        suite = os.path.join(self.tmp, "suite.sh")
        seed = self.seed(repo, suite, collection_probe={
            "kind": "append_test", "file": "tests/probe.txt",
            "snippet": "# test probe-fail"})
        r = qualify.qualify(repo, seed=seed, evdir=self.evdir(), probe=True)
        self.assertEqual(r["gate"]["G3b"], "pass")
        self.assertEqual(r["collection_probe"]["result"]["count"], 4)

    def test_malformed_collection_probe_skips_instead_of_crashing(self):
        repo = self.suite_repo()
        suite = os.path.join(self.tmp, "suite.sh")
        seed = self.seed(repo, suite, collection_probe={"kind": "append_test"})
        r = qualify.qualify(repo, seed=seed, evdir=self.evdir(), probe=True)
        self.assertEqual(r["gate"]["G3b"], "skip(bad-probe)")

    def test_collection_probe_accepts_a_passed_only_total(self):
        """The flox shape: the adapter's TAP total counts PASSED tests, so an
        injected failure leaves the total at N0. Liveness is then proven by the
        injected test being visible in the runner's own output."""
        repo, _ = self.repo(files={"README.md": "# r\n", "tests/probe.txt": "# test a\n"})
        suite = _write(os.path.join(self.tmp, "passed_only.sh"), """#!/usr/bin/env bash
# passed-only total: the failing test does not raise the count
f="tests/probe.txt"
n=$(grep -c '^# test' "$f")
if grep -q '^# test probe-fail' "$f"; then
  echo "not ok - nightshift_probe_collection ran and failed"
  echo "# tests $((n - 1))"
  exit 101
fi
echo "# tests $n"
exit 0
""", 0o755)
        seed = self.seed(repo, suite, collection_probe={
            "kind": "append_test", "target": "tests/probe.txt",
            "snippet": "# test probe-fail"})
        r = qualify.qualify(repo, seed=seed, evdir=self.evdir(), probe=True)
        result = r["collection_probe"]["result"]
        self.assertEqual(r["gate"]["G3b"], "pass")
        self.assertEqual(result["count_semantics"], "passed-only")
        self.assertEqual(result["probe_tokens_seen"], ["probe"])

    def test_collection_probe_rejects_a_suite_that_ignores_the_injected_test(self):
        """Red for an unrelated reason, with no trace of the injected test, is
        not liveness."""
        repo, _ = self.repo(files={"README.md": "# r\n", "tests/probe.txt": "# test a\n"})
        suite = _write(os.path.join(self.tmp, "always_red.sh"),
                       "#!/usr/bin/env bash\necho '# tests 1'\nexit 1\n", 0o755)
        seed = self.seed(repo, suite, collection_probe={
            "kind": "append_test", "target": "tests/probe.txt",
            "snippet": "# test probe-fail"})
        r = qualify.qualify(repo, seed=seed, evdir=self.evdir(), probe=True)
        self.assertEqual(r["gate"]["G3b"], "fail")
        self.assertFalse(r["collection_probe"]["result"]["probe_visible"])

    def test_red_entry_that_exits_zero_fails_g2(self):
        repo, _ = self.repo(files={"README.md": "# r\n"})
        always_green = _write(os.path.join(self.tmp, "green.sh"), "#!/bin/sh\nexit 0\n", 0o755)
        seed = self.seed(repo, always_green, verify=[
            {"argv": [always_green], "timeout_s": 60, "expect_at_base": "red",
             "source": {"kind": "operator", "note": "should be red, is not"}}])
        r = qualify.qualify(repo, seed=seed, evdir=self.evdir())
        self.assertEqual(r["gate"]["G2"], "fail")
        self.assertEqual(r["status"], "no-go")

    def test_bad_expect_at_base_is_rejected(self):
        repo, _ = self.repo()
        green = _write(os.path.join(self.tmp, "g.sh"), "#!/bin/sh\nexit 0\n", 0o755)
        seed = self.seed(repo, green, verify=[{"argv": [green],
                                               "expect_at_base": "maybe"}])
        r = qualify.qualify(repo, seed=seed, evdir=self.evdir())
        self.assertEqual(r["gate"]["G2"], "fail")

    def test_suite_without_authoritative_total_fails_g3(self):
        repo, _ = self.repo(files={"README.md": "# r\n"})
        quiet = _write(os.path.join(self.tmp, "quiet.sh"), "#!/bin/sh\necho ok\nexit 0\n", 0o755)
        seed = self.seed(repo, quiet)
        r = qualify.qualify(repo, seed=seed, evdir=self.evdir())
        self.assertEqual(r["gate"]["G3"], "fail")
        self.assertEqual(r["status"], "no-go")

    def test_verify_runs_in_a_throwaway_worktree(self):
        repo = self.suite_repo()
        suite = os.path.join(self.tmp, "suite.sh")
        r = qualify.qualify(repo, seed=self.seed(repo, suite), evdir=self.evdir())
        self.assertEqual(r["status"], "partial")
        self.assertEqual(_git(repo, "status", "--porcelain"), "")
        self.assertEqual(len(_git(repo, "worktree", "list").splitlines()), 1)
        self.assertTrue(os.path.isdir(r["evidence_root"]))


# --------------------------------------------------------------------------
# G8/G10 — config and adapter gates
# --------------------------------------------------------------------------

class TestConfigGates(QualifyCase):
    def test_emitted_config_parses_under_the_kernels_own_guards(self):
        repo = self.suite_repo()
        suite = os.path.join(self.tmp, "suite.sh")
        r = qualify.qualify(repo, seed=self.seed(repo, suite), evdir=self.evdir())
        self.assertTrue(r["checks"]["config_parse"]["ok"])
        self.assertEqual(r["gate"]["G8"], "pass")

    def test_suite_must_be_designated_exactly_once(self):
        entry = {"argv": ["x"]}
        with self.assertRaises(ValueError):
            qualify.build_config([], [entry, dict(entry)], 0, "tap", 600, "bug", "review")

    def test_config_key_order_matches_the_launch_envs(self):
        cfg = qualify.build_config([{"argv": ["a"]}], [{"argv": ["b"]}], 0, "tap", 600,
                                   "bug", "review")
        self.assertEqual(list(cfg), ["prepare", "verify", "suite", "suite_runner",
                                     "suite_timeout_s", "task_kind", "merge_mode"])
        self.assertEqual(json.dumps(cfg, separators=(",", ":")),
                         '{"prepare":[["a"]],"verify":[["b"]],"suite":["b"],'
                         '"suite_runner":"tap","suite_timeout_s":600,"task_kind":"bug",'
                         '"merge_mode":"review"}')

    def test_adapter_gate_is_skipped_without_an_adapter_or_probe(self):
        self.assertEqual(qualify._adapter_gate({}), "skip(no-adapter)")
        self.assertEqual(qualify._adapter_gate({"adapter": {"self_test": "pass"}}), "pass")
        self.assertEqual(qualify._adapter_gate({"adapter": {"path": "/nope/x.sh"}}),
                         "skip(no-adapter)")

    def test_adapter_gate_runs_the_zero_tests_probe(self):
        # an adapter that greens on zero tests is the vacuous-green hole itself
        ev = self.evdir()
        bad = _write(os.path.join(self.tmp, "bad.sh"),
                     "#!/bin/sh\necho '# tests 0'\nexit 0\n", 0o755)
        good = _write(os.path.join(self.tmp, "good.sh"),
                      "#!/bin/sh\necho '# tests 0'\nexit 1\n", 0o755)
        self.assertEqual(qualify._adapter_gate({"adapter": {"path": bad}}, ev), "fail")
        self.assertEqual(qualify._adapter_gate({"adapter": {"path": good}}, ev), "pass")
        self.assertEqual(qualify._adapter_gate({"adapter": {"path": good}}, None),
                         "skip(no-adapter)")
        self.assertEqual(
            qualify._adapter_gate({"adapter": {"path": good, "zero_tests_probe": False}}, ev),
            "skip(operator)")

    def test_emit_env_carries_repo_keys_and_comments_task_keys(self):
        repo = self.suite_repo()
        suite = os.path.join(self.tmp, "suite.sh")
        path = os.path.join(self.tmp, "recipe.json")
        r = qualify.qualify(repo, seed=self.seed(repo, suite, env={"A": "1"}),
                            evdir=self.evdir(), out=path)
        text = qualify.emit_env(r, path)
        self.assertIn("export FACTORY_NATIVE_CONFIG='", text)
        self.assertIn("export PRODUCT_REPO=%s" % repo, text)
        self.assertIn("export GITHUB_REPO=example/repo", text)
        self.assertIn("export DEPLOY_MODE=none", text)
        self.assertIn("export A=1", text)
        # F6: the gate table (with its reason-tagged skips) flows into the
        # env render as comments, so the launch env states what was measured
        self.assertIn("# gate G5=skip(no-netns)", text)
        # the header hash is the recipe file's own, re-derivable with sha256sum
        self.assertIn("recipe sha256: %s" % qualify._sha256(path), text)
        for key in ("FACTORY_TASK_FILE", "CODE_PATHS", "FACTORY_NEW_FILES", "SCENARIOS_DIR"):
            self.assertIn("# export %s" % key, text)

    def test_emit_env_without_a_config_does_not_emit_null(self):
        """A no-go recipe has no commands, so it must not export a config that
        would make settings.py raise at import."""
        r = {"repo": {"origin": "x/y", "base": "a" * 40, "path": "/tmp/r"},
             "config": None, "deploy_mode": "none", "env": {}, "status": "no-go"}
        text = qualify.emit_env(r)
        self.assertNotIn("export FACTORY_NATIVE_CONFIG", text)
        self.assertIn("# FACTORY_NATIVE_CONFIG not emitted", text)

    def test_status_from_gate_map(self):
        ok = {g: "pass" for g in qualify.NOGO_GATES + qualify.PARTIAL_GATES}
        self.assertEqual(qualify.compute_status(ok), "qualified")
        ok["G5"] = "skip(no-netns)"
        self.assertEqual(qualify.compute_status(ok), "partial")
        ok["G3"] = "fail"
        self.assertEqual(qualify.compute_status(ok), "no-go")


# --------------------------------------------------------------------------
# the load-bearing one: no model call on any deterministic or failure path
# --------------------------------------------------------------------------

class TestNoModelCalls(QualifyCase):
    def _assert_silent(self, **kw):
        with mock.patch.object(qualify.agent, "chat",
                               side_effect=AssertionError("model call made")):
            repo = self.suite_repo()
            suite = os.path.join(self.tmp, "suite.sh")
            seed = self.seed(repo, suite, **kw)
            return qualify.qualify(repo, seed=seed, evdir=self.evdir())

    def test_deterministic_pass_makes_no_model_call(self):
        r = self._assert_silent()
        self.assertEqual(r["status"], "partial")
        self.assertEqual(r["usage"], {})

    def test_no_commands_path_makes_no_model_call(self):
        r = self._assert_silent(prepare=[], verify=[])
        self.assertEqual(r["status"], "no-go")
        self.assertEqual(r["gate"]["G1"], "skip(no-commands)")
        self.assertIn("no commands proposed", r["gap"])

    def test_failing_dry_run_makes_no_model_call(self):
        r = self._assert_silent(prepare=[{"argv": ["false"]}])
        self.assertEqual(r["gate"]["G1"], "fail")
        self.assertEqual(r["status"], "no-go")


# --------------------------------------------------------------------------
# the agent layer: proposal only, and parse-tolerant
# --------------------------------------------------------------------------

class TestProposal(unittest.TestCase):
    def test_parse_fenced_json(self):
        self.assertEqual(qualify.parse_proposal('```json\n{"abstain": true}\n```'),
                         {"abstain": True})

    def test_parse_bare_json_with_prose(self):
        self.assertEqual(qualify.parse_proposal('here: {"a": 1} done'), {"a": 1})

    def test_unparseable_proposal_abstains(self):
        self.assertEqual(qualify.parse_proposal("no json here"),
                         {"abstain": True, "gap": "proposal was not parseable JSON"})

    def test_seed_wins_over_proposal_on_suite_and_env(self):
        # the model may propose; the operator's seed is authoritative where it
        # speaks, because a proposal is only ever bound by a dry-run
        repo = tempfile.mkdtemp(prefix="qualify-proposal-")
        self.addCleanup(shutil.rmtree, repo, ignore_errors=True)
        _make_repo(repo)
        with mock.patch.object(qualify.agent, "chat", return_value={
                "content": json.dumps({"suite_runner": "pytest",
                                       "env": {"FROM_MODEL": "1"}}), "usage": {}}):
            r = qualify.qualify(repo, seed={"suite_runner": "tap", "env": {"FROM_SEED": "1"},
                                            "prepare": [], "verify": []},
                                use_agent=True, evdir=os.path.join(repo, "ev"))
        self.assertEqual(r["suite_runner"], "tap")
        self.assertEqual(r["env"], {"FROM_SEED": "1"})
        self.assertEqual(r["status"], "no-go")  # nothing was dry-run


class TestCLI(QualifyCase):
    """main() is the only path an operator drives; exercise it without a build."""

    def main(self, argv):
        """main() with stdout captured, so the suite output stays readable."""
        with contextlib.redirect_stdout(io.StringIO()):
            return qualify.main(argv)

    def _seed_file(self, repo, suite):
        path = os.path.join(self.tmp, "seed.json")
        with open(path, "w") as f:
            json.dump(self.seed(repo, suite), f)
        return path

    def test_static_run_writes_a_recipe_and_reports_status(self):
        repo = self.suite_repo()
        suite = os.path.join(self.tmp, "suite.sh")
        out = os.path.join(self.tmp, "recipes", "r.json")
        rc = self.main([repo, "--seed", self._seed_file(repo, suite),
                           "--no-dry-run", "--out", out])
        recipe = _load(out)
        self.assertEqual(recipe["schema"], "nightshift.recipe/1")
        self.assertEqual(recipe["gate"]["G1"], "skip(no-dry-run)")  # no build was run
        self.assertEqual(recipe["status"], "no-go")        # gates unproven
        self.assertEqual(rc, 1)                            # no-go exits non-zero

    def test_static_run_with_quoted_provenance_passes_g7(self):
        repo, _ = self.repo(files={"README.md": "run: make test\n",
                                   "tests/probe.txt": "# test a\n"})
        suite = _write(os.path.join(self.tmp, "suite.sh"), SUITE_SH, 0o755)
        seed = self.seed(repo, suite)
        for entry in seed["prepare"] + seed["verify"]:
            entry["source"] = {"kind": "quote", "file": "README.md", "line": 1,
                               "text": "run: make test"}
        path = os.path.join(self.tmp, "seed.json")
        with open(path, "w") as f:
            json.dump(seed, f)
        out = os.path.join(self.tmp, "recipes", "r.json")
        self.main([repo, "--seed", path, "--no-dry-run", "--out", out])
        recipe = _load(out)
        self.assertEqual(recipe["gate"]["G7"], "pass")
        self.assertTrue(recipe["checks"]["provenance"]["ok"])

    def test_static_run_rejects_a_fabricated_quote(self):
        repo, _ = self.repo(files={"README.md": "run: make test\n"})
        suite = _write(os.path.join(self.tmp, "suite.sh"), SUITE_SH, 0o755)
        seed = self.seed(repo, suite)
        seed["verify"][0]["source"] = {"kind": "quote", "file": "README.md",
                                       "line": 1, "text": "run: ninja build"}
        path = os.path.join(self.tmp, "seed.json")
        with open(path, "w") as f:
            json.dump(seed, f)
        out = os.path.join(self.tmp, "recipes", "r.json")
        self.main([repo, "--seed", path, "--no-dry-run", "--out", out])
        self.assertEqual(_load(out)["gate"]["G7"], "fail")

    def test_emit_env_and_render_read_an_existing_recipe(self):
        repo = self.suite_repo()
        suite = os.path.join(self.tmp, "suite.sh")
        out = os.path.join(self.tmp, "recipes", "r.json")
        self.main([repo, "--seed", self._seed_file(repo, suite),
                      "--no-dry-run", "--out", out])
        env_out = os.path.join(self.tmp, "env.sh")
        self.main([repo, "--out", out, "--emit-env", env_out])
        self.main([repo, "--out", out, "--render"])
        self.assertIn("export FACTORY_NATIVE_CONFIG=", _read_text(env_out))

    def test_no_go_exits_nonzero(self):
        repo, _ = self.repo()
        empty = os.path.join(self.tmp, "empty.json")
        with open(empty, "w") as f:
            json.dump({"prepare": [], "verify": []}, f)
        self.assertEqual(self.main([repo, "--seed", empty, "--no-dry-run",
                                       "--out", os.path.join(self.tmp, "r.json")]), 1)

    def test_in_repo_mirror_is_byte_identical(self):
        repo = self.suite_repo()
        suite = os.path.join(self.tmp, "suite.sh")
        out = os.path.join(self.tmp, "recipes", "r.json")
        self.main([repo, "--seed", self._seed_file(repo, suite), "--no-dry-run",
                      "--out", out, "--in-repo"])
        mirror = os.path.join(repo, ".nightshift", "recipe.json")
        self.assertEqual(_bytes(out), _bytes(mirror))

    def test_repo_argument_is_required(self):
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                self.main([])


class TestGateEvidence(QualifyCase):
    """Every gate that runs a command must leave a receipt. A gate whose
    evidence cannot be re-inspected is not evidence."""

    def test_every_executed_gate_leaves_a_receipt(self):
        repo = self.suite_repo()
        suite = os.path.join(self.tmp, "suite.sh")
        seed = self.seed(repo, suite, collection_probe={
            "kind": "append_test", "target": "tests/probe.txt",
            "snippet": "# test probe-fail"})
        ev = self.evdir()
        qualify.qualify(repo, seed=seed, evdir=ev, probe=True, netns=True)
        for tag in ("prepare-0", "verify-0", "suite-det", "suite-netns", "suite-probe"):
            path = os.path.join(ev, tag + ".json")
            self.assertTrue(os.path.isfile(path), "no receipt for %s" % tag)
            with open(path) as f:
                receipt = json.load(f)
            self.assertIn("exit", receipt)
            self.assertIn("duration_s", receipt)

    def test_netns_receipt_records_the_wrapped_argv(self):
        repo = self.suite_repo()
        suite = os.path.join(self.tmp, "suite.sh")
        ev = self.evdir()
        qualify.qualify(repo, seed=self.seed(repo, suite), evdir=ev, netns=True)
        with open(os.path.join(ev, "suite-netns.json")) as f:
            receipt = json.load(f)
        self.assertEqual(receipt["argv"][:4], ["unshare", "-rn", "bash", "-c"])
        self.assertTrue(receipt["argv_wrapped"][-1].endswith("suite.sh"))
        self.assertTrue(receipt["lo_required"])


if __name__ == "__main__":
    unittest.main()
