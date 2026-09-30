# DAY5_REPORT.md — nightshift Day 5 (2026-09-26)

Implementer switched to **gpt-6-luna @ reasoning_effort=high** (max_tokens 16384, streaming).
Reviewer unchanged: glm-5.3-flash. Cost truth: `usage.buyer_cost_micro` (matches order book
exactly; `usage.cost` ~15% low — wiring updated this day, commit f8bd3d7).

Factory-spike commits deployed: `f8bd3d7` (luna wiring), `2553d19` (hunk-level apply-gate
line-count reconciliation + honest apply_incomplete caught-text), `558eb0a` (push
--force-with-lease — see L-010). 78 tests green local + [redacted-host] at each step.

## Pre-launch

- 2 fresh oracle-assertable issues filed on noor-latif/toy-product: **#12** (DELETE
  /paste/<id> → 204 then 404) and **#13** (GET /stats). Both scenarios proven RED against
  e6b3db4 and GREEN against a hand-made fix in a throwaway checkout before filing.
- State reset; #10 seeded at retries=2/RETRY_BUDGET=2 → exactly one earned attempt.
- 5/5 live-rig probes PASS; round-trip scenario suite green; RED set = exactly the open
  issues (#10, #12, #13) — plus **issue-9's scenario RED although #9 is CLOSED** (finding:
  closed-without-merge; #9 was parked Day-4 after 3 retries, its "fix" never landed on main).
- Launch: first supervisor 2026-09-26T20:36Z (supervisor PID 609830 recorded 20:54Z after
  two nohup races created duplicates; duplicates killed by observed PID, pid file corrected).

## Per-issue outcome table

Cost = buyer_cost_micro (÷1e6 USD). Wall = timeline lap-start→lap-end.

| run | issue | outcome | gate | class | cost µ$ | wall s |
|---|---|---|---|---|---|---|
| 20260926T203657-issue-10 | 10 | failure | diff-apply (patch does not apply @app.py:63) | **unclassified** — malformed diff verified by replay (trailing blank context line matches no tree position); see replay section | 67 | 184 |
| 20260926T204208-issue-13 | 13 | **success** | — verify-green → PR #14 (merge c17d2641) → deploy rc=0 → identity readback MATCH → issue closed | GREEN lap (concurrency-contaminated window: started the same second as the #12 lap despite MAX_CONCURRENT_LAPS=1) | 27 | 46 |
| 20260926T204208-issue-12 | 12 | crash | post-squash IdentityMismatch (8935820a vs 66ec070c) | **instrument defect** (see classification; same-second dispatch as #13 — concurrency-contaminated window, see dedicated section) | 34 | 118 |
| 20260926T205312-issue-10 | 10 | failure | diff-apply (@app.py:98) | **unclassified** — hunk context matches NO revision of app.py (fabricated adjacency); prompt not persisted, staleness vs hallucination indistinguishable | 79 | 317 |
| 20260926T210034-issue-12 | 12 | crash | git push non-fast-forward (agent/issue-12 diverged from crashed first attempt) | **instrument defect** (pre L-010 fix) | 39 | 131 |
| 20260926T210455-issue-12 | 12 | crash | same non-fast-forward (old code still running) | **instrument defect** | 23 | 39 |
| 20260926T210631-issue-10 | 10 | failure | diff-apply (@app.py:92) | **unclassified** — same fabricated-adjacency class as 205312; see replay section | 73 | 276 |
| 20260926T211313-issue-10 | 10 | failure | diff-apply (@app.py:94) | **unclassified** — same class; phantom extra attempt (park had already landed), never counted | 87 | 418 |
| 20260926T212214-issue-12 | 12 | failure | diff-apply (@app.py:96) | **refactor lap — issue already satisfied on main by PR #15 (8935820a, merged 20:44Z mid-incident); NOT an independent defect→fix attempt, excluded from luna failure arithmetic** | 25 | 111 |
| 20260926T212615-issue-12 | 12 | **success** | — verify-green → PR #16 (merge 9045492e) → deploy rc=0 → identity MATCH → issue closed | GREEN lap — **refactor lap: issue already satisfied on main by PR #15 mid-incident; a genuine zero-touch pipeline green, but not an independent defect→fix green** | 39 | 136 |
| 20260926T213434-issue-10 | 10 | failure | diff-apply | **unclassified** — hunk 1 is valid and applies at offset; killed by a new-file hunk count typo (74 declared vs 71 actual) and the recount tier's handling of a spurious blank line; tier-1 diagnostic lost to ladder stderr discard; phantom (restart race, never counted) | 24 | — |
| 20260926T214258-issue-10 | 10 | crash | worktree add ('agent/issue-10' already used — leftover from the killed phantom) | **instrument defect** (cleanup, not luna) | 0 | — |

Merged PRs: **#14** (issue 13, merge SHA c17d2641e32f251182423545fbffa826d2677219),
**#16** (issue 12, merge SHA 9045492e08337a880488ac27073963b937503c44). PR **#15**
(agent/issue-12, merged 20:44Z as merge commit 8935820a) was merged by the crashed first
#12 lap BEFORE the identity check fired — see classification.

Final rig: HEAD 9045492e == /health revision == origin/main; issue-12 and issue-13
scenarios PASS on the live rig; rig unit suite OK.

## The 20:42 concurrency contamination (two dispatches, same second)

Timeline evidence: `20260926T204208-issue-12` and `20260926T204208-issue-13` both record
`"lap-start"` at `2026-09-26T20:42:08Z` — two laps running simultaneously despite
`settings.MAX_CONCURRENT_LAPS = 1`. Mechanism (read-only analysis, factory-spike @558eb0a):
the concurrency budget exists only as a constant; **nothing in the dispatch path reads it**.
`supervisor.dispatch()` (supervisor.py:88) fences on the in-memory `state["lap"]` key, and
`claim_next` fences per-issue via an O_EXCL claim file — but neither fence excludes a
*second supervisor process*. The launch window documented above (two nohup races creating
duplicate supervisors, duplicates killed by observed PID at 20:54Z) is the plausible
cause: two supervisor processes each held `state["lap"] = None` in their own memory,
each called `claim_next`, and the per-issue claim files happily admitted two *different*
issues (#12, #13) in the same second. The per-process lap-record is not a cross-process
mutex, and no file lock guards the dispatch decision. Consequence for the record: the
entire 20:42 window is concurrency-contaminated — #13's first-attempt green ran
concurrently with #12's crash, and the mid-lap main move (c17d2641 landing while #12's
lap was in flight) is the direct input to the IdentityMismatch story below. Not fixed
here (report-only); the fix belongs with the L-009 reconcile work.

## #10 diff-apply failures: replay verdict — UNCLASSIFIED, not "genuine model failure"

All four judged #10 claimed.diffs were replayed against a throwaway worktree at each
relevant revision (9045492e, 8935820a, 66ec070c, e6b3db4, bf9ca06). No diff applies at
any tier on any revision. But the earlier "genuine model failure (context-misaligned)"
classification does not survive replay either:

- **203657**: hunk 1's context (`_not_found()/return/try:/json.loads`) matches the real
  do_POST region at 9045492e (lines 70–75) with offset — yet all three tiers fail, because
  the hunk carries a trailing blank context line that corresponds to no tree position
  adjacent to that region. The stated old-line numbers track no single revision exactly
  (do_POST sits at 57 on bf9ca06, 59 on e6b3db4, 69 on 9045492e).
- **205312 / 210631 / 211313**: hunk 3's context requires `self.wfile.write(body)`
  immediately followed by `def _read_body` — an adjacency that **does not exist in any
  revision** (bf9ca06, e6b3db4, 8935820a, 9045492e all place `_send_json`'s
  `wfile.write(body)` at the end of the class, far from `_read_body`). The model did not
  diff against a stale checkout — it diffed against a **fabricated file layout**.
- **213434**: hunk 1 is valid and applies cleanly at offset (verified in isolation),
  but the new-file hunk declares `@@ -0,0 +1,74 @@` while the body contains 71 `+`
  lines → tier-1 "corrupt patch"; the recount tier then fails on a spurious blank
  context line. A 3-character count typo in a new-file header killed a patch whose
  substantive hunk was correct.

Why the in-run artifacts couldn't show this: `lap.apply_diff` (lap.py:235-253) runs the
three-tier ladder and, on total failure, records **only the last tier's stderr**
(`r.stderr` from the recount-C1 attempt, lap.py:253). Tier 1's "corrupt patch at line N"
— the single most diagnostic message, pinpointing the malformed hunk — is discarded
every time. The verdict.json "patch does not apply @app.py:NN" texts are tier-2/3
messages from context-search failures, not structural-parse failures. Replay was
required to recover the distinction.

Gap: the implementer prompt is not persisted (only `implementer_raw.txt`, the response).
Replay subsequently established (BIGGEST_ISSUE_ANALYSIS.md §2) that the failures are
**fabricated adjacency on fresh bases** — per-run bases were FRESH (worktree_for fetches
origin/main per lap; 205312's `def delete` context exists only in its own base 8935820a),
and terminal-hunk old-side context has no contiguous window in ANY checked revision —
stale checkout EXCLUDED on the tree side. The residual caveat is solely prompt-side: what
the model was SHOWN is unverifiable, so "unclassified" means prompt-side provenance
unverifiable, not mechanism unknown. What changes: record every tier's exit code and
stderr separately (L-014), persist the implementer prompt alongside the response.

## State accounting defects (final state.json)

**#13 recorded `retries: 1` alongside `disposition: "merged"`.** #13 had exactly one
attempt, which succeeded — a success outcome should zero (or never have incremented) the
retry counter; the row instead carries a phantom retry from the concurrent-dispatch
window. Instrument defect: `handle_outcome` reconciliation does not normalize the retry
counter when an issue reaches a terminal merged disposition.

**#12 crash outcomes did not increment `retries` symmetrically.** Accounting: 3 crash
outcomes pre-reset (204208, 210034, 210455), hand-reset to 0 at 21:05Z, then one
diff-apply failure (212214) and one success (212615). Expected final `retries: 1`;
actual final state shows `retries: 2` — one extra increment from a restart race (the
same mechanism that inflated #10 to 6, here in the other direction: a raced outcome
landed that the visible timeline cannot account for). Also note the disposition stayed
"merged" while the BLOCKED exit text still said "issue 13 open PR or live claim" —
outcome reconciliation between lap results, state.json, and GitHub terminal state has
gaps in both directions. Reported as instrument defect; no code change made in this
correction pass.

## IdentityMismatch classification (task 3)

Code path: `merge.full_merge` → `gh pr merge --squash --match-head-commit <head>` →
fetch origin/main → `post_merge_identity(worktree, merge_sha, head_sha)` which asserts
`git diff --stat merge_commit head` empty (tree equality, never SHA — the squash of an
identical tree is allowed to re-derive the same content).

The crashed lap's worktree head was 66ec070c ("Implement issue 12" on top of e6b3db4 —
DELETE support only). But main at merge time already carried c17d2641 (issue 13's
`count` property + /stats), and the squash 8935820a merged BOTH the branch patch and the
already-merged #13 content onto c17d2641's parent. `git show 8935820a:app.py` contains
`/stats` + `count`; `git show 66ec070c:app.py` does not — 6 real content lines differ.
So the tree check compared the squash result (correct superset tree) against a branch
head based on a pre-#13 base. **Verdict: genuine integrity stop, not an instrument false
red** — the identity check fired exactly when the squash output was NOT tree-equal to the
verified head, which is what it exists for. The real instrument defect is upstream of it:
the lap pushed and merged a branch whose base had gone stale mid-run, and the merge was
already on GitHub when the gate fired (merge ≠ atomic with its check). L-011.

Note the merged tree itself is *correct for the issue*: 8935820a implements DELETE (the
#12 behavior) plus #13's stats — live rig verified both scenarios pass. The false part
was only the lap's outcome recording.

## #10 retries accounting (task 4)

Seed was retries=2 (budget). Park condition (selector.handle_outcome, selector.py:130-134):
`rec["retries"] += 1; if rec["retries"] > RETRY_BUDGET: park` → the seed attempt should
land retries=3 → park. Observed: retries hit **4, then 5, then 6** — three extra attempts
beyond the earned one. Mechanism: every supervisor restart (there were 5) re-reads
state.json, and each restart raced a lap already in flight: the killed supervisor's lap
kept running with the old code, or the fresh supervisor dispatched before my state edits
landed (one lap read pre-edit state). Each of those runs ended in failure →
handle_outcome incremented retries again. The parked-skip in claim_next
(selector.py:52) is correct and verified — the inflation came from *external restarts*
(me/operator), not from the selector. #10's earned attempt (20260926T205312, first
post-restart run) failed at diff-apply (replay classification: unclassified — see the
replay section; the park itself is valid on outcome regardless of root cause). The extra 3
attempts are operator-induced and did not produce a false green (all failed at diff-apply
or crashed on instrument defects).

## The non-fast-forward crash loop (L-010, steering-confirmed, fixed)

First #12 lap crashed AFTER `_git(["push","-u","origin","agent/issue-12"])` — the remote
branch was left pushed. `worktree_for()` rebuilds the local branch from origin/main with
`-B`, so the retry's history diverges from the stale remote branch → plain push rejected
→ crash before any model output is judged. Every retry of a once-pushed issue would loop
identically; the push sits before the merge gate so each crash re-poisons the next.
Fix: commit 558eb0a — `push --force-with-lease` (factory-owned branches). After deploy +
#12 accounting reset, #12's next-but-one attempt went GREEN through the whole chain
(a refactor lap — the issue was already satisfied on main by that point; see fair-attempt
accounting below).

## Issue #12 fair-attempt accounting

Zero fair attempts until 21:22Z. Both 20:42Z/21:00Z/21:04Z strikes were the instrument
(push divergence), not luna; retries were reset to 0 at 21:05Z per steering. After the
fix, the 21:22Z and 21:26Z laps are **refactor laps, not independent defect→fix
attempts**: PR #15 (8935820a) had already landed #12's DELETE behavior on main at 20:44Z,
mid-incident, via the crashed first lap's merge (verified: `git show 8935820a` implements
do_DELETE + PasteStore.delete; both later claimed.diffs only refactor that
already-present code — `pop(...)` idiom variants and a `_send_no_content` extraction).
The 21:26Z green therefore proves the pipeline (implement→verify→merge→deploy→identity
readback, all zero-touch) but not an independent defect→fix green, and the 21:22Z
diff-apply failure is not evidence of context misalignment on genuine work. Net for #12:
instrument-inflated strikes + 2 refactor laps (1 failure, 1 green); the one genuine
defect→fix attempt was the crashed 20:42Z lap itself.

## S-score assessment

| S | verdict | evidence |
|---|---|---|
| S1 zero-touch consecutive greens | **NOT MET** | The written criterion (SPIKE_PROD.md:10) is 3 consecutive laps with **zero human interventions** reaching terminal state — not "3 consecutive greens". Day 5 never had even 2 consecutive zero-touch laps: the launch transcript records manual `rm -f state/claims/issue-10.json state/claims/issue-12.json`, 5 supervisor kills/restarts, hand-written PID files, and a hand-reset of #12's retry accounting — every one an intervention under the written text, and no 3-lap window was free of them. S1 is also **unmeasurable in-run**: `state/interventions.jsonl` does not exist (verified on [redacted-host] and on the migrated laptop copy), so interventions were never recorded and this rescore rests on after-the-fact transcript reconstruction. Recommendation: adopt the stricter all-greens bar (3 consecutive zero-touch GREEN laps) as the *target* for a future session, but the criterion as written was already failed — stated plainly here. |
| S2 false greens | **none** | both merged trees verified against their oracles on the LIVE rig: c17d2641 (issue-13 scenario pass) and 9045492e (issue-12 + issue-13 scenarios pass); /health revision == rig HEAD == origin/main both times; hunk-level gate (new) caught nothing false |
| S3 cost/lap vs $0.01 | **pass, 250×+ margin** | max lap 87µ$; two green laps 27µ$ and 39µ$ (0.27%/0.39% of ceiling) |
| S7 receipts | **gap** | ntfy fired per terminal event (verified via cache-poll: FAILURE/CRASH/GREEN/blocked/HALT messages all present) but notify() still does not append to state/evidence/ntfy/receipts.json — receipts file holds only 4 Day-2 rows |

## luna (effort=high) vs corrected glm Day-4

| metric | glm-5.3-flash (Day-4, 5 attempts) | gpt-6-luna (Day-5, 10 real laps) |
|---|---|---|
| end-to-end greens | 0 | 2 (issues #13, #12 — first greens of the spike; the #12 green is a refactor lap, see fair-attempt accounting) |
| diff-apply failures | 2-3/5 attempts | **4/5 judged attempts on genuine work** — arithmetic: 5 attempts produced a judged diff (4× #10: 203657, 205312, 210631, 211313; 1× #12 genuine work: 212615 green), of which 4 failed at diff-apply. The 21:22Z #12 failure (212214) is excluded from both numerator and denominator: it was a refactor lap on an issue already satisfied on main by PR #15. The prior "4/7" figure did not reconcile with the table's 5 diff-apply rows and has been recomputed from the table. Note the 4 failures are now **unclassified**, not confirmed context-misalignment (see replay section). |
| implementer latency/lap | 54–209 s (lap wall) | 39–418 s; implementer call itself 20–185 s (finish=stop every time, no length-starves at 16384) |
| completion tokens | 777–2653 | 336–6854 (bigger, more ambitious diffs) |
| cost/lap (buyer truth) | not recorded truthfully (usage.cost) | 23–87 µ$, order-book exact |
| format compliance | unified diff, some header-less new-file sections | clean fenced unified diffs, no DSML leak; #10 laps carried malformed hunk counts / fabricated adjacency (unclassified, see replay section) |
| verdict | gate-catching machine, zero greens | **first end-to-end greens (1 of them a refactor lap); #10 failures unclassified — malformed hunk counts and fabricated file adjacency, root cause not established (prompt not persisted)** |

Caveat: n=1 independent defect→fix green (#13) + 1 refactor-lap green (#12), both on
1-2-hunk issues; #10 (older, harder) exhausted its budget on patches that replay could
not classify. Not a claim that luna generalizes.

## Queue terminal state

- #10: parked permanently (retries inflation documented above; earned park valid)
- #12: merged (PR #16, 9045492e) — green lap in-run merge+deploy+identity-readback (a refactor lap; see fair-attempt accounting)
- #13: merged (PR #14, c17d2641) — green lap in-run merge+deploy+identity-readback
- #9 (Day-4 leftover): CLOSED but never merged — its scenario is RED on main (pre-existing inconsistency, recorded as finding)
- Supervisor exited by design (BLOCKED → sys.exit(1)) once the only open issue (#10) was
  parked and #13 was already closed: "queue blocked: issue 13 open PR or live claim" is
  the residual mislabel (13 was terminal on GitHub but its state row stayed "retry") —
  cosmetic, noted as part of L-009's cleanup path.
- State-accounting defects in the final state.json are recorded in their own section
  above: #13 carries a phantom `retries: 1` despite a one-attempt success, and #12 ends
  at `retries: 2` where the visible timeline supports 1 — an extra restart-raced
  increment (the mirror image of #10's inflation to 6).
