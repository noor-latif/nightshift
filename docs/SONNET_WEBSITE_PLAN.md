# Sonnet website workflow: evidence and next-run plan

2026-10-03 · **Planning/documentation only.** No new runtime behavior, tests,
configuration, model-role defaults, paid calls, browser runs or deployment.
Canonical source is `~/repos/factory-spike`, not the divergent `~/nightshift`.
Run the README's local entrypoint only after the task's launch approval;
this plan is not approval to launch or publish.

## What is already fixed

These are integrated capabilities, not work to reimplement:

| Implemented behavior | Source |
|---|---|
| Trusted external local task input with shape validation | `src/lap.py:issue_data`, `src/settings.py:TASK_FILE` |
| Exact new-file allowlist, realpath/escape/existing-file rejection and exclusive creation | `src/lap.py:_create_path_error`, `apply_mutations`; `FACTORY_NEW_FILES` |
| Native argv gates, designated positive authoritative TAP suite, full artifacts, HOLD precedence | `src/verify.py:verify_candidate`; prerequisite doc |
| Enhancement baseline before model work and tracked-source drift refusal | `src/lap.py:run` |
| Creative direction passed to the text reviewer | `src/lap.py:design_brief_from`, reviewer call in `run` |
| Local review snapshot/ref retained without push/PR/merge/deploy | `src/lap.py:run`, `merge_mode:review` |
| Blank-model guard, sanitized request/response/error traces, explicit Responses transport and cap-field knobs | `src/agent.py:chat` |
| Missing-finish rejection and bounded retry; `length` retries once at doubled cap, then rejects | `src/agent.py:parse_stream`, `chat` |
| Supervisor fixture child strips real notification topic | `tests/test_supervisor.py` |

Existing canonical receipts: **201 tests exit0** and a **fresh synthetic
localhost lap** ending `awaiting-review`, bound to the integrated source.
Neither was rerun for this docs change. Synthetic success is not a real
model/service or visual-quality result. Source aggregate
`sha256sum src/*.py | sha256sum` is
`542d3d10b09e1fc0ba026436a4732e4ad84d06dc6b5e2c679b2da41fdb493577`.
Local receipts: `~/repos/factory-docs/kormotorn-trial/evidence/fresh-run-integration/`.

## What the Sonnet diagnosis establishes

[Official Sonnet5.5 overview](https://platform.claude.com/docs/en/models/sonnet-5-5/overview)
identifies native `claude-sonnet-5-5`, released September28,2026, with128K
synchronous output. The Surplus call requests/echoes `claude-sonnet-5.5`:
that is gateway metadata, not independently attested weights. Curated trusted
OpenRouter means host-operator curation, not direct Anthropic service or
individual-seller verification.

Actual retained full-prompt diagnostic: trusted HIGH/16,384 returned `length`
and incomplete JSON, consuming12,863 reasoning tokens inside16,384 output.
The conditional trusted LOW/32,768 returned `stop`,9,022 output tokens
including701 reasoning, and exactly three complete create mutations.
Request records identify marketplace/OpenRouter/no fallback. This proves
one complete transport/mutation envelope, not design, translation or
functional acceptance. The raw Sonnet preview is distinct from the retained
Luna/operator final homepage. No code was applied by the diagnosis.

Caps include hidden thinking; unused allowance is not automatically billed.
Omitting a cap is not proven unlimited (a retained call stopped at9,216,
all reasoning). Historic16,384 requested/17,408 reported usage and gateway
adaptation mean the request cap is not a verified invoice ceiling.
`x-si-truncated=0` does not override `length` or incomplete output.
[Surplus reasoning](https://www.surplusintelligence.ai/docs/reference/reasoning)
and [routing controls](https://www.surplusintelligence.ai/docs/marketplace/routing-controls)
define billing and host filters. The existing$0.01 default cost ceiling was
not changed; an observed$0.032243 successful call exceeds it, so an actual
future launch must explicitly reconcile its budget, not silently bypass it.

## Why a spectacular page needs a different creative contract

The previous brief already specified a calm two-column school-day board,
exact paper/blue palette, system sans, restrained motion and specific
anti-template patterns. More effort cannot override those instructions.
Adding “spectacular” while preserving every calm-layout token is not a new
art direction, and blaming LOW alone is not established by a visual test.

Next gate: owner supplies/selects **1–2 liked URLs or screenshots** and one
chosen direction. Domain research can suggest a driving journal, a school-day
board or Swedish information-design grammar; none is approved taste or a
Sonnet5.5 showcase. Avoid copying regulated signs or suggesting endorsement.
No model-specific spectacular-site success rate was established.

Write one approved **DESIGN contract** outside the candidate's writable view:
4–6 palette values/roles, system-type sizes/weights/line measures, spacing/grid,
shapes, one memorable subject-led hero, mobile transformation, motion and
static reduced-motion state, plus concrete reject examples. Use original
inline SVG/CSS composition if useful; do not add WebGL/dependencies/animation
libraries merely to make it flashy. Strong hierarchy can use system fonts.

Owner approval may supersede the old palette/layout/type restrictions;
record exactly which rules change. Until then they remain constraints.
Keep facts, bilingual behavior, accessibility and source containment fixed:
research/planning stage, **planned** school ownership, no launched platform,
signed schools, invented savings/prices/testimonials or functioning-booking
claim. Preserve payment-request and accounting boundaries in both languages.
The old brief's unqualified “owned by the schools” line must not be reused as
present-tense fact. Default scope remains three native HTML/CSS/JS files,
no dependencies, remote fonts or external assets. A licensed font/image/file
requires a separate scope decision, not a silent fourth file.

## Proposed stages (not automated in the current lap)

1. **HIGH art direction, no implementation.** Sonnet produces concise design
   alternatives and the selected concrete DESIGN artifact, with a separate
   generous reasoning-plus-output allowance and explicit wall/spend bounds.
   Do not ask for hidden chain of thought; ask for decisions and short rationale.
   Owner selects the reference/direction before code. HIGH planning is a
   proposal, not a tested healthy profile on this gateway.
2. **Complete scoped implementation.** Supply approved DESIGN, factual contract,
   all three files/allowed paths and acceptance criteria. Preserve the owner's
   HIGH ambition: if HIGH implementation is chosen, give actual supported
   seller/model headroom rather than repeat16,384. Native prompting guidance
   recommends128K for agentic coding; this is **not** a tested Surplus128K
   profile or authority to spend that amount. LOW/32,768 is only the observed
   complete-transport baseline; MEDIUM for well-specified work is official
   guidance but untested locally. Select effort and approved allowance explicitly,
   never silently downgrade. No successful HIGH full implementation is claimed.
3. **Independent screenshot critique.** One builder owns edits; a separate
   read-only critic sees actual desktop/mobile screenshots and interacts with
   the real page. Grade DESIGN fidelity, originality, craft and function;
   return concrete element/value fixes, not generic praise. Proposed initial
   budget: one build plus two targeted correction rounds; at most four rounds
   if separately approved, then stop for owner judgement. Keep the best
   accepted snapshot, not automatically the last. Retain every reject/cost.
4. **Acceptance and retention.** Run the actual native gate and browser checks
   on the exact candidate; Swedish/English desktop/mobile, narrow viewport,
   no overflow, keyboard/focus/skip link, mobile open/Escape/section-close,
   language round trips preserving child markup, correct payment/accounting
   translations, document lang/title and reduced motion. Recheck facts/real
   links and untouched protected sources. Owner decides taste. Retain source,
   screenshots, reviewer verdicts, exact hashes and per-call charge records.
   Text review/HTTP200/syntax-only output never certifies the surface.
   Local review mode remains no automatic push/merge/deploy or paid-green claim.

[Current Sonnet5.5 prompting](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-sonnet-5-5)
recommends MEDIUM for well-specified agentic work, HIGH for harder work and
headroom for thinking plus response; LOW can skip verification. Native
Messages uses `output_config.effort`, whereas observed Surplus chat uses
`reasoning_effort`. Do not transplant `thinking:between_tools`, native JSON
settings or model spelling into the gateway without compatibility proof.

The [frontend-design skill](https://raw.githubusercontent.com/anthropics/skills/main/skills/frontend-design/SKILL.md)
says “Spend your boldness in one place” and explicitly plans, reviews,
builds and critiques. Anthropic's [generator/evaluator harness](https://www.anthropic.com/engineering/harness-design-long-running-apps)
explains why builders overpraise their own designs and uses live-browser
critique. Its demonstrated runs are4.5/4.6-era, **not Sonnet5.5**; multi-hour,
5–15-round/$200 examples are not this plan's required budget or guaranteed
quality. Start with the smallest bounded loop and human taste gate.

## Deferred kernel changes: distinct from implemented fixes

None below is shipped by this documentation:

- **Route observability:** allowlisted `x-si-*` response/trace IDs captured at
  headers-open, before body reading; first-byte/chunk timing and partial body
  retained on interruption. Today `TRACE_HEADER_ALLOWLIST` omits `x-si-*` and
  `chat` reads the full body before collecting normal-response headers.
- **Usage honesty:** preserve complementary raw usage chunks without summing
  repeated counts, and join actual request-ledger buyer cost/status. Today
  `parse_stream` replaces usage with the last chunk, losing earlier detail.
- **Cheap-first Sonnet fallback:** proposed one full-request retry to a known
  trusted Sonnet host after missing-choice/no-finish/invalid-mutation failure,
  with bounded total attempts/spend and no partial apply. InferHub LOW/32,768
  already failed, so low effort is not a proven stabilization fix. Gateway
  cheapest-offer failover may try another InferHub seller; HTTP200 application
  failure rescue is not proven. Individual InferHub pin/block recognition,
  effective trust eligibility and real fallback need later authorized evidence.
  `provider_order` is preference, not eligibility; malformed pins can fail open.
  Current `chat` retries once under the same pin policy, doubles on `length`,
  and has no new family-changing Sonnet fallback. `PROVIDER_PINS` pins only
  DeepSeek; generic Sonnet pin config is absent. Do not advertise the external
  diagnostic helper's trusted request as current lap behavior.
- **Design/browser loop:** staged planner artifact, screenshot handoff and
  independent visual acceptance are workflow proposals, not a generic native
  UI oracle or existing automatic lap gate. Correctness regression tests belong
  with later runtime changes, not new wording/source-copy tests for this plan.

Next executable work requires approval of references/revised DESIGN, routing
policy, effort/output budget, total spend/attempt bound and behavioral gates.
Until then: source fixes remain integrated, this plan is discoverable, and no
new paid run or product replacement is queued.
