# Tech Mandate Review — "2026 Mandatory Architecture" Proposal

Reviewed: 2026-09-24. Proposal = 4 pillars allegedly mandatory for our single-server
python-stdlib factory spike ([redacted-host]; laps $0.0001–$0.0005; solo dev). Every claim checked
against primary sources; UNVERIFIED marked explicitly.

## §1 Verdict Table

| Pillar | Claim | Verified? | Actual facts (refs) | Solo/one-server feasibility | Verdict |
|---|---|---|---|---|---|
| 1. Zero-trust microVMs | `@deno/sandbox` SDK + Firecracker-on-demand is mandatory for agent code | Partly | SDK exists on JSR/npm, **but it is a Deno Deploy *cloud* service** — microVMs run in Deno's cloud, not on your box [1][2][3]. Firecracker needs /dev/kvm, bare metal or nested virt, KVM device access [8][9]. E2B TS SDK `Sandbox.create()` exists; ~$0.0504/vCPU-hr, $0.0162/GiB-hr, Pro $150/mo [5][6]. Firecracker **cannot run on [redacted-host] at all** (ssh-verified: KVM guest under AMD EPYC host, `/dev/kvm` absent, no vmx/svm flags, no nested virt exposed — would need bare metal or a nested-virt provider [8][9][10]). Available sandboxing primitive on [redacted-host]: Docker (installed, cgroup v2) + passwordless sudo for iptables egress rules | Firecracker self-host: heavy ops for a spike. E2B/Deno Sandbox: cost-prohibitive ($150/mo ≈ 300k–1.5M laps). `@deno/sandbox`: cloud lock-in + TS-only | **Premature + cost-prohibitive** (SaaS); wrong tool (SDK misdescribed as local) |
| 2. MCP-everything | All factory tools must be MCP servers; sub-agents as MCP microservices | Partly | MCP is real (Anthropic, Nov 2024, JSON-RPC standard) [13]; but its stated purpose is **cross-application interop** — one server serving many clients/apps. Practitioner guidance: MCP for a handful of internal tools in one process "is overhead" [14]. VoltAgent exists as a TS agent framework but MCP there is **optional, off by default** (env-gated) [11][12]. "Standard TypeScript MCP SDKs and Zod" — SDKs exist; mandate invented. No repo in this proposal does "modify the AST via MCP tools" | Feasible but pure overhead: each MCP server = separate process + JSON-RPC plumbing for tools used by exactly one agent | **Wrong** for our scale (interop value only when heterogeneous consumers arrive) |
| 3. Git-native lifecycle | Sandcastle-style: sandbox → clone → branch → modify → extract diffs | Partly | "Sandcastle" = `mattpocock/sandcastle` (`@ai-hero/sandcastle`, MIT) — TS library, `sandcastle.run()`, git **worktrees** as isolation primitive, branch strategies (head / merge-to-head / named branch), commits merged back; providers Docker/Podman/Vercel-Firecracker; agent providers claudeCode/codex/pi [4][7]. It does **not** "modify the AST via MCP tools" — agents get prompts and edit files normally; no AST layer anywhere in README [4]. It is Matt Pocock's project, not Anthropic's | The lifecycle pattern is sound and is essentially what we already do (worktrees, branch, merge). The TS library itself doesn't fit a python-stdlib spike | **Sound pattern, wrong conclusion** — we already implement it in stdlib |
| 4. Durable execution (Temporal) | Wrap agent loop in Temporal; idempotent checkpointed state | Partly | `@temporalio` TS SDK is real and first-class [16]; **workers are Node-only — Deno unsupported** (gRPC-js/http2 incompatibilities, per Temporal forum) [17]. Self-host = Temporal server services (frontend/history/matching/worker) + Postgres/MySQL/Cassandra + your worker fleet [18] — i.e., 4+ services for one solo dev. Real need, wrong default: Restate = single binary [19]; **DBOS TS = npm library, workflows checkpointed to your existing Postgres, no separate service** [20][21]; Inngest self-hosts but is orchestrator-plus-worker [19] | Temporal self-host is absurd overhead at our scale. DBOS-TS/Restate would be the sane picks *if/when* needed | **Premature** (need is real; Temporal specifically is wrong-sized) |

## §2 What the Proposal Gets RIGHT

1. **Durable execution is a real need.** Long agent loops (supervisor → verify → merge →
   deploy) crash mid-run; checkpoint/resume is the correct instinct. The need exists; the
   Temporal-shaped answer doesn't yet fit our scale.
2. **Sandboxing untrusted code is a real concern** — at some scale. Running arbitrary
   model-generated code on the host with full permissions is genuinely dangerous. The
   concern is valid; Firecracker-on-day-one is the wrong rung of the ladder.
3. **MCP interop has real value when heterogeneous consumers arrive** — its actual design
   purpose [13][14]: one tool server, many clients (IDEs, external agents, chat apps). If
   third-party agents ever join the factory, wrapping shared tools in MCP becomes sensible.
4. **Git-native lifecycle is correct** — and we already practice it: branch per lap,
   worktrees for parallel agents, diffs extracted, merge on verify-pass. Sandcastle
   validates the pattern [4]; we don't need the TS library to keep doing it.

## §3 What It Gets Wrong FOR OUR SCALE

1. **Cost math kills SaaS sandboxes.** E2B Pro is $150/mo [5] ≈ 300,000–1,500,000 laps at
   our $0.0001–$0.0005/lap cost. A "mandatory" dependency that costs 5–6 orders of
   magnitude more per unit of work than our entire AI spend is not an architecture, it's a
   budget line item.
2. **`@deno/sandbox` was misrepresented.** It's not a local Firecracker spawner — the
   microVMs run in Deno Deploy's cloud [1][3]. Using it means every lap's code execution
   makes a cloud round trip, and it's JS/TS-first while our spike is python-stdlib.
3. **The proposal's citations don't say what it claims.** Sandcastle does no AST-via-MCP
   tooling [4]; VoltAgent doesn't mandate MCP (off by default) [11][12]; Temporal doesn't
   run workers on Deno [17]. "Mandatory 2026 architecture" is a collage of real tools
   bolted to invented requirements.
4. **Process count vs. one server.** Full adoption = Temporal server ×4 services + DB +
   worker fleet [18] + N MCP server processes + Firecracker jailer/tap/rootfs management.
   Our factory is ~6 stdlib modules [context: POC_PROPOSAL.md]. The infrastructure would
   outnumber the product ~5:1 and every piece is a new failure mode at 3am.
5. **The harvest corpus already covers this.** Our supervision/durability patterns
   (checkpoint-on-crash, resume, idempotent steps) are catalogued in `harvest/`; the
   stdlib spike encodes them directly. Adding Temporal buys a distributed-systems runtime
   to solve a single-node problem.
6. **Deno's own permission system already sandbox-by-default** — `--allow-read=/x
   --allow-net=api.example.com` is a fine-grained capability sandbox built into the
   runtime we'd be using for TS agents, no VM required. The proposal skips rung 4
   (native platform feature) and jumps to rung 7 (datacenter hypervisor).

## §4 Migration Triggers (adopt each pillar WHEN, not IF-ever)

| Pillar | Trigger to adopt | What to adopt first (ladder order) |
|---|---|---|
| Sandboxing | We execute code from untrusted sources (user-submitted, scraped, third-party agents) | 1st: Deno permission flags / python `subprocess` + resource limits. 2nd: Docker+seccomp on [redacted-host] (already installed; passwordless sudo for iptables egress rules); bwrap/nsjail if finer grain needed. 3rd: Firecracker — **requires bare metal or a nested-virt provider; not possible on [redacted-host] (KVM guest, /dev/kvm absent)** — only if threat model justifies new infra |
| MCP wiring | A second, heterogeneous consumer (external agent, IDE plugin, another app) needs our tools | Plain python/TS function tools until then. First MCP server: expose exactly the shared tools, not "everything" |
| Durable execution | Crash-resume needs exceed our resume+ladder pattern: multi-day runs, >1 concurrent worker host, external event waits | DBOS-TS (Postgres-backed library, zero new services) [20][21]; Restate (single binary) [19] if orchestration grows. Temporal only with multi-team/multi-host scale |
| Git-native | Already adopted ✓ | Keep as-is; optionally study Sandcastle's branch strategies (merge-to-head as safe default for unattended runs) [4] |

## §5 References

1. https://jsr.io/@deno/sandbox — SDK exists; Quick Start requires Deno Deploy dashboard + `DENO_DEPLOY_TOKEN` (cloud service)
2. https://docs.deno.com/sandbox/getting_started — same cloud dependency
3. https://deno.com/blog/introducing-deno-sandbox — "lightweight Linux microVMs (running in the Deno Deploy cloud)"
4. https://github.com/mattpocock/sandcastle — README: worktrees, branch strategies, Docker/Podman/Vercel providers; no AST/MCP tooling
5. https://comparesandboxes.com/sandbox/e2b — ~$0.05/vCPU-hr per-second billing; Pro $150/mo
6. https://www.startuphub.ai/ai-news/artificial-intelligence/2026/daytona-vs-e2b-vs-modal-vs-vercel-sandbox-2026 — $0.0504/vCPU-hr, $0.0162/GiB-hr
7. https://www.codeline.co/thoughts/repo-review/2026/sandcastle-orchestrate-ai-coding-agents-in-isolated-sandboxes — "git worktrees as the isolation primitive"
8. https://github.com/firecracker-microvm/firecracker/blob/master/docs/dev-machine-setup.md — bare metal or nested-virt VM required; KVM
9. https://northflank.com/blog/what-is-aws-firecracker — direct KVM access requirement
10. https://mergebase.com/blog/scanning-a-firecracker-microvm — bare-metal/nested-virt constraint
11. https://voltagent.dev/docs/agents/mcp — VoltAgent MCP **client** capability
12. https://github.com/JoshuaC215/agent-service-toolkit/discussions/148 — "Toolkit works without MCP by default; when MCP_ENABLED=true, connect" (VoltAgent's MCP layer is env-gated optional)
13. https://en.wikipedia.org/wiki/Model_Context_Protocol — MCP: Anthropic, Nov 2024, JSON-RPC standard
14. https://casys.ai/blog/why-mcp-protocol — "three tools used by one model in one application: setting up an MCP server is overhead"
15. https://www.getmaxim.ai/articles/what-is-model-context-protocol-mcp-a-2026-guide — cross-app interop purpose
16. https://docs.temporal.io/develop/typescript/client/temporal-client — TS SDK real (`@temporalio/worker`)
17. https://community.temporal.io/t/support-for-deno-one-day/8158 — TS SDK workers on Deno unsupported (gRPC-js/http2)
18. https://docs.temporal.io/self-hosted-guide — self-host: server services + DB (Postgres/MySQL/Cassandra) + worker fleet
19. https://hookdeck.com/webhooks/platforms/inngest-alternatives — Restate single binary; Inngest orchestrator+worker
20. https://news.ycombinator.com/item?id=44842954 — DBOS: "Postgres-backed library you can npm install… no external service"
21. https://www.diagrid.io/faq/alternatives-dbos-inngest/in-what-scenarios-is-dbos-a-more-suitable-choice-than-catalyst-or-inngest-for-durable-agent-execution — DBOS TS for deterministic TS agent logic, MIT, self-host

**UNVERIFIED items:** exact npm package version numbers for `@deno/sandbox`; E2B's current
free-tier credit size (only third-party corroboration found [5][6]); whether any MCP SDK
"requires" Zod specifically (Zod is common but optional).
