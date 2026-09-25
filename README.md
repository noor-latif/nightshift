# nightshift

Time-boxed spike answering one question: can our own code run factory laps
(issue → implement → verify → merge → deploy) unattended, with zero human
interventions and zero false greens. Spec and evidence log are maintained
privately during the time-boxed spike.

## Layout

- `src/` — six modules + `settings.py` (literal values only):
  `supervisor` (tick loop), `selector` (issue claim), `agent` (surplus LLM
  calls), `verify` (oracle-first probes), `merge` (squash + tree-equality),
  `deploy` (PID-file launch + identity read-back).
- `scenarios/` — HTTP scenario probes for the toy-product rig.
- `tests/` — stdlib unittest; run offline, no network/ssh/gh/API key needed.

## Run

    python3 -m unittest discover -s tests

Python 3 stdlib only. No pip dependencies. Laps run on a remote host via ssh;
development happens locally. Scope: time-boxed spike — issue → implement → verify → merge → deploy laps, zero human interventions, zero false greens.
