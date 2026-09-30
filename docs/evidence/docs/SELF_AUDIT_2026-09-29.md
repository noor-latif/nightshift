# SELF_AUDIT_2026-09-29 — adversarial audit of nightshift's own code

Target: `~/nightshift/src/` @ 70035e7 (deployed == origin main == canonical factory-spike).
All probes run in a throwaway clone (`/tmp/audit-probe`) — no writes to nightshift state.
Baseline: full suite in the clone = **125 passed**, yet every kept finding below reproduces
against the real code — each is a coverage hole in the wiring/untested-real-path class this
codebase keeps shipping.

**VERDICT: 6 kept (1 blocker, 3 critical, 2 major); 4 discarded (calibration note).**

## KEPT findings (ranked)

| # | Location | Class | Mechanism | Trigger / RED repro sketch | Sev | Issue-ready |
|---|----------|-------|-----------|-----------------------------|-----|-------------|
| K1 | selector.py:54 `claim_next()` | wiring gap → livelock | `claim_next` skips `parked`/`timeout-park` dispositions but NOT `merged`. supervisor's red-recheck path (supervisor.py:177-184) and reconcile's terminal path both mark issues `merged` while the GitHub issue can remain open. Every tick re-claims it → `already-satisfied` → claim removed → re-claimed: infinite hot loop, zero laps, `DRAIN` never reached. Deployed state.json already shows 17/18/19/21 disposition=merged alongside the 21:56 "drained" halt — reopen any of them (or one `gh issue close` failure) and the next launch spins forever. | Fake gh emits issue 18 open + no PRs; `claim_next(..., dispositions={"18": {...,"disposition":"merged"}})` returns a NEW claim (observed: `{'issue': 18, ...}`). RED: same call must return None for merged issues. 3-line repro exists and passes. | **blocker** | Y |
| K2 | supervisor.py:240-289 `tick()` vs 461-463 `main()` | crash path → premature session end (untested real path) | Order inside one tick: dispatch → DRAIN/BLOCKED event appended → reconcile. `main()` acts on DRAIN *after* tick returns, but the claim written by this tick's `claim_next` was reaped by reconcile in the same tick (`dispatch:idle` + `reclaimed:...` in one events list, observed). Worse: after a `start_lap` spawn failure (claim written, Popen raised, state.json never saved), tick2 emits `DRAIN:0 parked, 0 merged` and main() **session-halts "queue drained"** while the issue is still open with full retry budget. Reproduced end-to-end with real selector + real reconcile + fake gh. | tick1: start_lap raises after claim write (real crash window: disk full, fork fail). tick2 with healthy deps → events `[dispatch:idle, DRAIN:0 parked, 0 merged, reclaimed:...18.json]` (observed). RED: an open claim/issue must never produce DRAIN. | **critical** | Y |
| K3 | lap.py:223-265 `apply_mutations()` | accounting/correctness in the mutation gate | Trailing-newline handling inserts a spurious blank line on the most common anchor shape. `_norm_indexed` returns a normalization whose last char is a `\n` that maps to the *original* line's trailing newline, but the code unconditionally does `end -= 1` for ANY needle ending in `\n` (line 260) — including anchors whose final newline is genuine content. Any replace ending in `\n` then leaves the file's own newline: `A\nB\nC\n`, find `A\nB\n`, replace `X\n` → **`X\n\nC\n`** (observed). A model doing a textbook rename gets a corrupted file — extra blank lines accumulate per mutation, review sees garbage, verify may fail on unrelated lines. Zero multi-line-anchored-to-EOF tests exist. | `apply_mutations([{"file":"app.py","find":"A\nB\n","replace":"X\n"}], wt)` → output `X\n\nC\n` (observed). RED: must be `X\nC\n`. | **critical** | Y |
| K4 | verify.py:262/64 `wait_ready`→`free_port` raise path | unhandled exception burns retry budget on infra failure | `verify_candidate` catches `Hold` only around the provenance block (309). `free_port` raising `Hold("no free port in scenario range")` from `run_scenario` (236) escapes `verify_candidate` entirely → lap.py:425 generic `except` → outcome **crash** → retries+1 → after RETRY_BUDGET(2) the issue is **parked**. 11-port range + SO_REUSEADDR already documented as scarce; a slow-releasing boot converts a transient resource condition into permanent park. The design's "Hold is never a pass" also implies Hold must reach the supervisor AS hold — it currently can't from the scenario ladder. | Occupy 8900-8910, call `verify_candidate(tmp, pid, sd, issue=None)` → raises `Hold` (observed). RED: verdict must be "HOLD" (fail hold-path, no retry burn). | **critical** | Y |
| K5 | agent.py:40-66 `parse_stream()` | parse fragility → uncontrolled retry budget | `json.loads(payload)` (54) unguarded: any malformed SSE data line raises `json.JSONDecodeError`, which is NOT `TransientError`, so chat's retry ladder (156-161) doesn't catch it → escapes as generic `Exception` → lap outcome crash → retries+1. Same for a truncated final chunk (network cut mid-stream). The module's own contract treats "stream ended without finish_reason" as a transient retry; a bad chunk mid-stream deserves the same, and instead it parks issues after 2 occurrences. | `parse_stream(b'data: {"choices":[{"delta":{"content":"hi"}}]}\n\ndata: NOT-JSON {\n\ndata: {"choices":[{"finish_reason":"stop"}]}')` → `JSONDecodeError` escapes (observed). RED: must raise `TransientError("stream chunk parse")`. | major | Y |
| K6 | supervisor.py:443-456 `main()` tick-error loop | resource/starvation wedge after bookkeeping error | On tick exception main() sleeps 5s and re-enters the loop — but if the exception struck mid-dispatch *after* `claim_next` wrote the claim (e.g. the K2 spawn failure), the loop **never retries that issue**: claim file fresh for 3h (LAP_WALLCLOCK), claim_next `continue`s, `dispatch` returns idle every tick. One transient OSError (e.g. `save_state` disk hiccup) permanently strands an open issue inside a single session. The c9977b5 "log + continue" fix made death visible but left the stranding unaddressed. | tick with start_lap raising post-claim (observed in K2 repro): claim persists fresh; subsequent ticks all `dispatch:idle`. RED: tick-error must release/break its own claim before continue. | major | Y |

## Test-coverage defects (independent of fixes)

- `fake_deps` (test_supervisor.py:15-26) still supplies no `lap_outcome`/`red_recheck`/
  `reconcile_observations` — tests exercise tick only through paths that never reach them;
  K2's order bug is invisible to every existing test because no test drives dispatch-idle
  and reconcile in the same tick with a fresh claim on disk.
- `TestApplyMutations` (test_lap_mutations.py:79-166) never uses a multi-line anchor with
  trailing `\n` — K3's corruption sits exactly between its cases.
- `TestVerifyAgainstFixture` never exhausts the port range; K4's Hold-escape needs a
  no-free-port scenario, absent from the suite.

## Hunt-class sweep notes (what was checked, found clean)

- **Wiring/dependency gaps (class 1)**: full AST scan of every `deps[...]`/`deps.get(...)`
  reference vs main()'s deps literal — all 10 keys wired; no undefined module-level names;
  no imports of missing names (pyflakes-equivalent AST pass; only unused imports:
  merge.py `json`, supervisor.py `EVIDENCE_DIR`, verify.py `urllib` — style, not filed).
  `COST_CEILING_USD` is defined-but-never-enforced (candidate for docs/parking, not a bug).
- **Untested real paths (class 2)**: enumerated every real signature (start_lap(issue,lap),
  kill_lap(lap), lap_outcome(lap), claim(now), reconcile(now)→[(path,claim)],
  break_claim(path,now), red_recheck(issue)) — all invoked with correct arity in the
  surviving code; the remaining divergence is the *absence* of tests driving them together
  (K2/K6), not a wrong call.
- **Crash paths (class 3)**: `lap_outcome` guards foreign/malformed result files correctly
  (probed: cross-issue result → crash, not false terminal). gh/git failures raise loud
  inside lap.py `_gh`/`_git` → caught by run()'s generic handler → crash outcome — designed.
- **Accounting (class 4)**: reconcile's live-lap exclusion, terminal-result reap-only,
  unparseable-claim reap — all verified by existing tests and re-probed clean. A suspected
  reconcile/handle_lap_end retry double-count across restart was falsified by a targeted
  probe (see calibration) — accounting clean.
- **Race/timing (class 5)**: heartbeat cadence 10s vs TTL 120s is sound; the stale-window
  at child boot (up to ~5s of loop delay before first write) is benign because pid_alive
  gates it — probed, not filed. flock scope correct (held for process lifetime). The
  known lap-end lag is not re-reported.
- **Gate holes (class 6)**: verdict precedence hold>fail>pass verified by reading +
  existing tests; provenance Hold refusal reachable; mutation normalization
  trailing-whitespace tolerance verified — the *content* bug found there is K3.
- **Parse fragility (class 7)**: `criteria_from` probes (bold, case, inline, singular)
  all acceptable; reviewer VERDICT regex handles case/space/bold/no-space variants
  (probed: all accept correctly); the malformed-chunk SSE failure is K5.
- **Resource leaks (class 8)**: `_worktree_add` self-heal re-probed against real git —
  missing-but-registered path prunes and re-adds cleanly; run()'s finally-reap is now
  unconditional (pre-assigned path, verified 5284986); verify's no-git tmp boot has
  try/finally with rmtree. Clean.
- **Injection (class 9)**: all gh/git calls are list-argv (no shell=True anywhere,
  verified by grep); issue number is int-coerced at every boundary (paths use
  `"issue-%d"`); titles never reach file paths. Clean.

## Calibration — discarded suspicions (checked, not filed)

- `_worktree_add` returning a failed `CompletedProcess` silently when stderr lacks all
  three magic substrings — condition reachable only with a *simultaneously* missing and
  registered worktree, which self-heals (probed rc=0). Discarded.
- `evaluate_assertion` `{{port}}` substitution colliding with saved values, and
  `frag in body` substring semantics on fragment checks — plausible-but-no observed
  failure in this scenario set; would need a live scenario to reach. Discarded.
- `handle_outcome("queue-empty")` reachable only from selector internals, never from
  supervisor outcomes — dead-code suspicion, no failure mechanism. Discarded.
- Verdict-regex tolerant of `**VERDICT: accept**` etc. — all probed variants behave; the
  "First reject then accept" multi-verdict case takes the FIRST (reject) — conservative
  direction (fails closed). Discarded.
- `criteria_from` returning the whole body when the heading is absent — deliberate
  fallback, probed benign. Discarded.
- **Retry double-count across restart (withdrawn during verification)**: suspected that
  reconcile's crash-at-reap and handle_lap_end's crash could both increment retries for
  one lap. Falsified by a targeted probe: handle_lap_end removes the claim file (so
  reconcile never sees it), the live-issue exclusion guards the in-flight path, and the
  reap path counts once with tick's break_claim removing the claim (observed: retries=1
  in all scenarios, claim gone after the reap tick). The interlock holds; no repro fails.
  Discarded.

Queue depth: 6 kept findings — K1, K2, K3, K4 each file-able with the observed repro as
RED; K5/K6 file-able with a small crafted fixture. Deep enough for a 3–5 issue self-run.

## Post-filing correction (2026-09-29, gh issue edit history as timestamp)

The criteria-1 wording of filed issues #2/#4/#6 was unsatisfiable-by-construction
under the factory's own provided-files contract: it demanded a standalone repro
script, but allowed_files comes from the checkout view (mutation-parse rejects any
other file — no new-file escape hatch) and the reviewer's view is CODE_PATHS=src+tests
only, so a scenarios/issue-N.json oracle or a tests/ test can never pair with a new
standalone file. Issue-authoring defect by the audit, not model failure. Issue #2's
first lap was rejected on exactly this (gate=review, criterion-1-only, criteria 2/3
PASS, correct fix). All three bodies' criterion 1 were edited 2026-09-29 to state the
repro requirement is satisfied by this issue's oracle (scenarios/issue-N.json, which
implements the repro and gates it at verify) and/or an equivalent test inside tests/;
no standalone new file is required or expected. Any gate=review park with a
criterion-1-only rejection BEFORE this edit is a wording artifact — post-run scoring
must attribute it as instrument failure, not model failure. #3/#5 confirmed clean
(inline `python3 -c` probes); #1 closed, untouched; RED evidence in all bodies
byte-identical.
