# Repo Updates Digest — 2026-09-28 (delta since clone ~2026-09-20/23)

| Repo | Δcommits | Notable changes | Relevant? |
|---|---|---|---|
| ai-software-factory | 0 | no upstream movement; still NO LICENSE | no |
| Archon (dev) | 1428 (!) | v0.10→v0.11.1; typed provider-failure contract, gate-outlasts-shell fix, run-stop reasons, workflow packs | **yes (3 items)** |
| symphony | 0 | none | no |
| NEEDLE | 270 | v0.6.8/9; ADR-028 fenced claim_handle gate, canary scoring fixes, self-tuning failure thresholds (Mitosis) | **yes (2 items)** |
| sortie | 84 | v1.25; Gemini CLI token accounting, cache pricing fixed (priced once each), config advisories, SQLite bump | **yes (1 item)** |
| gastown | 0 | none (last activity July) | no |
| no_human | 28 | merge-gate blocks when required checks never ran; mergeability≠merge-ready; coverage rejection feeds next round; grill requires acceptance criteria; rolling-median funnel cost | **yes (4 items)** |
| batty | 0 | none | no |
| omnara | 26 | deps bumps, MinIO→RustFS, webhooks, UI | no |
| aa-llm-compare | 11 | FINDINGS.md split out; **cache-write pricing can cost more than not caching**; missing axis = no composite score | **yes (1 item)** |
| reference/openrig | 4 | Codex `--no-daemon` opt-out; tolerate missing `mission.yaml` metadata; Node 22 on Apple silicon docs | **yes (1 item)** |

## WORTH LEARNING

### 1. no_human — merge gate blocks when required checks never ran on the head (pain c: races / false greens)
`1c0ecb0` — `src/no_human/vcs/ci_rollup.py`, `src/no_human/core/merge_policy.py` (+28/-, ~180 test lines in tests/test_ci_rollup.py). Previously an absent check was treated as a pass; now "required check never ran on this head" blocks the land. Companion `2d44289` (`src/no_human/vcs/landability.py`): unknown mergeability is no longer merge-ready. Directly our (c)+(d): nightshift's dispatch/merge path must re-verify the oracle/CI actually ran *on the current base*, not merely ran. Steal conceptually: a "checks-ran-on-this-head" assertion before squash merge. (MIT, fine.)

### 2. no_human — a coverage rejection must feed the next round (pain d: dispatch-time freshness)
`d2bf0c1` — review round wiring: a rejected round's findings are shown to the next reviewer (`7acd7bc`/`2e6cb5a`, feat(review)). Nightshift's cross-model review is stateless between rounds; carrying prior send-back findings forward is a cheap evidence-first improvement. Also `9f3324a`/`f85bf64`: intake *refuses to proceed without acceptance criteria* and refuses a non-.py repro on the pytest path — same shape as our RED-first gate: fail closed when the proof object is missing.

### 3. Archon — typed failure classes decide retry, not error text (pain b: retry accounting / e: cost)
`879c99fe` — new `packages/provider-contract` package: provider declares `{class, retryAfterMs?, resetAt?, evidence}`; the runner retries on the *class*, not on grepping "401"/"forbidden" out of prose. Nightshift's supervisor retries are ad-hoc; a tiny stdlib dataclass `ApiFailure(class, retry_after_s, evidence)` from the raw HTTP status/headers is a one-file steal for (b)+(e). Also `2eb31864`: a validation gate longer than the tool's call limit is now *detected and completed out-of-band* instead of reported incomplete forever — maps to our oracle-verification timeouts. And `9aadd1ee`: interrupted runs record *why* they stopped (maps to b: intervention logging). (MIT.)

### 4. NEEDLE — ADR-028 fenced claim_handle: fail-closed claim contract (pain b: stale claims)
Commits `5b99fc5` (probe fixture), `6681e32c` (gate itself): an enabled `transitions.fenced_claim` refuses any backend whose capability doc lacks `fenced_claim, renewable_lease, guarded_mutations, credential_transport` — i.e. claiming is a *negotiated lease with renewable expiry*, verified before the loop starts, not an assumption. Nightshift has no single-instance lock; the concept "claim = renewable lease with a capability check at startup" is the right model for (b). Also `5ba7a5d`: Mitosis fires at a *configured failure threshold* — self-tuning retry escalation. (Apache-2.0, fine.)

### 5. aa-llm-compare — cache-write pricing can exceed not caching (pain e: cost accounting)
`308b1f9` (FINDINGS.md): on some providers cache-write tokens are surcharged so caching a prompt costs *more* than re-sending it. Nightshift's single-call-per-lap design mostly dodges this, but any retry/resume accounting must price cache-write separately from cache-read — sortie landed the same fix (`2ac2703`: price cache-read and cache-write tokens once each). If we ever add prompt caching for long system prompts, audit this first.

### 6. openrig — judgment readiness tolerates missing manifest metadata (pain: zero false greens)
`4fcf291` — `packages/daemon/src/domain/proof/judgments.ts:280`: `doc.metadata != null ? mapping(...) : {}`. A scaffolded mission without a metadata block previously aborted readiness composition entirely (crash, not a red) — a *structural* failure masquerading as a state. Lesson for nightshift: every manifest/oracle parse must distinguish "field absent" from "field malformed"; absent optional fields default, malformed fail closed. Their 322-line test for the Codex `--no-daemon` opt-out (`codex-daemon-optout.test.ts`) is also a good pattern: capability detection with graceful fallback per seat.

## NOISE (one-liners)
- ai-software-factory: zero commits since 2026-09-16; dead quiet — nothing to learn from delta.
- symphony, gastown, batty: zero new commits since our clones. gastown's last activity was July.
- Archon: bulk of 1428 commits is workflow-pack catalog/plugin install, telemetry, web UI Cache-Control, Homebrew formulas — CLI/UI plumbing.
- NEEDLE: most of 270 commits is Forgejo CI plumbing, GLM-5.3-Flash adapter profiles, archive spool, checkpoint debouncing — agent-CLI infra.
- sortie: mostly provider CLI support (Kiro→ACP deprecation, OpenCode version support), changelogs, SQLite bump.
- omnara: deps bumps, org UI, MinIO→RustFS, webhooks.
- openrig: Codex seat launching docs/flags otherwise noise.

## License status
- **ai-software-factory: STILL UNLICENSED** (no LICENSE anywhere, including the 0-commit delta). Reference posture unchanged: concepts-only, no verbatim code.
- No relicensing in any other repo; Archon/NEEDLE/sortie/no_human/openrig all retain OSI licenses (MIT/Apache-2.0), quotable-with-attribution.
