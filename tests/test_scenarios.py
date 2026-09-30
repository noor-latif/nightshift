"""Structural alignment guard for self-run exec-oracles: each
scenarios/issue-<n>.json must gate exactly the GitHub issue whose number it
carries. The RED proofs cannot catch a cross-assignment — every oracle is
RED on the unfixed base regardless of which file it sits in, so a misplaced
oracle only surfaces as a wedged run (fixed issue gated by a still-RED
oracle). This guard fails at authoring time instead: it reads the JSON
(no execution) and asserts file number ↔ scenario name ↔ marker family all
align, plus the exec-oracle shape the kernel contract defines."""

import json
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

SELF_RUN_ISSUES = range(1, 7)  # filed audit findings #1-#6 on noor-latif/nightshift

# scenario name -> the GitHub issue it gates (from the filed issue bodies)
NAME_TO_ISSUE = {
    "claim-next-merged-skip": 1,
    "no-drain-with-open-issue": 2,
    "apply-mutations-newline-anchor": 3,
    "verify-hold-captured": 4,
    "parse-stream-malformed-chunk": 5,
    "tick-error-no-strand": 6,
    # dogfood queue (filed 2026-09-30): scenarios-dogfood/ oracles for the
    # deferred audit Layer-1 gaps; #6's oracle is re-queued there too
    "close-failure-not-crash": 12,
    "reap-attributes-issue": 13,
    "deploy-timeout-evidenced": 14,
}

# the dogfood dir is NOT in the repo: it lives in the self-run deployment
# (~/nightshift-dogfood/scenarios-dogfood). Guards read it via env override
# SCENARIOS_DOGFOOD_DIR, defaulting to the sibling deployment path; the
# self-run test runner sets it explicitly.
DOGFOOD_DIR = os.environ.get(
    "SCENARIOS_DOGFOOD_DIR",
    os.path.expanduser("~/nightshift-dogfood/scenarios-dogfood"))
DOGFOOD_ISSUES = {6, 12, 13, 14}


class TestSelfRunOracleAlignment(unittest.TestCase):
    def setUp(self):
        self.dir = os.path.join(os.path.dirname(__file__), "..", "scenarios")

    def sources(self):
        # repo scenarios/ for #1-#6; the deployment's scenarios-dogfood/
        # for the dogfood queue (#6 re-queued + #12-#14). Same checks both.
        for d, issues in ((self.dir, SELF_RUN_ISSUES),
                          (DOGFOOD_DIR, sorted(DOGFOOD_ISSUES))):
            for n in issues:
                yield d, n

    def load(self, d, n):
        with open(os.path.join(d, "issue-%d.json" % n)) as f:
            return json.load(f)

    def test_each_issue_file_gates_its_own_issue(self):
        # a scenario in the wrong issue-<n>.json is a crossed gate: the
        # factory fixing issue N would be held RED by another issue's
        # oracle forever. Name↔number must match the filed-issue map.
        for d, n in self.sources():
            sc = self.load(d, n)
            self.assertIn(sc["name"], NAME_TO_ISSUE,
                          "unknown scenario name in issue-%d.json" % n)
            self.assertEqual(NAME_TO_ISSUE[sc["name"]], n,
                             "scenario %r sits in issue-%d.json but gates issue %d"
                             % (sc["name"], n, NAME_TO_ISSUE[sc["name"]]))

    def test_markers_match_file_number(self):
        # stdout markers are run evidence; K<n>-* must belong to issue-<n>.
        # checked both in expect_stdout_fragment and inside argv -c sources
        # (print targets), so a relabel miss fails here, not in evidence.
        # K(\d+)-: dogfood issue numbers are multi-digit (K12-, K13-, K14-).
        for d, n in self.sources():
            sc = self.load(d, n)
            for a in sc["assertions"]:
                frag = a.get("expect_stdout_fragment")
                if frag:
                    self.assertRegex(frag, r"^K%d-" % n,
                                     "issue-%d.json fragment %r" % (n, frag))
                if a["argv"][1:2] == ["-c"]:
                    fams = set(re.findall(r"K(\d+)-", a["argv"][2]))
                    self.assertEqual(fams, {str(n)},
                                     "issue-%d.json argv carries markers %s"
                                     % (n, fams))

    def test_oracles_are_exec_shaped(self):
        # all-exec is the no-boot contract: a boot-shaped assertion in a
        # self-run oracle would demand an app.py nightshift does not have
        for d, n in self.sources():
            sc = self.load(d, n)
            self.assertTrue(sc["assertions"], "issue-%d.json has no assertions" % n)
            for a in sc["assertions"]:
                self.assertEqual(a["kind"], "exec")
                self.assertEqual(a["argv"][0], "python3")
                self.assertIn("expected_exit", a)


if __name__ == "__main__":
    unittest.main()
