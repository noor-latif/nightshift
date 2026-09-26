import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import selector  # noqa: E402
from settings import LAP_WALLCLOCK_LIMIT_S  # noqa: E402


class FakeGh:
    """Writes a stub `gh` script that emits canned JSON from a file."""

    def __init__(self, issues, prs):
        self.dir = tempfile.mkdtemp()
        self.script = os.path.join(self.dir, "gh")
        with open(self.script, "w") as f:
            f.write("""#!/bin/sh
# stub gh: emits the issues list for issue subcommands, pr list for pr subcommands
cat "$FAKEGH_ISSUES"
""")
        issues_path = os.path.join(self.dir, "issues.json")
        prs_path = os.path.join(self.dir, "prs.json")
        with open(issues_path, "w") as f:
            json.dump(issues, f)
        with open(prs_path, "w") as f:
            json.dump(prs, f)
        wrapper = os.path.join(self.dir, "ghw")
        with open(wrapper, "w") as f:
            f.write("""#!/bin/sh
case "$1" in
  issue) FAKEGH_ISSUES=%s ;;
  pr)    FAKEGH_ISSUES=%s ;;
esac
export FAKEGH_ISSUES
exec %s "$@"
""" % (issues_path, prs_path, self.script))
        os.chmod(self.script, os.stat(self.script).st_mode | stat.S_IEXEC)
        os.chmod(wrapper, os.stat(wrapper).st_mode | stat.S_IEXEC)
        self.script = wrapper

    @property
    def gh(self):
        return self.script


ISSUES = [
    {"number": 2, "createdAt": "2026-09-24T10:00:00Z"},
    {"number": 1, "createdAt": "2026-09-23T09:00:00Z"},
]
NOW = 1_000_000.0


class TestSelector(unittest.TestCase):
    def setUp(self):
        self.issues_dir = tempfile.mkdtemp()

    def test_claims_oldest_issue_without_open_pr(self):
        fake = FakeGh(ISSUES, [{"headRefName": "agent/issue-2"}])
        got = selector.claim_next("o/r", self.issues_dir, now=NOW, gh=fake.gh)
        self.assertEqual(got["issue"], 1)  # oldest not covered by an open PR
        with open(got["path"]) as f:
            body = json.load(f)
        self.assertEqual(body["issue"], 1)
        self.assertEqual(body["claimed_at"], NOW)

    def test_claim_exclusive_second_attempt_fails_or_skips(self):
        fake = FakeGh(ISSUES, [])
        first = selector.claim_next("o/r", self.issues_dir, now=NOW, gh=fake.gh)
        # with a live claim on issue 1 and no other eligible issue, next pick skips it
        second = selector.claim_next("o/r", self.issues_dir, now=NOW + 1, gh=fake.gh)
        self.assertEqual(first["issue"], 1)
        self.assertTrue(second is None or second["issue"] != 1)
        # and the file cannot be double-created
        with self.assertRaises(FileExistsError):
            os.open(first["path"], os.O_CREAT | os.O_EXCL | os.O_WRONLY)

    def test_queue_empty_returns_none(self):
        fake = FakeGh([], [])
        self.assertIsNone(selector.claim_next("o/r", self.issues_dir, now=NOW, gh=fake.gh))

    def test_stale_claim_broken_with_note(self):
        fake = FakeGh(ISSUES, [])
        path = os.path.join(self.issues_dir, "issue-1.json")
        with open(path, "w") as f:
            json.dump({"issue": 1, "claimed_at": NOW - LAP_WALLCLOCK_LIMIT_S - 10}, f)
        got = selector.claim_next("o/r", self.issues_dir, now=NOW, gh=fake.gh)
        self.assertEqual(got["issue"], 1)
        log = os.path.join(self.issues_dir, "broken.log")
        self.assertTrue(os.path.exists(log))
        with open(log) as f:
            entry = json.loads(f.read().splitlines()[-1])
        self.assertEqual(entry["previous"]["issue"], 1)

    def test_fresh_claim_not_broken(self):
        fake = FakeGh(ISSUES, [])
        path = os.path.join(self.issues_dir, "issue-1.json")
        with open(path, "w") as f:
            json.dump({"issue": 1, "claimed_at": NOW - 60}, f)
        got = selector.claim_next("o/r", self.issues_dir, now=NOW, gh=fake.gh)
        self.assertEqual(got["issue"], 2)  # skipped live claim, took next issue
        with open(path) as f:
            self.assertEqual(json.load(f)["claimed_at"], NOW - 60)  # untouched
        self.assertFalse(os.path.exists(os.path.join(self.issues_dir, "broken.log")))

    def test_outcome_dispatch_exhaustive(self):
        state = {}
        cases = {
            "success": "merged",
            "queue-empty": "idle",
            "timeout": "timeout-park",
        }
        for outcome, want in cases.items():
            st = {}
            self.assertEqual(selector.handle_outcome(outcome, 7, st, NOW), want)
        # failure retries then parks at budget
        st = {}
        self.assertEqual(selector.handle_outcome("failure", 7, st, NOW), "retry")
        self.assertEqual(selector.handle_outcome("failure", 7, st, NOW), "retry")
        self.assertEqual(selector.handle_outcome("failure", 7, st, NOW), "parked")
        # crash follows the same budget ladder
        st = {}
        selector.handle_outcome("crash", 8, st, NOW)
        self.assertEqual(st["issues"]["8"]["retries"], 1)

    def test_unknown_outcome_raises_never_falls_through(self):
        with self.assertRaises(ValueError):
            selector.handle_outcome("hijacked", 7, {}, NOW)


    def test_parked_issue_not_reclaimed_next_open_claimed(self):
        # park is durable: stale claim on a parked issue must NOT be broken/re-claimed
        fake = FakeGh(ISSUES, [])
        path = os.path.join(self.issues_dir, "issue-1.json")
        with open(path, "w") as f:
            json.dump({"issue": 1, "claimed_at": NOW - LAP_WALLCLOCK_LIMIT_S - 10}, f)
        dispositions = {"1": "parked"}
        got = selector.claim_next("o/r", self.issues_dir, now=NOW, gh=fake.gh,
                                  dispositions=dispositions)
        self.assertEqual(got["issue"], 2)
        self.assertFalse(os.path.exists(os.path.join(self.issues_dir, "broken.log")))

    def test_issue_without_disposition_claimed_normally(self):
        fake = FakeGh(ISSUES, [])
        got = selector.claim_next("o/r", self.issues_dir, now=NOW, gh=fake.gh,
                                  dispositions={"9": "parked"})  # unrelated entry
        self.assertEqual(got["issue"], 1)

    def test_missing_state_unaffected(self):
        fake = FakeGh(ISSUES, [])
        got = selector.claim_next("o/r", self.issues_dir, now=NOW, gh=fake.gh,
                                  dispositions=None)
        self.assertEqual(got["issue"], 1)

if __name__ == "__main__":
    unittest.main()
