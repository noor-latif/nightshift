# Calibration report — toy-product verification gate

Date: 2026-09-25 · Executor: delegated agent (owner-approved) · Repo: `noor-latif/toy-product` on [redacted-host] · Live revision at start and end: `bf9ca06b9c2e93e030e7916da35f765bfc9c4137`

## Verdict

**CALIBRATION PASS** — 7/7 defects red (CAUGHT by the gate), clean control green (ESCAPED), live app untouched.

## Install verification

- `harness/mutations/defects.json` landed via scp from `~/repos/factory-docs/DEFECTS_DRAFT.json` (local), with the file's own instruction applied: the `_scaffold` marker `SCAFFOLD_EXAMPLE_DELETE_THIS_LINE_WHEN_YOU_WRITE_YOUR_OWN` replaced by an install marker. No other change.
- Parses as JSON; exactly 7 defects with the expected ids:
  1. `health-revision-is-constant`
  2. `paste-id-collides`
  3. `unknown-id-answers-400`
  4. `body-read-off-by-one`
  5. `non-dict-body-leaks-500`
  6. `type-guard-reduced-to-truthiness`
  7. `responses-declared-plain-text`
- Companion tests installed into `app_test.py` (`PasteServiceTest`), verbatim from `DEFECTS_DRAFT.md` → `DEFECTS_DRAFT_APPENDIX`: `test_post_rejects_non_dict_json_body`, `test_responses_declare_json_content_type`. The two tests are in the same install as the defect set, as the draft requires; suite grew 15 → 17 tests (confirmed: clean run reports `Ran 17 tests`).
- All 7 `find` anchors verified to match [redacted-host]'s `app.py` exactly once (pre-verified locally by the draft author; re-verified on [redacted-host] before any run).
- Live checkout after install and after all runs: `git status --porcelain` shows only ` M app_test.py` and ` M harness/mutations/defects.json` — exactly the two documented install targets. `app.py` untouched; live :8642 process (PID 1000894) untouched.

## Evaluator used

Documented harness entrypoints only:
- Gate: `python harness/ci.py` (`harness.config.json`: static `py_compile app.py` + unit `python -m unittest discover -s . -p '*_test.py' -v`, with the rung-naming `GATE_FAILED:` markers).
- Mutation: `python harness/mutations/run.py list|apply|score` — `apply` performs the textual find/replace into a candidate copy (ambiguous anchor ⇒ NOT_INJECTED; all 7 reported `injected: true`), `score` maps gate exit + log to CAUGHT / ESCAPED / INCONCLUSIVE.
- No explicit per-defect evaluator entrypoint exists beyond these (e2e/holdout rungs are shared-workflow-owned; defect runs here exercised the static+unit gate).
- Candidates were throwaway copies under `/tmp/calib/<defect-id>` per the file's own `copy` list (`app.py`, `app_test.py`, `harness`). No candidate starts a server (no e2e rung configured), so there were no candidate processes and no PID files to clean. Nothing under the live repo was created or removed.

### Harness precondition note (candidate git identity)

The bare copy list produces a snapshot with no gitdir, and `current_revision()` (app.py:18) shells out to `git rev-parse HEAD` — the clean control's first run failed with `http.client.RemoteDisconnected` from `/health`, not a product failure. Candidates were therefore given their own detached gitdir (`git init --separate-git-dir /tmp/calib/gitdirs/<name>`) with a single orphan coordinate commit recording the live revision. This changes no source content; `/health` provenance remains exercisable, and `test_health_reports_ok_and_git_revision` proved it by failing under defect 1 with the real assertion (`'fixed-revision' != '<coordinate rev>'`), while passing in the clean control. Candidate gitdirs live in `/tmp/calib/gitdirs/`; no git objects or refs were created in the live repo.

## Red table (7/7)

Every defect's required must-fail test (DEFECTS_DRAFT.md column) failed; observed-vs-expected captured verbatim from the candidate's unittest log.

| defect id | failed required test(s) | evidence (observed vs expected) | verdict |
|---|---|---|---|
| `health-revision-is-constant` | `test_health_reports_ok_and_git_revision`, `test_health_reports_factory_runtime_candidate_exactly` | `AssertionError: 'fixed-revision' != '2109341b8dcfbd17cc5d4b673567f718ebd89f43'` (candidate coordinate rev; the candidate-env revision, distinct from the live HEAD — asserted equality fails either way) | RED (CAUGHT, unit) |
| `paste-id-collides` | `test_two_pastes_keep_distinct_ids_and_content`, `test_rapid_sequential_posts_each_resolve_with_own_content` | `AssertionError: 'stable-id' == 'stable-id'` | RED (CAUGHT, unit) |
| `unknown-id-answers-400` | `test_unknown_id_returns_404` (required `test_get_without_id_returns_404` did not fail — see note) | `AssertionError: 400 != 404` | RED (CAUGHT, unit) |
| `body-read-off-by-one` | `test_post_returns_201_with_non_empty_id` (+ 7 more tests failed) | `AssertionError: 400 != 201` | RED (CAUGHT, unit) |
| `non-dict-body-leaks-500` | `test_post_rejects_non_dict_json_body` (companion test) | `http.client.RemoteDisconnected: Remote end closed connection without response` (AttributeError → server aborts request instead of answering 400) | RED (CAUGHT, unit) |
| `type-guard-reduced-to-truthiness` | `test_post_rejects_non_string_content` (required `test_post_rejects_missing_content` did not fail — see note) | `AssertionError: 201 != 400` (content `42` accepted, stored) | RED (CAUGHT, unit) |
| `responses-declared-plain-text` | `test_responses_declare_json_content_type` (companion test) | `AssertionError: 'text/plain; charset=utf-8' != 'application/json'` | RED (CAUGHT, unit) |

### Draft-table note (two must-fail columns list two tests; one of the two did not fail)

- `unknown-id-answers-400`: `test_get_without_id_returns_404` (GET `/paste` with no id) did not fail — the mutated handler still reaches the no-id 404 branch before the store lookup, and the defect only rewires the unknown-*id* branch. The defect is red on its primary test (`test_unknown_id_returns_404`, `AssertionError: 400 != 404`); no action taken, recorded as an observation for the draft owner.
- `type-guard-reduced-to-truthiness`: `test_post_rejects_missing_content` did not fail — `not content` still rejects `{}` (missing → `None` → falsy), so only the non-string test distinguishes the weakened guard, which is exactly the defect's thesis in the draft. Red on `test_post_rejects_non_string_content` (`AssertionError: 201 != 400`).

Both defects remain RED by the agreed criterion (≥1 required test fails).

## Clean control

Clean candidate (no mutation, identical procedure): gate exit 0, `CHECKS_OK mode=ordinary`, `Ran 17 tests` / `OK` → scored **ESCAPED / gate-ok** = **GREEN**. The suite judges and can also let pass — the reds above are signal, not noise.

## Live app before/after

| | before install | after all runs |
|---|---|---|
| `curl -s http://127.0.0.1:[redacted-port]/health` | `{"status": "ok", "revision": "bf9ca06b9c2e93e030e7916da35f765bfc9c4137"}` | identical |
| `git rev-parse HEAD` | `bf9ca06b9c2e93e030e7916da35f765bfc9c4137` | identical |
| serving process | PID 1000894 | PID 1000894, untouched |

## Verdict

**CALIBRATION PASS**
