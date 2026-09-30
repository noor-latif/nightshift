# PROD.md — nightshift (factory-spike) spec and probes

The spike's own spec. Each success criterion (POC_PROPOSAL §3) is stated as a
machine-checkable probe: exact command + expected output. Probes marked
`[[redacted-host]]` run on the remote host during the integration step; the rest run
locally.

## Probes

### S1 — 3 consecutive laps, zero human interventions `[[redacted-host]]`
Probe: `grep -c '"event": "dispatch"' state/evidence/supervisor.log` across a
3-lap session; intervention log file (`state/interventions.jsonl`) must not
exist or be empty.
Expected: dispatch count ≥ 3; `test -f state/interventions.jsonl && wc -l
state/interventions.jsonl` → `0`.

### S2 — 0 false greens on injected defects `[[redacted-host]]`
Probe: with owner-installed `defects.json` in the product repo's
`harness/mutations/`, for each defect run one lap against the mutated
checkout: `python3 -m src.supervisor --once --defect <id>`; the lap must end
RED.
Expected: each defect id appears in `state/evidence/` with `"verdict":
"fail"` — zero laps green over a defect.

### S3 — cost/lap ≤ $0.01 and wall-clock ≤ 2× baseline `[[redacted-host]]`
Probe: after each lap, `jq .cost_usd state/evidence/<run-id>/cost.json` —
expected ≤ 0.01. Wall-clock: `jq .started_at, .merged_at
state/evidence/<run-id>/timeline.json` — span ≤ 2× the Archon baseline
(~1.5h to merge gate). 2× breach = STOP (kill criterion).

### S5 — every gate demonstrated red before trusted `[[redacted-host]]`
Probe: for each verifier (unit, scenarios, provenance) feed one known defect
before first green is recorded. Expected: `state/evidence/red-demo/<gate>.json`
exists with `"verdict": "fail"`. A gate without a red-demo file is treated as
absent.

### S6 — merge/deploy identity tree-bound `[local tests + [redacted-host]]`
Probe (local): `python3 -m unittest tests.test_merge tests.test_deploy`
Expected: OK (squash merge tree-equality + tampered variant fails + deploy
PID-file launch).
Probe `[[redacted-host]]`: post-merge `git diff --stat <mergeCommit> <pr-head>` →
empty output; deploy read-back `curl -s localhost:8899/health` revision ==
`git rev-parse main` → equal.

### S7 — notification on every terminal state `[[redacted-host]]`
Probe: subscribe `curl -s ntfy.sh/[redacted-ntfy-topic]/sse > ntfy-capture.log`
(topic = `settings.NTFY_TOPIC`) during a lap session. Expected: every terminal state (GREEN/RED/PARKED/HALT)
appears; receipts archived under `state/evidence/ntfy/`.

### S8 — outputs comparable across iterations `[[redacted-host]]`
Probe: `ls state/evidence/` — one run-id directory per lap containing
cost.json, timeline.json, verdict. Expected: schema identical across runs
(same keys), attributable by run-id.

## Day-1 (local) verification bar

    python3 -m py_compile src/*.py
    python3 -m unittest discover -s tests     # expected: OK, no network needed

## Decision record

| Decision | Value | Rationale |
|---|---|---|
| Language | Python 3 stdlib | lab tooling already Python; zero new runtime to provision on [redacted-host] (§5) |
| Time-box | 5 working days | hard box; not green by day 5 = finding, not extension (§2) |
| Archon | excluded entirely | de-risking independence from the wrapped engine's failure modes (§6) |
| Repo name | `nightshift` (renamed from factory-spike on publish, 2026-09-25) | per §10.4 |
| Cost ceiling | $0.01/lap | owner kept headroom for gateway retries over the $0.005 parity option (§10.5) |
| Implementer model | `deepseek-v4.1-flash` (owner call 2026-09-24) | adversarial stress testing, not cost-cutting: a factory robust enough to run unattended must mitigate a confabulation-prone implementer; a spike that only passes with a top-tier model proves nothing about its gates |
| Reviewer model | `glm-5.3-flash` | different family from the implementer for review (P5 mitigation); effort suffixes don't exist on this gateway (smoke test 2026-09-24) |
| License | Apache-2.0 (owner call 2026-09-25) | repo-level LICENSE, no per-file SPDX headers |
| ntfy topic | randomized (`[redacted-ntfy-topic]`) | public ntfy.sh topics are world-readable/writable by anyone who knows the name — random topic shrinks the leak surface |
| PROD/LEARNINGS | moved to `factory-docs/SPIKE_*.md` | internal docs off the public repo — owner call 2026-09-25 |

**Evaluation rule with a hostile implementer:** lap failures are ambiguous
(model lied vs factory missed). Disambiguation is by evidence: a lie reaching
verify.py's assertions and being killed = factory WINNING (record as
caught-confabulation in LEARNINGS.md); a green lap containing a lie = false
green = S2 kill-criterion, regardless of which model produced it.
