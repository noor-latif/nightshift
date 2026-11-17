# Known failure modes

Read when a lap crashes, parks, no-ops, or the scoring numbers disagree — signature → cause → fix.

- Lap crashes at spawn 3× then parks — supervisor spawns `src/lap.py` relative; unit must set `--property=WorkingDirectory=<factory repo root>` or it defaults to $HOME (factory-launch check 6; observed twice).
- ntfy receipt "no-transport" — NOT a flake: `NTFY_TOPIC` missing from the unit env at launch; the kernel's deliberate empty-topic status (receipt still written). Check the unit env before attributing transport. (REPLAY_SCORE dated correction.)
- Run no-ops `DRAIN:0` immediately — `state["issues"]` already holds the issue number: reused state dir. Use a per-run state dir or slice by run window (factory-launch §6a).
- Zero tests discovered — layout not adapted; bare-discover ≠ harness command (§2).
- cost.json `cost` vs `buyer_cost_micro` sums don't match — different measures; label, don't reconcile (§7).
- Duplicate test-name shadows a base test — rename in the holdout (§3).
- Scenario/issue number mismatch — `scenario_paths` matches by number; create the fork issue FIRST, then name the scenario file (§5).