# Launch and scoring

Read when launching laps or writing the score doc: the supervised-lap precondition, park attribution, run-window slicing, the two cost measures, memorization weighting, and the zero-undisclosed-operator basis.

## 7. Launch & scoring

Run the factory-launch six checks first — this section adds only replay specifics:

- Supervised GREEN lap FIRST on current main — contract changed since the last GO → the old GO is void (factory-launch check 4). Replay addition: pre-register that a MODEL-attributed red on the validation instance is NOT kernel regression; if it parks, run a separate trivial known-solvable lap (new fork issue + scenario) to clear the gate — do not burn the replay instance re-rolling it.
- Then unattended one-issue runs — queue of EXACTLY one issue per run (per-instance base rule: a multi-instance queue bases instance 2 on main-after-the-factory's-own-fix-1, destroying per-instance bases); all operator setup happens BETWEEN runs (§ "Unattended basis" in REPLAY_SCORE).
- Score by test-flip (primary): F2P pass AND P2P unbroken — executable, never diff-similarity; many divergent patches are equally correct. Expert-diff comparison is a diagnostic only (RESEARCH §4 step 7; plausible-patch evidence card).
- Slice the instrument log BY RUN WINDOW — `state/` is cumulative and cwd-relative; scoring reads the slice, never the whole dir (factory-launch §6a).
- Costs: totals = sums of `buyer_cost_micro` across each lap's cost.json rows (marketplace buyer price); the per-call `cost` field is a DIFFERENT measure (raw model cost, ~2-2.5× smaller) — label them separately, never reconcile the two. (REPLAY_SCORE dated correction.)
- Per-instance memorization flags go in the score doc, each green weighted by its flag.
- ZERO-undisclosed-operator basis: setup between runs is disclosed in DECISIONS.md per the F3 convention (operator actions during runs, disclosed; never mixed into the instrument log) — no operator `intervention` rows may exist inside a run window.