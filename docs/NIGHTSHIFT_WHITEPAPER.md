# nightshift: The Measured Trust Layer for Unattended Software Factories

**One-line thesis:** in a market drowning in AI-agent harnesses, the investable thing is not the
agent — it is the measured, zero-false-green trust layer that makes an unattended software
factory safe to point at a real repository. nightshift is that trust layer, and we publish our
own worst numbers to prove we can measure.

---

## 1. The problem: nobody can prove their agent actually works

You have seen the demos: an agent takes an issue, writes a patch, tests go green, a PR merges,
confetti. Every pitch shows you the green run. None can answer the only question that matters
for unattended operation — **what is your measured false-green rate?** Not the assumed rate,
not the "we use tests" rate: the measured rate, over adversarial inputs, with the ledger to
show for it. The published evidence says the question has no good answer anywhere — the
industry's evidence base is broken at the foundation:

- **The benchmark itself is the hole.** UTBoost found 345 SWE-bench "passing" patches were
  actually wrong; 40.9% and 24.4% of leaderboard entries re-ranked once the benchmark's tests
  were fixed (https://arxiv.org/abs/2506.09289).
- **OpenAI retracted its own SWE-bench Verified results.** After auditing, 59.4% of audited
  "unsolvable" tasks had broken tests, ~30% of the replacement benchmark was also broken, and
  the named failure category was literally "low-coverage tests... so incomplete fixes can pass"
  (https://openai.com/index/why-we-no-longer-evaluate-swe-bench-verified/,
  https://openai.com/index/separating-signal-from-noise-coding-evaluations/).
- **The benchmarks can be gamed to a perfect score while solving nothing.** Berkeley RDI's
  BenchJack exploit agent scored 100% on five of eight top agent benchmarks (roughly 100% on
  a sixth, 73–98% on the rest) while solving zero tasks
  (https://www.rdworldonline.com/how-a-berkeley-team-broke-8-major-ai-benchmarks-six-of-them-hit-100-without-solving-a-single-task).
- **Even the "validation" signals agents emit are hollow.** BSG-VA found 46.0% of repair
  agents' positive comparable validation events carry no bug-discriminating information at
  all (https://arxiv.org/html/2607.28871). The model saying "verified" is, in nearly half the
  measured cases, noise.

The conclusion is not "agents are bad." It is that **the trust instrumentation does not exist**,
so nobody — vendor, customer, or investor — can distinguish a factory that ships working
software from a factory that ships green CI on hollow tests. The market has fifty harnesses
competing on demo quality and zero competing on measured integrity.

The fix's architecture is already independently validated: Proof-or-Stop's evidence-gated
lifecycle achieved 10/10 scenarios with zero false-DONE, and gated review cut false-green
amplification from 31/1800 to 2/1800 (https://arxiv.org/abs/2607.14890). Evidence-gating
works. Nobody has productized it as the core of an unattended factory. That is the slot
nightshift occupies.

---

## 2. What we built

nightshift is an unattended software factory: a supervisor loop that takes a GitHub issue, makes
exactly one raw LLM API call to produce an edit artifact, and then subjects that artifact to
hard mechanical gates — cross-family review, oracle verification, identity-bound squash merge,
and deploy with a health readback — before anything reaches main. The output is a merged PR
and deployed software, or a kill. There is no in-between "probably fine."

It is eight stdlib Python modules, zero dependencies, running on a single VPS or a laptop. Open
source, Apache-2.0: github.com/noor-latif/nightshift. A five-day spike (2026-09-24 through 2026-09-28, calendar span) is complete and the
product build is scoped — and its two named fixes, the mutation-JSON artifact contract
(section 3) and the dispatch-time RED re-check (SPIKE_LEARNINGS.md L-013), shipped on
2026-09-28 and are validated in the record.

### 2.1 The scoreboard — published before the pitch

This is our culture, not a disclaimer: we publish our failures indexed. Every number below
traces to our evidence log — the DAY reports (DAY2_REPORT.md through DAY5_REPORT.md), the
learnings ledger (SPIKE_LEARNINGS.md, L-000 through L-016), and the bottleneck analysis —
kept as a complete internal record during the time-boxed spike and published in full with
the Phase 0 run, ugly entries included — with a redaction pass limited strictly to
infrastructure details (hostnames, endpoints, credential references); every finding and
number ships unedited. The Phase 0 run is pinned: it is the launch-6 scored window (2026-09-28), published with this document. To our knowledge, no other system in
our 17-repo landscape survey publishes a failures ledger at all. Here is the scoreboard,
unhidden:

| Criterion | Status | The honest number |
|---|---|---|
| S1: 3 consecutive laps, zero human interventions | **MET (launch-6, 2026-09-28)** | 3 consecutive zero-intervention red→green→merged laps in a 14-minute scored window (21:43–21:57Z): #17, #19, #21 all merged, every lap-check `observed []`, zero intervention rows (the mechanical audit covers claim-lifecycle consistency — orphan-claim reaps; the zero-touch claim also rests on the absence of any restart or second session-start row in the window, and the ledger's operator disclosures outside it) — the window's first lap-end row is launch-5's reaped dangling lap (crash/retry at 21:43:12Z, the session-start instant — pre-run bookkeeping, disclosed in the ledger, no intervention row), and the three consecutive greens are launch-6's own laps; the run drained the queue and halted cleanly. The window was short because the queue held exactly three issues — the overnight-duration form of S1 remains open and is the next measurement. The night's five aborted launches and three instrument fixes were operator remediation, disclosed in the ledger. |
| End-to-end green laps | **2 in ~24 (spike); 3/3 in the first clean scored window** | Two eras, labeled. Spike era: n=2 in ~24 runs, toy repo, 1–2 hunk issues — one independent defect→fix green (issue #13; its dispatch window was concurrency-contaminated — documented in the log); the other (issue #12) we label honestly as a refactor lap: the issue's behavior had already landed mid-incident via an earlier crashed lap's merge, and our own report classifies it as such (DAY5_REPORT.md, BIGGEST_ISSUE_ANALYSIS.md). Launch-6 scored window, 2026-09-28: 3 of 3 green — #17 (PR #23), #19 (PR #24), #21 (PR #25), zero interventions. The night's windows add two more greens outside the scored window: #10 (supervised validation lap, PR #20) and #18 (PR #22, a real merge inside the aborted launch-4 window) — 5 greens tonight, all toy-repo 1–2-hunk issues. We do not claim real-repo scale or overnight duration — those are Phase 1 and the next measurement. We claim the integrity thesis holds and the measured bottleneck's fix — the mutation-JSON contract — shipped and was validated by the first clean run. |
| S2: zero false greens | **HELD, ~24 runs** | Zero false greens across all ~24 runs. Every model confabulation was caught by a gate: fabricated diffs with fake commit banners, tool-markup leaks, a test-only "implementation," context-misaligned patches (SPIKE_LEARNINGS.md L-000, DAY2_REPORT.md, DAY5_REPORT.md). This is the thesis, measured. |
| RED-first discipline | **Admission + dispatch-time re-check (shipped 2026-09-28)** | Each issue was admitted only RED-proven — hand-verified RED on fresh main (#10/#12/#13; DAY5_REPORT.md) — and L-013 closed the gap the spike named: since 2026-09-28 the factory re-proves RED at dispatch, re-running the issue's scenario oracle on fresh main before spending a lap. Every scored dispatch in the launch-6 log is preceded by `red-recheck issue N verdict fail` — three re-proofs, one per lap. Admission-time hand-verification remains the root; the dispatch-time re-check is the mechanical restatement of it. |
| Cost | **110–417× under ceiling (all measured greens)** | Ceiling ~$0.01/lap. Two eras, labeled. Spike greens: 27 and 39 microdollars — 0.27% and 0.39% of ceiling, 256–370× under (DAY5_REPORT.md). Launch-6 greens: 24–91 µ$/lap measured — 110–417× under (launch-6 evidence, per-lap cost.json). |
| Latency | **39–418 s lap wall; 20–185 s implementer call (spike); launch-6 calls 8–210 s** | 1–2-hunk toy issues (DAY5_REPORT.md); launch-6 implementer calls measured 8–210 s (per-lap timeline.json). Larger real-repo workloads are unmeasured until Phase 1 — we do not quote a number we cannot trace. We are not a sub-minute demo; we are a measured pipeline. |

Read the scoreboard the way we do. **S1's scored form is met; its overnight-duration form is the
open gap — and S2 held is the moat.** Throughput was a contract problem; its fix — the
mutation-JSON contract of section 3 — shipped 2026-09-28 and the first clean run under it
went 3/3. Integrity under adversarial model behavior is the thing nobody else can show a
number for — and ours is zero, over ~24 runs, against a deliberately confabulation-prone
implementer chosen to stress the gates (SPIKE_LEARNINGS.md L-000). We selected hostile models
on purpose, because gates that only pass with a top-tier implementer prove nothing about
unattended robustness.

Because overclaiming is the failure mode this document exists to prevent, the two clarifications
that matter are already inside the table: RED-first is admission plus a dispatch-time re-check
shipped 2026-09-28 (SPIKE_LEARNINGS.md L-013), with every scored dispatch preceded by a live
RED re-proof on fresh main; and the greens are fully labeled by era — spike-era two,
including the one our own record calls a refactor lap, and the night's five, including the
supervised validation lap and the merge inside an aborted launch window. A scoreboard that flatters cannot be trusted.

---

## 3. The bottleneck finding — and why it is good news

The spike's most valuable discovery is a number a demo-chasing competitor would never surface:

**11 of 14 judged implementer attempts (79%) failed the edit-artifact contract** — malformed
unified diffs with fabricated context and hunk miscounts — across three model families
(deepseek, glm, luna) (BIGGEST_ISSUE_ANALYSIS.md).

Three properties make this finding an asset rather than a scar:

1. **The bottleneck is the interface, not model competence.** Stronger models did not reduce
   the failure rate — they moved the failure sub-class from structural malformation
   (miscounted hunks) to fabricated context (invented adjacency). The rate held; the shape
   shifted. That is the signature of a broken contract, not a weak model. Contracts are things
   we control; model competence is a vendor roadmap we do not.
2. **The fix was small — and it shipped.** Replace the model-authored unified-diff contract with a
   search/replace mutation JSON: the model quotes an exact anchor plus a replacement; the
   factory validates that the anchor occurs exactly once, applies it, and synthesizes the git
   diff itself. The model never authors line numbers or context headers again — the
   hunk-arithmetic and fabricated-adjacency failures in our 79% cannot be expressed in the
   new contract. A model that hallucinates context can still hallucinate anchors — but the
   ask shrinks, and misses fail loud and converge under retries (BIGGEST_ISSUE_ANALYSIS.md).
3. **The fix is independently corroborated three times in our reference survey**
   (BIGGEST_ISSUE_ANALYSIS.md — ai-software-factory and the agent-native cohort;
   AMI_PAPERCLIP_EVALUATION.md — SequentialEdit): coleam00/ai-software-factory already
   ships this exact contract; SuperInference Core (ami)'s own file-edit tool is
   search/replace with post-hoc diff synthesis; and the entire agent-native cohort — the
   Claude Code and Codex CLI factory patterns — never consumes model-authored diffs at
   all. Three independent lineages converged on the same answer. We measured the reason they did.

A 79% failure rate caused by model incompetence would be a bad investment. A 79% failure rate
caused by a contract, with a validated replacement, was fixable on a schedule — and it
shipped 2026-09-28; the first clean run under it went 3/3 green. The measurement discipline
that found it, fixed it, and re-measured is the product.

---

## 4. The three binding problems for "point it at any real repo"

These are scoped engineering items, not vision-ware. Each has a named mechanism, an external
corroboration, and an acceptance artifact. An unattended factory that cannot answer all three
is a toy regardless of its green rate.

### 4.1 Oracle authoring — who writes the failing test when the fixer can't be trusted?

A trust layer is only as strong as its oracle. Two failure modes dominate: overfitting (the
oracle shares the implementer's blind spots) and vacuity (the oracle passes anything). We
compose two mechanisms, each covering the other's documented failure mode:

- **DUBS-style cross-family sealed oracle authorship**
  (https://github.com/DUBSOpenHub/dark-factory): a different-family model derives fail-to-pass
  scenarios from the issue, hidden outside the repo, invisible to the implementer.
  Dark-factory's documented invariant — same-family models share failure modes, so the seal
  author must not share a family with the implementer — is a rule we adopt verbatim.
- **Mutation-proven admission:** a generated scenario is only accepted if it demonstrably
  fails on an injected defect. The oracle must prove it can go RED before it may say GREEN.
  This exists because generated tests are themselves untrustworthy: SWT-Bench measured 26.9%
  of generated fail-to-pass candidates also fail on the gold fix
  (FALSIFY_AND_ORACLE_RESEARCH.md). Oracles need differential proof, not vibes.

Sealing stops overfitting and same-family blind spots; mutation-proofing stops vacuous
oracles. Neither alone survives its documented failure mode. Together, the oracle is as
untrusted-and-proven as the implementer.

### 4.2 The artifact contract — the measured 79% bottleneck

The mutation-JSON contract of section 3 — not the spike's model-authored unified-diff
contract — shipped 2026-09-28 and is what the factory runs. Acceptance artifact met: a
supervised validation lap (#10, PR #20) against a live model emitted mutation JSON and the
factory applied it end to end, before any unattended run; the first clean run under it went
3/3. We did not spend an unattended night on an unvalidated contract — that sequencing was
itself a gate, and it held.

### 4.3 Entropy — agent-authored codebases rot

The 623M-change GitClear study measured what sustained agent authorship does to a codebase:
duplication +81%, refactoring movement −70%, cross-file reuse −35%
(https://www.gitclear.com/the_ai_code_quality_maintainability_gap). Every factory that merges
green PRs without structural gates compounds that debt at machine speed.

Our answer: **repo-structural invariant gates** — duplication, dead-code, and
refactor-movement checks as first-class lap gates, on par with the oracle. A lap that satisfies
its scenario but degrades the repository's structure does not merge. No factory in our
17-system landscape survey ships this; it is the difference between "merged a PR" and
"develops large software long-term without degrading it."

---

## 5. The falsifier — the novel gate, and the moat

Every verification system in the landscape verifies that work was done. None verifies that the
work is *wrong in a way the oracle missed*. nightshift adds a falsifier role:

- A cross-family model receives the fix plus the fixer's stated assumptions, and **tries to
  construct executable counterexamples** — new inputs, not critique prose.
- **Admission is differential:** a counterexample counts only if it passes on the pre-fix base
  AND fails on the fixed tree. The falsifier cannot manufacture false reds; it can only
  surface real ones.
- **Every admitted case becomes permanent regression armor**, added to the suite.

Our 17-repo survey found the neighboring roles but not this one: debate tools produce
critique prose, red-team frameworks attack specs, replay tools re-run old commands. None
constructs new inputs against a fix. It is unoccupied, mechanically checkable, and it
compounds — each run leaves the repository harder to silently break than the night before.

---

## 6. Market positioning: the crowded market and the unoccupied slot

The agent-factory category is crowded. Our survey covered 17 systems — zeroshot, foreman,
paperclip, Archon, NEEDLE, sortie, gastown, no_human, batty, omnara, aa-llm-compare, openrig,
ami, ai-software-factory, symphony, SWE-AF, and dark-factory (COMPETITOR_LANDSCAPE.md,
LANDSCAPE_SCOUT_2026-09-28.md). The pattern: harnesses, dashboards, governance planes.
Execution plumbing and its observability are commodities.

What nobody ships is **an active falsifier that constructs executable counterexamples against a
fix**, and, to our knowledge, none of the surveyed systems publishes a **measured false-green
rate**. The slot is not just unoccupied — the evidence in section 1 says the rest of the market
*cannot* occupy it without retracting their demos, because their demos are the product and
our product is the measurement that would fail those demos.

nightshift's positioning in one sentence: **we are not selling an agent that appears to work;
we are selling the trust layer that proves whether it did, with numbers, against adversarial
models, published either way.**

---

## 7. Roadmap

Each phase ships a public acceptance artifact. No phase is "explored" — it is either landed
with its artifact or it has not happened.

### Phase 0 — the founding artifact: one instrumented overnight run

Three fresh RED-proven issues, an interventions log, single-instance locking, and crash
reconcile — run overnight, unattended, **published either way**. The artifact is: three
zero-intervention greens, or an honest forensic of why not. This run is the falsifiable core
of the thesis (section 9).

### Phase 1 — the real-repo kernel

Two capabilities that gate "point it at any real repo": context-fit — targeted-read injection
over whole-file dumps, so the implementer sees the code relevant to the issue, not the
repository — and the entropy gates of section 4.3. Acceptance artifact: end-to-end laps on a
repository we did not author.

### Phase 2 — self-hosting

nightshift develops nightshift. The founder's own use is the acceptance test — this factory's
job is to maintain the software you would be investing in. A family-rotation rule keeps the
factory from grading its own homework: the implementer family is never the judge family, and
the rotation is mechanical, not discretionary.

### Cost and latency honesty, as standing policy

Measured lap wall on 1–2-hunk toy issues: 39–418 s, with the implementer call itself 20–185 s
(spike; DAY5_REPORT.md) and 8–210 s in launch-6 (per-lap timeline.json). Larger real-repo
workloads are unmeasured until Phase 1. Cost is measured against order-book truth: the factory
records `buyer_cost_micro` — what a buyer actually pays — not vendor-reported cost, which
our wiring measured at ~15% under the real number (DAY5_REPORT.md). The spike's green laps
cost 27–39 µ$ against a $0.01 ceiling; when we quote cost, it is
the buyer's number, not the vendor's.

---

## 8. Why this team

Three behaviors, all in our evidence log — published in full, redacted only for infrastructure details, findings unedited, with the Phase 0 run (pinned: the launch-6 scored window, 2026-09-28, published with this document) — that predict how this build behaves under pressure:

- **We publish failures indexed.** SPIKE_LEARNINGS.md L-000 through L-016 is a failures
  ledger — including the entries that make our spike look worse (L-013: the RED re-verification
  gate the spike was missing, since shipped 2026-09-28 and proven in the scored log; the
  interventions-log gap that made S1 unmeasurable). No competitor in our 17-repo survey has
  an equivalent. A team that indexes its own failures will find yours before you do.
- **We falsified our own judge-gate.** We selected a deliberately confabulation-prone
  implementer against our reviewer specifically to stress the verification machinery
  (SPIKE_LEARNINGS.md L-000) — our zero-false-green number is adversarial, not curated.
- **Stdlib discipline.** Eight modules, zero dependencies, one VPS or a laptop. The trust layer
  must never itself rot; we built it boring on purpose, and the 110–417× cost margin under
  the $0.01 ceiling — every measured green, both eras (the spike era alone: 256–370×) — is
  a byproduct of that discipline, not a retrofitted target.

---

## 9. The falsifiable prediction

Here is the thesis in a form you can hold us to:

**We will run the Phase 0 overnight instrument — three fresh RED-proven issues, interventions
logged, published either way. If three issues do not go zero-intervention red→green→merged,
the unattended thesis is wrong, and we will publish that result with the same care as a
success.**

**Resolution — 2026-09-29 (dated after the prediction above; the prediction text is unchanged
and stands as written):** the first genuinely clean run met the criterion — but in 14 minutes,
not overnight. The launch-6 scored window (2026-09-28T21:43:12Z–21:56:55Z) delivered three
consecutive zero-intervention red→green→merged laps (#17, #19, #21; every lap-check
`observed []`), then drained the queue and halted cleanly — because the queue held exactly
three issues. The run was unattended, but it was not overnight-length, and we report the
divergence rather than round it up. The next measurement is an overnight window with a queue
deep enough to outlast it.

We are not asking you to trust the demo. We are asking you to invest in the measurement — and
the next measurement is scoped, prepped, and one go-decision away. The trust layer is the product; the scoreboard above
is its first output; the overnight run is its second.

The market has fifty factories that will show you a green run. nightshift is the one that will
show you the ledger.
