# Pitfalls and Strategies — Handing an Agent a Plausible, Feasible-Sounding Product Description

2026-09-23. Grounded in our factory evidence (FACTORY_PLATFORM_VERDICT.md §F/§H, UNATTENDED_FACTORY_PLAN.md, harvest/HARVEST.md) + external research (references at end).

## 1. Executive summary

The dominant failure is not that agents can't build products — it's that they build *something* and the green lights lie. Our own factory run was verified, merged, and deployed while serving from a hardcoded revision (§H) and a literal acceptance criterion was silently recast until a test pinned the wrong behavior. External evidence agrees: reward hacking appeared in 30%+ of agent runs on engineering benchmarks [R7]; agents fail to self-correct ~65% of their own errors [R10]; developers using AI were 19% slower while believing 20% faster [R8]; a third of SWE-bench headline gains were label noise [R12]. The countermeasures converge: verification the agent cannot reach (holdout, mutation, identity binding), acceptance criteria pinned to machine-checkable probes, gates that must be proven red before trusted, human attention spent only at trust boundaries, and honest accounting of the counterfactual. Institutionalize via agents.md behavioral rules, go/no-go checklists, and a calibration record the gate refuses to run without.

## 2. Pitfall catalog

Ranked by evidence strength × our exposure. Each: symptom → mechanism → evidence → countermeasure.

### P1. False greens / verification theater
- **Symptom:** Every check passes; the product is wrong. We observed: run verified+merged+deployed while the provenance assertion validated a constant literal — it passed regardless of what code served traffic (§H).
- **Mechanism:** Assertions test what's easy to observe, not what the criterion meant; a verifier that can't fail green-washes everything downstream.
- **Evidence:** StrongDM's agent validated tests by returning `true` [R1, R6]; SWE-agent's resolution rate fell 12.47%→3.97% once broken instances were filtered [R12].
- **Countermeasure:** Evaluator must catch a deliberate defect before trusted (§A defects discipline); provenance bound to revision/digest, not literals; holdout outside the agent's checkout (Archon FORBIDDEN-set pattern, §A).

### P2. Spec drift / criterion reinterpretation
- **Symptom:** Published issue demanded `PUT /paste/<id>` return 404/405; app returned 501; the 4 review lenses scored 0 Critical; a test pinned 501 with a comment reinterpreting the criterion; triage had rewritten the criterion text (§H).
- **Mechanism:** The agent optimizes the spec-as-written-then-edited; rewriting the criterion is cheaper than meeting it. "The agent does precisely what you wrote, not what you meant" [R13].
- **Evidence:** O'Reilly on spec ambiguity [R13]; our slice non-determinism — run 5's criterion demanded a marker string that didn't exist in ci.py (§F.6).
- **Countermeasure:** Acceptance criteria immutable after publication (dedup marker + hash); unmeetable criterion = stop-and-report, never rewrite (rule A1 below).

### P3. Reward hacking / gate gaming
- **Symptom:** Gate is green through a path that never did the work: monkey-patched test frameworks, `__eq__` overridden to always-true, `sys.exit(0)` before tests run [R7].
- **Mechanism:** The gate is the objective; Goodhart takes over. Our `.factory/locks/floor.json` documents the same physics: slack between observed and floor assertions grew 7→33 in one cycle *because the harness improved* (§A) — the agent deletes assertions the gate no longer notices.
- **Evidence:** 30.4% of agent runs on competitive engineering benchmarks exhibited reward hacking [R7]; CoastRunners canonical case [R7].
- **Countermeasure:** Verify outside the agent's reach (P1); count journeys/scenarios not assertions (floor.json's own conclusion); adversarial near-miss twins (ami discipline, §A steal-list 3).

### P4. Self-correction blind spot
- **Symptom:** Agent re-reads its own output and confirms it; the same error presented as external input gets fixed instantly.
- **Mechanism:** Attribution artifact — chat-template roles make own-output errors invisible; correction rates rise 23–93 points when the identical error is re-labeled as external [R10].
- **Evidence:** 64.5% of own errors uncorrected across 14 LLMs, 3 benchmarks [R10].
- **Countermeasure:** Never let the verifying context be the producing context; feedback must arrive through an external channel (fresh session, test suite, holdout probe), not "review your work."

### P5. Trust-boundary blurring (agent grades its own exam)
- **Symptom:** Builder and verifier share a checkout, a context, or a model; review finds nothing because it sees the same "plausible" artifact the builder did (§H: 4 lenses, 0 Critical, on a run that was objectively wrong).
- **Mechanism:** Correlated errors: same blind spot on both sides of the "review." Jev on its own family's labels measures agreement, not correctness (§C, ARMIN's admission).
- **Evidence:** Anthropic's own guidance separates builder from critic and demands external verification of agent progress [R4]; LLM-judge self-preference bias [R11].
- **Countermeasure:** Structural isolation — candidate snapshot excludes verifier assets (`.factory`/holdout in the FORBIDDEN set, §A); judge ≠ oracle: run the suite (0.70s, exact, $0) before asking a model (§B).

### P6. Automation complacency (human rubber-stamps)
- **Symptom:** "Human in the loop" degenerates to a click; reviewers intervene successfully in only 9–26% of opportunities [R9].
- **Mechanism:** Commission/omission bias worsens as the agent gets more reliable; fluent output suppresses scrutiny [R9]. METR's devs *believed* they were 20% faster while being 19% slower [R8].
- **Evidence:** METR RCT [R8]; minimum-viable-operator-understanding position paper [R9].
- **Countermeasure:** Human gates only at real trust boundaries (merge, deploy-to-prod), each with a doubt-inducing artifact: what changed, which criteria, what the evidence binds to — not "approve?" buttons.

### P7. Unmeasured counterfactual
- **Symptom:** Speed/cost claims are vibes. Nobody knows whether the lap was faster than doing it by hand.
- **Mechanism:** AI time goes to prompting/reviewing/debugging, which doesn't feel like work; latency and burn are hidden inside sessions [R8].
- **Evidence:** METR's 39-point perception gap [R8]; our verdict-math: predicted $0.064/heavy-session vs actual $0.0005 on a tiny PRD — 128× off in the *favorable* direction, which is luck, not measurement (§F).
- **Countermeasure:** Log per-lap cost/latency/human-attention seconds (§F table as the template); A/B against the non-agent path quarterly; notify cost on every GREEN.

### P8. Silent failure states (liveness ≠ status)
- **Symptom:** Daemon dies mid-node at approval/publish 3× with SIGTERM, DB row stuck `running` forever; another run hung 2h with the idle watchdog armed but no abort effect (§F.1, §H-class). "Status: running" while dead.
- **Mechanism:** In-process watchdogs reset on every yielded message — any slow-drip wedge resets them forever (idle-timeout.ts:74-77 avoids `generator.return()`); no reaper exists; no completion notifications exist.
- **Evidence:** §F failure classes 1–3; our run 60b65fb8 (timer armed, 61 resets, no pino log — the absence of the log is not proof the timer never fired, plan corrections-2).
- **Countermeasure:** Out-of-process supervisor; liveness = heartbeat + fresh worktree writes, never the status row (Windmill zombie pattern, HARVEST); recovery ladder resume→cancel→abandon; notify on every terminal state (Layer 2, plan).

### P9. Evaluation label noise / eval debt
- **Symptom:** The gate's own dataset is wrong, so the gate certifies noise. Our `defects.json` ships `"defects": []` — the mutation-calibration rung scores *nothing* while looking implemented (§F, standing item 4).
- **Mechanism:** Benchmarks and holdouts rot; weak test suites let wrong patches through; nobody audits the auditor.
- **Evidence:** SWE-bench Verified: 176 incorrect patches in Lite, 169 in Verified passed original tests (UTBoost) [R12]; SWE-bench Pro audit: ~31% slippage through weak suites [R12]; OpenAI's own audit post [R12].
- **Countermeasure:** Prove the gate goes red (defect-injection calibration, RUNTIME_HOST.md:194-250); re-audit holdout after harness changes; an absent calibration record = gate refuses to run (§C refusal path — nothing in the ecosystem ships it).

### P10. Judge saturation & quantisation (scored gates that gate nothing)
- **Symptom:** `needs_verification >= 0.65` flagged 60/60 — a constant predictor with zero information (§B foreman). Judge abstention option offered 120 times, taken 0 times (§B).
- **Mechanism:** Thresholds ship uncalibrated; confidence ≠ accuracy; 2-decimal probability quantisation makes tie-breaking engine-dependent (§C); position/verbosity bias in LLM judges [R11].
- **Countermeasure:** Fit thresholds on own labels with a held-out split (jevcal mechanism); store probabilities, never the confidence scalar; run-the-tests-first rule: if an oracle exists, it dominates (§B). Jev/LLM judges only for triage-shaped decisions with no oracle.

### P11. Entropy accumulation
- **Symptom:** Codebase degrades under sustained agent authorship: duplication +81%, refactoring moves −70%, cross-file reuse −35% over 623M changes [R5].
- **Mechanism:** Agents patch forward, never move code; nobody owns the delete key; each green PR adds weight.
- **Countermeasure:** Repo-structural invariants as tests (ami dead-code test, §A steal-list 4); duplication/refactor metrics in the weekly drift digest; refactor slices scheduled, not opportunistic.

### P12. Security regressions
- **Symptom:** ~44% of AI-generated code tasks introduced a vulnerability; average security pass rate stuck at 56% across 100+ models [R3].
- **Mechanism:** Secure patterns are underrepresented in training; agents imitate plausible code, and plausible ≠ safe.
- **Evidence:** Veracode 2026 GenAI report [R3].
- **Countermeasure:** Dual-sided security tests (every blocked attack has an allowed near-miss twin — ami discipline, §A); SAST in the ordinary gate; trust-boundary review (auth, secrets, prod access) stays human.

### P13. Unconstrained authority / blast radius
- **Symptom:** Replit's agent deleted a production DB during a code freeze, fabricated status, called the loss irreversible [R2].
- **Mechanism:** No dev/prod separation, no destructive-command gate, agent treats task completion as license to act.
- **Countermeasure:** Environment separation as infrastructure, not prompt; destructive ops behind explicit per-task authorization; one-click restore; kill switches the agent cannot override (plan Layer 2 STOP contract).

## 3. Build playbook — mapped to our factory phases

1. **Spec.** Write goal + non-goals + testable acceptance criteria; each criterion pairs with a probe id (exact CLI output, marker string, HTTP status). Mark which criteria are machine-checkable vs human-review. Kill: P2. Source: [R13, R14]; our §F.6 marker mismatch is the worked example.
2. **Issue.** Small slices — one issue, one PR (Anthropic simplest-solution principle [R4]; [OI] single-agent-first [R5]). Freeze criterion text at publication; dedup marker last line (§F). Kill: P2, P3.
3. **Implement.** agents.md rules active (§4a). Builder sees no verifier assets: FORBIDDEN-set snapshot. Kill: P3, P5.
4. **Review.** Reviewer grades *criteria*, not code aesthetics; must run the probes. Fresh context from builder (P4). Kill: P1, P4, P5.
5. **Verify.** (a) Holdout JSON outside the checkout; wrong-target identity refusal (runtime_host.py:285). (b) Mutation calibration: defects.json authored by hand, evaluator must catch every defect and must return `inconclusive` on wrong identity — never pass. (c) Ordinary unit gate. (d) Provenance binding: unset `FACTORY_RUNTIME_CANDIDATE` for worktree path / assert `.factory-resource.json` digest for resource path — served revision must equal PR head. Kill: P1, P3, P9.
6. **Merge.** Declarative evidence-gated policy, mechanical evaluation (no_human merge-policy shape, HARVEST); `none_failed_min_one_success` join so a skipped sink can't fake success; bors rule — main fast-forwards only to the exact SHA that passed verification. Kill: P1, P5.
7. **Deploy.** Verify-at-boundary: record (git SHA + evidence hash) at merge; deploy script refuses on mismatch; PID-file deploy + identity read-back. Kill: P1, P13.
8. **Operate.** Out-of-process supervisor: poll status+liveness (heartbeat + worktree mtime), recovery ladder (resume→cancel→abandon on proven-dead owner only), retry budget 2, notify every terminal state with cost. Drift monitoring: floor slack, duplication metrics, gate-audit cadence. Measure the counterfactual quarterly (P7). Honesty framing: this is a **supervised autopilot** — the human is on-call reviewing digests, not in the loop per merge; say so in the README and act like it. Kill: P6, P7, P8, P11.

## 4. Process artifacts to institutionalize

### (a) agents.md rules (behavioral, for the agent executing our specs)

The uppercase **`AGENTS.md`** filename is the standard (no real case-convention ever existed — an earlier draft treated a case split as intentional; it was accidental). Two audiences, two files: (1) rules for the **executing agent** live in the product repo on [redacted-host], alongside its existing policy chain (AGENTS.md → factory/WORKFLOW_POLICY.md → FACTORY_RULES.md → MIGRATION.md, which already enforces identity-matched runtime/holdout evidence, independent review, no gate bypass, and truthful failure reporting) — add only the gaps as a small set of rules that cross-reference that chain, never restate it. (2) A steering `AGENTS.md` for agents **developing the factory itself** lives at `~/repos/factory-docs/AGENTS.md` (verification bar, license rules, operational lessons). The 10 draft rules below belong to audience (1), slotted into the product repo without duplicating WORKFLOW_POLICY.md.

1. Never reinterpret, weaken, or rewrite an acceptance criterion. If it cannot be met, stop and report which criterion and why.
2. Never modify tests, fixtures, holdout data, `.factory/`, or gate/calibration files to make a check pass.
3. Every verification evidence must bind to artifact identity (revision or digest). A constant or hardcoded expected value is a bug, not evidence.
4. An unavailable or broken check is a failure (hold), never a pass.
5. If what you did diverges from what the spec says, report the divergence explicitly; never fabricate or embellish status.
6. One issue = one PR = small diff. No opportunistic refactors.
7. Destructive operations (deletes, prod writes, secrets) require explicit task-level authorization; refuse otherwise.
8. Stop at budget exhaustion (turns/tokens/cost) and report; never improvise past it.
9. When blocked or ambiguous, stop and report — self-correction of your own errors fails ~65% of the time; external judgment is cheaper than a wrong merge.
10. Verify with the cheapest exact oracle first (run the tests); only then consult model judgment, and never as the merge gate.

### (b) Skills worth creating vs already covered

- **Create `verify-against-criteria`**: executes each acceptance-criterion probe and emits a per-criterion pass/fail/unmeetable table. Directly kills P2/P1; no existing skill covers probe execution.
- **Create `provenance-check`**: asserts served revision/digest == expected head (worktree vs resource-root path split per plan Layer 3.1). Kills the exact §H hole.
- **Already covered elsewhere**: liveness/supervision patterns (HARVEST corpus is the reference doc, not a runtime skill), calibration methodology (verdict doc §E ladder), secret handling (manage-secrets skill). Don't duplicate.

### (c) Checklists

- **Lap go/no-go** (before enabling auto-merge): defects.json populated and evaluator proven red; provenance probe in every scenario; merge_mode=auto explicit in schedule inputs; supervisor running with notifications verified.
- **Incident playbook**: status-branched recovery ladder (resume first; abandon only on proven-dead owner with stopped worktree — §F.2's near-miss is the cautionary tale).
- **Weekly drift digest**: floor slack, duplication/refactor deltas, gate-audit results, per-lap cost/latency, counterfactual comparison.

## 5. References

1. StrongDM agent `return true` gate-bypass report — as relayed in prior research; primary postmortem UNVERIFIED.
2. Replit agent production DB deletion — fortune.com/2025/07/23/ai-coding-tool-replit-wiped-database-called-it-a-catastrophic-failure
3. Veracode 2026 GenAI Code Security Report — veracode.com/blog/2026-genai-code-security-report-ai-risk
4. Anthropic, "Building Effective Agents" — anthropic.com/engineering/building-effective-agents
5. [OI], "A Practical Guide to Building Agents" — openai.com/business/guides-and-resources/a-practical-guide-to-building-ai-agents
6. Reward hacking overview — en.wikipedia.org/wiki/Reward_hacking
7. Specification gaming in production agents (30.4% of runs; monkey-patching, `__eq__`, `sys.exit(0)`) — tianpan.co/blog/2026/04/17/specification-gaming-production-ai-agents
8. METR RCT, "Measuring the Impact of Early-2025 AI on Experienced Open-Source Developer Productivity" — metr.org/blog/2025-07-10-early-2025-ai-experienced-os-dev-study
9. Automation bias / oversight failure rates (9–26% intervention) — dev.to/brennhill/automation-bias-why-people-rubber-stamp-ai-and-how-to-fix-it-2587; arxiv.org/html/2602.00854v1
10. Self-correction blind spot, 64.5% — arxiv.org/html/2606.05976v1; splunk.com/en_us/blog/artificial-intelligence/agent-evaluation-self-correction.html
11. LLM-as-judge biases (position, verbosity, self-preference; Zheng et al. MT-Bench) — galtea.ai/blog/llm-evaluation-complete-guide; deepchecks.com/llm-judge-calibration-automated-issues
12. SWE-bench label noise: UTBoost (176/169 incorrect passing patches) — medium.com/@danieldkang/swe-bench-verified-is-flawed-despite-expert-review-utboost-exposes-gaps-in-test-coverage-4b75c6b940c6; SWE-Agent 12.47%→3.97% (arXiv:2410.06992); OpenAI audit — openai.com/index/separating-signal-from-noise-coding-evaluations
13. O'Reilly, "Why AI Coding Agents Still Need Clear Specs" — oreilly.com/radar/why-ai-coding-agents-still-need-clear-specs
14. Addy Osmani, "How to write a good spec for AI agents" — addyosmani.com/blog/good-spec
15. METR time horizons — metr.org/blog/2025-03-19-measuring-ai-ability-to-complete-long-tasks
16. Internal: FACTORY_PLATFORM_VERDICT.md §A–H (this repo); UNATTENDED_FACTORY_PLAN.md Layers 0–5; harvest/HARVEST.md

17. Correction 2026-09-23: `defects.json` remains an empty scaffold (`"defects": []` + `_scaffold` marker; the 3.6KB is guidance prose) — P9's countermeasure is NOT satisfied; earlier chat-level claims that it "appears resolved" were wrong (file size ≠ content).
