# DAY 3 REPORT — second supervised lap: model switch (glm-5.3-flash), diff-artifact bottleneck isolated

Date: 2026-09-26 · Executor: day3-prep · Repo: noor-latif/nightshift · Rig: noor-latif/toy-product on [redacted-host]

## Verdict

**DAY 3 TERMINAL (PARKED)** — one lap ran end-to-end (RED → retry → RED → retry → **PARKED**, supervisor HALT) with zero human interventions during the lap and the rig serving a verified revision (5/5 live-rig probes pre-lap; live revision unchanged, correct — nothing merged). Two of three runs died at the **diff-apply gate** producing broken hand-written diffs; one was a transient transport crash. The bottleneck is now sharply localized: **diff-artifact production (hunk-count errors), independent of model family**.

## Phase A — pre-lap state

- Supervisor state reset (Day 2 ended PARKED + HALT):
  - `state/state.json` → archived to `state/state.day2.archived.json` (contained `{'6': {'retries': 3, 'disposition': 'parked'}}`, `lap: null`).
  - `state/lap-result.json` (the `RESULT_PATH` at `src/lap.py:43`) → archived to `state/lap-result.day2.archived.json`.
  - Stale `state/claims/` removed; all Day-2 evidence dirs preserved.
  - Issue **noor-latif/toy-product#6 closed** (permanently parked, 3 strikes on Day 2).
- Wiring state: model-switch commit `351c6e25` (implementer switched to **glm-5.3-flash**; reviewer already glm-5.3-flash); selector guard deploy at `44fb1e9`; **46/46 tests** on [redacted-host].
- New work unit: **noor-latif/toy-product#7** — "POST /paste with a malformed Content-Length header crashes the request instead of answering 400" (real gap in `PasteHandler._read_body()`: unguarded `int()` on the Content-Length header raises `ValueError` inside `do_POST`, killing the connection with no JSON response; small diff + one new `*_test.py`; both-gate verifiable). Filed via `gh issue create` from [redacted-host].
- **Live-rig oracle verification: 5/5 PASS** against the LIVE app on 127.0.0.1:[redacted-port] via temp-file+scp probe script (paste-round-trip POST 201 → GET 200 with exact content, malformed-JSON 400, non-string-content 400, unknown-id 404, `/health` revision == live HEAD).
- Revision check: live HEAD `bf9ca06b9c2e93e030e7916da35f765bfc9c4137` == `origin/main` (read-only `git rev-parse`).

## Launch (Phase B)

- `run.env` located at `~/factory-lab/toy-product/.factory/run.env` (gitignored; exports `SURPLUS_INTELLIGENCE_API_KEY` only — key never echoed).
- Exact command: `cd ~/nightshift && set -a && source ~/factory-lab/toy-product/.factory/run.env && set +a && nohup python3 src/supervisor.py > state/supervisor.log 2>&1 &`
- PID file `/tmp/nightshift-supervisor.pid`; supervisor PID **4181636**; first heartbeat 06:11 local / 04:11 UTC; wall-clock guard 3h; ntfy topic subscribed (but see Open Defects).

## Phase C — the lap (SUPERVISED, zero interventions)

### Lap narrative

| run | start (UTC) | end | gate | outcome | classification |
|---|---|---|---|---|---|
| 20260926T041023-issue-7 | 04:10:23 | 04:11:27 (64s) | — (transport) | **crash** | transient-crash: gateway stream cut mid-call (`IncompleteRead(700657 bytes read)`); NOT a model defect |
| 20260926T041334-issue-7 | 04:13:34 | ~04:14 | **diff-apply** | FAIL | caught-confabulation (verified): model hand-wrote the diff with miscounted hunk headers — `@@ -62,7 +62,10 @@` claims 7 old/10 new lines but the hunk body has 6 old/11 new → `git apply`: "corrupt patch at line 20". Genuine broken artifact; gate correct. |
| 20260926T041715-issue-7 | 04:17:15 | ~04:19 | **diff-apply** | FAIL → retries=3 > budget=2 → **PARKED** | caught-confabulation (verified): same class — miscounted hunks (`@@ -28,6 +28,10 @@` mismatch) **plus fabricated index hashes** (`a1b2c3d..d4e5f6a`) → "patch fragment without header at line 17". Gate correct. |

Total wall-clock 04:10:23 → ~04:19 ≈ **9 min** (limit 3h). Supervisor HALTed; state.json durable (`{'7': {'retries': 3, 'disposition': 'parked'}}`, `lap: null`); worktree auto-removed. No merge, no deploy.

### The bottleneck, sharpened

Across both live laps (Day 2 + Day 3): **6 model attempts total** — 3 deepseek-v4.1-flash (Day 2), 2 glm-5.3-flash (Day 3), 1 transport crash — and **4 of 6 died producing an invalid diff artifact**. Both model families fail at hand-written hunk counts. The failure is not model-specific competence; it is the **interface**: requiring the implementer to emit a context-exact unified diff makes hunk arithmetic a mandatory, unverifiable-by-the-model step.

**Recommended product-build fix (pending owner decision):** change the implementer contract to emit **full file contents** (app.py, new test file) and have `lap.py` synthesize the diff itself (e.g. `git diff --no-index` old vs new). This eliminates hand-written hunks entirely — the only remaining artifact the model must produce is code, which is what it is actually good at. Cost: slightly larger prompts/responses; benefit: removes the single failure class that has parked 100% of live laps so far.

### Cost (S3, from usage fields)

| run | cost |
|---|---|
| 20260926T041023 (transport crash) | $0 (no cost.json — no completed calls) |
| 20260926T041334 | $0.0000462436 (implementer, 8675 tok) |
| 20260926T041715 | $0.00001 (implementer, 9034 tok) |
| **total** | **$0.0000562436** (ceiling $0.01/lap; ~0.56% of ceiling) |

## Open defects (both new, both observability — the gates themselves performed correctly)

1. **ntfy receipts: ZERO for Day 3.** `state/evidence/ntfy/receipts.json` contains only the 4 Day-2 lines (issue-6 retry/retry/parked + HALT). The Day-3 park notification and supervisor HALT notification were not recorded. Terminal-state notification is currently unobservable/likely broken for Day 3 — needs investigation before the next lap.
2. **`state/supervisor.log` is EMPTY (0 bytes)** despite the nohup redirect `> state/supervisor.log 2>&1` (the exact Day-2 command pattern). Either the supervisor writes nothing to stdout/stderr (possible — Day 2's log was also empty per Day 2 evidence) or output is going elsewhere. As it stands, a supervisor crash leaves no log trail. Recommend the supervisor write structured tick/lifecycle events to a log file itself.

## Success-criteria status

| criterion | status |
|---|---|
| S1 (end-to-end lap reaches terminal state) | **PASS** — parked + HALT, full evidence, zero interventions, 2nd consecutive day |
| S2 (zero false greens) | **UNEXERCISED** — 5/5 caught at pre-verify gates across Day 2+3, zero false greens, zero false reds, but no green lap yet so merge/deploy remain red-demo'd only |
| S3 (cost) | **PASS** — $0.000056 total, far under ceiling |
| S7 (ntfy receipts) | **FAIL for Day 3** — 0 receipts recorded despite terminal states reached (Day 2: 4/4 recorded). Open defect above. |

## Final state

- Deployed revision on :8642: `bf9ca06b9c2e93e030e7916da35f765bfc9c4137` — **unchanged and correct** (nothing merged; pre-lap probes 5/5).
- Issue: noor-latif/toy-product#7 **open, parked** (3 strikes; selector will never re-dispatch). No PR created — merge gate never reached.
- Evidence tree: 3 new run-id dirs (`20260926T04*`) with timeline/verdict per run, `claimed.diff` + `implementer_raw.txt` + `cost.json` for runs 2–3 (run 1 has timeline+verdict only — crashed before implementer call completed) alongside the Day-2 evidence.

## Interventions (honesty bar)

**During the lap: 0.** Dispatch, retries, park, and HALT all autonomous. Pre-lap state reset (Step 1) and issue filing (Step 2) were the sanctioned prep role; observation was read-only polling throughout.

## Verdict line

**DAY 3 TERMINAL (PARKED)** — chain ran clean end-to-end twice in two days; gates caught both broken diffs; $0.000056 total; 0 interventions; bottleneck isolated to diff-artifact production with a concrete fix proposed; two observability defects opened.
