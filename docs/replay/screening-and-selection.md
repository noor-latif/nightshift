# Repo viability screen and instance selection

Read when screening candidate repos for a replay run or choosing historical PR instances: the exact probe rows, the invalidated candidates, the selection validation loop, and the WHY behind each criterion.

## 2. Repo viability screen

The binding constraint is the harness's EXACT command, not the repo's CI. Unset native config, `src/verify.py:37-41` runs `python3 -m unittest discover -s tests` IF a top-level `tests/` dir exists, ELSE `discover -s . -p "*_test.py"`; `Ran 0` = FAIL, never a vacuous pass (verify.py:34-35). Probe with whatever argv the instance will DECLARE — that IS the harness command now: stdlib repos with the discover command above; a pytest repo with `python3 -m pytest -q -p no:cacheprovider` (the exact argv recorded in the instance's native config) and the pytest zero-tests signatures. The bare-`unittest discover` trap generalizes: a row measured with a command other than the declared suite argv is VOID — three candidate repos measured green on the wrong command and were invalidated (RESEARCH dated correction 2026-09-30). `python-ecdsa` looked fine until the harness command found zero tests.

Screen checklist:
- [ ] Harness-command probe green: fresh shallow clone, run the exact verify.py command. If tests live elsewhere (e.g. `pypika/tests/`), plan the layout adaptation (§4) and re-probe adapted.
- [ ] Test imports: stdlib + pytest only. `import pytest` is now an allowed test import (pytest is a candidate-side runner invoked by argv); `parameterized`, fixtures, or any other non-stdlib test dep still disqualify unless provisioned via a trusted prepare argv. tenacity's tests are TestCase classes yet `import pytest` at module top — CI name is NOT the criterion (RESEARCH §3).
- [ ] Full suite < 600s — verify.py has a hard subprocess timeout; slower suites crash verify with unhandled TimeoutExpired instead of recording FAIL (BATTLE_TEST dated correction).
- [ ] Default branch: `main` preferred, but `master` is fine — the replay fork pins main anyway (§4). This widens the pool.
- [ ] Char budget: measure the CODE_PATHS-matched source view per base (§4) — never default.
- [ ] Permissive license (Apache-2.0/MIT/BSD); you will fork, adapt layout, and publish evidence.
- [ ] Issue tracker with ≥5 merged bugfix PRs that ADD tests (GitHub search: `repo:X type:pr is:merged test`). Zero-dep unittest repos skew small/older — trade "actively maintained" against "harness green".

## 3. Instance selection

Per candidate PR, require ALL of (RESEARCH §4 + addenda; worked examples in REPLAY_INSTANCES):

- [ ] Merged PR linked to an issue — linkage by REFERENCE, not closing keywords: real maintainers rarely use them; pypika's #834 is still open and the PR title just carries `#834`. Bar = "PR body references issue + issue text is the behavioral spec" (REPLAY_INSTANCES protocol finding 1).
- [ ] Fix touches ≤2 source files, ≤~30 LOC source — easy tier first (LOC is the endorsed difficulty proxy).
- [ ] Test diff ADDS-ONLY: no existing test method/class modified; import-block additions permitted (finding 2). A PR that rewrites an existing test's expectation leaves the base suite encoding pre-fix behavior, so a CORRECT fix fails the unit gate — a false red charged to the model (test-integrity addendum). Check: `grep -c '^-[^-]'` on the test diff.
- [ ] Contamination: truncate issue text at the PR creation date (strip later comments); discard if issue text quotes the gold patch (#732 disqualified for exactly this); discard if the PR spans multiple issues or implements a different approach than the issue proposes.
- [ ] Duplicate-name shadowing: a PR adding a test method whose name collides with an existing one shadows it (unittest keeps the last definition; #837's second `test__between_datetime` silently skipped the base test). Rename in the holdout.
- [ ] MANDATORY per-instance memorization flag — there is no "global none"; every instance carries its flag: PR merge date + issue-text age + implementer/reviewer model names; cutoffs unknown → flag stands. Prefer post-cutoff PRs. Real run: #837 LOW (both 2025), #841 ELEVATED (2025 merge, 2021 issue), #539 MAXIMAL (both 2021) — each green's capability weight differs accordingly (memorization addendum + REPLAY_SCORE dated correction).

Validation loop per instance — run at the BASE commit (PR merge-commit parent), adapted layout (RESEARCH §4 step 4; exact commands in REPLAY_INSTANCES):
1. Base + adaptation → full suite green TWICE (flaky filter).
2. Apply path-rewritten expert test patch → new tests RED at base; full-suite RED check shows exactly the F2P failures, zero collateral sibling breakage.
3. Apply gold source patch → new tests GREEN; full suite green.
4. Record: F2P test ids, P2P count, gold LOC, per-base view size (`wc -c` over CODE_PATHS files — the measure varies per base: pypika 167,615–201,219 bytes across three bases; master-HEAD figures understate).

## Native-suite scope and vacuous FAILs

Stdlib unittest remains the DEFAULT gate (the harness's own suite is unittest). A repo DECLARING a native suite is in scope by its runner: `suite_runner: "pytest"` (FACTORY_NATIVE_CONFIG) is authoritative on exit 0 + one `N passed in X.XXs` summary with N ≥ 1, while exit 5 / `collected 0 items` / all-skipped are vacuous FAILs. Node/TAP was already reachable via the native argv path (Körmotorn precedent). Go/cargo test repos stay out of scope — the unit rung counts no total for them yet (phase 2).