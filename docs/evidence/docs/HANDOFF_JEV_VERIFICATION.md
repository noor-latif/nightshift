# Handoff: Jev measurement, verification pass, and naming call

**For:** the research session that produced `FACTORY_PLATFORM_VERDICT.md`.
**From:** later session, 2026-09-20. **No network fetches in this pass.**

---

## 1. What I did

You asked why Jev exists, what it solves, and what alternatives exist. I answered that, then
went further and **measured** it rather than reading about it, because every public Jev
evaluation I could find is vendor-authored or self-annotated.

Four pieces of work:

1. **Deep read** of cloudroom-core (10k LOC, 53 files) and the Jev ecosystem (~248 projects).
2. **Built an objective benchmark** for Jev: 120 AST mutants of a real 600-LOC module, labelled
   by *actually running pytest* — no model in the labelling loop.
3. **Verification pass** on `FACTORY_PLATFORM_VERDICT.md`'s own claims against the local clones.
4. **Naming analysis** with live registry collision checks.

---

## 2. Where the insights live

### `/tmp/FACTORY_PLATFORM_VERDICT.md` — 83 → 269 lines

Addendum starts at **line 81**. Section anchors:

| § | Line | Contents |
|---|---|---|
| A | 85 | Verification pass — every claim in your report re-checked against the clones |
| B | 111 | The Jev measurement — method, numbers, controls, limits |
| C | 176 | Market gap analysis — four needed capabilities vs what Jev supplies; prior art; the missing primitive |
| D | 223 | Naming — collision table with evidence |
| E | 244 | How I found it — 11-rung method, repeatable |
| — | 262 | Next actions (revised) |

Also edited in place:
- **Gap ledger (line 68–77)** — two rows annotated with verification status; **one new row added: "Calibration record + refusal path — owner: nobody"**.

### `/tmp/DEEP_RESEARCH_PRD_FACTORY.md` — 131 → 135 lines

- **Line 25** (§2.1) — the Jev bullet went from *assumption* ("modelRoles is free, skip it") to *measurement* with numbers.
- **Line 100** (§5) — Jev precisely scoped: triage-shaped calls only, never the merge gate.
- **Line 111** (§6) — new risk: **probabilistic-gate risk**, citing the 60/60 saturation.
- **Line 134** — new reference **[21]**, the full measurement record.

---

## 3. Verification pass — what your report got right, and what I couldn't close

### Confirmed

| Claim | Evidence |
|---|---|
| README pin contradicts pack.json | `README.md:49` = `a02b9ab6…`; `template/factory/pack.json` `integration_revision_required` = `24796870605b0fd576734b79a8d5c781f2b1c1e1`. Exactly one occurrence of each, repo-wide. |
| Snapshot excludes `.factory`/holdout | `test_runtime_resource.py:123-134` — writes `.factory/holdout/HOLDOUT.md`, commits it, asserts prepared resource has no `.factory`. |
| Include paths refused on escape/link | `test_runtime_resource.py:149-157` — loops `../outside.py`, `.factory`, `missing.py`, `linked.py`; all non-zero exit, prior resource bytes unchanged. |
| Wrong-target-identity refusal | `template/factory/runtime_host.py:285-286` — `raise ValueError("wrong target identity")`. |
| `none_failed_min_one_success` | `Archon/packages/workflows/src/schemas/dag-node.ts:52`; asserted at `schemas.test.ts:399`. |
| Evaluator must fail before it's trusted | `RUNTIME_HOST.md:194-250` — and **richer than you quoted**: requires `expectations_passed: true` **and** `baseline_verified: true`; a deliberately-different `candidate` must return `inconclusive`; **"An unavailable case never counts as a caught mutation"**; recalibrate after any material evaluator/assertion/identity-contract change, "not after prose-only edits". |

### Could NOT be closed — three items

1. **`check-evidence.py` — not found.** No `*evidence*.py` anywhere in either clone. The assertion-id/coverage/identity contract you describe is real in spirit but the artifact isn't in the local tree.
2. **"4-state verdict vocabulary `verified|failed|inconclusive|malformed`" — unconfirmed as an enum.** `inconclusive` appears only in **prose** (`RUNTIME_HOST.md`; `investigate/commands/investigate.md:72`). `malformed` appears as a **node id** in `Archon/.../dry-run.test.ts:1082`, not a verdict.
3. **`archon-verify-runtime` / `archon-verify-runtime-suite` implementations — not in the local clone.** Named in `pack.json` entries and `RUNTIME_HOST.md`, but the code lives in the pinned revision.

### The correction that matters

**`Archon/` HEAD is `e237584d` (2026-09-15) — NOT the pinned `24796870…`.** The clone is
**shallow** and `git cat-file` on the pin fails. So **every Archon-side citation in your report
comes from the wrong revision for factory purposes** — which is exactly why items 1–3 above
could not be closed. The pin is named in `pack.json`; **its availability was not verified in
this pass** (a fetch was started, then abandoned on instruction).

**Action for you:** fetch the pin before trusting any Archon-side citation, then re-close items 1–3.

### One artifact your steal list omits — arguably the best in the repo

`.factory/locks/floor.json` is a ratchet that documents its own failure mode:

> SLACK. The gap between observed and floor is exactly the number of assertions that can be
> deleted with the gate still green, and it GROWS as the harness improves. Measured on a real
> factory, the hole went from 7 to 33 in one cycle BECAUSE the harness got better. It used to
> PIN THE AUTONOMY DIAL, which was the right instinct and the wrong remedy: it made a change
> that ADDS tests the case needing a human.

It also explains why the floors count **journeys/scenarios** rather than assertions: an agent
decides how many assertions a journey needs, and the count moved **12 → 13 on unchanged code**.
"The journey count is stable because it is the number of headings in a protected file."

---

## 4. The Jev measurement

### Method (regenerable in ~40 lines)

1. Target: real 600-LOC module (`jevkit/route.py`) from a real repo with a 768-test pytest suite, zero deps.
2. Mutations: classic mutation-testing operators over the **AST** — comparison flips, constant bumps, `not` removal, `and`↔`or`, slice off-by-one, `return` flip. 120 candidates.
3. **Ground truth = run pytest.** Fails → bug. Passes → not a bug. Free, exact, no model involved.
4. Ask Jev `jev-review`'s **verbatim** correctness question on the focused diff.
5. Controls: unmutated file (negative), shuffled scores (permutation).

Corpus: **81 bugs / 39 clean**.

### Numbers

| Judge | AUC vs test outcome | Accuracy |
|---|---:|---:|
| Jev `noul` correctness | **0.867** | — |
| Jev `choice` (`introduces_bug`/`clean`/`unclear`) | 0.858 | **0.858** |
| Permutation control | 0.477 | — |
| **Negative control** (unmutated file) | — | **p = 0.02** |

**Confidence is monotone — it carries signal:**

| band | n | accuracy |
|---|---:|---:|
| [0.0, 0.5) | 35 | **0.743** |
| [0.5, 0.8) | 25 | **0.880** |
| [0.8, 1.0) | 60 | **0.917** |

This **contradicts** the "calibration is refuted" reading *for this task family* — it holds here.
Ceiling: **8.3% of high-confidence verdicts are wrong.**

**The abstention option never fires.** Offered `unclear` on 120 cases → chosen **0 times**.
Every "route low confidence to a human" design is on the caller to implement.

**Dominated as an oracle:**

```
run the focused suite (44 tests) : 0.70s, $0,        100% accurate, exact
ask Jev                          : 0.70s, $0.000024,  86% accurate, text-only
```

Same latency, free, exact. Cost for all 120: 69,049 input tokens = **$0.0029**. Median call **0.70s**, p90 0.76s.

### Same corpus falsifies foreman's premise

| foreman question | bugs | clean | AUC |
|---|---:|---:|---:|
| `needs_verification` | 0.882 | 0.839 | 0.735 |
| `tests_sufficient` | 0.314 | 0.391 | — |
| `implementation_complete` | 0.501 | 0.553 | **wrong direction** |

`needs_verification >= 0.65` flagged **60/60**. Precision 0.7167. Base rate 0.7167.
**Constant predictor — zero information.** Indistinguishable from "verify everything".

> **Generalisable line:** a System One model is good at *"is this diff inverted?"* and useless at
> *"is this job done?"* The second is not a perception problem, it's a global state problem, and
> 32k tokens of `state` cannot hold the answer.

### Limits — state these alongside the numbers

- One file, one task family (defect detection), one model version (`jev-1.13.0`).
- Labels are "does the suite catch it" — **not** "is it a bug".
- **Survivors are untested, not correct.** The `boolop` cluster (mean p 0.818 on suite-*passing* mutants) is exactly that divergence: Jev correctly sees a semantic change the tests don't observe. **That's a finding about the tests, not about Jev.**
- **Raw per-mutant scores are NOT retained** — scratch dir `/tmp/jevlab` was deleted after the run. Numbers above are recorded in the docs; the corpus is regenerable from the recipe in §B/§E, not byte-reproducible.

---

## 5. Market gap — the part that converges with your ledger

Jev is real, working, cheap, fast. Three first-party integrations that *could* have treated it as
an LLM **refused to**: Vercel's AI SDK throws `NoSuchModelError` for `languageModel` and exposes
`evaluationModel`; Effect added `Decision.ts` beside `LanguageModel.ts`; Pydantic AI's docs open
with *"Jev is not a language model."*

### Four things a factory needs, against what Jev supplies

| Needed | Jev? | Evidence |
|---|---|---|
| **Verification oracle** | **No** | Dominated by running tests. Vendor's own jaggedness doc removes the two cheap oracle designs: `confidence` ≠ per-answer accuracy, and internal consistency is *explicitly not* an invariant — their example gives P(refund)=0.72 and P(¬refund)=0.47, summing to **1.19**. |
| **Decision as reviewable artifact** | **Partly — policy half only** | JevFlow's `Threshold` is serializable data and `MatchedRule{threshold, actual}` records *why* a rule fired. But `EvaluationRecord` **omits the input entirely, has no input digest**, hardcodes `attempts: 1` (SDK silently retries 3×), never populates `requestId`, and **discards `response.model` and `usage`** — handed over by the SDK, dropped at `index.ts:72-76`. Not replayable ⇒ a log line, not an artifact. |
| **Operator principal in the schema** | **No — nothing has it** | Contract is `{state, model, questions}` → `{model, answers, usage}`. **No field for who is asking.** ARMIN goes further wrong: hardcodes `agent_id: "jev-native"` (`jev.rs:443`), *overwriting* the real speaker the plugin already captured. |
| **Thread state machine, one writer** | **No** | Every integration is a hook on someone else's lifecycle. `pi-typesafe-compact` returns `undefined` on error — fails open. ARMIN's episodic layer is per-process memory with no replay, and its `UnverifiedChange` detector **can never be cleared in production**: a real `cargo test` through the plugin carries `files: []`, and `files_overlap([], …)` is always false. |

### Prior art worth citing

- **`huncho`** — JSONL journal, **replay of a threshold change over recorded answers with no inference**, `enter`/`exit` hysteresis, Brier reporting.
- **`jevcal`** — fits per-question thresholds on your labels, verifies on a held-out split, writes a lock file, **fails CI when a model update breaks the locked thresholds**. Name taken; mechanism is closest prior art.
- **`abide`** — the only project that **reports its own error rate**: 39 flagged edits → 10 confirmed (**26% precision**); 15 flagged turns → 11 confirmed (73%).
- **`jev-axi` postmortem** — $36.85, 56 sessions, to discover the agent **loaded the tool zero times in 22 free-choice runs**; when forced, effect flipped sign between sessions (−5% then +29%). Their conclusion: *"Exploration was never the bottleneck; comprehension was, and a model that only emits probabilities cannot do comprehension for you."*
- **`SemIf`** (2,357★) — open 4B model hits **0.845 modal agreement vs Jev's published 0.883**. The interface is a commodity. But SemIf labels its own output `"conditional option score; uncalibrated as decision confidence"` and lists calibrated probabilities under **not reproduced**.

### The convergence

**Your gap ledger independently named "Evaluator calibration (prove the gate goes red)".** The
ecosystem research arrives at the same place from the other direction: **nothing in ~248 projects
ships a calibration record as a runtime artifact.**

Four rules nobody implements as code:
1. don't threshold the `confidence` field — fit a threshold on your own labels;
2. don't reuse a Noul threshold on a Choice — miscalibration sign flips by primitive;
3. don't sort on a 2-decimal probability — quantisation makes ties engine-dependent;
4. don't pool the two signs of miscalibration.

And the primitive on top, which nobody ships: **refuse to decide when the calibration record is
absent, stale, or from a different model version.** `jevcal` locks thresholds and fails CI;
nothing makes the *gate* decline to run.

**Verdict:** Jev is **not** the verification oracle and must not be the auto-merge gate. It is
usable for triage-shaped decisions where no oracle can exist — is this issue ready, is this diff
in scope, which candidate matches the intent. Everything load-bearing stays on the factory's
existing rungs: holdout, runtime identity, mutations. The Jev-shaped work is the **cheap
pre-filter in front of** those rungs, and it needs its own calibration record to be worth trusting.

---

## 6. Naming

**Recommendation: `trueness`** — free on PyPI, npm, crates.io; no GitHub exact match.

Metrology term: closeness to the *true* value, as distinct from precision — exactly the
distinction the artifact encodes (`confidence` ≠ P(correct), calibration ≠ accuracy).
Vendor-neutral, because `SemIf` proves the interface is a commodity and the gap is the record.

**Runner-up: `jevfloor`** (also free everywhere). GitHub's `jev in:name` returns 50+ repos
including **five separate `awesome-jev` lists** (94–694★) indexing the prefix — a real
distribution channel, three weeks old. Cost: couples the primitive to a vendor.

**Do not use `jevcal`** — free on all registries, but already prior art (see §5).

Taken: `tare`, `noisefloor`, `failclosed`, `interlock`, `holdout`, `firstpass`, `greenwash`, `abstain`, `redgate`, `verdict`, `quorum`, `witness`, `attest`, `provenance`, `canary`.

---

## 7. Open items for you

1. **Fetch the pinned Archon revision** (`24796870605b0fd576734b79a8d5c781f2b1c1e1`) and re-close §3 items 1–3.
2. **Add `.factory/locks/floor.json` to the steal list** — the SLACK/ratchet insight is the best design idea in that repo and it's currently missing from your report.
3. **Don't put Jev on the merge gate.** Cheap pre-filter in front of the holdout/runtime/mutation rungs at most.
4. **If building the calibration primitive**, start with the **refusal path**, not the fitting — a gate that declines to run without a fresh, version-pinned record is the part nothing else ships, and the part that would have caught foreman's saturated threshold.
5. **Repo state:** `/tmp/hermes` byte-identical to HEAD (all mutation work ran in a throwaway copy, since deleted). `/tmp/ai-software-factory`, `/tmp/Archon`, `/tmp/omnara`, `/tmp/ami` all present.
