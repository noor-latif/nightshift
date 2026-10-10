"""Slice 5: the committed sqlparse checker's hermetic self-test — fed the
measured buggy reindent output (clause split, ONLY orphaned) the checker
must FAIL it, and fed the fixed output it must PASS — no external repo."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))

import echelon  # noqa: E402


class TestCheckerSelftest(unittest.TestCase):
    def test_selftest_passes_at_tip(self):
        ok, buggy, fixed = echelon.checker_selftest()
        self.assertTrue(ok, "buggy fails=%r fixed fails=%r" % (buggy, fixed))

    def test_buggy_fixture_discriminates(self):
        """Pin the polarity per fixture, not just the aggregate: a checker
        that fails BOTH must not green the self-test leg."""
        ok, buggy, fixed = echelon.checker_selftest()
        self.assertTrue(buggy, "buggy fixture should be FAILED by the checker")
        self.assertEqual(fixed, [], "fixed fixture should pass")
        self.assertTrue(ok)

# NOTE: no unit test for the fail-closed stale-bank rule. echelon.py has no
# unit-test harness (main() is a stdlib script over module-global paths), and
# calling main() from a test that echelon's own suite_slices() discovers would
# recurse (echelon -> suite -> test -> echelon). The rule is verified directly
# against a stale bank copy instead (see 2026-10-10 external-control repair).


if __name__ == "__main__":
    unittest.main()
