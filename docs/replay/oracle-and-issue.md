# Holdout oracle and issue authoring

Read when building the per-issue holdout scenario or writing the fork issue: the oracle plumbing (verify.py paths), the stdout/`sys.path` traps, and the `Acceptance criteria:` extraction rule.

## 5. Holdout oracle contract

The unit oracle is green at a replay base, so it can never supply the RED that red-recheck demands — FAIL_TO_PASS lives in the per-issue exec scenario (replay-oracle addendum; verify.py:322-331):

- Expert tests live OUTSIDE the checkout (holdout dir) — committed at base they'd hand the implementer the answer and destroy the blind property.
- Create the GitHub issue on the fork FIRST; the scenario is `issue-<N>.json` where N = the ACTUAL fork issue number — `scenario_paths` matches by number (issue-number drift: instance-3 was fork issue #5, not #4; earlier runs consume numbers; REPLAY_SCORE dated correction).
- Exec assertion runs the holdout with cwd = the candidate worktree (verify.py:225-255, no path munging).
- The runner MUST `sys.path.insert(0, os.getcwd())` or run via `python3 -c` — subprocess argv puts the script's dir on sys.path[0], NOT the worktree; import fails and a correct fix gets charged a FAIL.
- Fragment matching is stdout-ONLY (verify.py:248) — use `TextTestRunner(stream=sys.stdout)`; unittest's default stderr output will not match.
- On success print a per-instance marker (e.g. `K<n>-RED-GREEN`); exit nonzero on test failure; `expected_exit: 0` is the GREEN gate.
- RED at base = red-recheck verdict "fail" (fail-not-pass proves the ladder is not empty); GREEN = exit 0 + marker. Prove BOTH pre-launch and quote the rows in the score doc.

## 6. Issue authoring

Body = the upstream issue's behavioral spec (post-truncation), NO code, NEVER a reference to the upstream PR or gold patch — the implementer prompt must not leak the fix's existence. Then an AUTHORED section starting with the literal line `Acceptance criteria:` — `criteria_from` (lap.py:147-149) extracts only after that heading via regex; miss it and the whole issue body becomes the criteria block. Criteria are derived from the expert tests' assertions, phrased behaviorally; upstream context goes above the heading, authored criteria below. (cost-ceiling addendum §3; RESEARCH implementer-view addendum.)