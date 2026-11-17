# RED-proven issue authoring

Six steps. The run's defect history lives in these rules — each step names the receipt.

## 1. Generate candidates against current `origin/main`

Quote CURRENT main text in any anchor (mutation anchor, criteria quote) and quote it exactly: run #6
parked after 3 kills because every find block mis-transcribed one character of a main-verbatim line
(`])] ["disposition"]` vs main's `])]["disposition"]`), not because the text had moved. A pre-apply
anchor-exists check guards both this and genuine anchor drift. Re-check anchors against `origin/main` at
dispatch time.

## 2. Prove each RED on a fresh checkout

Every issue must fail on unmodified current main. The trap: RED proofs pass on ANY unfixed base
regardless of oracle file placement — the cross-assignment bug (oracle files keyed to build order, not
issue numbers) is invisible from the RED direction. Only the GREEN direction catches it. So after any
GREEN, verify oracle↔issue alignment explicitly: name ↔ number ↔ marker. The repo's
`TestSelfRunOracleAlignment` is the pattern — an alignment test lives in the repo's tests for exactly
this.

- For misattribution-class defects (shared or key-aliased state), the oracle must include a
  **TWIN-RECORD branch**: two records sharing the lookup key where only one belongs to the subject (an
  older sibling attempt's terminal record vs the current attempt's non-terminal one), and the oracle
  must reject a fix that reads the wrong one. Validate the synthetic gold adversarially too: ask what
  lazy implementation passes every tested branch while violating a criterion; if one exists, add the
  branch that discriminates and keep the lazy variant as a negative control. WHY: round-3's #26 oracle
  validated GREEN on a gold that was itself the naive misattributing shape — newest-terminal-record —
  because negative controls covered only behaviour deletion, not adjacent-lazy-fix.
- A fixture minting historical timestamps must make filesystem mtimes coherent (`os.utime` the dirs and
  their files to their timeline ts). WHY: a production-legitimate mtime-pairing fix reads
  wallclock-now mtimes as "newer than started_at", misattributes a sibling's record, and false-REDs at
  gold.
- Ground fixture parameters (latencies, mtime orderings, gaps) in real instrument data, never plausible
  guesses. WHY: a fixture assumed "realistic spawn latency ~2-3 s"; the instrument (14/14
  dispatch→lap-start pairs) showed same-second or +1 s — the fixture encoded a false production claim
  and had to be re-grounded.
- If an issue sanctions more than one implementation mechanism, prove the oracle GREENs each (one
  session: timestamp-window pairing AND dir-mtime pairing both flipped all five branches). When windows
  are involved, add a tolerance-0 / exact-equality control.

## 3. Criteria wording rule

Every acceptance criterion must be satisfiable within the provided-files contract (reviewer view =
`CODE_PATHS` only). Never demand a standalone repro script — that is unsatisfiable by construction and
forces a mid-run `gh issue edit`. State that oracles and/or `tests/` satisfy the repro requirement.

## 4. File via `gh`

Open the issue on the target repo with the behavioural spec as the body, then name the scenario file
`issue-<n>.json` for the number `gh` actually returned.

## 5. Verify the open set equals the RED-proven set

No orphans (open but unproven), no silently dropped candidates.

## 6. Re-verify RED at dispatch time

The L-013 `red-recheck` exists for this. Make it cheap by construction: criteria and anchors quote
current main, so the dispatch-time recheck is a diff, not a re-derivation.

Source: the `red-issue-authoring` skill (original in `~/.agents/skills-backup-2026-11-17.tar.gz`).