# PRD Critique & Grounded Plan: Vision-Aware AI Software Factory on $10–20

Deep research, 2026-09-20. Evidence: 5 parallel scouts (primary sources), live Surplus Intelligence market data, live Artificial Analysis data via aa-llm-compare, prior cloudroom-core deep-dive.

---

## 1. Executive Summary

**Verdict: the PRD proposes building a factory you already own, around models you can't buy, constrained by rate limits that don't apply to you.**

1. **The harness is YAGNI.** OMP already ships every primitive the PRD designs: parallel workspace-isolated subagents with typed returns, 9-role model routing, a real browser driver + host desktop control with screenshots and AX-tree walking, skills, memory, session resume [8]. The PRD's "custom agent harness with throttling and semantic caching" is building a worse copy of the tool this research ran inside.
2. **The orchestrator pick is unusable.** Nex-N2.5-Pro is real (Nex-AGI, 397B/17B Qwen3.5-MoE, Apache-2.0) but on OpenRouter it has **no paid endpoint — free tier only** [10], and it is not on the surplus marketplace at all. The PRD's "optimal choice" cannot be purchased for this stack.
3. **The budget framing is off by ~3 orders of magnitude.** The PRD's entire resource-optimization chapter (50→1000 req/day, 20 RPM, leaky buckets) is OpenRouter-free-tier math. On surplus: **1,200 completion calls/min, no marketplace-side spend caps, prompt caching natively supported** [4][5][6].
4. **$10–20 is not the constraint — ever.** At surplus best-offer prices, a heavy 3.5M-token agentic session on glm-5.3 (the #1 Artificial Analysis model, II 44.78) costs **$0.064**. $15 ≈ **400 heavy glm-5.3 sessions**, or ~3,600 glm-5.3-flash sessions, or ~19,700 deepseek-v4.1-flash sessions [1]. The binding constraints are wall-clock (133–180 tok/s median) and uptime (84.7% on glm-5.3), not dollars.
5. **Vision verification is commoditized and noisy.** The deterministic layer (AX-tree/snapshot) should be primary; a VLM pass is a cheap secondary that must be run with multi-vote consistency, because controlled testing shows AI-only UI audits produce **64% false alarms and 27% hallucinations, only 9% genuine finds** [17].

---

## 2. PRD Critique, Point by Point

**2.1 Orchestrator selection (§ "Selecting the Core Orchestrator")**
- PRD: Nex-N2.5-Pro is "the optimal choice." Reality: exists, open-weights on HuggingFace, but OpenRouter's endpoint list for the paid variant **is empty** — only a `:free` endpoint with 99.92% uptime serves it [10]. Not present in surplus's 395-model market [1]. For a paid pipeline, this pick is a dead end.
- PRD's fallback reasoning ("GLM-5.2 lacks multimodality") is also stale: GLM-5.2 is **deprecated**; GLM-5.3 (AA Index 45, #1 of 113, 1M context, $1.40/$4.40 list) supersedes it [12], and on surplus it trades at **$14/$44 per M with 54 sellers** [1] — a 100x discount to list. AA live data confirms GLM-5.3 measured (not estimated) II 44.78 with the best confabulation rate in its class (19.6 per 100 questions) [2].
- Inkling (Thinking Machines, 975B/41B, 1M ctx, Apache-2.0) is real and on OpenRouter (~$0.95/$4.05) [9]; surplus lists it with 23 sellers at $12.50/$50.63 per M [1]. That's 8x glm-5.3-flash blended cost with no top AA standing. Self-hosting 975B params on a 4GB-Iris-Xe laptop is fantasy. Skip.
- Jev (TypeSafe "System One" classifier, $0.042/M in, 32k ctx) exists [11] — but OMP's `modelRoles` already does the routing decision deterministically, for free. A Jev router adds a paid dependency to replace a YAML key. **Now measured, not assumed** [21]: on 120 AST mutants of a real 600-LOC module with **pytest as the objective label**, Jev's correctness judgment reaches AUC 0.867 / accuracy 0.858, and its `confidence` is monotone (0.743 → 0.880 → 0.917 across bands) — so it is a genuinely competent judge, not noise. Three findings decide its role: (a) it is **dominated as an oracle** — the focused 44-test suite is the same 0.70s latency, $0, and exactly right; (b) its **abstention option never fires** (offered `unclear` on 120 cases, chosen **zero** times), so every "route low confidence to a human" design is on you to implement; (c) **8.3% of its high-confidence verdicts are wrong**, and the ecosystem's independent calibration work found the miscalibration *sign flips by primitive*. Use it for triage-shaped calls where no oracle can exist; never as a verification gate.

**2.2 Resource optimization (§ "Optimizing Resource Utilization")**
- OpenRouter numbers in the PRD are arithmetically right but mis-framed: 20 RPM / 50 RPD / 1000 RPD apply to `:free` model variants only; paid variants have no platform request cap, and the 1000-RPD unlock keys off all-time credits ≥ 9 USD [3]. Irrelevant anyway — the plan runs on surplus.
- Surplus, verified from their docs: **1,200 completion calls/min** buyer limit, 600 buyer control-plane calls/min, source-IP WAF ceiling [4]. No marketplace-side hourly USD cap; only per-offer `cap_daily_usd` [7]. Routing skips exhausted/capped offers and fails over to the next seller transparently; 503 `no_healthy_sellers` only when nothing healthy remains [5].
- Prompt caching: the marketplace injects `prompt_cache_key` and Anthropic `cache_control` breakpoints on the OpenAI-compatible path and bills `best_cache_read_per_1m` — deepseek-v4.1-flash cache-read is **$6 per *billion* tokens** ($0.000006/M) [6][1]. The PRD's "semantic cache" layer is already priced into the wire protocol.

**2.3 Vision self-verification (§ "Implementing Vision-Based Self-Verification")**
- The PRD's tiered VLM plan (cheap pass → Qwen3-VL deep pass) is directionally fine but misses the failure mode: AI UI audits are dominated by false alarms (64%) and hallucinations (27%); only 9% of flagged problems are real [17]. A single-pass VLM verifier in a self-correction loop would send the factory into hallucination-driven repair spirals.
- The deterministic alternative already exists in the toolchain: agent-browser ships `screenshot --if-changed --annotate --threshold` and an accessibility-tree `snapshot` with element refs, explicitly "best for AI" [18]. OMP's browser tab exposes the same surface (observe/ariaSnapshot/evaluate) [8]. AX-tree assertions catch "button exists and is enabled" without a VLM at all.
- Pricing if a VLM pass is wanted: surplus's deepseek-v4.1-flash and glm-5.3-flash both accept image input per the live catalog [1]; qwen3-vl-235b-a22b-instruct is on surplus at $2.1/$19 per M [1]; off-marketplace, Qwen3-VL-32B is $0.104/$0.416 on OpenRouter [20] and scores mid-pack on MMMU-Pro (0.693 vs Gemini 3.5 Flash 0.836) [19] — mid-pack is fine for "is the modal visible."
- PRD's "DeepSeek V4 Flash Vision" as a tier: works (catalog row accepts images [1]) but note deepseek-v4.1-flash's **96.5%-of-wrong-answers-are-confabulations** profile [2] — the worst possible verifier temperament. Use it for extraction, not judgment.

**2.4 Self-correction & reviewer loops (§ "Engineering Resilience")**
- The generator/critic pattern the PRD describes as future work is already running: OMP ships code-reviewer, silent-failure-hunter, falsifier, and pr-test-analyzer subagents; the deep-research skill's Phase 3 gate (this checkpoint) is the same discipline. Nothing to build.

**2.5 Citation quality of the PRD itself**
- Load-bearing claims rest on content-farm blogs (mindstudio.ai, developersdigest.tech) and Reddit threads, and the piece reads as an unedited deep-research dump. Cross-checking against measured data flips several conclusions: e.g. it implicitly favors DeepSeek for cheap tiers, while AA's conditional hallucination data shows DeepSeek V4.1 Flash at 51.7 confabulations per 100 questions vs GLM's 19.6–20.0 [2] — the opposite ranking for unattended operation.

---

## 3. Budget Reality (live surplus `/api/markets`, 2026-09-20) [1]

Per-session cost at two workload shapes (USD):
- **Heavy session**: 3M fresh input + 0.5M output (big multi-file PR).
- **Agent loop**: 2.4M cache-read + 0.6M fresh input + 0.5M output (harness with ~80% cache hit).

| Model | $/M in | $/M out | $/M cache-r | Heavy/session | Loop/session | Sessions per $15 | II (AA) [2] | Confab/100 [2] | Sellers | Uptime |
|---|---|---|---|---|---|---|---|---|---|---|
| deepseek-v4.1-flash | 0.000287 | 0.001147 | 0.000006 | $0.0014 | $0.0008 | 19,734 | 39.46 | **51.7** | 31 | 96.8% |
| kimi-k2.7-code | 0.001024 | 0.004843 | 0.000208 | $0.0055 | $0.0035 | 4,243 | 25.81 | 32.5 | 55 | 99.3% |
| qwen3.8-flash | 0.001401 | 0.004114 | 0.000140 | $0.0062 | $0.0032 | 4,638 | — | — | 8 | 97.2% |
| **glm-5.3-flash** | 0.0015 | 0.005 | 0.0003 | **$0.0070** | **$0.0041** | 3,640 | 41.81 | 20.0 | 45 | 79.5% |
| **glm-5.3** | 0.014 | 0.044 | 0.0026 | **$0.0640** | $0.0366 | **409** | **44.78 (#1)** | **19.6** | 54 | 84.7% |
| gpt-5.6-luna | 0.01496 | 0.08976 | 0.001496 | $0.0897 | $0.0574 | 261 | 37.32 | 53.1 | 29 | 96.7% |
| inkling | 0.0125 | 0.050625 | 0.002125 | $0.0628 | $0.0379 | 395 | — | — | 23 | 99.5% |
| gemini-3.8-flash | 0.029331 | 0.146655 | 0.002933 | $0.1607 | $0.098 | 153 | 40.93 | 25.1 | 29 | 72% |
| gpt-6-astra | 0.36614 | 1.8307 | 0.036614 | $3.95 | ~$2.5 | 6 | — | — | 19 | 76.1% |

Vision add-on: 1,000 verification screenshots × ~1.5k tokens ≈ $0.002 on glm-5.3-flash, ~$0.003+ on qwen3-vl-235b-instruct [1]. Trivial.

Multi-agent overhead ground truth: Claude Code Agent Teams consumes **~7x** single-session tokens; dynamic workflows fan to dozens–hundreds of subagents [13]. Even at 7x, a glm-5.3 fan-out session is $0.45 — $15 buys ~33 of those.

**Conclusion: budget the wall clock, not the wallet.** glm-5.3's 84.7% uptime (~1 in 7 calls fails) is the real number to engineer around; OMP's `retry.fallbackChains` (glm-5.3 → glm-5.3-flash) already covers it.

---

## 4. What to Adopt / Skip

| Component | Verdict | Evidence |
|---|---|---|
| OMP as the factory | **Adopt (already have)** | task fan-out, modelRoles, browser+computer, skills, hub supervision [8] |
| coleam00/ai-software-factory | **Optional** — the one off-the-shelf PRD→merged-PR path: `archon-backlog --input prd=<path>`, independent holdout verification, merge queue; active (commits 2026-09-14/16), 307★, engine Archon 23.5k★. Its installer drives provider CLIs, so inference flows through your configured accounts. | [7] |
| Vision tier | **Build nothing**: browser AX-snapshot assertions primary; glm-5.3-flash image pass secondary, ≥2-of-3 votes before flagging | [17][18][1] |
| getbb.app (bb) | **Skip on Linux** — real, MIT, free, headless-drivable (HTTP API, `BBSdk.threads.spawn/wait/output`), and can drive omp as a provider; but pre-1.0 and macOS-first, Linux AppImage is alpha. You'd add a GUI orchestrator around the orchestrator you already run. | [16] |
| cloudroom-core | **Skip** — 3 days old at research time, 5 commits, pre-release, self-admitted "planned, not yet implemented" components; weak isolation (no seccomp/cgroup limits beyond freeze/kill, codex launched `danger-full-access` + `approvalPolicy: never`). **Steal the idea** (fsynced receipt per request_id, `unknown` vs `unknown_after_restart`), don't run the code. | [15] |
| Omnara | **Skip for now** — mature (2.9k★, 490 commits, Apache-2.0, durable Postgres state), but solves machine-death survival and phone steering; OMP `--resume` + tmux covers a single-operator $20 operation. Revisit if the factory outlives its host. | [14] |

---

## 5. The Plan on $10–20

1. **No new harness.** OMP session = factory controller. `task` fans out to workspace-isolated subagents; `modelRoles` routes; `hub` supervises; PRD enters as a plan file, milestones as todos.
2. **Model duo on surplus** (one-line config change each):
   - `default: surplus/glm-5.3:high` — planner/coder. #1 AA, 1M ctx, best confabulation rate, $0.064/heavy-session.
   - `task: surplus/glm-5.3-flash:high` — subagent fan-out. II 41.81 at 1/9th the cost, 20.0 confab/100 (vs deepseek's 51.7 — the current `task` role runs a model 2.5x more likely to confabulate when wrong).
   - `smol: surplus/glm-5.3-flash:low` — cheap mechanical calls.
   - Add `retry.fallbackChains` glm-5.3 → glm-5.3-flash to absorb the 15% uptime gap.
   - deepseek-v4.1-flash stays for pure extraction/bulk reads where wrongness is cheap to catch (its 96.5%-confabulation-on-wrong profile is disqualifying for judgment roles).
3. **Verification loop per feature:** build → run → browser `observe()`/AX assertions on the changed surface (deterministic gate) → one glm-5.3-flash image pass on a diffed screenshot → defect only if 2 of 3 runs agree. Then OMP's code-reviewer/silent-failure-hunter subagents on the diff. No custom VLM tier.
4. **If you want the full PRD→merged-PR gate off the shelf:** clone coleam00/ai-software-factory into the app repo, run `python factory/consumer.py run archon-backlog --input prd=<path>` [7]. Note its README's own caveat: the installer pins an exact Archon revision and "doctor does not prove a live agent can sign in or complete a run" — smoke it on a toy PRD first.
5. **Runway accounting:** treat $15 as ~400 glm-3-heavy sessions. Burn discipline is pointless; instead cap **turns** (wall-clock at 133 tok/s median) and **repair-loop depth** (2 retries then human) so a hallucination spiral can't eat the evening.

Skipped: semantic cache layer (surplus bills cache-read at $6/B tokens [1][6]), Jev router (modelRoles is free [8]), custom harness (OMP [8]), cloudroom/bb/Omnara (maturity/OS-fit [15][16][14]).

**Jev, precisely scoped** [21]: measured at AUC 0.867 on 120 objectively-labelled mutants, but **dominated as a verification oracle** by running the tests (same 0.70s latency, $0, exact) and with an abstention option that never fires. Adopt it only for triage-shaped calls where no executable oracle can exist — issue readiness, diff-in-scope, candidate-vs-intent. Never on the merge gate. Full method and limits: `/tmp/FACTORY_PLATFORM_VERDICT.md` Addendum §B–§C.

---

## 6. Trade-offs & Risks

- **Surplus discount durability** [INFERENCE]: best-offer prices are marketplace spot prices with 99%+ discounts; they can move. Mitigation: pi-surplus fetches live quotes on every model refresh, so config reflects reality; re-run the budget table when planning beyond weeks.
- **glm-5.3-flash uptime 79.5%** is the weakest link in the recommended duo — more sellers (45) but flaky. The fallback chain is mandatory, not optional.
- **Contradiction recorded (Phase 3 gate):** ModelVerifier reports the surplus `inkling` catalog row as auto-proposed "awaiting review" from OpenRouter; the live `/api/markets` shows 23 sellers and 99.5% uptime for the same slug. Both facts come from the same API family; treat inkling as buyable but not the cheap pick either way.
- **AA index caveats** [2]: 76% of AA indices are estimated; the five compared here are measured (`firstParty`), but gemini-3.8-flash was benched at `high` effort vs the GLMs' `max` — not apples-to-apples.
- **Unattended-merge risk:** ai-software-factory's holdout gates make auto-merge defensible; OMP-alone flows need you to keep the code-reviewer subagent in the loop before merging.
- **Probabilistic-gate risk** [21]: any gate thresholded on a model's own probability needs a *measured* false-positive rate and a version-pinned calibration record, or it silently degrades into a constant predictor. Measured failure case: a shipped `needs_verification >= 0.65` gate fired on **60/60** cases — precision 0.7167 against a base rate of 0.7167, i.e. zero information, indistinguishable from "verify everything". Calibrate against an executable oracle before trusting any such threshold; recalibrate after any model or prompt change.

## References

- [1] Surplus Intelligence live market data — https://api.surplusintelligence.ai/api/markets (fetched 2026-09-20; 395 models, best-offer microdollar prices)
- [2] aa-llm-compare live run against Artificial Analysis — https://github.com/noor-latif/aa-llm-compare (653-model RSC payload, `compare glm-5-3 glm-5-3-flash deepseek-v4-1-flash kimi-k2-7-code gemini-3-8-flash`)
- [3] OpenRouter rate limits — https://openrouter.ai/docs/api-reference/limits
- [4] Surplus FAQ (buyer limits: 1,200 completion calls/min) — https://www.surplusintelligence.ai/faq
- [5] Surplus health & routing (cap-skip, failover, 503 no_healthy_sellers) — https://www.surplusintelligence.ai/docs/marketplace/health-routing
- [6] Surplus parameter compatibility (prompt-cache injection, prompt_cache_key, cache_control) — https://www.surplusintelligence.ai/docs/reference/parameter-compatibility
- [7] coleam00/ai-software-factory — https://github.com/coleam00/ai-software-factory (engine: https://github.com/coleam00/Archon)
- [8] Oh My Pi README (subagents, modelRoles, browser, computer-use, resume/collab) — https://github.com/can1357/oh-my-pi
- [9] Inkling model card — https://thinkingmachines.ai/model-card/inkling (OpenRouter: https://openrouter.ai/thinkingmachines/inkling)
- [10] Nex-N2.5-Pro — https://huggingface.co/nex-agi/Nex-N2.5-Pro ; https://openrouter.ai/nex-agi/nex-n2.5-pro (endpoints: free only)
- [11] Jev 1.13 — https://openrouter.ai/typesafe/jev-1.13 ; https://typesafe.ai/blog/introducing-system-one-models-and-jev
- [12] GLM-5.2/5.3 — https://artificialanalysis.ai/models/glm-5-2 ; https://artificialanalysis.ai/models/glm-5-3 ; https://z.ai/blog/glm-5.2
- [13] Token consumption ground truth — https://www.faros.ai/blog/claude-code-token-limits (Agent Teams ~7x, 200K ctx)
- [14] Omnara — https://github.com/omnara-ai/omnara
- [15] cloudroom-core — https://github.com/davidondrej/cloudroom-core (prior deep-dive: receipt/journal model in src/session/mod.rs, outbox.rs, docs/session-lifecycle.md)
- [16] bb — https://getbb.app/ ; https://github.com/get-bb/bb (npm bb-app 0.43.3, 2026-09-18)
- [17] AI UI-audit false-alarm study — https://measuringu.com/does-ai-find-real-ui-problems-or-just-hallucinations
- [18] agent-browser — https://github.com/vercel-labs/agent-browser
- [19] MMMU-Pro leaderboard — https://llm-stats.com/benchmarks/mmmu-pro
- [20] Qwen3-VL-32B-Instruct pricing — https://openrouter.ai/qwen/qwen3-vl-32b-instruct
- [21] Jev measurement, 2026-09-20 (this session): 120 AST mutants of `jevkit/route.py` (600 LOC), objective labels from its 768-test pytest suite; 81 bugs / 39 clean; Jev `jev-1.13.0` via `POST https://api.typesafe.ai/v1/systemone` using `jev-review`'s verbatim correctness question. AUC 0.867 (`noul`) / 0.858 (`choice`); confidence bands 0.743 / 0.880 / 0.917; abstention offered and never taken (0/120); negative control p = 0.02 on the unmutated file; permutation control 0.477. Cost 69,049 input tokens = $0.0029; median latency 0.70s. Full writeup, ecosystem survey, and gap analysis: `/tmp/FACTORY_PLATFORM_VERDICT.md` Addendum §B–§E.
