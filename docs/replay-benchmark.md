# Replay benchmark — historical PR battle test

Replay = clone a respected repo, rewind it to a pre-fix historical base, hand the factory the upstream
issue blind, and score against the expert's own tests. Validated 2026-09-30: 3/3 pypika instances merged
green, first attempt each, $0.002 total. Research and per-run evidence live in `~/repos/factory-docs`:
`REPLAY_BENCHMARK_RESEARCH_2026-09-30.md` (protocol + dated corrections), `REPLAY_INSTANCES_2026-09-30.md`
(selection loop, budgets, disqualifications), `REPLAY_SCORE_2026-09-30.md` (scoring conventions),
`DECISIONS.md` (F3 convention, fork strategy), `BATTLE_TEST_FORK_CONSTRAINTS_2026-09-30.md` (harness
contract).

Detail files: `docs/replay/screening-and-selection.md`, `setup.md`, `oracle-and-issue.md`,
`independent-oracles.md`, `scoring.md`, `claim-ladder.md`, `failure-modes.md`.

## 1. When to use, and when not

Use when asked to battle-test the factory against a real repo via historical replay. Prereqs: nightshift
deployed and idle (`docs/factory-launch.md` check 1); `gh auth` push rights on the fork; a surplus API
key in env. Out of scope: Go/cargo test repos with no unit total; full-ladder deploy validation
(`DEPLOY_MODE=none`, §8). A DECLARED native suite governs by its runner: exit 0 plus `N passed`, N ≥ 1;
vacuous-FAIL signatures are in `docs/replay/screening-and-selection.md`.

## 2. Repo viability screen

The binding constraint is the harness's EXACT command, not the repo's CI. Verified 2026-11-17:
`src/verify.py:run_unit_tests` still runs `python3 -m unittest discover -s tests` when a top-level
`tests/` exists, else `discover -s . -p "*_test.py"`, and `Ran 0` is a FAIL, never a vacuous pass. The
kernel also has a declared native-command path with TAP/pytest summary parsers; whatever argv the
instance DECLARES is the harness command now, and a row measured with any other argv is VOID.

- Imports stdlib + pytest only (anything else needs a trusted prepare argv); suite < 600 s; `main` or
  `master`; permissive licence; ≥ 5 merged test-adding bugfix PRs.
- Budget measured per base (§4); adapt layout and re-probe when tests sit outside `tests/`.
- Read `docs/replay/screening-and-selection.md` before screening: checklist, invalidated candidates, WHYs.

## 3. Instance selection

All bars required (`docs/replay/screening-and-selection.md`, `REPLAY_INSTANCES`):

- Merged PR linked to its issue by REFERENCE, not closing keywords; the issue text is the behavioural spec.
- ≤ 2 source files, ≤ ~30 LOC (easy tier first).
- Test diff adds-only (import blocks excepted).
- Issue text truncated at PR creation; no quoted gold patch, no multi-issue PR, no different-approach PR.
- Rename colliding test names in the holdout.
- Memorization flag mandatory per instance, never "global none"; prefer post-cutoff; weight each green.
- Validate at the base commit (merge parent): green TWICE → expert tests RED with exactly the F2P
  failures → gold green → record F2P ids, P2P count, gold LOC, view size.

## 4. Per-instance setup

`docs/replay/setup.md` — read when cutting a fork base, adapting layout, or setting budgets.

- ONE fork ever; archive `replay-<id>-final` at the merged sha before each rewind, then force-push main
  to the next base.
- Fork main = base + disclosed layout adaptation; the harness force-fetches origin main. Deploy a fresh
  `git clone --single-branch --branch main <fork-url>`.
- `CHECKOUT_CHAR_BUDGET` = `wc -c` over `CODE_PATHS`-matched files at the base × 1.25 — measured, never
  defaulted.
- `CODE_PATHS`: source only; `**` does not recurse; mutation-apply rejects files outside it; assert the
  fix's target file is IN the emitted view.
- Per-instance measurement call before launch; stop at 80 % of `COST_CEILING_USD` ($0.01/lap default in
  `src/settings.py`).

## 5. Holdout oracle contract

`docs/replay/oracle-and-issue.md` — the full contract.

- Expert tests live OUTSIDE the checkout (holdout dir).
- Fork issue FIRST; scenario file `issue-<N>.json` where N is the ACTUAL fork issue number.
- Runner cwd = the candidate worktree; `sys.path.insert(0, os.getcwd())` or run via `python3 -c`.
- stdout-only matching: `TextTestRunner(stream=sys.stdout)`; a per-instance marker; `expected_exit: 0`.
- F2P comes only from the scenario: prove RED at base and GREEN pre-launch, and quote the rows in the
  score doc.
- When the result set must support the RELIABILITY claim, read `docs/replay/independent-oracles.md`:
  issue-spec-only holdouts authored blind to the gold patch, separate artifacts, sealed scribe,
  base-only materialization.

## 6. Issue authoring

Body = the upstream issue's behavioural spec (post-truncation), no code, never a pointer to the upstream
PR or gold patch. Then the literal line `Acceptance criteria:` — `criteria_from` (in `src/lap.py`)
extracts only after it, so missing it turns the whole body into the criteria block. Upstream context
above, behavioural criteria derived from the expert tests below.

## 7. Launch and scoring

Run the `docs/factory-launch.md` six checks first.

- A supervised GREEN lap on current main FIRST; a MODEL-attributed red on the validation instance is NOT
  kernel regression — clear a park with a separate trivial lap, never a re-roll.
- EXACTLY one issue per run: a multi-instance queue destroys per-instance bases.
- Score by test-flip (F2P pass, P2P unbroken), never diff-similarity; slice the instrument log BY RUN
  WINDOW.
- `docs/replay/scoring.md` — cost measures, memorization weighting, the zero-undisclosed-operator basis.

## 8. Scope and claim level

With `DEPLOY_MODE=none` the provenance check is absent from the verdict and the deploy leg never runs: a
green validates implementer → mutation-apply → review → verify (unit + holdout) → merge → issue-close
ONLY. Every score doc states this.

Hard rule: the score-doc header states its claim level in ONE line, computed from the ladder BEFORE the
narrative — no rung, no claim. Read `docs/replay/claim-ladder.md` when writing it.

## 9. Known failure modes

`docs/replay/failure-modes.md` — read when a lap crashes, parks, no-ops, discovers zero tests, or the
scoring numbers disagree.

## 10. Evidence and publication

- Artifacts in `~/repos/factory-docs/replay-patches/<id>/`: gold and rewritten test patches, holdout
  runner, scenario json, `DEPLOYMENT_NOTES.md`, independent holdout.
- Score doc in `~/repos/factory-docs` (`REPLAY_SCORE_2026-09-30.md` template): outcomes, gates, costs by
  measure, memorization flags, oracle counts, scope, unattended basis, claim level.

No setup script: setup has been executed correctly twice from this document alone. Revisit a script only
if a future run shows setup errors.

Source: the `replay-benchmark` skill (original in `~/.agents/skills-backup-2026-11-17.tar.gz`); the
seven detail files are in `docs/replay/`.