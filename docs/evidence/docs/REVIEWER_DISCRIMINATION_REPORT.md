# Reviewer Gate — Discrimination-Matrix Validation (2026-09-28, post-fix c9978b5)

**VERDICT: discrimination HOLDS in both directions.**
- ACCEPT direction: **holds** (2/2 — both canonical issue-17 diffs accepted).
- REJECT direction: **holds** (4/4 genuine reject cases rejected; see calibration note on the invalid R4a construction).

Deployed code used: `~/nightshift/src/` (imported `agent` + `settings` directly; `agent.reviewer_prompt` + `agent.chat`, REVIEWER_MODEL=`glm-5.3-flash`, REVIEWER_MAX_TOKENS=4096, checkout view bounded at CHECKOUT_CHAR_BUDGET=100_000 — exactly lap.py:409-412). One run per case, no retries; all finish_reason=`stop`. Raw reviews: `/tmp/mx/results/*.review.txt`.

## Matrix

| case | source artifact | expected | verdict | one-line quote |
|---|---|---|---|---|
| A1 | `20260928T204441-issue-17/applied.diff` + fresh clone @69e186e | accept | **accept** ✓ | "`do_GET` already strips the query string (`path = urllib.parse.urlsplit(self.path).path` in the current file)" — the exact criterion the old diff-only prompt falsely failed |
| A2 | `20260928T204745-issue-17/applied.diff` (identical to A1) + clone @69e186e | accept | **accept** ✓ | Criterion 2 PASS "against the provided current file contents" — re-run for the record confirms fix-time validation |
| R3 | A2 diff with the do_POST fix hunk removed (context-only) | reject | **reject** ✓ | "the diff makes no change… `do_POST` still compares the raw `self.path`" — corrupted variant re-confirmed |
| R4b | `20260926T205312-issue-10/claimed.diff` (fabricated adjacency, L-000 class; never applied — died at diff-apply) + base checkout @e6b3db4 | reject | **reject** ✓ | "the candidate `app.py` also lacks the `delete` method that appears as unchanged context in the diff, confirming the supplied candidate state is not the post-apply state" — context-misalignment caught against the file view |
| R4c | `20260926T210631-issue-10/claimed.diff` (same class, second artifact) + base @e6b3db4 | reject | **reject** ✓ | 411 criterion FAIL: "no `_MissingContentLength` exception… a POST without Content-Length would still return 400" |
| R5 | constructed: test-only `empty_content_test.py` vs issue-9/#21 criteria, base @e6b3db4 | reject | **reject** ✓ | "The diff ships the tests but omits the actual fix… `""` is a `str`, so it passes the check" — test-only implementation class caught |
| R4a | `20260925T101308-issue-6/applied.diff` + base @bf9ca06 | reject | **accept** ✗ | "the required JSON 404 behavior is already present in the candidate `app.py`" — **invalid case construction, not a gate miss; see calibration note** |

Matrix row count: 7 (6 valid rows, 4/4 reject + 2/2 accept all correct; R4a disclosed as construction error).

## Authority: the deterministic oracle remains the merge authority

From deployed `lap.py` — review is a pre-filter; verify-green is required before merge:

- Review precedes verify and a reject is terminal for the lap (lap.py:416-421):
  > `verdict_m = re.search(r"VERDICT:\s*(accept|reject)", rev["content"], re.I)`
  > `if not verdict_m or verdict_m.group(1).lower() != "accept": return finish(lap, "failure", gate="review", …)`
- Verify-green gates merge — a review accept without a passing deterministic verify never merges (lap.py:425-429):
  > `evidence = verify.verify_candidate(worktree, pid_file, scenarios_dir, issue=issue)`
  > `if evidence["verdict"] != "pass": return finish(lap, "failure", gate="verify", error=evidence)`
- Only after `lap.event("verify-green")` does the lap push and call `merge.full_merge` (lap.py:429-441).

## Calibration note (reconstructed vs verbatim)

- **Verbatim diff artifacts**: A1/A2 (`applied.diff` byte-identical), R3 (canonical minus fix hunk), R4b/R4c (`claimed.diff` as recorded).
- **Reconstructed candidate state**: all file views built from fresh clones at the recorded base commits (A-cases/R3 @69e186e; R4b/R4c/R5 @e6b3db4), assembled with lap.py's own `checkout_files` semantics.
- **R4a invalid construction, disclosed**: the issue-6 premise ("404 body currently plain-text/empty") is contradicted by every recorded revision of app.py — `_not_found` already sent `{"error": "not found"}` JSON since d538552. The base genuinely satisfied criteria 1-5, so the reviewer's accept was **correct given the input**; the historical 101308 reject under the old prompt was itself a false reject of the diff-only gate (DAY2_REPORT's own review text failed criteria the file view shows already satisfied). Substituted the genuine fabricated-adjacency artifacts R4b/R4c per the substitution rule. No artifact was fabricated; all diffs are recorded evidence or explicit constructions (R3, R5).
- **R4b/R4c caveat**: these diffs never applied (fabricated adjacency), so no true post-apply state exists; per assignment, base state was supplied as the plausible file state. The reviewer correctly flagged the diff/candidate mismatch rather than trusting the diff.
- **R4 other classes**: Day-2 runs 101559 (narrated bash transcript, no diff) and 101931 (DSML markup leak) were caught by *earlier* gates (diff-extraction); they produce no diff artifact to replay through the reviewer and are out of its input domain — noted, not replayed.

## Conclusion

The fixed reviewer prompt discriminates in both directions on genuine cases: it accepts real fixes (relying on the file view for untouched-path criteria) and rejects corrupted, fabricated-adjacency, and test-only "implementations". The deterministic verify stage remains the merge authority; the reviewer is a working pre-filter.
