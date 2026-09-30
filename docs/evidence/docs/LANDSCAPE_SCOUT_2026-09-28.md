# AI Factory / Agentic Orchestration Landscape Scout — 2026-09-28

Scope: NEW and upcoming (2025-2026, active) factory/orchestration systems worth cloning for nightshift.
Excluded (already tracked): ai-software-factory (coleam00), Archon, symphony, NEEDLE, sortie, gastown,
no_human, batty, omnara, aa-llm-compare, openrig, ami, paperclip, OpenRig blog.
Relevance lens: supervisor/claim/lease mechanics, artifact contracts, verification gates, failure
taxonomies, retry/escalation, self-improvement with guardrails. Not cared about: approval UIs, daemon UX,
provider plumbing. All stars/commit-dates/license verified via GitHub API or github search on 2026-09-28.

## 1. Findings table

| Name | Upstream | What it actually is | Last commit / stars | License | Rel. | Clone? |
|---|---|---|---|---|---|---|
| zeroshot | https://github.com/the-open-engine/zeroshot | Multi-agent graph orchestrator: worker implements, independent reviewers accept/reject, failures route to bounded repair; delivery only after graph checks pass. Native Rust binary (v8 retired the Node runtime). | 2026-09-28 / 1915★ | MIT | 5 | Y |
| Foreman | https://github.com/thruwire/foreman | **PRIOR ART, REFUTED (own corpus)** Supervisor layer placing a fast decision model (TypeSafe Jev) over Codex/OpenCode workers; emits probabilistic responsibilities (worker_stuck .02, needs_human .01, needs_verification .82) then continue/steer/stop/retry. Shipped gate measured as constant predictor (60/60, zero information; FACTORY_PLATFORM_VERDICT.md:156-166). Python. | 2026-09-27 / 599★ | MIT | 5 | Y |
| SWE-AF | https://github.com/Agent-Field/SWE-AF | "One API call -> full engineering team -> shipped code." Fleet runtime on AgentField; planner/coder/reviewer/QA with enable_learning flag. Python 3.12+. | 2026-09-24 / 1015★ | Apache-2.0 | 4 | Y |
| dark-factory (DUBS) | https://github.com/DUBSOpenHub/dark-factory | Copilot CLI skill: goal -> PR via 8 specialist agents from different model families, judged by sealed-envelope hidden acceptance tests (shadow score = sealed failures / sealed total). Markdown skills + spec repo. | 2026-09-11 / 27★ | MIT | 5 | Y |
| software-factory (`sf`) | https://github.com/nicolasmelo1/software-factory | Rust single binary: every rule written twice (prose + failing check), every check has a mutation test proving it fires; config self-protected so an agent can't reach green by disabling a rule. Catalog digest pinned in `--version`. | 2026-09-25 / 34★ | MIT | 5 | Y |
| aeon | https://github.com/aeonfun/aeon | Runs unattended on GitHub Actions; markdown-defined skills dispatched to agent CLIs with self-healing of failing skills. Shell. | 2026-09-28 / 756★ | MIT | 4 | Y |
| fabro | https://github.com/fabro-sh/fabro | "Open source dark software factory": process-as-graph with deterministic verification nodes (tests, linters, LLM-as-judge), automatic fix loops, durable event streams/checkpoints, 24/7 API-server queue. Rust. | 2026-09-28 / 1663★ | MIT | 4 | Y |
| Proof-or-Stop | https://arxiv.org/abs/2607.14890 | Paper + method (not a repo): lifecycle transitions only when fresh, source-state-bound, mechanically verifiable evidence satisfies the gate; "10 of 10 scenarios with zero false-DONE." Implementation repo not found on GitHub (org has only a profile README). | 2026-07-16 / n/a | paper | 5 | N (paper) |
| agentic-orchestrator | https://github.com/doordash-oss/agentic-orchestrator | DoorDash's deterministic harness: feature description -> reviewed PR through gated phases (research, design, plan, implement, review, publish). Go. | 2026-09-25 / 108★ | Apache-2.0 | 3 | N |
| Machinist (owainlewis) | https://github.com/owainlewis/machinist | Worker-fleet infra pulling tasks from ticket queues into isolated workspaces; "accepts any executable that reads a prompt from stdin". | not verified (API rate limit) | unknown | 3 | N |
| gh-aw | https://github.com/github/gh-aw | GitHub's official: markdown+YAML agentic workflows compile to locked-down Actions with sandboxed agents and validated "safe outputs". Go. | 2026-09-28 / 5196★ | MIT | 3 | N |
| majiayu000/harness | https://github.com/majiayu000/harness | "Fleets of parallel coding agents with governance": Rust control plane, orchestration, policy, cross-agent review, observability. Claude Code & Codex. | 2026-09-27 / 80★ | MIT | 3 | N |
| sample-autonomous-cloud-coding-agents | https://github.com/aws-samples/sample-autonomous-cloud-coding-agents | AWS sample: tasks -> PRs via isolated runtimes (AgentCore), with orchestration, observability, governance. TypeScript. | 2026-09-28 / 152★ | MIT-0 | 3 | N |
| Kapso | https://github.com/Leeroo-AI/kapso | Self-improving factory built for measurable objectives; published results on MLE-Bench and ALE-Bench. Python. | 2026-09-28 / 115★ | MIT | 3 | N |
| fspec | https://github.com/sengac/fspec | Spec-driven multi-agent "Dark Factory" harness; TDD/BDD/example-mapping topics suggest oracle-style gates. Rust. | 2026-09-27 / 95★ | MIT | 3 | N |
| Forgeo | https://github.com/lucaGazzola/forgeo | Scheduled factory: plain-JSON backlog, agent per task, commits to main, refactors when idle. No branches, no PRs. Python. | 2026-09-19 / 32★ | MIT | 3 | N |
| Optio | https://github.com/jonwiggins/optio | Self-hosted platform: GitHub/Linear/Jira/Notion tickets -> merged PRs through a "Kubernetes-style reconciliation control plane". TypeScript. | 2026-09-26 / 1054★ | MIT | 3 | N |

Context finds (lists/papers, not clones): awesome-software-factories (CC0, updated 2026-09-28,
https://github.com/varun1505/awesome-software-factories) — the best map of the whole space; best-of-Agent-Harnesses
(CC-BY-SA-4.0, 993★, rescored weekly, https://github.com/RyanAlberts/best-of-Agent-Harnesses);
"Why Software Factories Fail" (HumanLayer/Dex Horthy, 394 pts on HN,
https://github.com/humanlayer/advanced-context-engineering-for-coding-agents/blob/main/wsff.md).

## 2. Per-strong-find steals (relevance >= 4)

**zeroshot (5)** — The steal is the explicit graph-as-authored-data with independent parallel review and
bounded repair routing: "One agent implements. Independent agents review. Failures route back into bounded
repair. Delivery happens only after the graph's checks pass." Read `software-change` graph definition first
(see README "The built-in `software-change` graph" sequence). MIT, no friction. The retry-path/exit-condition
data model is directly mappable to nightshift's gate sequence.

**Foreman (5) — PRIOR ART AND REFUTED, not a fresh lead** — Already in our corpus and already
falsified by our 2026-09-20 measurement (FACTORY_PLATFORM_VERDICT.md:156-166): the shipped gate
(`needs_verification >= 0.65`) flagged 60/60 mutants on the 120-mutant corpus — precision 0.7167
equals the base rate, a constant predictor with zero information; AUC 0.735 for
`needs_verification`, `implementation_complete` scored in the wrong direction (bugs 0.501 vs
clean 0.553). Recorded as the canonical scored-gate-that-gates-nothing antipattern in
PITFALLS_AND_STRATEGIES.md:67-70 (P10). The "steal: calibrated probabilities" framing is
withdrawn — the shipped probabilities carried zero information; per the run-the-tests-first
rule, any supervision decision that has an oracle must use the oracle (nightshift's gates
already do; measured: oracle free and exact at the same ~0.70s latency vs Jev $0.000024/call
at 86%). Residual value, honestly stated: only as a *negative* exemplar (ship uncalibrated
thresholds → judge saturation) and possibly as reference for its evidence-provider/routing
docs — NOT a steal-read. Limits, so the refutation is not overstated: one 600-LOC file, 120
mutants, one task family (defect detection), one model version (jev-1.13.0) — this refutes
the shipped gate as shipped on that corpus, not proof Jev can never be calibrated.

**DUBSOpenHub/dark-factory (5)** — The steal is sealed-envelope testing + cross-family model independence:
"the QA Sealed agents write acceptance tests before any code exists, hide them in a vault outside the
repository, and the builder never sees them", with the explicit warning that same-family models share
failure modes so "the bias ... always points toward 0% — the system overclaims quality exactly when it is
least entitled to." This is the strongest third-party validation of nightshift's RED-first oracle + cross-model
review design. MIT (both dark-factory and shadow-score-spec). Also grab
https://github.com/DUBSOpenHub/shadow-score-spec (the scoring spec).

**nicolasmelo1/software-factory (5)** — The steal is mutation-tested gates: "every check has a mutation
that proves it fires" and self-protecting config ("an agent cannot reach a green build by turning a rule
off"). Directly answers nightshift's zero-false-greens requirement. Rust, MIT. Read `sf verify`/`sf check`
rule catalog structure.

**SWE-AF (4)** — The steal is the fleet architecture + `enable_learning` flag (self-improvement with an
off switch = guardrail). Apache-2.0. Read the planner build graph in the README's architecture section.
Note vendor marketing: AgentField is a company (WorldSpace Community Developer badge); treat adoption
claims as marketing, mechanisms as code.

**aeon (4)** — The steal is self-healing skills on GitHub Actions: skill fails -> heals -> retries,
unattended. MIT. Read the healing loop implementation first.

**fabro (4)** — The steal is durable event streams + checkpoints + 24/7 queue ("Fabro's API server queues
and executes runs continuously") — queue/liveness primitives to borrow. Rust, MIT. Larger diff, web-wizard
onboarding is not relevant to us.

**Proof-or-Stop (5, paper)** — Read the paper for the evidence-gated lifecycle formalism: "treats agent
outputs as claims rather than lifecycle state". Their "10 of 10 scenarios with zero false-DONE" and the
9,240-cell ablation (visible-pass/hidden-fail reduced 31/1800 -> 2/1800) is the strongest published
evidence for nightshift's zero-false-greens thesis. Implementation repo not locatable on GitHub; the org
(https://github.com/Proof-or-Stop) contains only a profile README as of 2026-09-28. Note dispute: paper
claims "an open-source implementation"; no public repo found — record as unresolved.

## 3. Evidence cards (top 3)

### zeroshot — https://github.com/the-open-engine/zeroshot (MIT, 1915★, pushed 2026-09-28)
> "The agent that writes the code should not be the one that decides it works."
> "Zeroshot turns a software goal into an explicit multi-agent graph. One agent implements. Independent
> agents review. Failures route back into bounded repair. Delivery happens only after the graph's checks
pass."
> "The built-in `software-change` graph: 1. gives the goal to a worker; 2. runs acceptance and code review
> independently and in parallel; 3. routes rejected evidence to a repair worker and repeats both reviews;
> 4. with delivery enabled, delivers an accepted change through Git, CI, and merge; 5. routes delivery
> conflicts back through repair and review."
Source: README via GitHub API, read 2026-09-28.

### DUBSOpenHub/dark-factory — https://github.com/DUBSOpenHub/dark-factory (MIT, 27★, pushed 2026-09-11)
> "Sealed testing creates a blindfolded QA loop: the QA Sealed agents write acceptance tests before any
> code exists, hide them in a vault **outside the repository**, and the builder never sees them."
> "[Shadow scores] (sealed failures / sealed total) expose blind spots numerically."
> "A Shadow Score is only meaningful if the tests and the code come from **different minds**. ... Two
> instances of one model family share training data, reasoning priors, and — critically — **failure modes**."
Source: README via GitHub API, read 2026-09-28. Low stars but exact mechanism match + shipped spec.

### Proof-or-Stop — https://arxiv.org/abs/2607.14890 (paper, 2026-07-16)
> "lifecycle states such as reviewed, tested, DONE, and ready-to-merge remain claims unless supported by
> current evidence."
> "permits lifecycle transitions only when fresh, tracked-source-state-bound, mechanically verifiable
> evidence satisfies the relevant gate."
> "The unattended-loop engine passed 10 of 10 scenarios with zero false-DONE, and local-key receipt
> bundles rejected 18 tamper classes with zero false accepts."
Source: arXiv abstract via export API, read 2026-09-28. Related follow-up: "From Agent Output to
Authorized Transition" (https://arxiv.org/html/2609.28216v1, 2026-09-23).

## 4. Clone-now shortlist (ordered)

1. https://github.com/the-open-engine/zeroshot — graph contract + independent review/repair routing.
2. https://github.com/DUBSOpenHub/dark-factory — sealed-envelope testing + cross-family independence
   (plus https://github.com/DUBSOpenHub/shadow-score-spec).
3. https://github.com/nicolasmelo1/software-factory — mutation-tested, self-protecting gate catalog.
4. https://github.com/thruwire/foreman — probabilistic supervision/failure taxonomy over workers
   (kept as prior-art/negative exemplar; gate refuted — see §2; refuted as a fresh lead, so it
   drops below the genuine fresh leads above; already cloned at ~/repos/foreman).
5. https://github.com/Agent-Field/SWE-AF — fleet runtime with learning flag; Apache-2.0.

## 5. Noise (hyped-but-irrelevant or thin)

- addyosmani/factory (211★, MIT) — issue-queue operating model but draft-PR triage with human merge; no new gate mechanics. https://github.com/addyosmani/factory
- safe-agentic-workflow / SAW (416★, MIT) — SAFe methodology in Claude Code commands; process cosplay, not mechanism. https://github.com/bybren-llc/safe-agentic-workflow
- Loop-engineering blog wave (Shakudo, AI Builder Club, johnmatrix.org) — "write more loops" content marketing, no repo evidence.
- Autoheal ($7.9M raise, SiliconAngle 2026-09-28) — closed-source YC company, no repo. https://siliconangle.com/2026/09/28/autoheal-raises-7-9m-to-evaluate-and-fix-ai-agents-with-ai-agents/
- AugmentCode "9 Open-Source Agent Orchestrators" roundup — vendor list, mostly approval-UI tools. https://www.augmentcode.com/tools/open-source-agent-orchestrators
- Ralph/ralphex/ralph-* ecosystem — raw re-prompt loops without gates; mostly unmaintained forks; nightshift superseded the pattern.
- gnomish-factory (9★, Apache-2.0) — real claim/pick/sandbox design but Groovy and tiny; skim only. https://github.com/oinsio/gnomish-factory
- Tencent workbuddy-bench (368★, NOASSERTION) — enterprise agent benchmark, not a factory. https://github.com/Tencent/workbuddy-bench
- Ivy Tendril (200★, C#, NOASSERTION) — verification-gate design worth reading, wrong license/stack to clone. https://github.com/Ivy-Interactive/Ivy-Tendril

## 6. Sources (URLs actually read)

- https://github.com/topics/dark-factory (repo list + descriptions)
- https://github.com/topics/software-factory (search results snippet)
- https://raw.githubusercontent.com/varun1505/awesome-software-factories/main/README.md (the canonical map; CC0)
- GitHub API repo metadata (stars/pushed_at/license) for all table rows, fetched 2026-09-28
- https://github.com/thruwire/foreman README (via API)
- https://raw.githubusercontent.com/fabro-sh/fabro/main/README.md
- https://github.com/Agent-Field/SWE-AF README (via API)
- https://github.com/nicolasmelo1/software-factory README (via API)
- https://github.com/DUBSOpenHub/dark-factory README (via API)
- https://raw.githubusercontent.com/humanlayer/advanced-context-engineering-for-coding-agents/main/wsff.md
- https://hn.algolia.com/api/v1/search?query=software%20factory%20agents (and unattended-coding-agent query)
- https://stripe.dev/blog/minions-stripes-one-shot-end-to-end-coding-agents-part-2 (vendor blog; blueprint state-machine: deterministic nodes intermixed with agent nodes, one CI retry then escalate)
- https://arxiv.org/abs/2607.14890 + https://export.arxiv.org/api/query?id_list=2607.14890 (Proof-or-Stop)
- GitHub search tool (gh): org:Proof-or-Stop, "openrig", "Proof-or-Stop lifecycle", code search hits
- https://arxiv.org/html/2609.28216v1 (follow-up paper, referenced only) + https://github.com/Proof-or-Stop (org profile README only)

## 7. Vector summary (for the shortlist answer)

- GitHub repo search (factory/dark-factory/topics): full, rich.
- HN/blog vector: full — wsff.md (394 pts) is the key critical essay; Stripe Minions the key mechanism blog.
- Research/eval vector: Proof-or-Stop paper is the standout; no RED-first-branded *harness* repos found — the terminology that surfaces is "sealed-envelope", "evidence-gated"; "oracle" appears mostly in papers.
- Orchestration-runtime vector: fabro (queue+checkpoints), zeroshot (graph), Optio (reconciliation control plane) have stealable queue/liveness primitives; Machinist unverified due to API rate limit.
- Successor/spinoff of tracked repos: EMPTY — no notable new Archon/coleam00/OpenRig successor beyond mvschwarz/openrig itself (1.5k★, active, already tracked).
