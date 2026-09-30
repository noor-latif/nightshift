# DOGFOOD_SCORE_2026-09-30 — first unattended end-to-end run on the factory's own repo

Target: noor-latif/nightshift (the factory's own repo). Deployment:
`~/nightshift-dogfood` @ f41cadd-era (src byte-identical to the validated 2e719bcd
kernel: `git diff 2e719bcd f41cadd -- src` is empty). Scored log:
`~/nightshift-dogfood/state/interventions.jsonl` — 36 rows, window
2026-09-30T05:13:53Z → 05:56:45Z (42m52s). Every number below traces to a path
in that deployment (journal corroborates: the three supervisor segments consumed
"2min 27.292s", "1.749s CPU", and "4.017s CPU over 10min 24.671s" wall clock —
the last ending exactly at the halt).

**VERDICT: RUN COMPLETE — TRUE DRAIN.** 4 issues attempted across 8 laps;
**2 merged green (each first attempt), 2 parked after honest gate kills; 5
model-attributed failures, 1 restart-attributed kill; ZERO UNDISCLOSED operator
actions** (two disclosed topic-security rotations, `DECISIONS.md` 2026-09-30
lines 1–2 of the dated block). Terminal row: `session-halt reason="drained"
events=["dispatch:idle","DRAIN:2 parked, 2 merged"]` (log row 36) — matches
`state/state.json` exactly (6/14 parked, 12/13 merged, lap null). Total LLM cost:
**$0.006457**.

## Per-issue outcome (source: scored log `lap-end`/`lap-check`/`red-recheck` rows; per-lap evidence dirs; state.json)

| Issue | Attempts | Gate sequence (per attempt) | Disposition | PR / merge sha |
|---|---|---|---|---|
| #6 tick-error stranding | 3 | a1 killed at **mutation-apply** (anchor occurs 0 times, L-013 prefix); a2 killed at **review** (no parseable verdict); a3 killed at **review** (no parseable verdict; truncated review body carries the substantive fake-gh double-escaping analysis) → PARK | **parked** (retries 3) | — |
| #12 crash-relabel on gh close fail | 1 | lap-start → claimed → implementer-done → mutation-apply (7 mutations) → review-accept → verify-green (oracle `close-failure-not-crash`, K12-RED-GREEN) → merged → deploy-skip (mode none) → issue-closed → lap-end | merged (retries 0) | #15 397717e7 |
| #13 issue=None unattributed reaps | 1 | full green chain completing 05:41:00Z (merged 05:40:58Z); supervisor killed 05:42:52Z before writing the log row; new process reconciled lap-end success/merged + lap-check observed [] at 05:43:54Z (oracle `reap-attributes-issue`, K13-RED-GREEN) | merged (retries 0), restart-reconciled | #16 1404d6f5 |
| #14 deploy-timeout crash escape | 3 | a1 dispatched 05:44:08Z, killed in-flight 05:46:21Z by the disclosed second topic-rotation restart (evidence dir holds only lap-start+claimed); **RESTART-ATTRIBUTED**; a2 killed at **review** (substantive reject: criterion-4 regression test absent); a3 killed at **review** (same reject) → PARK | **parked** (retries 3) | — |

## Per-lap cost (source: each evidence dir's `cost.json`, total_usd summed)

| Lap (evidence dir) | LLM calls | USD |
|---|---|---|
| 20260930T051402-issue-6 (a1, killed at mutation-apply) | impl | 0.000826 |
| 20260930T052139-issue-6 (a2, killed at review) | impl+rev | 0.001003 |
| 20260930T052749-issue-6 (a3, killed at review → PARK) | impl+rev | 0.001492 |
| 20260930T053226-issue-12 (MERGED #15) | impl+rev | 0.000972 |
| 20260930T053953-issue-13 (MERGED #16) | impl+rev | 0.000734 |
| 20260930T054408-issue-14 (a1, restart-killed in flight) | none completed | **no row** |
| 20260930T054635-issue-14 (a2, killed at review) | impl+rev | 0.000823 |
| 20260930T055134-issue-14 (a3, killed at review → PARK) | impl+rev | 0.000607 |
| **Total (7 recorded rows)** | | **0.006457** |

Honest accounting: **zero `missing_usage:true` rows in this run** (grep across the
deployment's state: no such row; the field exists only in `src/` code). One
explicit gap: #14 attempt-1 was killed ~2min into the implementer call, so no
cost row exists — any in-flight tokens died with the process and are
unaccounted (bounded above by one implementer call's typical ~0.0003–0.0008).
The $0.006457 sum includes exactly the 7 recorded rows. Per-issue: #6 $0.003321,
#12 $0.000972, #13 $0.000734, #14 $0.001430 (recorded rows only). Cost ceiling:
the deployed kernel enforces `COST_CEILING_USD = 0.01` per lap at runtime
(`src/settings.py:33`, the 582cfa64 fix confirmed in the prior score's dated
correction); max observed lap $0.001492, ~6.7× under; no cost-gate hits.

## Zero-undisclosed-intervention basis

- 36 log rows decompose exactly: 3 `session-start`, 8 `red-recheck`, 8
  `dispatch`, 8 `lap-end`, 8 `lap-check`, 1 `session-halt` — **zero
  `intervention` rows, zero operator rows** (F3 honored: operator actions live
  only in `DECISIONS.md`, never in the instrument log).
- All 8 `lap-check` rows carry `observed: []` — reconcile detected no anomaly
  on any lap, including both restart-affected ones.
- Three `session-start` rows: 05:13:53Z pid 818457 (launch), 05:43:54Z pid
  837819 and 05:46:21Z pid 839029 — the two mid-run starts are exactly the two
  `DECISIONS.md` 2026-09-30 disclosures: the NTFY_TOPIC repoint off the burned
  public topic, and the second rotation after both prior topic values were
  found published in a `docs/evidence/MANIFEST.md` rule-doc line. Security
  hygiene, not factory failures. Journal corroborates: stop 05:42:52Z → start
  05:43:53Z (segment "2min 27.292s"), stop/start 05:46:21Z.
- **Honest-not-zero framing: zero UNDISCLOSED operator actions; two disclosed
  restarts (topic security rotations); one in-flight lap killed (#14 a1) and
  correctly handled by the retry machinery; one completed-but-unrecorded lap
  (#13) correctly reconciled.** Neither restart counts as a harness or model
  defect.

## Attribution

- **#6 (parked, model-attributed, all 3 attempts).** Attempt-1: the
  transcription defect, occurrence 5 (see taxonomy below). Attempts 2–3:
  mutation-apply succeeded (4 and 2 mutations; attempt-2's review explicitly
  PASSed the anchor-exists check — "the disposition line reads exactly
  `...["disposition"] = "merged"` (no space)"), then the reviewer failed to
  produce a parseable verdict: both reviewer rows show
  `completion_tokens: 4096` — the glm-5.3-flash output cap truncated the review
  mid-criterion before any VERDICT line (attempt-3's truncated body contains
  the substantive fake-gh stub double-escaping analysis — `\\n`/`\\\"`
  double escapes corrupting the stub shebang — but never reached a verdict).
  The gate fail-closed correctly on both; both kills are review-gate model
  failures.
- **#12, #13 (merged, green, first attempt each).** #13 is counted green,
  restart-reconciled: its lap completed the full chain at 05:41:00Z (merged
  05:40:58Z, PR #16, merge_sha 1404d6f — also visible on origin/main); the
  supervisor died 05:42:52Z before writing the log row; the replacement process
  reconciled lap-end success/merged with `lap-check observed: []` at 05:43:54Z.
  **Reconcile-honesty note:** unparseable-claim crash-relabeling was itself
  issue #13's subject, and the kernel reconciled this restart-affected lap as
  success instead of crashing it (log rows 21–22) — the affected claim was
  well-formed and already closed, so the pre-#13 deployed reconcile path
  handled it correctly; the unparseable-claim edge #13 targets did not arise.
- **#14 (parked; a1 restart-attributed, a2–a3 model-attributed).** a1's lap-end
  `outcome: crash, disposition: retry` at 05:46:21Z was written by the
  replacement process for a lap the operator's second rotation killed mid-flight
  (evidence dir `20260930T054408-issue-14` holds only lap-start + claimed — no
  implementer output, no cost row). RESTART-ATTRIBUTED, not model. Its prior
  red-recheck (05:44:08Z, verdict fail) is valid ladder proof. a2 and a3 both
  failed at **review** with substantive `VERDICT: reject`: the implementation
  (a `TimeoutExpired` handler emitting a `deploy` event row and
  `gate="deploy-timeout"` instead of a generic crash) was called sound both
  times, but criterion 4 — an in-repo regression test driving `lap.run` with a
  hanging deploy script, failing pre-fix — was never delivered (the
  provided-files contract excludes new files and no existing test was
  extended). Two honest review kills on the same implementer capability gap.
- All 6 non-restart lap outcomes were gate verdicts; the 5 model failures are
  mutation-apply ×1, review ×4. Zero verify-rung failures, zero gateway errors,
  zero harness defects.

## Failure taxonomy (this run)

| Gate | Kills |
|---|---|
| review | 4 (#6 a2, #6 a3 — no parseable verdict; #14 a2, #14 a3 — substantive reject) |
| mutation-apply | 1 (#6 a1 — anchor occurs 0 times) |
| verify | 0 |
| green | 2 (#12, #13) |
| crash | 1 (#14 a1 — **restart-attributed**, not a model failure) |

### Transcription-defect recurrence (the #6 class)

Historical occurrences 1–4 predate this run (per the prior score
`SELF_RUN_SCORE_2026-09-29` — the 2026-09-29 self-run's #6 attempts 1–3 each
mis-transcribed the L-013 disposition line — plus the supervised session
before it). **This run adds occurrence 5**: #6 attempt-1's find block
(`evidence/20260930T051402-issue-6/claimed.json`) writes
`state["issues"][str(claim["issue"])] ["disposition"]` — one extra space —
where main has `])]["disposition"]`; the anchor prefix `# L-013: never spend a
lap on an already-satisfied issue` existed on the deployed revision, and the
mutation-apply gate killed it (`anchor occurs 0 times (expected 1)`). **Total
across all sessions: 5.** A stable implementer-model defect class (same
character, same line, across sessions and deployments) — the pre-apply
anchor-fuzzy-match fix (flag near-miss anchors before burning a lap) would
convert each occurrence into a cheap, clear pre-apply diagnosis; noted here,
not filed.

## What the run proves

1. **First unattended end-to-end exercise of the full downstream contract on
   the factory's own repo:** claim → implement → mutation-apply → review →
   verify → merge → PR → issue-close, with real PRs **#15 (397717e)** and
   **#16 (1404d6f)** squash-merged into noor-latif/nightshift public main and
   the issues closed — no operator in the loop.
2. **Oracles served from the deployment's own `scenarios-dogfood/` dir** (issue
   6/12/13/14 scenario files; the c4ad280 commit points the
   `SCENARIOS_DOGFOOD_DIR` default here). The red ladder held on all 8
   dispatches: every red-recheck verdict was `fail` pre-fix, and both merged
   laps' verify runs found their oracle fragments (K12-RED-GREEN,
   K13-RED-GREEN) post-fix.
3. **Gates caught every model failure without operator help:** 5 kills across
   2 parked issues, including fail-closed review on unparseable verdicts and
   the anchor-occurs-0-times kill on the transcription defect.
4. **The retry/reconcile machinery survived real operator restarts:** a killed
   in-flight lap became crash/retry with its red-recheck proof preserved and
   the issue re-dispatched; a completed-but-unrecorded lap was reconciled to
   success/merged with `observed: []` — exactly the disclosed behavior
   (`DECISIONS.md` 2026-09-30, both lines).
5. **The drain was truthful:** halt reason "drained", 2 parked + 2 merged
   matches `state.json`; journal shows clean stop at 05:56:45Z.
6. **Cost discipline held under enforcement:** $0.006457 total, max lap 6.7×
   under the per-lap $0.01 ceiling, zero cost-gate hits.

## Known limits

- **2 of 4 issues parked (50% green rate).** Both parks are model-capability
  failures honestly gated — the system working as designed — but it caps the
  run's throughput: #6 on the recurring transcription defect plus
  reviewer-cap truncation; #14 on an implementer that twice shipped the fix
  without the criterion-mandated regression test.
- **Reviewer output cap burns retries:** both #6 review kills stem from
  glm-5.3-flash reviews hitting 4096 completion tokens and truncating before
  a verdict line. The gate fail-closed correctly, but a capped review
  costs a full retry; reviewer `max_tokens` is a harness tunable worth raising.
- **Fork-of-itself drift:** the deployed kernel checkout stayed at f41cadd the
  whole run while origin/main advanced underneath it — by the run's own merges
  (#15 at 05:37:34Z, #16 at 05:40:55Z: **two of its own merges behind by
  session end**, not one) plus the operator's mid-run MANIFEST-scrub commit
  (1cba876, 05:47:55Z) — three commits total. The deployment picked up nothing
  mid-run; implementer worktrees (which do fetch origin/main) saw the fixes,
  the running kernel did not.
- **Notifications partially on burned topics:** 9 receipts, all HTTP 200, but
  receipts record transport, not destination. Destination attribution (from
  `DECISIONS.md` + restart timestamps): rows 1–4 (≤05:39:42Z) went to burned
  topic A — the launch-recovery bug recovered the topic value from git history
  instead of env; row 5 (05:43:54Z) went to burned topic B, the first
  rotation's target later found published in a rule-doc line; only rows 6–9
  (≥05:46:21Z) hit the owner's fresh subscribed topic. The topic-recovery bug
  and both rotations are already disclosed in `DECISIONS.md` — cited here, not
  re-litigated.

## Deployment / provenance

- Clone: `~/nightshift-dogfood`, HEAD f41cadd during the run; `src/`
  byte-identical to the validated 2e719bcd kernel (empty `git diff` on src).
- Queue: issues #6, #12, #13, #14 (`scenarios-dogfood/issue-{6,12,13,14}.json`;
  `DOGFOOD_ISSUES = {6, 12, 13, 14}` in `tests/test_scenarios.py:42`).
- Oracles: deployment-curated `scenarios-dogfood/` dir (env/default per
  c4ad280), names `close-failure-not-crash` (#12), `reap-attributes-issue`
  (#13); #6/#14 oracles exercised only as red-rechecks (their laps never
  reached verify).
- Unit env facts: `GITHUB_REPO=noor-latif/nightshift` (PR URLs in both merge
  evidence files; settings default is the toy repo, so env-set),
  `DEPLOY_MODE=none` (verify provenance skip rows + `deploy-skip mode: none`),
  `NTFY_TOPIC` env-only (settings.py:29), `SURPLUS_INTELLIGENCE_API_KEY` via
  env, name only, value never in any file (settings.py:17),
  `FACTORY_RUNTIME_CANDIDATE` unset (leak = refuse). Models: implementer
  gpt-6-luna (effort=high), reviewer glm-5.3-flash; `MAX_CONCURRENT_LAPS=1`,
  `RETRY_BUDGET=2`, `COST_CEILING_USD=0.01` per lap (enforced).
- Run window 2026-09-30T05:13:53Z → 05:56:45Z (42m52s); session-halt drained.

## Dated corrections (vs. the run brief / supervised-session record; evidence wins)

Corrected 2026-09-30 (#6 review taxonomy): the supervised-session record
described #6's sequence as mutation-apply → review "no parseable verdict" →
review substantive; the evidence dirs show attempts 2 AND 3 both failed review
with "no parseable verdict" (both reviewer outputs capped at 4096 completion
tokens and truncated before a verdict line). Attempt-3's review body does
contain the substantive fake-gh double-escaping analysis, but as a truncated
criterion-1 FAIL inside an unparseable review, not as a parseable reject
(`20260930T052139-issue-6/verdict.json`, `20260930T052749-issue-6/verdict.json`,
both `cost.json` reviewer rows).

Corrected 2026-09-30 (#13 restart account): the brief said #13's lap was
"killed by the first operator restart" and merged "mid-restart"; the evidence
shows the lap completed its full green chain at 05:41:00Z (merged 05:40:58Z) —
~2 minutes BEFORE the 05:42:52Z stop. The restart interrupted only the
supervisor's recording; the 05:43:54Z reconcile backfilled the log rows
(`20260930T053953-issue-13/timeline.json` last event 05:41:00Z vs log row 21 at
05:43:54Z).

Corrected 2026-09-30 (drift count): the brief said the deployed kernel was
"one merge behind main"; by session end it was two of its own merges behind
(#15 397717e, #16 1404d6f both on origin/main, absent from the f41cadd
deployment), plus the operator's 1cba876 scrub landed mid-run.
