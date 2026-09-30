# SELF_RUN_SCORE_2026-09-29 — the factory runs on itself: unattended, scored

Target: noor-latif/nightshift (the factory's own repo). Deployment:
`~/nightshift-selfrun` @ fb8af5f2; product checkout `~/factory-lab/nightshift`.
Scored log: `~/nightshift-selfrun/state/interventions.jsonl` — pinned byte-for-byte as
`interventions.jsonl.scored-snapshot` (S1 precedent). Every number below traces to a
file path in that deployment.

**VERDICT: RUN COMPLETE.** Launch-3 window 2026-09-29T08:47:20Z → 10:00:00Z
(1h12m40s; journal: "Consumed 26.151s CPU over 1h 12min 40.242s"). Terminal row:
`session-halt reason="drained" events=["dispatch:idle","DRAIN:1 parked, 4 merged"]`
(log final row) — a TRUE drain: all 5 queued issues dispositioned, clean exit
(Result=success, ExecMainStatus=0). **4 of 5 issues fixed and merged by the factory
on its own code; 1 parked after honest gate kills; ZERO human interventions.**

## Per-issue outcome (source: scored log `lap-end`/`lap-check` rows; state.json)

| Issue | Attempts | Gate sequence (final lap) | Disposition | PR / merge sha | GitHub |
|---|---|---|---|---|---|
| #1 claim_next merged-skip | 1 (supervised, pre-launch) | lap-start→…→verify-green→merged→deploy-skip→issue-closed | merged | #7 da1cf1cd | CLOSED |
| #2 DRAIN-with-open-claim | 2 | lap-start → claimed → implementer-done → mutation-apply → review-accept → verify-green → merged → deploy-skip → issue-closed → lap-end | merged (retries 1) | #8 82879696 | CLOSED |
| #3 apply_mutations newline | 2 | attempt-1 killed at **review** (no-op fix rejected); attempt-2 full chain: lap-start → … → verify-green → merged → issue-closed | merged (retries 1) | #9 a4b35b1d | CLOSED |
| #4 Hold escapes verify | 2 | attempt-1 killed at **mutation-apply** (anchor miss on tests/test_verify.py); attempt-2 full chain: lap-start → … → verify-green → merged → issue-closed | merged (retries 1) | #10 e8fc858e | CLOSED |
| #5 parse_stream chunk | 1 | same, all green, first try | merged (retries 0) | #11 c98f7d18 | CLOSED |
| #6 tick-error stranding | 3 | 3× killed at **mutation-apply** on `src/supervisor.py`: every find block transcribed the L-013 disposition line with an extra space (`])] ["disposition"]` vs main's `])]["disposition"]`) — a one-char transcription defect repeated on every retry; the anchor text itself existed verbatim on main | **parked** (retries 3) | — | OPEN |

Issue #1 was the supervised validation lap (PR #7, merged before launch-3, included
for completeness). Issues #2–#6 were dispatched and resolved unattended in launch-3.

## Per-lap cost (source: each evidence dir's `cost.json`; buyer_cost_micro summed)

| Lap (evidence dir) | LLM calls | USD |
|---|---|---|
| 20260929T084729-issue-2 (attempt-1, killed at verify) | impl+rev | 0.000608 |
| 20260929T085540-issue-2 (attempt-2, MERGED #8) | impl+rev | 0.000779 |
| 20260929T090652-issue-3 (attempt-1, failure) | impl+rev | 0.000681 |
| 20260929T091503-issue-3 (attempt-2, MERGED #9) | impl+rev | 0.000673 |
| 20260929T092544-issue-4 (attempt-1, failure) | impl | 0.000513 |
| 20260929T093416-issue-4 (attempt-2, MERGED #10) | impl+rev | 0.000531 |
| 20260929T093823-issue-5 (MERGED #11) | impl+rev | 0.000546 |
| 20260929T094229-issue-6 (killed mutation-apply) | impl | 0.000523 |
| 20260929T094921-issue-6 (killed mutation-apply) | impl | 0.000372 |
| 20260929T095508-issue-6 (killed mutation-apply → PARK) | impl | 0.000459 |
| **Total (launch-3, 10 laps)** | | **0.005685** |

(Cost ceiling: no runtime ceiling check exists — `COST_CEILING_USD=0.01` is defined in `src/settings.py` and referenced nowhere else in the code. As a measurement, the max observed per-lap cost was 0.000779, ~13× under the $0.01 design budget — no lap came near it, but nothing would have stopped one that did.)

## Zero-intervention basis (S1 criterion)

- All 10 `lap-check` rows in the scored log carry `observed: []` — no reconcile-detected
  intervention on any lap.
- Exactly one `session-start` row in the window (08:47:20Z) and no `supervisor-restart`
  rows: the supervisor never restarted mid-run.
- No `intervention` rows in the scored log.
- Operator disclosure: two aborted launch attempts exist as ADJACENT, SEPARATE files —
  `interventions.jsonl.aborted-launch1-*` and `.aborted-launch2-*` (plus
  `.supervised-issue1-*` for the validation lap). The scored log contains ONLY
  launch-3 rows. Each abort was diagnosed and disclosed at the time: launch-1 (stale
  harness / truncating checkout view / curation fragility) and launch-2 (the false
  wiring-report incident, corrected in the aborted-launch2 disclosure).

## Attribution

- **No wording artifact applies to launch-3.** The acceptance-criteria rewording
  landed 08:39Z; launch-3 started 08:47:20Z — every dispatch in the scored window
  saw post-rewording criteria. (The pre-08:39 criterion-1 review rejects live in the
  `aborted-launch2` log — already disclosed there, not part of this score.)
- All 10 lap outcomes were gate verdicts (review ×1, mutation-apply ×4, verify ×1,
  green ×4) — zero `crash` outcomes, zero gateway errors. The six failing laps:
  #2 attempt-1 (verify), #3 attempt-1 (review), #4 attempt-1 (mutation-apply), and
  #6 attempts 1-3 (mutation-apply).
- **The one genuine model implementation failure among the merged issues** (#2
  attempt-1, killed at verify): the implementer's own regression test referenced
  `self.now`, an attribute its host class never sets — caught by the candidate's
  unit suite at the verify rung, retried, fixed on attempt-2. Harness-pristine
  under the launch env was verified at the time (fresh worktree of fb8af5f2: 155
  tests OK) — model-attributed, not harness-attributed.
- **#6's park is a verbatim-anchoring (transcription) failure, not anchor drift**:
  all three attempts' find blocks transcribed the L-013 disposition line
  `state["issues"][str(claim["issue"])]["disposition"] = "merged"` with an extra
  space — `])] ["disposition"]` where main has `])]["disposition"]` — while the rest
  of the anchor (dispatch signature, docstring, L-013 comment) matched. The
  anchor text existed VERBATIM on the main revision every attempt ran against
  (post-#5 merge c98f7d18: verified in `git show c98f7d18:src/supervisor.py`,
  ~L157-180); the spaced variant appears nowhere in the repo tree at that revision
  (grep: 0 hits); and neither #2's (82879696, tick()'s DRAIN block only) nor #4's
  (e8fc858e, src/verify.py + tests only) merge touched the dispatch/L-013 region —
  so no moving target existed. The model simply mis-transcribed one character,
  identically on every retry, and the mutation-apply gate correctly killed each
  attempt (`anchor occurs 0 times`). 3 correct gate kills, parked correctly, issue
  still OPEN. The oracle for #6 (tick-error-no-strand) is still RED on origin/main;
  the fix is real future work (a fresh issue quoting current main's text). The
  upgrade path that would have caught it sooner: a pre-apply anchor-exists
  validation would have killed attempt-1 with a cheaper, clearer diagnosis (and
  is worth having for the anchor-drift risk class too — but anchor drift was NOT
  #6's cause).


## Chain integrity notes

- Every merged lap's timeline is the full 10-event green chain (see per-issue table);
  every terminal was written to `state/lap-result.json` before evidence rotation.
- DRAIN at halt was truthful — the K5 false-drain bug did not fire because the run
  itself fixed K5 (issue #2, PR #8) before any drain condition arose.
- The K1 hot-loop also could not fire (issue #1 fixed pre-launch, verified live).
- exec-oracles selected per-issue in every lap (red-recheck verdicts all "fail" pre-
  fix, then verify-green post-fix; no boot scenario ever ran: provenance skip on
  every merged lap's verify.json).

Score pinned to: `state/interventions.jsonl.scored-snapshot` (identical bytes).

Corrected 2026-09-30: #6 attribution (one-char transcription defect in the find
block, not anchor drift) and failure taxonomy (review ×1, mutation-apply ×4,
verify ×1, green ×4), evidence re-verified from the per-lap evidence dirs.

Corrected 2026-09-30 (cost ceiling): the parenthetical under the cost table previously
read as if a ceiling check ran; in fact no runtime enforcement exists — the constant
is defined-but-unreferenced, and 0.000779 is the measured per-lap maximum.

Corrected 2026-09-30 (post-fix): the statement above was true when written against the pre-fix main; since 582cfa64 the ceiling is enforced as a real runtime gate (add_cost raises CostCeilingExceeded past the cumulative total; the lap then fails at gate='cost').
