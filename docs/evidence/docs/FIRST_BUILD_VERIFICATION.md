# FIRST_BUILD_VERIFICATION.md — Acceptance protocol for the first unattended build

2026-09-23. For the product owner. Total time: ~45 min pre-launch + one lap of watching + ~15 min audit.
Basis: UNATTENDED_FACTORY_PLAN.md (Layers 2/3/5), FACTORY_PLATFORM_VERDICT.md §F/§H (+addendum),
PITFALLS_AND_STRATEGIES.md. Commands run via `ssh [redacted-host] <cmd>` unless noted.

## Scope of the first build

What you are about to accept:

- **Supervisor** per plan Layer 2 (~150 lines bash/python on [redacted-host]): poll status+liveness,
  recovery ladder (resume→cancel→abandon), retry budget 2, ntfy notification on every terminal state.
  Plus Layer 5 corrections: launch entry is `.factory/schedule.json` + a selector (atomic claim of next
  unit of work), NOT a static loop over one target.
- **Provenance-fixed scenarios** per plan Layer 3.1: `FACTORY_RUNTIME_CANDIDATE` unset so `/health`
  reports real `git rev-parse HEAD`, and every scenario asserts observed revision == expected head.
- **`merge_mode=auto` set explicitly** in the schedule inputs — the archon-merge-queue.yaml default is
  `approve`; omitting it silently puts the human merge gate back in the loop.
- **PID-file deploy** as the deploy input; no `pkill` anywhere in the path (it self-kills the daemon,
  §H finding 3b; `/tmp/launch-lifecycle.sh` was retired for exactly this).
- Phase 1 contract: **one supervised lap, zero interventions, human watching.** You are the trust gate.

## Pre-launch review (~30 min)

Run each check on [redacted-host]. An item fails → fix before launch; do not waive.

1. **Provenance is code-bound, not literal.**
   `grep -rn FACTORY_RUNTIME_CANDIDATE ~/factory-lab/toy-product/harness/ ~/factory-lab/toy-product/.factory/`
   — no scenario JSON may set it to a constant (§H addendum 2: `736a1b2-lifecycle-candidate` made the
   revision assertion pass regardless of served code). Also `grep -rn '736a1b2' ~/factory-lab/toy-product/`
   → zero hits. Acceptable: the variable is unset in scenarios and assertions compare observed revision
   against `git rev-parse HEAD` (worktree path) or `.factory-resource.json` digest (resource path).
   Covers plan Layer 3.1; P1 (false greens), P3 (gate gaming).
2. **merge_mode=auto is explicit.**
   `cat ~/factory-lab/toy-product/.factory/schedule.json` — `merge_mode: "auto"` must appear literally
   in the per-tick inputs. Acceptable: present; absent means the YAML default `approve` pauses the lap
   at the merge gate (or worse, a silent assumption either way). Covers plan Layer 5; P2 (spec drift).
3. **Selector exists and claims atomically.**
   Read the supervisor's selector code (plan Layer 5): it must pick the next unit (e.g. oldest open
   `archon-ready` issue without an open PR), take the `.factory/locks/` lock, and write per-tick inputs —
   not re-run a fixed target forever. Acceptable: handler defined for every outcome (success/failure/
   timeout/crash/queue-empty), escalation ends in notify-and-wait. Covers plan Layer 5 / Layer 4
   NEEDLE pattern; P3, P8.
4. **Deploy uses PID files, not pkill.**
   `grep -rn 'pkill' ~/factory-lab/toy-product/.factory/ ~/factory-lab/toy-product/harness/` → zero hits.
   `grep -rn 'pid' .../deploy*` → PID file written at start, kill reads the file. Acceptable: no pkill,
   no `kill $(pgrep -f ...)`. Covers plan Layer 2 deploy tail; §H finding 3b (pkill matched the
   daemon's own argv and killed it).
5. **Liveness checks the owner, not the status row.**
   Read the supervisor's liveness function: it must check (a) a live `bun … workflow` process for the
   run (pgrep by run id) and (b) fresh writes under the run's worktree (mtime < 5 min). A "Status:
   running" row alone is NOT liveness — §F.1 left rows `running` for hours post-mortem; run 60b65fb8
   hung 2h. Acceptable: both checks present, 15-min wedge threshold. Covers plan Layer 2; P8.
6. **Recovery ladder order is resume→cancel→abandon.**
   Read the supervisor's recovery branch: `failed`/`paused` → `factory resume <id>` first;
   `running`-but-wedged → `workflow cancel` on a reachable owner; `abandon` ONLY on proven-dead owner
   WITH stopped worktree — never on "cancel says no owner reachable" alone (§F.2 near-miss: a healthy
   lap was killed that way). Covers plan Layer 2; P8, P13.
7. **Notifications fire before you need them.**
   `curl -d "factory test" ntfy.sh/<your-topic>` (or the webhook configured in the supervisor) — confirm
   arrival on your phone/endpoint, and confirm the supervisor sends on EVERY terminal state (GREEN with
   cost+node count, RED with last node+artifact pointer). No in-platform hooks exist (plan Layer 1);
   this is the only channel. Covers plan Layer 2; P6, P8.
8. **Launch cwd is the product repo.**
   The supervisor launches `consumer.py` from `~/factory-lab/toy-product` — launching from the pinned
   Archon clone auto-registered `coleam00/Archon` as the codebase (§H finding 4: wasted lap + stray
   commit on main). Acceptable: supervisor script's cwd / `WorkingDirectory=` is the product repo.
   Covers plan Layer 5; P13.
9. **Retry budget and STOP wiring are real.**
   Supervisor shows budget 2 per lap, and a notification path for budget exhaustion that STOPS (does
   not relaunch forever). A hard rate limit must end in RED, not an infinite loop. Covers plan Layer 2;
   P13, P3.
10. **Time the supervised baseline.**
    Note the wall clock of the supervised Phase-1 lap from launch to GREEN (§G baseline ~65 min ship,
    §H ~1.5h to merge gate). You need this number for the 2× STOP condition below.

## During-lap watch points

Expect, in order: lap-start notification → progress pings (if configured) → GREEN notification with
cost and node count at the end. Nothing else should arrive. Expected duration: ≤2× baseline (item 10).

**STOP conditions — the human MUST intervene the moment any of these fire:**

- Any RED notification (terminal failure, retry budget exhausted).
- Lap wall clock exceeds **2× the supervised baseline** — suspect a wedge; check liveness yourself.
- Any notification or log line mentioning provenance/revision mismatch (observed ≠ expected head).
- Retry budget (2) exhausted — provider flakiness is absorbable, a second failure is not (plan Layer 2).
- Any notification you cannot map to an expected state. Unexplained ≠ benign.

On STOP: do not improvise. Read the supervisor's last poll output, run the liveness check manually,
then apply the recovery ladder (item 6) or abandon only on a proven-dead owner. Record the intervention —
an intervention voids the Phase 1 exit criterion.

## Post-lap PRD-conformance audit (~15 min)

Walk the evidence chain end to end. This is where §H lies were caught — each step includes what the lie
looked like. Substitute the actual run's PR number / SHAs.

1. **Issue criterion, verbatim from GitHub** — not from any report or summary (triage rewrote criterion
   text in §H; the recast shipped as wrong behavior).
   `gh issue view <N> -R noor-latif/toy-product --json body -q .body`
   Expected: the original acceptance criterion text (e.g. `PUT /paste/<id>` → 404/405).
   *The §H lie: a test pinned 501 with a justifying comment; 4 review lenses scored 0 Critical.*
2. **PR diff actually implements it.**
   `gh pr view <N> -R noor-latif/toy-product --json headRefOid -q .headRefOid` then
   `gh pr diff <N> -R noor-latif/toy-product`
   Expected: the changed code produces the criterion's exact behavior/status. Read the diff yourself.
   *The §H lie: the delivered behavior diverged from the published criterion and nobody re-read it.*
3. **Qualification artifact says verified, at the PR head.**
   Locate the run's artifacts dir via
   `ssh noor@[redacted-host] 'ls ~/.archon/workspaces/_local/toy-product/artifacts/runs/<run-id>/runtime-qualification.md'`
   (run-id from the supervisor's launch log / `workflow list`), then read it:
   `ready: true`, and the revision it cites == the PR head from step 2.
   *The §H lie: "verified at the delivered revision" rested on a constant literal in the scenario —
   probe agreement, not code-bound provenance (addendum 2).*
4. **Merged tree on main == that head (bors rule, squash-adjusted).**
   `MC=$(gh pr view <N> -R noor-latif/toy-product --json mergeCommit -q .mergeCommit.oid)` then
   `git -C ~/factory-lab/toy-product diff --stat $MC $PR_HEAD` must be EMPTY (tree equality).
   Squash merges create a new SHA — never compare SHAs, compare trees; a moved base produces a
   non-empty diff = fail and re-verify.
   *The §H lie mode: merging a ref that was never the verified state would invalidate every upstream
   evidence artifact.*
5. **Deployed service reports that SHA.**
   `ssh [redacted-host] curl -s localhost:8642/health` → `revision` field == step 4's merge commit (`$MC`
   — under squash, main's HEAD is the squash commit, not the PR head), and `git -C
   ~/factory-lab/toy-product rev-parse HEAD` agrees.
   *The §H lie: `/health` echoed `FACTORY_RUNTIME_CANDIDATE` — a constant — so any code could serve
   and pass. Here it must be the real rev-parse because the variable is unset (step 1).*
6. **Divergence test — re-run one probe yourself.**
   Pick one acceptance criterion (e.g. the PUT /paste/<id> status) and execute its probe manually
   against the deployed service:
   `ssh [redacted-host] curl -s -o /dev/null -w '%{http_code}' -X PUT localhost:8642/paste/test-id`
   Expected: matches the issue's criterion text exactly. If it doesn't, the evidence chain is broken
   regardless of how green steps 1–5 looked — this is the audit that catches P2 spec drift.

## Go/no-go for Phase 2

Enable Phase 2 (supervisor + notifications + 3 unattended laps) only when ALL hold:

- **Audit clean:** the §Post-lap audit passes on all 6 steps for the Phase 1 lap, zero divergences.
- **Zero interventions:** the lap completed with no human touch beyond watching (plan Phase 1 exit).
- **Notifications proven:** at least one real GREEN received end-to-end (test ntfy in item 7 is
  necessary but not sufficient).
- **Cost within budget:** lap cost ≤ $0.05 (plan Layer 2 budget envelope; §G/§H actuals were
  $0.0001–0.0005 — anything near the ceiling is itself a signal to investigate).
- **No provenance incidents:** no revision-mismatch event during the lap.

Run 3 consecutive Phase-2 laps under the same rules before Phase 3 (scheduled + mutation calibration).
Auto-merge stays enabled only while these keep holding; the mutation rung (defects.json authored and
proven red — currently an empty scaffold) is the Phase 3 backstop, not a Phase 2 gate.
