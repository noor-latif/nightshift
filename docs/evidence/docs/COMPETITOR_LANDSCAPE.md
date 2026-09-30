# AI Software Factory — Competitor & Architecture Landscape (2026-09-23)

Research question: has anyone already fixed what we're fixing (unattended self-hosted PRD→deploy loop with liveness, recovery, and merge trust)? Verdict up front: **nobody ships the whole thing; every piece exists, solved cleanly, in borrowable form.**

## 1. Executive summary

- **No commercial player merges its own work.** Devin, Copilot coding agent, Codex cloud, Cursor background agents all stop at PR + human merge — even Devin's own docs recommend human oversight [4][7]. Factory.ai claims "tickets into merged code" but is closed SaaS [6]. The unattended full loop is deliberately avoided industry-wide for trust reasons.
- **No OSS project ships the full loop either.** OpenHands (closest OSS analog: event-sourced clean core, issue→PR with tests) has no merge/deploy/holdout stages [5].
- **Our missing layers are solved in niche OSS**: Batty (tmux-native supervisor daemon with `restart_dead_members()` poll loop) [9], NEEDLE (exhaustive-outcome state machine, atomic claim queue, health/watchdog module, bounded escalation to human) [10], Sortie (SQLite-persisted retry/park failure model, re-dispatch in-flight on restart, consecutive-absence ceiling that parks instead of looping) [11].
- **Off-the-shelf liveness/resume exists in Windmill**: zombie detection (worker ping-based, 30s), auto-restart of zombie jobs, per-step retries, error-handler webhooks, bash steps natively, self-hostable [1].
- **Merge/deploy trust is a solved pattern-set**: bors gate-and-merge (fast-forward only the tested SHA) [12], deploy-time provenance lookup (Google) [17], DSSE/SLSA attestation via cosign [13][14], Flux/Argo-style self-heal reconciliation loop [15][16], Kayenta-style runtime-gated promotion [18].
- **Build vs borrow verdict: wrap, don't re-platform.** Keep Archon (its holdout/qualification machinery is the differentiator no competitor has); build the ~150-line supervisor by stealing Batty's loop shape, NEEDLE's outcome table, Sortie's park semantics. Fallback: re-platform the DAG on Windmill if hangs keep recurring.

## 2. Autonomous dev-loop landscape

| Project | Loop depth | Unattended mode | Verification | Self-host OSS | Architecture note |
|---|---|---|---|---|---|
| Devin [4] | issue→PR+review | cloud async | review-as-check, repo CI | no | opaque cloud orchestrator |
| Copilot coding agent [7] | issue→draft PR (never merges) | Actions container | build/lint/tests | no | ephemeral container per task — no daemon at all |
| Codex cloud [7b] | issue→PR, Best-of-N | container queue | CI + best-of-N | CLI only | one-shot containers |
| Cursor bg agents [8] | task→PR, notify | cloud VMs | sandbox tests | no | VM-per-agent + queue; notifications built-in (our gap) |
| Factory.ai [6] | claims ticket→merged | cloud+local | CI checks, depth unclear | no | closed; enterprise |
| OpenHands [5] | issue→PR + tests | headless possible | runs test suite | yes (MIT) | stateless agent + event-sourced state — clean, replay-friendly |
| SWE-agent [20] | issue→fix | batch CLI | benchmark harness | yes | research harness, not a factory |
| vercel-labs/open-agents [21] | task→PR template | serverless (Vercel) | repo CI only | yes | reference app, platform-coupled |
| **Ours (Archon)** | **issue→PR→runtime-verify→holdout→qualify→merge→deploy** | detach+auto (in progress) | **live per-assertion evidence + holdout** | yes | daemon DAG; weak liveness, no notify |

Take: our verification depth (holdout + qualification + per-assertion evidence) exceeds every player found, commercial included. Our weakness is exactly what nobody else solved either: daemon reliability.

## 3. The niche gold — three projects worth reading wholesale

**NEEDLE (jedarden/NEEDLE, 26★) [10]** — Rust headless orchestrator as explicit finite state machine. Every transition has a defined handler; outcome table covers success/failure/timeout/crash/race-lost/queue-empty. Atomic SQLite claim (SELECT→CLAIM transaction, no central orchestrator). `src/health/` = liveness, stale-claim cleanup, watchdog. Escalation strands end in "alert human, wait" — bounded, never loops. Its README argues workflow engines misfit non-deterministic agent steps: correct for our case.
→ Borrow: exhaustive outcome table + atomic claim + bounded escalation for the selector.

**Sortie (sortie-ai/sortie, 190★) [11]** — Go single binary, SQLite persistence, 21 architecture docs including a dedicated failure-model doc. Running sessions not recoverable (agent subprocesses die) BUT orchestrator re-dispatches in-flight issues immediately on restart; retries with future `due_at` restored from SQLite; consecutive-absence ceiling (default 3) PARKS an issue durably instead of looping forever. "Every disposition ends in a bounded retry followed by escalation, an immediate escalation, or an explicit logged stop, and never a silent drop."
→ Borrow: park semantics + restart re-dispatch + the failure-model doc as a writing template.

**Batty (battysh/batty) [9]** — Rust tmux-native agent supervisor: synchronous 5s poll loop `poll_watchers(); restart_dead_members(); deliver_inbox_messages(); retry_failed_deliveries(); maybe_auto_dispatch(); maybe_fire_nudges();` — no async runtime, state in YAML/Markdown/Maildir/JSONL. MergeLock file lock (60s) serializes merges, 2 conflict retries then escalate.
→ Borrow: the supervisor loop shape (maps 1:1 to our Layer-2 design — validates it).

Honorable mentions: **no_human** (adversarial verification: repro must FAIL at merge-base — a harder version of our holdout), **gastown** (3-tier watchdogs Witness/Deacon/Dogs + bors-style Refinery merge queue).

## 4. Orchestration engines (the re-platform option)

| Engine | Wedged-but-alive detection | Durable resume | Retries | Hooks | Wraps shell/LLM steps | Self-host |
|---|---|---|---|---|---|---|
| Windmill [1] | YES — ping-based, ZOMBIE_JOB_TIMEOUT=30s, RESTART_ZOMBIE_JOBS=true | partial (Postgres, re-queue, skip completed steps) | per-step + backoff | error handlers → Slack/webhook | bash/python native | yes |
| Temporal [2] | via heartbeat timeout (no autonomous probe) | YES — event-sourced replay | first-class RetryPolicy | weak (watcher workflows) | activities arbitrary | yes, heavy |
| Dagster [3] | YES — run monitoring daemon, hanging-run detection | auto-restart crashed workers | run_retries + step retry | built-in alerting | ops shell out | yes |
| Prefect | Crashed-state detection | flow re-run from start | per-task | automations | yes | yes |

Temporal is the gold standard but operationally heavy (server cluster + worker fleet). **Windmill is the pragmatic fallback**: self-hostable single docker-compose, bash steps = our LLM nodes, zombie detection solves our exact hang class, error webhooks solve notifications. Cost of re-platform: rewriting the lifecycle DAG as Windmill flows and losing Archon's holdout/qualification semantics — which are our differentiator.

## 5. Merge/deploy trust patterns (for Layer 3 of the unattended plan)

1. **Bors gate-and-merge [12]**: stage the merge, verify the *merged SHA*, fast-forward main only to that exact tested revision. Our merge-queue already approximates this; make the identity pinning exact.
2. **Deploy-time provenance (Google BSRS ch.14) [17]**: record provenance (git SHA + evidence hash) at merge; the deploy step refuses to run unless the serving artifact's declared revision matches the record. Verification at the trust boundary, not trusted from CI. ~20 lines.
3. **DSSE attestation (SLSA/cosign) [13][14]**: sign the evidence record; key-based cosign is one binary, or hand-roll ~50 lines. Optional hardening for now.
4. **Self-heal reconciliation (Flux/Argo) [15][16]**: a ~50-line loop recomputing desired state (pinned SHA + evidence hash) and reverting drift — subsumes our identity read-back into continuous enforcement.
5. **Runtime-gated promotion (Kayenta) [18]**: post-deploy, diff health/error signals new-vs-old, auto-rollback on failure. Minimal toy version: one script.

## 6. Trade-offs & decision

- **Wrap Archon + build 150-line supervisor** (chosen): preserves holdout/qualification (our differentiator), cheapest path, borrows Batty/NEEDLE/Sortie patterns directly. Risk: refresh-hang root cause unknown; if per-lap hangs persist, escalate upstream or re-platform.
- **Re-platform on Windmill**: gets zombie detection + retries + webhooks for free. Cost: rewrite DAG, lose Archon trust semantics, new Postgres dependency. Fallback only.
- **Adopt a merge-queue tool (bors-ng/Zuul)**: not worth it — our merge volume is 1 PR/lap; the pattern (fast-forward tested SHA only) is 10 lines, the tooling is not.

## References

- [1] Windmill — https://github.com/windmill-labs/windmill ; https://www.windmill.dev/docs/core_concepts/error_handling
- [2] Temporal heartbeat timeouts — https://docs.temporal.io/develop/go/activities/timeouts ; https://docs.temporal.io/encyclopedia/detecting-activity-failures
- [3] Dagster run monitoring/retries — https://docs.dagster.io/deployment/execution/run-monitoring ; https://docs.dagster.io/deployment/execution/run-retries
- [4] Devin — https://docs.devin.ai/work-with-devin/devin-review ; https://cognition.com/blog/devin-101-automatic-pr-reviews-with-the-devin-api
- [5] OpenHands — https://www.openhands.dev
- [6] Factory.ai — https://factory.com/pricing
- [7] Copilot coding agent — https://github.blog/ai-and-ml/github-copilot/assigning-and-completing-issues-with-coding-agent-in-github-copilot
- [7b] Codex cloud — https://sequoiacap.com/podcast/training-data-openai-codex
- [8] Cursor background agents — https://finance.yahoo.com/news/cursor-launches-app-manage-ai-150000184.html ; https://runtimewire.com/article/cursor-builds-origin-to-host-code-from-fleets-of-ai-agents-launching-today
- [9] Batty — https://dev.to/battyterm/building-a-tmux-native-agent-supervisor-in-rust-5hek ; https://github.com/battysh/batty
- [10] NEEDLE — https://github.com/jedarden/NEEDLE
- [11] Sortie — https://github.com/sortie-ai/sortie (docs/architecture/19-failure-model-and-recovery-strategy.md)
- [12] Bors — https://bors.tech ; https://kflansburg.com/posts/merge-queues
- [13] SLSA — https://slsa.dev
- [14] cosign attestations — https://docs.sigstore.dev/cosign/verifying/attestation
- [15] Flux — https://fluxcd.io/flux/concepts
- [16] Argo CD auto-sync — https://argo-cd.readthedocs.io/en/stable/user-guide/auto_sync
- [17] Google, Building Secure & Reliable Systems ch.14 — https://google.github.io/building-secure-and-reliable-systems/raw/ch14.html
- [18] Kayenta — https://netflixtechblog.com/automated-canary-analysis-at-netflix-with-kayenta-3260bc7acc69
- [19] Zuul gating — https://zuul-ci.org/docs/zuul/latest/gating.html
- [20] SWE-agent — https://github.com/swe-agent/swe-agent
- [21] vercel-labs/open-agents — https://github.com/vercel-labs/open-agents

## 7. Source-verified addendum (2026-09-23, deep-read of cloned repos)

All six pillar repos verified by `git ls-remote` + cloned to `~/repos` and read from source (not READMEs):

| Repo | HEAD | Language/scale | Verified in source |
|---|---|---|---|
| battysh/batty | 5637f78 | Rust, ~122k src LOC | supervisor loop `src/team/daemon/poll.rs:17-155`; shim NDJSON over tmux panes; health modules (stall/restart/ping_pong/context_exhaustion/pane-death); `auto_respawn_on_crash`; post-restart resume prompts per active task (#707) |
| no-human-ai/no_human | 92cf4fa | Python 3.12+ | adversarial repro gate CONFIRMED: `orchestrator.py:10058` requires the manifest's named tests to FAIL on unfixed code at merge-base and pass on the new tree; `merge_policy.py:70,95,356` enforces repro_gate pass/pass_or_not_required; tamper guard (agent/guard.py, blockers/) + second-model review |
| gastownhall/gastown | 649b832 | Go | three-tier watchdogs confirmed: `internal/daemon/{checkpoint,doctor,compactor}_dog.go` (Dogs), `internal/deacon/` with crashloop+idle guards, Witness per-rig (`internal/agent/state.go:2`); Refinery = bors-style bisecting merge queue (`internal/refinery/`); restart tracking with exponential backoff (`daemon.go:93`) |
| sortie-ai/sortie | 50a13c9 | Go | see below |
| jedarden/NEEDLE | 8538485 | Rust, ~235k src LOC (correction: earlier "~51k" figure was wrong) | Outcome enum + handlers all real: `types/mod.rs:399` (Success/Failure/Timeout/AgentNotFound/Interrupted/Crash/GateError/GateUnsatisfiable), dispatch `outcome/mod.rs:1419-1469`, each with a named handler; heartbeat files + staleness TTL + PID checks (`health/mod.rs:646-843`); atomic claim with `BEGIN IMMEDIATE` + claim-epoch fencing |
| openai/symphony | be10a1b | spec + Elixir ref impl | spec-first orchestration SPEC (language-agnostic, RFC-2119); scheduler state deliberately in-memory (SPEC.md §14.3) — the v1 spec of what Sortie hardens |

**Sortie adapter facts (change §6 calculus):** `AgentAdapter` is a Go interface — `StartSession/RunTurn/StopSession` (`internal/domain/agent.go:242-260`), registered via `registry.Agents.RegisterWithMeta` in `init()`, blank-imported only from cmd/sortie; contract tests reject orchestrator→adapter imports. The generic escape is `agent.kind: agent-client-protocol` where `agent.command` must speak ACP — `factory/consumer.py` is neither, so hosting Archon under Sortie costs a Go adapter. Re-dispatch after restart is a FRESH session (docs §14.3); only retries-with-`due_at`, parks, budget notices, session metadata, and run history are restored from SQLite. Park release needs explicit operator action or observed "work observed" evidence. Consecutive-absence ceiling 3 = initial run + 2 retries, then park.

**Decision unchanged but sharpened:** wrap Archon with our own supervisor (resume-first ladder; plan Layer 2/5), borrow failure-model semantics from Sortie/NEEDLE/omnara, decline Sortie-as-host (Go adapter cost + fresh-session re-dispatch loses Archon's resume-with-skip).
