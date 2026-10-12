"""F9 base-pinning guard at the `worktree_for` level (issue-9803 a1): what
the lap runs must be the DECLARED base.

The 9803 a1 fault: the lap clone's origin was the clone itself (bank recipe),
so `fetch origin main` re-resolved origin/main from the local main branch —
which already contained the gold fix — and the checkout silently advanced past
the pinned defect base. The implementer "resolved" an already-fixed base and
the lap greened vacuously (awaiting-review), caught only by operator audit.

Real git scenarios, no mocks of git itself, no network. Companion coverage at
the run level: an OperationalFault from worktree_for propagates out of run()
and would be classified operational via the except-clause in run() (gate
name carried on the exception)."""

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
    return r.stdout.strip()


class BasePinScenario(unittest.TestCase):
    """Upstream repo (branch main) + clone; the clone is PRODUCT_REPO."""

    ISSUE = 9803

    def setUp(self):
        self.base = tempfile.mkdtemp()
        up = os.path.join(self.base, "upstream")
        os.mkdir(up)
        git(up, "init", "-q", "-b", "main")
        with open(os.path.join(up, "app.py"), "w") as f:
            f.write("x = 1\n")
        git(up, "add", "-A")
        git(up, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "init")
        self.old_sha = git(up, "rev-parse", "HEAD")
        with open(os.path.join(up, "app.py"), "w") as f:
            f.write("x = 2\n")
        git(up, "add", "-A")
        git(up, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "gold fix")
        self.new_sha = git(up, "rev-parse", "HEAD")
        self.repo = os.path.join(self.base, "repo")
        git(self.base, "clone", "-q", up, self.repo)
        self._patches = [
            unittest.mock.patch.object(lap, "PRODUCT_REPO", self.repo),
            unittest.mock.patch.object(lap, "BASE_REF", "origin/main"),
        ]
        for _p in self._patches:
            _p.start()
            self.addCleanup(_p.stop)
        self.path = os.path.join(self.repo, ".factory", "worktrees",
                                 "agent-issue-%d" % self.ISSUE)

    def pin_old(self):
        """The 9803 compensation: pin the base to the pre-fix parent."""
        git(self.repo, "update-ref", "refs/remotes/origin/main", self.old_sha)

    def worktree_head(self):
        return git(self.path, "rev-parse", "HEAD")


class TestBasePinHappy(BasePinScenario):
    """(1) declared base == checkout: passes through unchanged."""

    def test_base_matches_checkout_passes(self):
        self.assertEqual(lap.worktree_for(self.ISSUE), self.path)
        self.assertEqual(self.worktree_head(), self.new_sha)
        self.assertEqual(self.worktree_head(),
                         git(self.repo, "rev-parse", "origin/main"))


class TestBasePinMismatch(BasePinScenario):
    """(2) declared base != checkout: operational failure naming both shas
    and the gate."""

    def test_fetch_advancing_base_ref_fails_operational(self):
        # the local main branch sits at the fix (a real clone of upstream);
        # `fetch origin main` drags origin/main there while the pin names
        # the old rev — the 9803 a1 shape in miniature
        self.pin_old()
        with self.assertRaises(lap.BasePinError) as cm:
            lap.worktree_for(self.ISSUE)
        self.assertIn("declared base %s" % self.old_sha, str(cm.exception))
        self.assertIn("checkout %s" % self.new_sha, str(cm.exception))
        self.assertIn("vacuous-already-fixed risk", str(cm.exception))
        self.assertEqual(cm.exception.gate, "base-pin")

    def test_run_classifies_mismatch_as_operational_gate_base_pin(self):
        # run-level contract: the guard's exception reaches the OperationalFault
        # handler, so the lap ends failure/gate=base-pin — never a scored pass.
        sys.path.insert(0, os.path.dirname(__file__))
        from test_lap_run import FakeLapEnv
        with FakeLapEnv("none") as env, \
             unittest.mock.patch.object(
                 lap, "worktree_for",
                 side_effect=lap.BasePinError(
                     "declared base %s != checkout %s after fetch "
                     "(vacuous-already-fixed risk)" % (self.old_sha, self.new_sha))):
            lap.run(FakeLapEnv.ISSUE)
        with open(os.path.join(env.base, "lap-result.json")) as f:
            result = json.load(f)
        self.assertEqual(result["outcome"], "failure")
        self.assertEqual(result["gate"], "base-pin")
        self.assertIn("declared base", result["error"])
        self.assertIn("vacuous-already-fixed risk", result["error"])


class TestSelfCloneFetchGuard(BasePinScenario):
    """(3) self-referential origin (bank recipe): fetching nothing keeps the
    checkout ref from being re-resolved past the pin. F10: a self-clone whose
    main and origin/main DIVERGE has an ambiguous pin — BasePinError. So the
    scenario pins BOTH refs to the defect base (the 9803-a2 operator re-pin),
    proving the fetch-skip path leaves the checkout at the pin."""

    def test_self_clone_fetch_skipped_keeps_pin(self):
        git(self.repo, "remote", "set-url", "origin", ".")
        self.pin_old()
        # both refs at the pin (9803-a2 shape): the fetch-skip must leave the
        # worktree at the declared base even though a divergent local main
        # would drag origin/main to the fix if the fetch ran
        git(self.repo, "update-ref", "refs/heads/main", self.old_sha)
        self.assertEqual(git(self.repo, "rev-parse", "refs/heads/main"),
                         self.old_sha)
        lap.worktree_for(self.ISSUE)
        self.assertEqual(self.worktree_head(), self.old_sha)
        self.assertEqual(git(self.repo, "rev-parse", "origin/main"), self.old_sha)

    def test_self_clone_divergent_refs_fail_closed(self):
        # F10: the negctl §3 taint left main=60cdc64 (fix) while
        # origin/main=f80af6a (pin) — a self-clone with divergent refs has an
        # ambiguous pin and must fail closed, never silently pick one
        git(self.repo, "remote", "set-url", "origin", ".")
        self.pin_old()
        # main stays at the fix (clone default), origin/main pinned old:
        # refs diverge
        self.assertNotEqual(git(self.repo, "rev-parse", "refs/heads/main"),
                            git(self.repo, "rev-parse",
                                "refs/remotes/origin/main"))
        with self.assertRaises(lap.BasePinError) as cm:
            lap.worktree_for(self.ISSUE)
        self.assertIn("self-clone pin ambiguous", str(cm.exception))
        self.assertIn(self.new_sha, str(cm.exception))
        self.assertIn(self.old_sha, str(cm.exception))

    def test_self_clone_without_local_main_still_works(self):
        # consistency assert fires only when BOTH refs exist; a repo with no
        # local main branch (detached checkout) keeps the F9 behavior
        git(self.repo, "remote", "set-url", "origin", ".")
        self.pin_old()
        git(self.repo, "update-ref", "-d", "refs/heads/main")
        lap.worktree_for(self.ISSUE)
        self.assertEqual(self.worktree_head(), self.old_sha)

class TestShaPinnedBase(BasePinScenario):
    """F10 (a): FACTORY_BASE_SHA is an immutable pin — honored even when
    origin/main has moved elsewhere."""

    def setUp(self):
        super().setUp()
        _p = unittest.mock.patch.object(lap, "BASE_SHA", self.old_sha)
        _p.start()
        self.addCleanup(_p.stop)

    def test_sha_pin_honored_when_origin_main_moved(self):
        # origin/main pre-tainted to the fix (negctl §3 shape): the sha pin
        # still lands the worktree on the declared defect base
        git(self.repo, "update-ref", "refs/remotes/origin/main", self.new_sha)
        lap.worktree_for(self.ISSUE)
        self.assertEqual(self.worktree_head(), self.old_sha)

    def test_ref_mismatch_is_not_an_error(self):
        # BASE_REF resolves elsewhere but the checkout equals the sha: the
        # sha wins, no exception (the ref is mutable, the pin is not)
        git(self.repo, "update-ref", "refs/remotes/origin/main", self.new_sha)
        lap.worktree_for(self.ISSUE)  # BASE_REF=origin/main -> new_sha, sha wins
        self.assertEqual(self.worktree_head(), self.old_sha)

class TestOracleRedAtBase(BasePinScenario):
    """F10 (b)-(d): the red-at-base pre-dispatch gate."""

    def setUp(self):
        super().setUp()
        _p = unittest.mock.patch.object(lap, "BASE_SHA", self.old_sha)
        _p.start()
        self.addCleanup(_p.stop)
        self.oracle = os.path.join(self.base, "oracle.sh")

    def set_oracle(self, value):
        lap.ORACLE = value
        self.addCleanup(setattr, lap, "ORACLE", "")
        return value

    def write_oracle(self, body):
        with open(self.oracle, "w") as f:
            f.write(body)
        os.chmod(self.oracle, 0o755)
        return self.oracle

    def test_oracle_green_at_base_fails_vacuous(self):
        # a GREEN oracle at the base = the base already contains the fix =
        # vacuous instance; must fail closed before any paid call
        self.set_oracle(self.write_oracle("#!/bin/sh\nexit 0\n"))
        with self.assertRaises(lap.BasePinError) as cm:
            lap.worktree_for(self.ISSUE)
        self.assertIn("oracle GREEN at declared base", str(cm.exception))
        self.assertIn("vacuous", str(cm.exception))
        self.assertEqual(cm.exception.gate, "base-pin")

    def test_oracle_red_at_base_proceeds_unchanged(self):
        # RED (exit 1) with the NS-ORACLE-RED sentinel on stdout is the
        # expected state; the worktree is left untouched at the base checkout
        self.set_oracle(self.write_oracle(
            "#!/bin/sh\necho %s\n[ \"$(cat app.py)\" = \"x = 1\\n\" ]"
            " || exit 1\n" % lap.RED_SENTINEL))
        path = lap.worktree_for(self.ISSUE)
        self.assertEqual(path, self.path)
        self.assertEqual(self.worktree_head(), self.old_sha)
        with open(os.path.join(self.path, "app.py")) as f:
            self.assertEqual(f.read(), "x = 1\n")

    def test_oracle_red_without_sentinel_fails_closed(self):
        # F10c: the bank oracles are `#!/bin/sh ... exec python check_*.py`
        # wrappers whose checkers import the product at top level outside any
        # try — a broken venv / missing module exits 1 as a harness crash.
        # Exit 1 WITHOUT the NS-ORACLE-RED sentinel on stdout must never read
        # as verified RED.
        self.set_oracle(self.write_oracle("#!/bin/sh\nexit 1\n"))
        with self.assertRaises(lap.BasePinError) as cm:
            lap.worktree_for(self.ISSUE)
        self.assertIn(lap.RED_SENTINEL, str(cm.exception))
        self.assertIn("harness crash", str(cm.exception))
        self.assertIn("verified RED", str(cm.exception))
        self.assertEqual(cm.exception.gate, "base-pin")

    def test_oracle_red_sentinel_on_stderr_not_stdout_fails_closed(self):
        # F10c: the sentinel must be on STDOUT — a stderr-only match (or any
        # other channel confusion) is not the contract and fails closed
        self.set_oracle(self.write_oracle(
            "#!/bin/sh\necho %s >&2\nexit 1\n" % lap.RED_SENTINEL))
        with self.assertRaises(lap.BasePinError) as cm:
            lap.worktree_for(self.ISSUE)
        self.assertIn("without the %s sentinel" % lap.RED_SENTINEL,
                      str(cm.exception))

    def test_oracle_harness_error_fails_closed(self):
        # F10b: exit 2 is the oracle-contract harness-error code; a broken
        # oracle must fail closed, never read as verified RED
        self.set_oracle(self.write_oracle("#!/bin/sh\nexit 2\n"))
        with self.assertRaises(lap.BasePinError) as cm:
            lap.worktree_for(self.ISSUE)
        self.assertIn("harness error fails closed", str(cm.exception))
        self.assertIn("exited 2", str(cm.exception))
        self.assertEqual(cm.exception.gate, "base-pin")

    def test_oracle_command_not_found_fails_closed(self):
        # F10b: 127 (command-not-found) — the oracle crashed, not RED
        self.set_oracle(self.write_oracle("#!/bin/sh\nexit 127\n"))
        with self.assertRaises(lap.BasePinError) as cm:
            lap.worktree_for(self.ISSUE)
        self.assertIn("exited 127", str(cm.exception))
        self.assertIn("harness error fails closed", str(cm.exception))

    def test_oracle_sees_scrubbed_env(self):
        # the oracle runs with candidate_env(): kernel-config variables are
        # scrubbed, and cwd is the base worktree
        self.set_oracle(self.write_oracle(
            '#!/bin/sh\necho "$PWD|$PRODUCT_REPO|$F10_PROBE" > envdump.txt\n'
            'echo %s\nexit 1\n' % lap.RED_SENTINEL))
        os.environ["PRODUCT_REPO"] = "/leaked/product/repo"
        self.addCleanup(os.environ.pop, "PRODUCT_REPO", None)
        os.environ["F10_PROBE"] = "passes-through"
        self.addCleanup(os.environ.pop, "F10_PROBE", None)
        lap.worktree_for(self.ISSUE)
        with open(os.path.join(self.path, "envdump.txt")) as f:
            cwd, product, probe = f.read().strip().split("|")
        self.assertEqual(cwd, self.path)
        self.assertEqual(product, "")  # kernel-config scrubbed
        self.assertEqual(probe, "passes-through")  # non-kernel env passes

    def test_oracle_path_set_but_missing_fails_closed(self):
        self.set_oracle(os.path.join(self.base, "does-not-exist.sh"))
        with self.assertRaises(lap.BasePinError) as cm:
            lap.worktree_for(self.ISSUE)
        self.assertIn("not an executable file", str(cm.exception))
        self.assertEqual(cm.exception.gate, "base-pin")

    def test_oracle_set_but_unexecutable_fails_closed(self):
        with open(self.oracle, "w") as f:
            f.write("#!/bin/sh\nexit 0\n")
        os.chmod(self.oracle, 0o644)  # exists but not executable
        self.set_oracle(self.oracle)
        with self.assertRaises(lap.BasePinError):
            lap.worktree_for(self.ISSUE)

class TestUnsetF10Compat(BasePinScenario):
    """F10 (f): FACTORY_ORACLE unset + FACTORY_BASE_SHA unset -> byte-identical
    F9 behavior (defaults; happy path unchanged)."""

    def test_unset_sha_and_oracle_matches_f9_happy_path(self):
        self.assertEqual(lap.BASE_SHA, "")
        self.assertEqual(lap.ORACLE, "")
        lap.worktree_for(self.ISSUE)
        self.assertEqual(self.worktree_head(), self.new_sha)
        self.assertEqual(self.worktree_head(),
                         git(self.repo, "rev-parse", "origin/main"))

if __name__ == "__main__":
    unittest.main()
