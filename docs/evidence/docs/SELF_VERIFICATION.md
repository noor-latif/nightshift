# Self-Verification for AI Agents — Evidence and Recommended Stack

Researched 2026-09-23. Every claim below is grounded in a fetched primary source unless marked UNVERIFIED.

## 1. Technique taxonomy

| Technique | What it does | Evidence it works | Cost | Citation |
|---|---|---|---|---|
| Exact oracles (tests, typecheck, compilers, repro) | Environment ground truth; pass/fail loop closes itself | Anthropic: agents gain "ground truth from the environment at each step"; "Give Claude something that produces a pass or fail, and the loop closes on its own" [1][2] | Low (runtime only) | [1][2] |
| Test-first agents (write failing test before code; split Writer/Reviewer) | Tests become the executable spec; author can't grade own homework | Anthropic best practices prescribe it verbatim: "have one Claude write tests, then another write code to pass them" [3] | Low–med | [3] |
| Fresh-context review (separate session/subagent sees only the diff) | Removes author bias; same error seen as external input gets caught | CCR experiment: F1 28.6% vs 24.6% same-session (p=0.008), +11pp on critical errors; second same-session pass made it WORSE (21.7%) [4]; Tsui: identical errors corrected when external, missed when own (64.5% blind spot) [5] | One extra session | [3][4][5] |
| Separate critic model (generator-verifier gap) | Generator and judge are different models; verification is easier than generation (Verifier's Rule) | CriticGPT: human+Critic teams beat unassisted humans >60%; DeepMind GenRM Best-of-N: GSM8K 73%→93.4% [6][7] | Med–high (second model) | [6][7][8] |
| Process reward models (step-level checks) | Score each step, not just the outcome; better credit assignment | PRM 78.2% vs ORM 72.4% vs majority-vote 69.6% (best-of-1860, MATH); gap widens with N [9] | High (training/labels) | [9] |
| Chain-of-Verification (CoVe) | Draft → plan verification questions → answer them independently → revise | Llama 65B Wikidata precision 0.17→0.36; FactScore 55.9→71.4; factored (independent) prompts beat joint [10] | 4+ prompts, parallelizable | [10] |
| Self-consistency (N samples + majority vote) | Sample N reasoning paths, vote | GSM8K +17.9%, SVAMP +11.0% absolute; but fails when errors are correlated (shared priors converge to shared wrong answer) [11][12] | N× inference | [11][12] |
| Reflexion (verbal self-reflection loop) | Agent reflects on task feedback signals into episodic memory, retries | 91% pass@1 HumanEval — but the loop is driven by EXTERNAL feedback (tests/env), not free-form self-review [13] | Trials | [13] |
| Checklist/rubric eval (CheckEval) | Decompose judgment into binary checklist items instead of Likert/free-form | Average inter-judge agreement +0.45, score variance down, across 12 evaluator models [14] | Low (prompt design) | [14] |
| Adversarial near-miss pairs | Calibrate a judge/classifier on allowed-vs-blocked boundary cases from a written constitution | Constitutional Classifiers: synthetic hard cases from permitted/restricted rules; no universal jailbreak in 3,000h red-teaming; +0.38% false refusals [15] | Med (pair construction) | [15] |
| Cheap self-check nudge ("Wait" token) | Force continued scrutiny of own output | Cuts the 64.5% self-correction blind spot by 89.3% with zero training [5] | ~Zero | [5] |
| Hooked deterministic gates ([CC] hooks pattern) | Shell checks run automatically at lifecycle points; can block tool calls/completion | Mechanism verified in official docs [16] (blog endorsement sentence: UNVERIFIED) | Low | [16] |
| Generator paired with automated evaluators (AlphaEvolve) | Only pursue objectives that are automatically verifiable | Production: 0.7% of worldwide compute recovered, 23% kernel speedup [17] | High infra | [17] |

## 2. What the evidence says does NOT work

- **Same-context self-review.** Intrinsic self-correction without external feedback fails and often degrades performance (Huang et al.) [18]; 64.5% of injected errors in own output go uncorrected while identical external errors are fixed [5]; a second review pass in the SAME session added noise, not signal (F1 24.6%→21.7%) [4]. Verdict: never the only gate.
- **Second same-session pass as "more review".** Explicitly ruled out as a fix by the CCR experiment [4].
- **Free-form LLM-judge-only gates.** Unstructured judging has low inter-judge agreement and high variance [14]; combine with a checklist at minimum, and never as the sole gate when an oracle exists.
- **Majority voting on correlated errors.** If models share priors (same pretraining), debate/sampling converges to the shared misconception [12].
- **Trusting worker self-reports.** Anthropic observed agents "mark a feature as complete without proper testing" — "looks done" is the only signal without a check [2].
- **The claimed 23–93 point fresh-context gap: UNVERIFIED.** Direction is supported [4][5][3], but the specific magnitude was not found in any primary source; the controlled measurement is much smaller (~4 F1 points overall, +11pp critical) [4]. Treat 23–93 as unattributed.

## 3. Recommended stack

### (a) Factory executing agent (per phase, cheap-first)

- **Spec:** decompose the spec into a binary acceptance checklist before any code (CheckEval pattern [14]). Each item must name an observable, ideally executable, oracle.
- **Issue:** no issue without acceptance criteria that a machine can evaluate — front-load the test suite (Verifier's Rule [8]).
- **Implement:** test-driven — failing test first, then code to pass it [3]. Deterministic hooks on every edit: typecheck/lint block the loop on failure [16].
- **Review:** fresh-context reviewer subagent that sees ONLY the diff + the checklist, never the implementation reasoning [3][4]. Route non-executable aspects (docs, claims, naming) through factored CoVe-style independent questions [10]. Optionally append "Wait" before the reviewer's verdict [5].
- **Verify:** exact oracles first (tests, typecheck, repro script, actually running the thing); only then model judgment on whatever oracles can't cover, checklist-formatted, calibrated on near-miss pairs [15].
- **Merge:** gate on pass/fail oracle output, never on the agent's completion report [2]. If sampling multiple candidate implementations, prefer step-level (PRM-style) checking over final-answer voting [9][12].
- **Deploy:** environment ground truth only — health checks and smoke probes post-deploy; AlphaEvolve principle: don't claim objectives you can't automatically verify [17].

### (b) Our build process (director verifying workers)

- **Never trust the report.** The director reads the changed files/diff itself and re-runs the checks in its own fresh session — it is a fresh-context reviewer by construction [3][4].
- **Require evidence, not claims.** Worker completion = command + output the director can re-execute. Missing evidence = not done, regardless of prose.
- **Adversarial re-derivation.** Director independently derives expected behavior from the spec and compares against worker output — not against the worker's description of its output.
- **Near-miss calibration for judgment calls.** For every gate where the director uses model judgment (spec adherence, "done-ness"), build allowed/blocked example pairs from the spec first and test the judge on them [15]; an uncalibrated judge is not a gate.
- **Checklist-gated acceptance.** Acceptance is a per-item binary checklist derived from the spec, not a free-form verdict [14].
- **Sampling for contested calls.** If two workers disagree or output is contested, that is a judgment with a canonical answer → sample/vote with distinct models (uncorrelated errors), else escalate to a human [11][12].

## 4. References

1. Anthropic — Building Effective Agents — https://www.anthropic.com/engineering/building-effective-agents
2. Anthropic — Effective Harnesses for Long-Running Agents — https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents
3. Anthropic — Claude Code Best Practices (tests-first, adversarial review subagent) — https://www.anthropic.com/engineering/claude-code-best-practices
4. Cross-Context Review (2026) — https://arxiv.org/abs/2603.12123
5. Tsui — Self-Correction Bench (2025) — https://arxiv.org/abs/2507.02778
6. [OI] — Finding GPT-4's Mistakes with GPT-4 (CriticGPT) — https://openai.com/index/finding-gpt4s-mistakes-with-gpt-4/
7. Zhang et al. (DeepMind) — Generative Verifiers (GenRM) — https://arxiv.org/abs/2408.15240
8. Wei — Asymmetry of Verification and Verifier's Rule — https://www.jasonwei.net/blog/asymmetry-of-verification-and-verifiers-law
9. Lightman et al. ([OI]) — Let's Verify Step by Step — https://arxiv.org/abs/2305.20050
10. Dhuliawala et al. — Chain-of-Verification — https://arxiv.org/abs/2309.11495
11. Wang et al. — Self-Consistency — https://arxiv.org/abs/2203.11171
12. Estornell & Liu — Multi-LLM Debate (NeurIPS 2024, correlated-error failure) — https://proceedings.neurips.cc/paper_files/paper/2024/hash/32e07a110c6c6acf1afbf2bf82b614ad-Abstract-Conference.html
13. Shinn et al. — Reflexion — https://arxiv.org/abs/2303.11366
14. Lee et al. — CheckEval (EMNLP 2025) — https://arxiv.org/abs/2403.18771
15. Anthropic — Constitutional Classifiers — https://arxiv.org/abs/2501.18837
16. [CC] Hooks reference — https://docs.anthropic.com/en/docs/claude-code/hooksclaude.com/docs/en/hooks
17. DeepMind — AlphaEvolve — https://deepmind.google/blog/alphaevolve-a-gemini-powered-coding-agent-for-designing-advanced-algorithms/
18. Huang et al. — LLMs Cannot Self-Correct Reasoning Yet (ICLR 2024) — https://arxiv.org/abs/2310.01798
19. Madaan et al. — Self-Refine (works for open-ended generation w/ turnable signals; not reasoning, per [18]) — https://arxiv.org/abs/2303.17651
20. Kamoi et al. — When Can LLMs Actually Correct Their Own Mistakes? (survey) — https://arxiv.org/abs/2406.01297
