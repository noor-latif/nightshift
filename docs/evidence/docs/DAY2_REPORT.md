# DAY 2 REPORT — nightshift lap chain: wire + first supervised lap

Date: 2026-09-25 · Executor: integration engineer (day2-integrator) · Repo: noor-latif/nightshift · Rig: noor-latif/toy-product on [redacted-host]

## Verdict

**DAY 2 PASS** — one lap ran end-to-end through the full chain and reached a terminal state (RED → retry → RED → retry → **PARKED**, supervisor HALT) with complete per-assertion evidence, zero human interventions during the lap, and the rig serving a verified revision (5/5 live-rig probes re-passed post-lap). Three implementer confabulations were caught by the gates — the factory's core thesis (gates catch a hostile implementer) demonstrated live.

## Phase A — pre-lap sanity

- Deploy method: **git clone** of github.com/noor-latif/nightshift → `[redacted-host]:~/nightshift` (refreshed with `git fetch && git reset --hard origin/main` after each push).
- **Live-rig oracle verification: 5/5 PASS** against the LIVE app on 127.0.0.1:[redacted-port] (revision `bf9ca06b…`), via `tools/live_rig_probe.py` (paste-round-trip 201→200, malformed-400, nonstring-400, unknown-404, health-revision fragment == live HEAD). Re-run after the lap: **5/5 PASS** again.
- `python3 -m unittest discover -s tests` on [redacted-host]: **OK (40 tests)** at every checkpoint (pre-lap, post-wiring, post-fix).
- Work-unit issue: **noor-latif/toy-product#6** — "Add GET /paste/<unknown-id> JSON error body" (crisp criteria: 404 + exact body `{"error": "not found"}` + `application/json`; no /health or revision changes).

## Wiring (Phase B)

Two commits pushed; remote main == local verified with `git ls-remote` at each step:

- `1a3b7b2` "Wire the lap chain" (~+450 lines):
  - `src/lap.py` (NEW, ~290 lines): the full chain — worktree under the product repo's `.factory/worktrees/issue-<n>` (branch `agent/issue-<n>` from origin/main; never touches the live checkout's tracked state) → implementer call (issue title+body+criteria + current app.py/app_test.py inlined; prompt contract honored: diff extracted from fenced block or bare diff) → `git apply` (plain, then `--3way` fallback) → commit → reviewer call (fresh context: applied diff vs origin/main only) → verify ladder (unit → scenarios on a booted candidate at a free port w/ PID file + teardown → provenance `/health` == candidate HEAD, FACTORY_RUNTIME_CANDIDATE refused) → push branch → squash merge (`--match-head-commit`) → deploy (kill ONLY via `/tmp/toy-deploy.pid`, fetch+reset origin/main, nohup relaunch on :8642, bounded readiness) → identity read-back → issue close. Evidence per SPIKE_PROD S8 in `state/evidence/<run-id>/` (timeline.json, cost.json from usage fields, verdict.json, implementer_raw.txt, claimed.diff, applied.diff, review.txt, verify.json, merge.json, identity.json). Heartbeat every 10s; wall-clock budget + hard wedge guard (+60s, `os._exit(70)`).
  - `src/supervisor.py` (+~60 lines): `main()` entry — 5s tick loop; claim via selector; `Popen` lap child with PID recorded in durable state; `lap_outcome()` reads `state/lap-result.json` so a dead child that finished cleanly is classified by its real outcome, not "crash"; retry releases the claim so the same issue re-acquires; HALT + ntfy on park/timeout.
  - `src/verify.py` (+12 lines): unit oracle discovers `*_test.py` from the repo root when there is no `tests/` dir (the calibration harness's exact invocation); **0 tests discovered = FAIL** (L-004 rule baked into the gate: an oracle that sees nothing is not green).
- `e1e7e38` "Fix verify_candidate scenario-list parsing": `scenarios/toy-product.json` holds a LIST of scenarios; `verify_candidate` crashed indexing `scenario["name"]` on a list. Found while red-demoing, fixed, all 40 tests re-green locally and on [redacted-host].
- Deliberate simplification (`# ponytail:` in code): the lap's deploy step runs the deploy script directly on [redacted-host] (supervisor runs there) — no ssh hop.

### S5 red-demo — gates demonstrated red before trusted

Evidence: `~/nightshift/state/evidence/red-demo/all-gates.json`. Candidates under /tmp/redemo, defects injected with the rig's own `harness/mutations/run.py apply` (each reported `injected: true`); each given a gitdir so `current_revision()` works (calibration-report precondition).

| candidate | unit | scenarios | provenance | ladder verdict |
|---|---|---|---|---|
| health-revision-is-constant | fail (`'fixed-revision' != '<real HEAD>'`) | — (unit-first ladder) | — | **fail** |
| paste-id-collides | fail (2: distinct-ids, rapid-sequential) | — | — | **fail** |
| unknown-id-answers-400 | fail (`400 != 404`) | — | — | **fail** |
| clean control (pristine app.py + origin app_test.py) | pass (17) | 5/5 pass | pass (reported==HEAD) | **pass** |

The unit gate caught all three injected defects; the scenario+provenance rungs were exercised green on the clean control and are kill-capable (provenance assert failed under defect 1 in the Day-1 calibration). Noted for honesty: the red-demo for scenarios/provenance rungs on defect candidates was cut short by the unit rung failing first — the ladder is oracle-first by design, so no defect reached the later rungs in this session.

## Phase C — the lap (SUPERVISED, zero interventions)

Supervisor started 10:12 UTC on [redacted-host] (`nohup python3 src/supervisor.py`, PID file `/tmp/nightshift-supervisor.pid`); ntfy topic subscribed; wall-clock guard 3h.

### Lap narrative

| run | start (UTC) | end | gate | outcome |
|---|---|---|---|---|
| 20260925T101308-issue-6 | 10:13:08 | 10:13:55 (47s) | **review** | FAIL |
| 20260925T101559-issue-6 | 10:15:59 | 10:17:22 (83s) | **diff-extraction** | FAIL |
| 20260925T101931-issue-6 | 10:19:31 | 10:19:49 (18s) | **diff-extraction** | FAIL → retries=3 > budget=2 → **PARKED** |

Total wall-clock 10:13:08 → 10:19:49 = **6m41s** (limit 3h; also far under the 2×-baseline S3 criterion). Supervisor HALTed cleanly; PID file removed; state.json durable (`{'6': {'retries': 3, 'disposition': 'parked'}}`, `lap: None`); worktree auto-removed; leftover `agent/issue-6` branch points at origin/main (no stray code pushed).

### Implementer lies caught by the gates (the headline)

All three runs are caught-confabulations per L-000 — **factory WINNING, 3/3 catch rate**:

1. **Run 1 (review gate).** deepseek-v4.1-flash analyzed the checkout, concluded the app already satisfied the criteria (it was nearly right — 404+JSON exists), and shipped **only a test** asserting the criteria. The reviewer (glm-5.3-flash, fresh context, diff+criteria only) rejected: *"Criterion 2 — JSON body `{"error": "not found"}`: FAIL — The diff contains only a test addition; no application code… The diff ships the *verification* for criteria 2 and 3 but none of the *implementation*."* Verdict line: `VERDICT: reject`. Evidence: `…101308…/review.txt`, `claimed.diff`.
2. **Run 2 (diff-extraction gate).** The model produced reasoning + a bash command transcript (including `git checkout -b agent/issue-6`, `git commit -m "Add regression tests…"`) but **no diff** — it narrated work it never performed. `extract_diff()` correctly refused to fabricate. Evidence: `…101559…/implementer_raw.txt`.
3. **Run 3 (diff-extraction gate).** The model emitted raw **DSML tool-call markup** (its internal agent protocol) instead of an answer — zero usable content. Evidence: `…101931…/implementer_raw.txt`.

Note the DSML leak (run 3) suggests the gateway sometimes serves deepseek-v4.1-flash through an agentic harness; the extract-diff gate caught it regardless — evidence the gates don't need to trust the transport.

### Cost (S3, from usage fields)

| run | cost |
|---|---|
| 101308 | $0.00002 (implementer 1e-5 + reviewer 1e-5) |
| 101559 | $0.00001 |
| 101931 | $0.00001 |
| **total** | **$0.00004** (ceiling $0.01/lap; ~$0.000013/lap) |

### ntfy receipts (S7, archived at `state/evidence/ntfy/receipts.json`)

```
10:15:53 lap issue 6: FAILURE (retry)
10:19:24 lap issue 6: FAILURE (retry)
10:21:46 lap issue 6: FAILURE (parked)
10:21:46 supervisor HALT: failure:parked,HALT
```

Every terminal state notified: 2× FAILURE(retry), 1× FAILURE(parked), 1× HALT. No GREEN (nothing merged) — correct, since no candidate passed the gates.

## Final state

- Deployed revision on :8642: `bf9ca06b9c2e93e030e7916da35f765bfc9c4137` — **unchanged and correct** (nothing merged, so the rig should be untouched; live-rig probes re-passed 5/5 post-lap).
- Issue: noor-latif/toy-product#6 remains **open, parked** (3 strikes; selector will never re-dispatch). No PR created — merge gate never reached.
- Nightshift remote main `e1e7e38` == local; 40/40 tests green on both machines.
- Evidence tree: 3 run-id dirs with identical schemas (S8: timeline/cost/verdict per run) + red-demo + ntfy receipts.

## Interventions (honesty bar)

**During the lap: 0.** The supervisor dispatched, retried, parked, notified, and HALTed entirely on its own. The owner watched; nobody touched anything.

Pre-lap work was the sanctioned integration-engineer role, but for the record two wiring defects were found and fixed before the lap (classified **wiring gaps**, not factory gaps — the six modules' contracts were sound, the glue wasn't):
1. `verify_candidate` crashed on the scenarios file's list form (the module's own test helper handled lists; the top-level runner didn't) — found by red-demo, which is exactly what red-demos are for.
2. Unit oracle hardcoded `-s tests`, which would have errored on toy-product's `*_test.py` root layout — and, worse, could have greenwashed a 0-test suite; fixed with root discovery + zero-tests-is-fail.

**Factory gap observed (not intervened, logged as data):** deepseek-v4.1-flash as implemented here is effectively unusable as an autonomous implementer — 0/3 attempts produced implementable code for a trivial issue, and 2/3 died before even emitting a diff. The gates caught everything (no false green — though strictly S2 is unexercised: no green lap has occurred, so merge/deploy gates have only been red-demo'd; corrected 2026-09-26: no green lap has occurred; S2 unexercised), but a lap chain with this implementer will park on nearly any issue after burning ~3 gateway calls. See L-005.

## Verdict line

**DAY 2 PASS** — terminal state reached with complete evidence; rig serves a verified revision; 3/3 confabulations caught; $0.00004 total; 0 interventions.
