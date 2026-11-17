# Factory launch gate

Six checks, in order. Each names the failure that motivated it — that is why the check exists. Run all
six; print the go/no-go with an evidence line per check; hand the owner a one-line going-dark summary
(what runs, what notifies, what to check in the morning). The owner makes the go/no-go call — this
document encodes the checks, never the decision.

Anchor note (2026-11-17): this lives beside the kernel. Line numbers from the 2026-09/10 skills were
dropped because `src/` has moved since (F8–F10c); cite symbols with `grep` instead.

## 1. Single-instance check

The factory repo must be present at `~/repos/factory-spike` (nightshift is laptop-only since the
2026-09-28 migration; nixlab is no longer a nightshift host) and no lap/supervisor process may be
running locally (`pgrep`). Check processes, unit state and stale PID files (`*.pid` is gitignored).

The systemd unit must carry `Restart=on-failure` — two prior launches died silently with no restart
policy. If it is missing, add it (mechanical edit, pre-launch window only). If anything is live: stop,
do not double-launch. Two live factories race the same `GITHUB_REPO`.

## 2. Queue check

At least 3 open issues, each RED-proven on FRESH `origin/main`. If short, run `red-issue-authoring`;
do not proceed on a thin queue.

## 3. S1-instruments-present check

Grep the DEPLOYED revision — `git show origin/main:<path>` or the running process's actual code, never
a working copy. This class killed launch-1: a kernel fix was on origin/main but the RUNNING process
predated it. Verify the instruments exist in the code that will actually run (interventions log,
reconcile, crash-retry accounting, receipts wiring). Verify the working-tree `git rev-parse HEAD`, not
refs/branches — colocated-repo refs can lag the working copy.

## 4. Kernel-contract validation check

If the deployed revision's per-lap contract changed since the last supervised validation lap
(`lap` / `supervisor` / `verify` / `merge` — e.g. `red_recheck`'s return shape, `add_cost`'s row
contract, notify's event rows, `kill_lap`'s escalation, the merge evidence argument), run supervised
lap(s) on the new kernel BEFORE the unattended run — NO-GO until one has gone GREEN once under
observation. A model-attributed failure is an honest partial validation of the front half
(implementer → mutation-apply), but it does not satisfy this check: the downstream contract
(review → verify → merge with real evidence → deploy/issue-close) only exercises on a green lap. If the
queue parks without a green, that is a NO-GO with the park evidence attached.

This class killed launch-1 and launch-2: a stale harness and a false wiring report were both
contract-validation failures. An unattended night on an unvalidated contract cannot be attributed
between contract bugs and model behaviour (see `SESSION_HANDOFF_2026-09-28` discipline and the
launch-1/launch-2 aborts).

## 5. Env-effectiveness check (through the REAL code path)

Every env override the launch relies on — `SCENARIOS_DIR`, `CODE_PATHS`, `CHECKOUT_CHAR_BUDGET`,
`DEPLOY_MODE`, `GITHUB_REPO`, `PRODUCT_REPO`, `NTFY_TOPIC` — needs behavioural proof, not
config-attribute equality. `src/settings.py` defines all of them (verified 2026-11-17); `NTFY_TOPIC`
belongs in the launch env and never in a file.

This class killed launch-2: a wiring claim (dir listing present + settings attribute equal) was never
proven through the code path. The proof model is the `red_recheck` logging verdict row reading `fail`
for a KNOWN-RED issue — not null, and not `pass`: `pass` on an issue you have RED-proved means the
scenario ladder is EMPTY (wrong `SCENARIOS_DIR`, e.g. a dir missing that issue's `issue-<n>.json`) and
the run would vacate the queue with false greens via already-satisfied. Also verify the checkout view is
not truncated: budget ≥ actual tree size. `CHECKOUT_CHAR_BUDGET` truncation once silently dropped 3
test files from the implementer's view, making acceptance criteria structurally unsatisfiable.

## 6. Criteria-satisfiability check

No acceptance criterion may demand a standalone new file that the provided-files contract forbids
(reviewer view = `CODE_PATHS` only) — that wording wall forced a mid-run `gh issue edit`. Oracles must
satisfy repro criteria. If an open issue violates this, send it back to `red-issue-authoring` step 3.

Also: the unit launch MUST set `--property=WorkingDirectory=<factory repo root>`; `supervisor.py`
spawns `src/lap.py` as a relative path, so without it the unit defaults to `$HOME` and every lap
crashes at spawn (3 crash-retries then park, with the operator claim-reset it demands — observed twice).

## 6a. Pre-flight asserts (before dispatch)

- (a) The target issue number must NOT already appear in `state/state.json` issues. `claim_next` skips
  merged/parked issues, so a reused state dir with a colliding issue number silently no-ops and halts
  `DRAIN:0`, which reads as a clean pass.
- (b) The scenario file name must equal the ACTUAL fork issue number: create the GitHub issue first,
  then name the scenario `issue-<n>.json` to match — `scenario_paths` matches by number.
- (c) The red-recheck row must read verdict `fail` for a known-RED target before dispatch; `pass` on
  known-RED is an empty ladder.
- (d) After the FIRST lap, assert `cost.json`'s `prompt_tokens` is on the order of the measured checkout
  view (rough bound: within ~2× below to ~3× above the expected char-budget/4). Dogfood r2 ran 5 laps
  on a ~300-token toy view because `PRODUCT_REPO` was missing from the unit env, and nothing in the
  harness flags the mismatch; an implausibly small prompt means the checkout wiring is wrong and every
  later lap is wasted.
- (e) When the view includes `tests/`, scoring must assert the applied diff does not WEAKEN tests — no
  test method deleted, no assertion dropped or loosened. Modifying a pre-existing test that pins
  pre-fix behaviour is legitimate (a behaviour change may require updating its expectation) and must be
  justified criterion by criterion in the review; a deletion or loosening without justification is a
  defect. Widening `CODE_PATHS` to `tests/` removes the structural test-weakening guard and makes the
  verify leg run the candidate's own suite, so this assert is the only in-harness check.

Per-instance replay runs must use a per-run state dir, or slice the instrument log by run window:
`state/` is cwd-relative and cumulative, and scoring reads the slice.

## Output

Go/no-go, one line per check with its evidence (command + observed result), then the going-dark
summary. A blocked check is a NO-GO with the receipt showing why — that is the gate working, not
failing.

Source: the `factory-launch` skill (original in `~/.agents/skills-backup-2026-11-17.tar.gz`).