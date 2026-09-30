# AMI + Paperclip Evaluation — nightshift adopt/skip verdicts
2026-09-28 · Read-only review of fresh clones `~/repos/ami`, `~/repos/paperclip`. No builds/tests run.
## 1. ami — SuperInference Core (ADOPT selectively)
**What:** SuperInference Core, an agentic coding-engine (multi-provider LLM, tool loop, POMDP
"SuperInference mode") — upstream `github.com/superinference/ami`, Carlos Camacho, 2026-09-24. Engine
core + OpenShell container packaging (`README.md:17-59,285-319`, `Dockerfile:7-18`). **Matches the
Sept-20 ami exactly** — same POMDP machinery and core/test layout FACTORY_PLATFORM_VERDICT.md:60-66
describes; its "no `common/` layer" caveat still holds. **License:** Apache-2.0 (`LICENSE:1-2`,
`README.md:344`, `Dockerfile:91`).

**Mechanisms (source-verified):**
1. **Its own file-edit tool is search/replace, not unified diff.** `SequentialEdit
   {old_string, new_string, replace_all?}` (`file-edit.ts:11-15`), applied in order
   (`file-edit.ts:166-206`); **matchCount 0 → hard error with nearest-line hint**
   (`file-edit.ts:184-191`); **matchCount >1 → error unless `replace_all`** (`file-edit.ts:194-199`).
   It then *synthesizes* the unified diff itself (`buildUnifiedDiff`, `file-edit.ts:507`).
2. **Error→recovery truth table:** 10 categories × `{retryable, shouldCompact, shouldFallback,
   suggestedDelay}`, precedence abort>auth>rate-limit (`error-classifier.ts:21-29,43-145`) — the
   contract FACTORY_PLATFORM_VERDICT.md:61,76 flagged.
3. **LLM critic, fail-closed:** strict-reviewer JSON `{approved, score, reason}`, temperature 0
   (`critic.ts:20-27`); **parse/transport failure → `approved:false`** (`critic.ts:54-58`).
4. **POMDP belief/EIG math** (`belief.ts:22-86`): research formalism; α=0.05/β=0.10 are paper
   constants, never measured — the self-annotated-calibration trap FACTORY_PLATFORM_VERDICT.md:250
   rejects. Do not adopt.
**Nightshift applicability:**
- **Strengthens pending recommendation (a), materially.** Third independent confirmation (after
  ai-software-factory and the agent-native cohort, BIGGEST_ISSUE_ANALYSIS.md:96-97) that no production
  engine consumes model-authored unified diffs: anchor/replace edits + *post-hoc synthesized* diff —
  byte-for-byte the §4 design (BIGGEST_ISSUE_ANALYSIS.md:128-146).
- **Adopt (~10 lines):** anchor-miss error ergonomics — explicit `matchCount>1` error + nearest-line
  hint (`file-edit.ts:184-199`) makes "anchor occurs 0/>1 times" failures actionable evidence
  (feeds open question 3, BIGGEST_ISSUE_ANALYSIS.md:215-217).
- **Do NOT adopt:** ami's fuzzy matching (`file-edit.ts:181,204`) — auto-repair, forbidden by L-008's
  "gates catch, never fix". Exact-once + whitespace normalization stays.
- **Adopt (S2 hygiene, ~60 lines, 2-4 h):** error→recovery truth-table shape for agent.py retry
  classification — extends L-001/L-002 PERMANENT/transient into 10 classes.
- **Skip:** belief/EIG/critic loops (single-shot laps), container packaging (no sandboxing need).
## 2. paperclip — agent-workforce control plane (SKIP as platform)
**What:** `github.com/paperclipai/paperclip` — Node.js server + React UI orchestrating *teams of
bring-your-own agents* (OpenClaw, Claude Code, Codex, Cursor) as a "company": org charts, goals,
budgets, approval gates, heartbeats (`README.md:29-37,41-45,90-95`). Active (last commit 2026-09-28).
**License:** MIT, Paperclip Labs, Inc (`README.md:15,526`). **Scale:** pnpm monorepo, embedded
PostgreSQL (`README.md:396`), Node 24.11+ (`README.md:398`), Storybook/Playwright/OTel/Sentry/plugins
(`README.md:489-491`) — the anti-nightshift: heavy, human-governance-first, multi-tenant.

**"Drives the business" — honest read:** real loop, but it is *governance*, not *execution*. Strategy
is a goal you type (`README.md:43`); the deep features are approval workflows, budget hard-stops,
audit trails (`README.md:242,249,273`) — review gates around agent work, not revenue functions or
autonomous product decisions. Its own "What Paperclip is not" table says it manages the
*organization*, not agents or workflows (`README.md:286-295`). The product is agent workforce
oversight for humans (`README.md:73,141`) — what nightshift's zero-intervention charter avoids.
**Nightshift applicability:**
- **Skip the platform.** Inverts all three constraints: stdlib-only (Node+pnpm+Postgres), thin
  (12-system control plane, `README.md:179-282`), single-agent (`README.md:294`).
- Headline mechanisms are covered by cheaper sources: atomic checkout/execution locks → NEEDLE
  ADR-028 lease (BIGGEST_ISSUE_ANALYSIS.md:100); budget hard-stops → irrelevant at <$0.01/lap.
- **Smallest useful steal (~1 h, concept only):** `@paperclipai/paperclip-eval-kernel` — deterministic
  scenario×candidate matrix with unique-ID assertions and **fail-closed per-candidate preflight**
  (`packages/paperclip-eval-kernel/src/index.ts:16-17,40-63`, MIT). Right shape for the S1 prep
  regression harness: replay #10's edits as scenarios × {unified-diff, mutation-JSON} candidates,
  preflight fails closed if the base commit is missing. Discipline only; no code copied (TS anyway).
## 3. Combined recommendation
Neither repo changes the (a)-vs-(b) decision — **(a) stands and is stronger**: ami's own edit tool
being search/replace-with-synthesized-diff (`file-edit.ts:11-15,507`) is the strongest independent
corroboration yet that the artifact contract, not model competence, is the ceiling
(BIGGEST_ISSUE_ANALYSIS.md:22). S1 prep list, amended: (1) mutation-apply failures carry ami-style
actionable evidence — anchor prefix + occurrence count + nearest-line hint (`file-edit.ts:184-199`);
(2) agent.py gains the error→recovery truth table (`error-classifier.ts:43-145`); (3) the replay
harness adopts the scenario×candidate matrix + fail-closed preflight shape (`eval-kernel
index.ts:40-63`). Everything else: skip. Product-build path unchanged: mutation-JSON contract first,
then S1 attempt, no new dependencies.

---
**ami:** Apache-2.0 engine whose own edit tool already proves the mutation-JSON contract — steal its
error ergonomics and error taxonomy, skip the POMDP math.
**paperclip:** a well-built governance platform for problems nightshift deliberately doesn't have —
skip the platform, take one hour of eval-matrix discipline.
**Strongest recommendation:** proceed with (a) — adopt the search/replace mutation-JSON contract for
the clean S1 overnight attempt; ami independently validates it, and nothing in either repo argues
for anything heavier.
