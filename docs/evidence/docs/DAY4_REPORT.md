# DAY4_REPORT.md — nightshift Day 4 (2026-09-26), corrected post-mortem

Corrected 2026-09-26 after apply-gate forensics (issue #9/#10 evidence replay on [redacted-host]).

## Correction: the two review-rejects were wrong-gate recordings

Runs **20260926T143026 (issue-9)** and **20260926T152543 (issue-10)** were recorded as
`gate=review` rejects, but the reviewer never saw the implementer's full work. Both diffs
contained an app.py hunk **plus a new-file section** (`--- /dev/null` / `+++ b/*_test.py`)
whose body lines follow **without a `@@ -0,0 +1,N @@` hunk header**. `git apply` applied the
app.py hunk and **silently dropped the header-less new-file section while exiting 0**. The
reviewer then correctly rejected the *incomplete artifact it was handed* ("no test file
addition anywhere in the provided diff").

Verdict: **genuine malformed-diff model failures, recorded under the wrong gate.** The
model produced malformed diffs (root cause, genuine failure); the reviewer judged honestly;
the instrument's apply gate manufactured the misattribution. Worse, with a dropped
*implementation* file the same hole would manufacture a **false green**: a patch whose
declared files only partially land passes diff-apply and is verified as if complete.

Fix (factory-spike commit df0d5a1d): apply_diff now asserts declared-vs-applied file set
after every successful tier; mismatch → loud `apply_incomplete` outcome (recorded in
verdict/timeline), never proceeds to review/verify. Auto-repair of malformed diffs is
deliberately out of scope — emitting them is a genuine model failure the gate must catch.

## Reclassification of 20260926T142715 (issue-9, first attempt)

**Instrument artifact (apply-gate silent drop), not a substantively-correct reject.** Its
claimed.diff is the *inverse* of the later runs: the implementation hunk (app.py empty-content
400) is well-formed, but the new test file section (`--- /dev/null` / `+++ b/paste_empty_content_test.py`)
is header-less — 40 lines of `+` body with no `@@` hunk header. applied.diff confirms git
apply kept only app.py and dropped the test file; the reviewer then failed criterion 4 ("no
test file addition") and rejected. All four substantive criteria passed on the artifact it
saw. Same mechanism as 143026/152543: genuine malformed-diff model failure, **wrong gate
(recorded as review-reject; mechanism = apply-gate silent drop)**. The Day-4 tally is
unchanged by this reclassification — it was already counted as a genuine model failure
under review, and stays a genuine model failure; only the gate attribution was wrong.

## Corrected Day-4 tally

| class | runs |
|---|---|
| genuine model failures: **4** | 2 malformed-diff (143026, 152543 — recorded under review; mechanism = git apply silent drop), 1 verify-fail, 1 review-reject (142715 — substantively the same malformed-diff mechanism, gate attribution corrected above) |
| instrument false reds: **2** | extractor (143357, 153446 — L-007) |

## Issue #10 park accounting (note for the Day-5 relaunch seed)

Park rests on **2 genuine strikes (143026 malformed-diff, 152543 malformed-diff) + 1 false
red (153446 extractor)**. Removing the false red: retries 2 vs RETRY_BUDGET 2 — **#10 earned
ONE final attempt; its park was not invalid** (2 genuine failures still consumed the budget
under the recorded outcomes), but the relaunch seed should grant issue #10 a fresh single
attempt first (budget already spent on the false-red-inflated count is the only adjustment
warranted; the failures themselves were genuine).
