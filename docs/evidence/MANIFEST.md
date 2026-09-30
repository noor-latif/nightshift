# Nightshift S1 — Redacted Publication Corpus MANIFEST

Built: 2026-09-29; refreshed 2026-09-30 with the self-hosting run (self-run) evidence. Sources: `~/repos/factory-docs/` (docs), `~/nightshift/state/` (S1 instrument), `~/nightshift-selfrun/state/` + `~/nightshift-selfrun/scenarios-selfrun/` (self-run instrument). Originals untouched (md5-verified). Nothing is published by this artifact; it is staged for a one-push publish.

## Redaction rules applied (deterministic perl, re-runnable)

```
find ~/repos/factory-docs-publication -type f -exec grep -Il '' {} + > textfiles.txt
xargs -a textfiles.txt perl -pi -e \
  -e 's/\bnixlab\b/[redacted-host]/g' \
  -e 's/[A-Za-z0-9.-]*\.latif\.se/[redacted-host]/g' \
  -e 's/127\.0\.0\.1:[0-9]+/127.0.0.1:[redacted-port]/g' \
  -e 's/nightshift-[0-9a-f]{16}/[redacted-ntfy-topic]/g' \
  -e 's|/home/noor/|~/|g'
```

Note 2026-09-29: the sed form of this command silently no-ops on \b under sed 0.1.1 on the build machine; the perl form above is the verified one and was used for the final pass.

1. **Hostnames**: `nixlab` and any `*.latif.se` / private hostname → `[redacted-host]`.
2. **Loopback ports**: `127.0.0.1:<port>` → `127.0.0.1:[redacted-port]` (loopback literal kept).
3. **ntfy topics**: every `nightshift-<hex16>` literal → `[redacted-ntfy-topic]`.
4. **Env var references**: `SURPLUS_INTELLIGENCE_API_KEY` as a NAME is allowed (whitelisted; already in the public repo). No key VALUES were found anywhere (verified pre- and post-copy; see verification block).
5. **Paths**: `/home/noor/` → `~/`. No other path changes.
6. **Whitepaper**: `NIGHTSHIFT_WHITEPAPER.md` verified leak-clean pre-copy (0 hits on all patterns); copied; sed applied regardless (0 substitutions, as expected).

## Known-public items (no action)

- Public repo `settings.py` carries dormant alias `REPO_HOST="nixlab"` — pre-existing, public; not touched here.
- Old ntfy topic value exists in the **public repo's git history**; short of a history rewrite it stays there. Recommendation: rotate the subscription — **already done**; no further action.
- Both prior ntfy topic values (pre-2026-09-30 rotations) persist in the public repo's git history; the remedy is rotation (done 2026-09-30), not history rewriting.

## Exclusions (and why)

- `state/interventions.jsonl` (live) — superseded by the scored snapshot, which IS included (renamed to `interventions.jsonl`).
- `state/interventions.jsonl.scored-snapshot` (as a separate name) — included once, renamed; duplicate-name copy removed.
- Lap logs (`lap-*.log`), supervisor logs/pids/lock, `heartbeat`, `lap-result*.json`, archived `state.day*.json` — zero-byte or operational scaffolding, not part of the disclosed record.
- `state/claims/` — empty dir at snapshot time; structure preserved.
- `state/evidence/ntfy/day4-capture.sse`, `day4b-capture.sse` — raw SSE captures of day-4 notification traffic; not cited by any doc; contained the burned old topic (excluded rather than redacted).
- Uncited spike/interim evidence dirs (2026-09-25/26 dirs not named above) — included ONLY when cited by exact name in the copied docs (per corpus policy).
- `docs/DEFECTS_DRAFT.html`, `DEFECTS_DRAFT.json.html` (5.3 MB each), `OPPORTUNITY_SCAN_2026-09-28.html`, `harvest/`, `holdout.json`, `scenario.json`, `launch-lifecycle.sh.retired-one-shot` — bulk HTML/JSON artifacts and retired scripts outside the document corpus; excluded (also the retired script contained loopback ports and `/home/noor/` paths).
- `WHITEPAPER_FALSIFICATION_REPORT_2.md` — landed after initial packaging; ADDED in the 2026-09-29 refresh (leak-scan clean, sed no-op). Same refresh re-copied the corrected 309-line `NIGHTSHIFT_WHITEPAPER.md`; both re-passed the sed + verification suite.
- No binary/pyc/venv artifacts encountered in the included set.

## File inventory (381 files + this manifest)

| Path | Redactions applied | Citations / note |
|---|---|---|
| `docs/AGENTS.md` | host x2 |  |
| `docs/AMI_PAPERCLIP_EVALUATION.md` | none |  |
| `docs/BIGGEST_ISSUE_ANALYSIS.md` | host x1 |  |
| `docs/CALIBRATION_REPORT.md` | host x2, port x1 |  |
| `docs/CLONE_SURVEY_2026-09-26.md` | host x1 |  |
| `docs/COMPETITOR_LANDSCAPE.md` | none |  |
| `docs/DAY2_REPORT.md` | host x6, port x1 |  |
| `docs/DAY3_REPORT.md` | host x3, port x1 |  |
| `docs/DAY4_REPORT.md` | host x1 |  |
| `docs/DAY5_REPORT.md` | host x2 |  |
| `docs/DEEP_RESEARCH_PRD_FACTORY.md` | none |  |
| `docs/DEFECTS_DRAFT.md` | host x4 |  |
| `docs/END-TO-END.md` | none |  |
| `docs/FACTORY_PLATFORM_VERDICT.md` | host x3 |  |
| `docs/FALSIFY_AND_ORACLE_RESEARCH.md` | none |  |
| `docs/FIRST_BUILD_VERIFICATION.md` | host x6 |  |
| `docs/HANDOFF_JEV_VERIFICATION.md` | none |  |
| `docs/HOLDOUT.md` | none |  |
| `docs/JJ_FOR_AGENTS_REVIEW.md` | none |  |
| `docs/LANDSCAPE_SCOUT_2026-09-28.md` | none |  |
| `docs/LAPTOP_MIGRATION.md` | host x6, ntfy-topic x1 |  |
| `docs/MISSION.md` | none |  |
| `docs/NIGHTSHIFT_WHITEPAPER.md` | none | refreshed 2026-09-30 ("seven modules"→"eight" at L57/L279); previously refreshed 2026-09-29 (falsification-report-2 fixes: cost 110–417×, S1 dangling-lap disclosure, L-016, PR #24, latency era labels, citation repoint, Phase-0 pin, five-day span dates); leak-clean, sed no-op |
| `docs/PITFALLS_AND_STRATEGIES.md` | host x1 |  |
| `docs/POC_PROPOSAL.md` | host x6 |  |
| `docs/REPO_UPDATES_DIGEST.md` | none |  |
| `docs/REVIEWER_DISCRIMINATION_REPORT.md` | none |  |
| `docs/SELF_AUDIT_2026-09-29.md` | none | added 2026-09-30; adversarial self-audit, K1-K6 kept findings + executed RED repros; post-filing acceptance-criteria correction note; leak-clean, perl no-op |
| `docs/SELF_RUN_SCORE_2026-09-29.md` | none | added 2026-09-30; formal score of the self-hosting run (launch-3 08:47:20Z→10:00:00Z, 4/5 merged PRs #8-#11, #1 supervised PR #7, #6 parked, $0.005685, zero interventions); leak-clean, perl no-op |
| `docs/SESSION_HANDOFF_2026-09-28.md` | host x4 |  |
| `docs/SPIKE_LEARNINGS.md` | host x5 |  |
| `docs/SPIKE_PROD.md` | host x10, ntfy-topic x2 |  |
| `docs/SURPLUS_GATEWAY_SMOKE.md` | host x2 |  |
| `docs/TECH_MANDATE_REVIEW.md` | host x3 |  |
| `docs/UNATTENDED_FACTORY_PLAN.md` | host x1 |  |
| `docs/VIBE_CODING_FAILURE_RESEARCH.md` | none |  |
| `docs/WHITEPAPER_FALSIFICATION_REPORT.md` | host x1, port x1 |  |
| `docs/WHITEPAPER_FALSIFICATION_REPORT_2.md` | none | added 2026-09-29 refresh; cites evidence/20260928T203353-issue-10 and 20260928T214639-issue-19 (both in corpus); leak-clean, sed no-op |
| `state/evidence/20260925T101308-issue-6/applied.diff` | none | DAY2_REPORT.md, SPIKE_LEARNINGS.md, REVIEWER_DISCRIMINATION_REPORT.md |
| `state/evidence/20260925T101308-issue-6/claimed.diff` | none | DAY2_REPORT.md, SPIKE_LEARNINGS.md, REVIEWER_DISCRIMINATION_REPORT.md |
| `state/evidence/20260925T101308-issue-6/cost.json` | none | DAY2_REPORT.md, SPIKE_LEARNINGS.md, REVIEWER_DISCRIMINATION_REPORT.md |
| `state/evidence/20260925T101308-issue-6/implementer_raw.txt` | none | DAY2_REPORT.md, SPIKE_LEARNINGS.md, REVIEWER_DISCRIMINATION_REPORT.md |
| `state/evidence/20260925T101308-issue-6/review.txt` | none | DAY2_REPORT.md, SPIKE_LEARNINGS.md, REVIEWER_DISCRIMINATION_REPORT.md |
| `state/evidence/20260925T101308-issue-6/timeline.json` | none | DAY2_REPORT.md, SPIKE_LEARNINGS.md, REVIEWER_DISCRIMINATION_REPORT.md |
| `state/evidence/20260925T101308-issue-6/verdict.json` | none | DAY2_REPORT.md, SPIKE_LEARNINGS.md, REVIEWER_DISCRIMINATION_REPORT.md |
| `state/evidence/20260925T101559-issue-6/cost.json` | none | DAY2_REPORT.md |
| `state/evidence/20260925T101559-issue-6/implementer_raw.txt` | none | DAY2_REPORT.md |
| `state/evidence/20260925T101559-issue-6/timeline.json` | none | DAY2_REPORT.md |
| `state/evidence/20260925T101559-issue-6/verdict.json` | none | DAY2_REPORT.md |
| `state/evidence/20260925T101931-issue-6/cost.json` | none | DAY2_REPORT.md |
| `state/evidence/20260925T101931-issue-6/implementer_raw.txt` | none | DAY2_REPORT.md |
| `state/evidence/20260925T101931-issue-6/timeline.json` | none | DAY2_REPORT.md |
| `state/evidence/20260925T101931-issue-6/verdict.json` | none | DAY2_REPORT.md |
| `state/evidence/20260926T041023-issue-7/timeline.json` | none | DAY3_REPORT.md |
| `state/evidence/20260926T041023-issue-7/verdict.json` | none | DAY3_REPORT.md |
| `state/evidence/20260926T041334-issue-7/claimed.diff` | none | DAY3_REPORT.md, CLONE_SURVEY_2026-09-26.md |
| `state/evidence/20260926T041334-issue-7/cost.json` | none | DAY3_REPORT.md, CLONE_SURVEY_2026-09-26.md |
| `state/evidence/20260926T041334-issue-7/implementer_raw.txt` | none | DAY3_REPORT.md, CLONE_SURVEY_2026-09-26.md |
| `state/evidence/20260926T041334-issue-7/timeline.json` | none | DAY3_REPORT.md, CLONE_SURVEY_2026-09-26.md |
| `state/evidence/20260926T041334-issue-7/verdict.json` | none | DAY3_REPORT.md, CLONE_SURVEY_2026-09-26.md |
| `state/evidence/20260926T041715-issue-7/claimed.diff` | none | DAY3_REPORT.md, CLONE_SURVEY_2026-09-26.md |
| `state/evidence/20260926T041715-issue-7/cost.json` | none | DAY3_REPORT.md, CLONE_SURVEY_2026-09-26.md |
| `state/evidence/20260926T041715-issue-7/implementer_raw.txt` | none | DAY3_REPORT.md, CLONE_SURVEY_2026-09-26.md |
| `state/evidence/20260926T041715-issue-7/timeline.json` | none | DAY3_REPORT.md, CLONE_SURVEY_2026-09-26.md |
| `state/evidence/20260926T041715-issue-7/verdict.json` | none | DAY3_REPORT.md, CLONE_SURVEY_2026-09-26.md |
| `state/evidence/20260926T142715-issue-9/applied.diff` | none | DAY4_REPORT.md |
| `state/evidence/20260926T142715-issue-9/claimed.diff` | none | DAY4_REPORT.md |
| `state/evidence/20260926T142715-issue-9/cost.json` | none | DAY4_REPORT.md |
| `state/evidence/20260926T142715-issue-9/implementer_raw.txt` | none | DAY4_REPORT.md |
| `state/evidence/20260926T142715-issue-9/review.txt` | none | DAY4_REPORT.md |
| `state/evidence/20260926T142715-issue-9/timeline.json` | none | DAY4_REPORT.md |
| `state/evidence/20260926T142715-issue-9/verdict.json` | none | DAY4_REPORT.md |
| `state/evidence/20260926T143026-issue-9/applied.diff` | none | DAY4_REPORT.md |
| `state/evidence/20260926T143026-issue-9/claimed.diff` | none | DAY4_REPORT.md |
| `state/evidence/20260926T143026-issue-9/cost.json` | none | DAY4_REPORT.md |
| `state/evidence/20260926T143026-issue-9/implementer_raw.txt` | none | DAY4_REPORT.md |
| `state/evidence/20260926T143026-issue-9/review.txt` | none | DAY4_REPORT.md |
| `state/evidence/20260926T143026-issue-9/timeline.json` | none | DAY4_REPORT.md |
| `state/evidence/20260926T143026-issue-9/verdict.json` | none | DAY4_REPORT.md |
| `state/evidence/20260926T143357-issue-9/cost.json` | none | SPIKE_LEARNINGS.md |
| `state/evidence/20260926T143357-issue-9/implementer_raw.txt` | none | SPIKE_LEARNINGS.md |
| `state/evidence/20260926T143357-issue-9/timeline.json` | none | SPIKE_LEARNINGS.md |
| `state/evidence/20260926T143357-issue-9/verdict.json` | none | SPIKE_LEARNINGS.md |
| `state/evidence/20260926T152543-issue-10/applied.diff` | none | DAY4_REPORT.md |
| `state/evidence/20260926T152543-issue-10/claimed.diff` | none | DAY4_REPORT.md |
| `state/evidence/20260926T152543-issue-10/cost.json` | none | DAY4_REPORT.md |
| `state/evidence/20260926T152543-issue-10/implementer_raw.txt` | none | DAY4_REPORT.md |
| `state/evidence/20260926T152543-issue-10/review.txt` | none | DAY4_REPORT.md |
| `state/evidence/20260926T152543-issue-10/timeline.json` | none | DAY4_REPORT.md |
| `state/evidence/20260926T152543-issue-10/verdict.json` | none | DAY4_REPORT.md |
| `state/evidence/20260926T153446-issue-10/cost.json` | none | SPIKE_LEARNINGS.md |
| `state/evidence/20260926T153446-issue-10/implementer_raw.txt` | none | SPIKE_LEARNINGS.md |
| `state/evidence/20260926T153446-issue-10/timeline.json` | none | SPIKE_LEARNINGS.md |
| `state/evidence/20260926T153446-issue-10/verdict.json` | none | SPIKE_LEARNINGS.md |
| `state/evidence/20260926T203657-issue-10/claimed.diff` | none | DAY5_REPORT.md |
| `state/evidence/20260926T203657-issue-10/cost.json` | none | DAY5_REPORT.md |
| `state/evidence/20260926T203657-issue-10/implementer_raw.txt` | none | DAY5_REPORT.md |
| `state/evidence/20260926T203657-issue-10/timeline.json` | none | DAY5_REPORT.md |
| `state/evidence/20260926T203657-issue-10/verdict.json` | none | DAY5_REPORT.md |
| `state/evidence/20260926T204208-issue-12/applied.diff` | none | DAY5_REPORT.md |
| `state/evidence/20260926T204208-issue-12/claimed.diff` | none | DAY5_REPORT.md |
| `state/evidence/20260926T204208-issue-12/cost.json` | none | DAY5_REPORT.md |
| `state/evidence/20260926T204208-issue-12/implementer_raw.txt` | none | DAY5_REPORT.md |
| `state/evidence/20260926T204208-issue-12/review.txt` | none | DAY5_REPORT.md |
| `state/evidence/20260926T204208-issue-12/timeline.json` | none | DAY5_REPORT.md |
| `state/evidence/20260926T204208-issue-12/verdict.json` | none | DAY5_REPORT.md |
| `state/evidence/20260926T204208-issue-12/verify.json` | port x10 | DAY5_REPORT.md |
| `state/evidence/20260926T204208-issue-13/applied.diff` | none | DAY5_REPORT.md |
| `state/evidence/20260926T204208-issue-13/claimed.diff` | none | DAY5_REPORT.md |
| `state/evidence/20260926T204208-issue-13/cost.json` | none | DAY5_REPORT.md |
| `state/evidence/20260926T204208-issue-13/identity.json` | none | DAY5_REPORT.md |
| `state/evidence/20260926T204208-issue-13/implementer_raw.txt` | none | DAY5_REPORT.md |
| `state/evidence/20260926T204208-issue-13/merge.json` | none | DAY5_REPORT.md |
| `state/evidence/20260926T204208-issue-13/review.txt` | none | DAY5_REPORT.md |
| `state/evidence/20260926T204208-issue-13/timeline.json` | none | DAY5_REPORT.md |
| `state/evidence/20260926T204208-issue-13/verdict.json` | none | DAY5_REPORT.md |
| `state/evidence/20260926T204208-issue-13/verify.json` | port x11 | DAY5_REPORT.md |
| `state/evidence/20260926T205312-issue-10/claimed.diff` | none | DAY5_REPORT.md, REVIEWER_DISCRIMINATION_REPORT.md |
| `state/evidence/20260926T205312-issue-10/cost.json` | none | DAY5_REPORT.md, REVIEWER_DISCRIMINATION_REPORT.md |
| `state/evidence/20260926T205312-issue-10/implementer_raw.txt` | none | DAY5_REPORT.md, REVIEWER_DISCRIMINATION_REPORT.md |
| `state/evidence/20260926T205312-issue-10/timeline.json` | none | DAY5_REPORT.md, REVIEWER_DISCRIMINATION_REPORT.md |
| `state/evidence/20260926T205312-issue-10/verdict.json` | none | DAY5_REPORT.md, REVIEWER_DISCRIMINATION_REPORT.md |
| `state/evidence/20260926T210034-issue-12/applied.diff` | none | DAY5_REPORT.md, SPIKE_LEARNINGS.md |
| `state/evidence/20260926T210034-issue-12/claimed.diff` | none | DAY5_REPORT.md, SPIKE_LEARNINGS.md |
| `state/evidence/20260926T210034-issue-12/cost.json` | none | DAY5_REPORT.md, SPIKE_LEARNINGS.md |
| `state/evidence/20260926T210034-issue-12/implementer_raw.txt` | none | DAY5_REPORT.md, SPIKE_LEARNINGS.md |
| `state/evidence/20260926T210034-issue-12/review.txt` | none | DAY5_REPORT.md, SPIKE_LEARNINGS.md |
| `state/evidence/20260926T210034-issue-12/timeline.json` | none | DAY5_REPORT.md, SPIKE_LEARNINGS.md |
| `state/evidence/20260926T210034-issue-12/verdict.json` | none | DAY5_REPORT.md, SPIKE_LEARNINGS.md |
| `state/evidence/20260926T210034-issue-12/verify.json` | port x10 | DAY5_REPORT.md, SPIKE_LEARNINGS.md |
| `state/evidence/20260926T210455-issue-12/applied.diff` | none | DAY5_REPORT.md |
| `state/evidence/20260926T210455-issue-12/claimed.diff` | none | DAY5_REPORT.md |
| `state/evidence/20260926T210455-issue-12/cost.json` | none | DAY5_REPORT.md |
| `state/evidence/20260926T210455-issue-12/implementer_raw.txt` | none | DAY5_REPORT.md |
| `state/evidence/20260926T210455-issue-12/review.txt` | none | DAY5_REPORT.md |
| `state/evidence/20260926T210455-issue-12/timeline.json` | none | DAY5_REPORT.md |
| `state/evidence/20260926T210455-issue-12/verdict.json` | none | DAY5_REPORT.md |
| `state/evidence/20260926T210455-issue-12/verify.json` | port x10 | DAY5_REPORT.md |
| `state/evidence/20260926T210631-issue-10/claimed.diff` | none | DAY5_REPORT.md, REVIEWER_DISCRIMINATION_REPORT.md |
| `state/evidence/20260926T210631-issue-10/cost.json` | none | DAY5_REPORT.md, REVIEWER_DISCRIMINATION_REPORT.md |
| `state/evidence/20260926T210631-issue-10/implementer_raw.txt` | none | DAY5_REPORT.md, REVIEWER_DISCRIMINATION_REPORT.md |
| `state/evidence/20260926T210631-issue-10/timeline.json` | none | DAY5_REPORT.md, REVIEWER_DISCRIMINATION_REPORT.md |
| `state/evidence/20260926T210631-issue-10/verdict.json` | none | DAY5_REPORT.md, REVIEWER_DISCRIMINATION_REPORT.md |
| `state/evidence/20260926T211313-issue-10/claimed.diff` | none | DAY5_REPORT.md |
| `state/evidence/20260926T211313-issue-10/cost.json` | none | DAY5_REPORT.md |
| `state/evidence/20260926T211313-issue-10/implementer_raw.txt` | none | DAY5_REPORT.md |
| `state/evidence/20260926T211313-issue-10/timeline.json` | none | DAY5_REPORT.md |
| `state/evidence/20260926T211313-issue-10/verdict.json` | none | DAY5_REPORT.md |
| `state/evidence/20260926T212214-issue-12/claimed.diff` | none | DAY5_REPORT.md, SPIKE_LEARNINGS.md |
| `state/evidence/20260926T212214-issue-12/cost.json` | none | DAY5_REPORT.md, SPIKE_LEARNINGS.md |
| `state/evidence/20260926T212214-issue-12/implementer_raw.txt` | none | DAY5_REPORT.md, SPIKE_LEARNINGS.md |
| `state/evidence/20260926T212214-issue-12/timeline.json` | none | DAY5_REPORT.md, SPIKE_LEARNINGS.md |
| `state/evidence/20260926T212214-issue-12/verdict.json` | none | DAY5_REPORT.md, SPIKE_LEARNINGS.md |
| `state/evidence/20260926T212615-issue-12/applied.diff` | none | DAY5_REPORT.md, SPIKE_LEARNINGS.md, LAPTOP_MIGRATION.md |
| `state/evidence/20260926T212615-issue-12/claimed.diff` | none | DAY5_REPORT.md, SPIKE_LEARNINGS.md, LAPTOP_MIGRATION.md |
| `state/evidence/20260926T212615-issue-12/cost.json` | none | DAY5_REPORT.md, SPIKE_LEARNINGS.md, LAPTOP_MIGRATION.md |
| `state/evidence/20260926T212615-issue-12/identity.json` | none | DAY5_REPORT.md, SPIKE_LEARNINGS.md, LAPTOP_MIGRATION.md |
| `state/evidence/20260926T212615-issue-12/implementer_raw.txt` | none | DAY5_REPORT.md, SPIKE_LEARNINGS.md, LAPTOP_MIGRATION.md |
| `state/evidence/20260926T212615-issue-12/merge.json` | none | DAY5_REPORT.md, SPIKE_LEARNINGS.md, LAPTOP_MIGRATION.md |
| `state/evidence/20260926T212615-issue-12/review.txt` | none | DAY5_REPORT.md, SPIKE_LEARNINGS.md, LAPTOP_MIGRATION.md |
| `state/evidence/20260926T212615-issue-12/timeline.json` | none | DAY5_REPORT.md, SPIKE_LEARNINGS.md, LAPTOP_MIGRATION.md |
| `state/evidence/20260926T212615-issue-12/verdict.json` | none | DAY5_REPORT.md, SPIKE_LEARNINGS.md, LAPTOP_MIGRATION.md |
| `state/evidence/20260926T212615-issue-12/verify.json` | port x10 | DAY5_REPORT.md, SPIKE_LEARNINGS.md, LAPTOP_MIGRATION.md |
| `state/evidence/20260926T213434-issue-10/claimed.diff` | none | DAY5_REPORT.md |
| `state/evidence/20260926T213434-issue-10/cost.json` | none | DAY5_REPORT.md |
| `state/evidence/20260926T213434-issue-10/implementer_raw.txt` | none | DAY5_REPORT.md |
| `state/evidence/20260926T213434-issue-10/timeline.json` | none | DAY5_REPORT.md |
| `state/evidence/20260926T213434-issue-10/verdict.json` | none | DAY5_REPORT.md |
| `state/evidence/20260926T214258-issue-10/timeline.json` | none | DAY5_REPORT.md |
| `state/evidence/20260926T214258-issue-10/verdict.json` | none | DAY5_REPORT.md |
| `state/evidence/20260928T203353-issue-10/applied.diff` | none | scored S1 run (launch-6), issue-10 GREEN |
| `state/evidence/20260928T203353-issue-10/claimed.json` | none | scored S1 run (launch-6), issue-10 GREEN |
| `state/evidence/20260928T203353-issue-10/cost.json` | none | scored S1 run (launch-6), issue-10 GREEN |
| `state/evidence/20260928T203353-issue-10/identity.json` | none | scored S1 run (launch-6), issue-10 GREEN |
| `state/evidence/20260928T203353-issue-10/implementer_raw.txt` | none | scored S1 run (launch-6), issue-10 GREEN |
| `state/evidence/20260928T203353-issue-10/merge.json` | none | scored S1 run (launch-6), issue-10 GREEN |
| `state/evidence/20260928T203353-issue-10/mutations.json` | none | scored S1 run (launch-6), issue-10 GREEN |
| `state/evidence/20260928T203353-issue-10/review.txt` | none | scored S1 run (launch-6), issue-10 GREEN |
| `state/evidence/20260928T203353-issue-10/timeline.json` | none | scored S1 run (launch-6), issue-10 GREEN |
| `state/evidence/20260928T203353-issue-10/verdict.json` | none | scored S1 run (launch-6), issue-10 GREEN |
| `state/evidence/20260928T203353-issue-10/verify.json` | port x9 | scored S1 run (launch-6), issue-10 GREEN |
| `state/evidence/20260928T204441-issue-17/applied.diff` | none | SESSION_HANDOFF_2026-09-28.md (launch-2 false-reject), REVIEWER_DISCRIMINATION_REPORT.md |
| `state/evidence/20260928T204441-issue-17/claimed.json` | none | SESSION_HANDOFF_2026-09-28.md (launch-2 false-reject), REVIEWER_DISCRIMINATION_REPORT.md |
| `state/evidence/20260928T204441-issue-17/cost.json` | none | SESSION_HANDOFF_2026-09-28.md (launch-2 false-reject), REVIEWER_DISCRIMINATION_REPORT.md |
| `state/evidence/20260928T204441-issue-17/implementer_raw.txt` | none | SESSION_HANDOFF_2026-09-28.md (launch-2 false-reject), REVIEWER_DISCRIMINATION_REPORT.md |
| `state/evidence/20260928T204441-issue-17/mutations.json` | none | SESSION_HANDOFF_2026-09-28.md (launch-2 false-reject), REVIEWER_DISCRIMINATION_REPORT.md |
| `state/evidence/20260928T204441-issue-17/review.txt` | none | SESSION_HANDOFF_2026-09-28.md (launch-2 false-reject), REVIEWER_DISCRIMINATION_REPORT.md |
| `state/evidence/20260928T204441-issue-17/timeline.json` | none | SESSION_HANDOFF_2026-09-28.md (launch-2 false-reject), REVIEWER_DISCRIMINATION_REPORT.md |
| `state/evidence/20260928T204441-issue-17/verdict.json` | none | SESSION_HANDOFF_2026-09-28.md (launch-2 false-reject), REVIEWER_DISCRIMINATION_REPORT.md |
| `state/evidence/20260928T204745-issue-17/applied.diff` | none | SESSION_HANDOFF_2026-09-28.md (launch-2 false-reject, canonical diff), REVIEWER_DISCRIMINATION_REPORT.md |
| `state/evidence/20260928T204745-issue-17/claimed.json` | none | SESSION_HANDOFF_2026-09-28.md (launch-2 false-reject, canonical diff), REVIEWER_DISCRIMINATION_REPORT.md |
| `state/evidence/20260928T204745-issue-17/cost.json` | none | SESSION_HANDOFF_2026-09-28.md (launch-2 false-reject, canonical diff), REVIEWER_DISCRIMINATION_REPORT.md |
| `state/evidence/20260928T204745-issue-17/implementer_raw.txt` | none | SESSION_HANDOFF_2026-09-28.md (launch-2 false-reject, canonical diff), REVIEWER_DISCRIMINATION_REPORT.md |
| `state/evidence/20260928T204745-issue-17/mutations.json` | none | SESSION_HANDOFF_2026-09-28.md (launch-2 false-reject, canonical diff), REVIEWER_DISCRIMINATION_REPORT.md |
| `state/evidence/20260928T204745-issue-17/review.txt` | none | SESSION_HANDOFF_2026-09-28.md (launch-2 false-reject, canonical diff), REVIEWER_DISCRIMINATION_REPORT.md |
| `state/evidence/20260928T204745-issue-17/timeline.json` | none | SESSION_HANDOFF_2026-09-28.md (launch-2 false-reject, canonical diff), REVIEWER_DISCRIMINATION_REPORT.md |
| `state/evidence/20260928T204745-issue-17/verdict.json` | none | SESSION_HANDOFF_2026-09-28.md (launch-2 false-reject, canonical diff), REVIEWER_DISCRIMINATION_REPORT.md |
| `state/evidence/20260928T211505-issue-18/applied.diff` | none | scored S1 run (launch-6), issue-18 GREEN (PR #22) |
| `state/evidence/20260928T211505-issue-18/claimed.json` | none | scored S1 run (launch-6), issue-18 GREEN (PR #22) |
| `state/evidence/20260928T211505-issue-18/cost.json` | none | scored S1 run (launch-6), issue-18 GREEN (PR #22) |
| `state/evidence/20260928T211505-issue-18/identity.json` | none | scored S1 run (launch-6), issue-18 GREEN (PR #22) |
| `state/evidence/20260928T211505-issue-18/implementer_raw.txt` | none | scored S1 run (launch-6), issue-18 GREEN (PR #22) |
| `state/evidence/20260928T211505-issue-18/merge.json` | none | scored S1 run (launch-6), issue-18 GREEN (PR #22) |
| `state/evidence/20260928T211505-issue-18/mutations.json` | none | scored S1 run (launch-6), issue-18 GREEN (PR #22) |
| `state/evidence/20260928T211505-issue-18/review.txt` | none | scored S1 run (launch-6), issue-18 GREEN (PR #22) |
| `state/evidence/20260928T211505-issue-18/timeline.json` | none | scored S1 run (launch-6), issue-18 GREEN (PR #22) |
| `state/evidence/20260928T211505-issue-18/verdict.json` | none | scored S1 run (launch-6), issue-18 GREEN (PR #22) |
| `state/evidence/20260928T211505-issue-18/verify.json` | port x10 | scored S1 run (launch-6), issue-18 GREEN (PR #22) |
| `state/evidence/20260928T212724-issue-17/timeline.json` | none | SPIKE_LEARNINGS.md, SESSION_HANDOFF_2026-09-28.md (launch-5 worktree-crash) |
| `state/evidence/20260928T212724-issue-17/verdict.json` | none | SPIKE_LEARNINGS.md, SESSION_HANDOFF_2026-09-28.md (launch-5 worktree-crash) |
| `state/evidence/20260928T212948-issue-17/timeline.json` | none | SPIKE_LEARNINGS.md (launch-5 worktree-crash) |
| `state/evidence/20260928T212948-issue-17/verdict.json` | none | SPIKE_LEARNINGS.md (launch-5 worktree-crash) |
| `state/evidence/20260928T213213-issue-17/timeline.json` | none | SPIKE_LEARNINGS.md (launch-5 worktree-crash) |
| `state/evidence/20260928T213213-issue-17/verdict.json` | none | SPIKE_LEARNINGS.md (launch-5 worktree-crash) |
| `state/evidence/20260928T214334-issue-17/applied.diff` | none | scored S1 run (launch-6), issue-17 GREEN (PR #23) |
| `state/evidence/20260928T214334-issue-17/claimed.json` | none | scored S1 run (launch-6), issue-17 GREEN (PR #23) |
| `state/evidence/20260928T214334-issue-17/cost.json` | none | scored S1 run (launch-6), issue-17 GREEN (PR #23) |
| `state/evidence/20260928T214334-issue-17/identity.json` | none | scored S1 run (launch-6), issue-17 GREEN (PR #23) |
| `state/evidence/20260928T214334-issue-17/implementer_raw.txt` | none | scored S1 run (launch-6), issue-17 GREEN (PR #23) |
| `state/evidence/20260928T214334-issue-17/merge.json` | none | scored S1 run (launch-6), issue-17 GREEN (PR #23) |
| `state/evidence/20260928T214334-issue-17/mutations.json` | none | scored S1 run (launch-6), issue-17 GREEN (PR #23) |
| `state/evidence/20260928T214334-issue-17/review.txt` | none | scored S1 run (launch-6), issue-17 GREEN (PR #23) |
| `state/evidence/20260928T214334-issue-17/timeline.json` | none | scored S1 run (launch-6), issue-17 GREEN (PR #23) |
| `state/evidence/20260928T214334-issue-17/verdict.json` | none | scored S1 run (launch-6), issue-17 GREEN (PR #23) |
| `state/evidence/20260928T214334-issue-17/verify.json` | port x12 | scored S1 run (launch-6), issue-17 GREEN (PR #23) |
| `state/evidence/20260928T214639-issue-19/applied.diff` | none | scored S1 run (launch-6), issue-19 GREEN |
| `state/evidence/20260928T214639-issue-19/claimed.json` | none | scored S1 run (launch-6), issue-19 GREEN |
| `state/evidence/20260928T214639-issue-19/cost.json` | none | scored S1 run (launch-6), issue-19 GREEN |
| `state/evidence/20260928T214639-issue-19/identity.json` | none | scored S1 run (launch-6), issue-19 GREEN |
| `state/evidence/20260928T214639-issue-19/implementer_raw.txt` | none | scored S1 run (launch-6), issue-19 GREEN |
| `state/evidence/20260928T214639-issue-19/merge.json` | none | scored S1 run (launch-6), issue-19 GREEN |
| `state/evidence/20260928T214639-issue-19/mutations.json` | none | scored S1 run (launch-6), issue-19 GREEN |
| `state/evidence/20260928T214639-issue-19/review.txt` | none | scored S1 run (launch-6), issue-19 GREEN |
| `state/evidence/20260928T214639-issue-19/timeline.json` | none | scored S1 run (launch-6), issue-19 GREEN |
| `state/evidence/20260928T214639-issue-19/verdict.json` | none | scored S1 run (launch-6), issue-19 GREEN |
| `state/evidence/20260928T214639-issue-19/verify.json` | port x12 | scored S1 run (launch-6), issue-19 GREEN |
| `state/evidence/20260928T215353-issue-21/applied.diff` | none | scored S1 run (launch-6), issue-21 GREEN |
| `state/evidence/20260928T215353-issue-21/claimed.json` | none | scored S1 run (launch-6), issue-21 GREEN |
| `state/evidence/20260928T215353-issue-21/cost.json` | none | scored S1 run (launch-6), issue-21 GREEN |
| `state/evidence/20260928T215353-issue-21/identity.json` | none | scored S1 run (launch-6), issue-21 GREEN |
| `state/evidence/20260928T215353-issue-21/implementer_raw.txt` | none | scored S1 run (launch-6), issue-21 GREEN |
| `state/evidence/20260928T215353-issue-21/merge.json` | none | scored S1 run (launch-6), issue-21 GREEN |
| `state/evidence/20260928T215353-issue-21/mutations.json` | none | scored S1 run (launch-6), issue-21 GREEN |
| `state/evidence/20260928T215353-issue-21/review.txt` | none | scored S1 run (launch-6), issue-21 GREEN |
| `state/evidence/20260928T215353-issue-21/timeline.json` | none | scored S1 run (launch-6), issue-21 GREEN |
| `state/evidence/20260928T215353-issue-21/verdict.json` | none | scored S1 run (launch-6), issue-21 GREEN |
| `state/evidence/20260928T215353-issue-21/verify.json` | port x12 | scored S1 run (launch-6), issue-21 GREEN |
| `state/evidence/launch5-termination/interventions.jsonl` | none | SESSION_HANDOFF_2026-09-28.md (launch-5 aborted-window artifacts) |
| `state/evidence/launch5-termination/journal-tail.txt` | none | SESSION_HANDOFF_2026-09-28.md (launch-5 aborted-window artifacts) |
| `state/evidence/launch5-termination/state.json` | none | SESSION_HANDOFF_2026-09-28.md (launch-5 aborted-window artifacts) |
| `state/interventions.jsonl` | none | renamed copy of interventions.jsonl.scored-snapshot (the scored log) |
| `state/interventions.jsonl.aborted-launch1-20260928T2040` | none | disclosed aborted/test window log |
| `state/interventions.jsonl.aborted-launch1b-20260928T2052` | none | disclosed aborted/test window log |
| `state/interventions.jsonl.aborted-launch2-20260928T231047` | none | disclosed aborted/test window log |
| `state/interventions.jsonl.aborted-launch3-20260928T231256` | none | disclosed aborted/test window log |
| `state/interventions.jsonl.aborted-launch4-20260928T232704` | none | disclosed aborted/test window log |
| `state/interventions.jsonl.aborted-launch5-20260928T214305` | none | disclosed aborted/test window log |
| `state/interventions.jsonl.testpollution-20260928T223915` | none | disclosed aborted/test window log |
| `state/ntfy/receipts.json` | none | ntfy delivery receipts (active); no topic literal present |
| `state/ntfy/receipts.json.testpollution-20260928T223915` | ntfy-topic x4 | test-pollution window receipts; contained old ntfy topic (redacted) |
| `state/state.json` | none |  |

## Self-run (2026-09-29 self-hosting run) additions — 2026-09-30 refresh

Source: `~/nightshift-selfrun/` (read-only). Layout mirrors the S1 conventions, namespaced under `selfrun/` so S1's `state/` tree is untouched:

- `selfrun/state/interventions.jsonl` — the scored log (launch-3, 08:47:20Z→10:00:00Z): renamed copy of `interventions.jsonl.scored-snapshot`, byte-identical to the ROTATED scored file `interventions.jsonl.scored-launch3-20260929` (rotation 2026-09-30, disclosed in SUPERVISED_LAP_2026-09-30.md; the live log was rotated pre-lap and now carries only validation-lap rows). S1 precedent for the rename.
- `selfrun/state/interventions.jsonl.aborted-launch1-20260929T101550`, `.aborted-launch2-20260929T104222` — disclosed adjacent aborted-window logs (stale-harness checkout/truncation; false wiring-report incident), per the S1 "scored log + all aborted windows disclosed adjacent" convention.
- `selfrun/state/lap-result.json.supervised-issue1-20260929T100624` — the supervised issue-#1 validation lap's terminal (PR #7, pre-launch).
- `selfrun/state/state.json` — terminal dispositions at publication (#2–#5 merged, #6 parked retries=3); the live source was subsequently rewritten by the 2026-09-30 supervised lap (copy is the published-moment snapshot).
- `selfrun/state/evidence/20260929T*-issue-*` (16 dirs incl. supervised/aborted-suffixed) — per-lap evidence, copied verbatim; same file classes as S1's dirs.
- `selfrun/state/evidence/ntfy/receipts.json` + `ntfy.aborted-launch2-20260929T104222/receipts.json` — delivery receipts; no topic literal present (grep-verified).
- `selfrun/scenarios/issue-1..6.json` — the K1–K6 exec-kind oracles used by the run's red-recheck and verify rungs.
- Excluded (S1 precedent): `lap-*.log` (zero-byte), `lap-2.log.aborted-*` (zero-byte), `heartbeat`, `supervisor.lock`, live `lap-result.json` (superseded by the supervised variant disclosure + scored log terminal rows), `claims/` (empty at copy time).
- Leak-class inspection: every candidate file was grep-scanned for the 5 classes pre-copy; only `/home/noor/` paths (rule 5) were found — 53 occurrences across 7 files (all `~/factory-lab/nightshift/...` worktree paths in verify/verdict unit-output listings). No hostnames, loopback ports, ntfy topics, API-key values, or token shapes anywhere; the unit env listings contain NO API key and NO ntfy topic (grep-verified). Implementer/reviewer raw text is unedited model output, per S1 policy.

Inventory (all rows perl-processed; substitutions recorded per row):

| Path | Redactions applied | Citations / note |
|---|---|---|
| `selfrun/scenarios/issue-1.json` | none | SELF_AUDIT_2026-09-29.md K1-K6 oracles (exec-kind); SELF_RUN_SCORE (red-recheck/verify-green usage) |
| `selfrun/scenarios/issue-2.json` | none | SELF_AUDIT_2026-09-29.md K1-K6 oracles (exec-kind); SELF_RUN_SCORE (red-recheck/verify-green usage) |
| `selfrun/scenarios/issue-3.json` | none | SELF_AUDIT_2026-09-29.md K1-K6 oracles (exec-kind); SELF_RUN_SCORE (red-recheck/verify-green usage) |
| `selfrun/scenarios/issue-4.json` | none | SELF_AUDIT_2026-09-29.md K1-K6 oracles (exec-kind); SELF_RUN_SCORE (red-recheck/verify-green usage) |
| `selfrun/scenarios/issue-5.json` | none | SELF_AUDIT_2026-09-29.md K1-K6 oracles (exec-kind); SELF_RUN_SCORE (red-recheck/verify-green usage) |
| `selfrun/scenarios/issue-6.json` | none | SELF_AUDIT_2026-09-29.md K1-K6 oracles (exec-kind); SELF_RUN_SCORE (red-recheck/verify-green usage) |
| `selfrun/state/interventions.jsonl` | none | renamed copy of interventions.jsonl.scored-snapshot (SELF_RUN_SCORE scored log, launch-3); byte-identical to the ROTATED scored file `interventions.jsonl.scored-launch3-20260929` (rotation 2026-09-30, disclosed in SUPERVISED_LAP_2026-09-30.md; the live log was rotated pre-lap and now carries only validation-lap rows) |
| `selfrun/state/interventions.jsonl.aborted-launch1-20260929T101550` | none | disclosed adjacent aborted-window log (SELF_RUN_SCORE_2026-09-29.md; stale-harness checkout/truncation) |
| `selfrun/state/interventions.jsonl.aborted-launch2-20260929T104222` | none | disclosed adjacent aborted-window log (SELF_RUN_SCORE_2026-09-29.md; false wiring-report incident, corrected at the time) |
| `selfrun/state/lap-result.json.supervised-issue1-20260929T100624` | none | SELF_RUN_SCORE_2026-09-29.md (issue #1 supervised validation lap, PR #7) |
| `selfrun/state/state.json` | none | SELF_RUN_SCORE_2026-09-29.md (dispositions: #2-#5 merged, #6 parked) (source subsequently modified by the 2026-09-30 supervised lap; copy is the published-moment snapshot) |
| `selfrun/state/evidence/20260929T075718-issue-1.supervised-issue1-20260929T100624/applied.diff` | none | SELF_RUN_SCORE_2026-09-29.md (issue #1 supervised validation lap, PR #7) |
| `selfrun/state/evidence/20260929T075718-issue-1.supervised-issue1-20260929T100624/claimed.json` | none | SELF_RUN_SCORE_2026-09-29.md (issue #1 supervised validation lap, PR #7) |
| `selfrun/state/evidence/20260929T075718-issue-1.supervised-issue1-20260929T100624/cost.json` | none | SELF_RUN_SCORE_2026-09-29.md (issue #1 supervised validation lap, PR #7) |
| `selfrun/state/evidence/20260929T075718-issue-1.supervised-issue1-20260929T100624/implementer_raw.txt` | none | SELF_RUN_SCORE_2026-09-29.md (issue #1 supervised validation lap, PR #7) |
| `selfrun/state/evidence/20260929T075718-issue-1.supervised-issue1-20260929T100624/merge.json` | none | SELF_RUN_SCORE_2026-09-29.md (issue #1 supervised validation lap, PR #7) |
| `selfrun/state/evidence/20260929T075718-issue-1.supervised-issue1-20260929T100624/mutations.json` | none | SELF_RUN_SCORE_2026-09-29.md (issue #1 supervised validation lap, PR #7) |
| `selfrun/state/evidence/20260929T075718-issue-1.supervised-issue1-20260929T100624/review.txt` | none | SELF_RUN_SCORE_2026-09-29.md (issue #1 supervised validation lap, PR #7) |
| `selfrun/state/evidence/20260929T075718-issue-1.supervised-issue1-20260929T100624/timeline.json` | none | SELF_RUN_SCORE_2026-09-29.md (issue #1 supervised validation lap, PR #7) |
| `selfrun/state/evidence/20260929T075718-issue-1.supervised-issue1-20260929T100624/verdict.json` | none | SELF_RUN_SCORE_2026-09-29.md (issue #1 supervised validation lap, PR #7) |
| `selfrun/state/evidence/20260929T075718-issue-1.supervised-issue1-20260929T100624/verify.json` | path x7 | SELF_RUN_SCORE_2026-09-29.md (issue #1 supervised validation lap, PR #7) |
| `selfrun/state/evidence/20260929T080651-issue-2.aborted-launch1-20260929T101550/timeline.json` | none | SELF_RUN_SCORE_2026-09-29.md (disclosed adjacent aborted window) |
| `selfrun/state/evidence/20260929T082133-issue-2.aborted-launch2-20260929T104222/applied.diff` | none | SELF_RUN_SCORE_2026-09-29.md (disclosed adjacent aborted window; false wiring-report incident) |
| `selfrun/state/evidence/20260929T082133-issue-2.aborted-launch2-20260929T104222/claimed.json` | none | SELF_RUN_SCORE_2026-09-29.md (disclosed adjacent aborted window; false wiring-report incident) |
| `selfrun/state/evidence/20260929T082133-issue-2.aborted-launch2-20260929T104222/cost.json` | none | SELF_RUN_SCORE_2026-09-29.md (disclosed adjacent aborted window; false wiring-report incident) |
| `selfrun/state/evidence/20260929T082133-issue-2.aborted-launch2-20260929T104222/implementer_raw.txt` | none | SELF_RUN_SCORE_2026-09-29.md (disclosed adjacent aborted window; false wiring-report incident) |
| `selfrun/state/evidence/20260929T082133-issue-2.aborted-launch2-20260929T104222/mutations.json` | none | SELF_RUN_SCORE_2026-09-29.md (disclosed adjacent aborted window; false wiring-report incident) |
| `selfrun/state/evidence/20260929T082133-issue-2.aborted-launch2-20260929T104222/review.txt` | none | SELF_RUN_SCORE_2026-09-29.md (disclosed adjacent aborted window; false wiring-report incident) |
| `selfrun/state/evidence/20260929T082133-issue-2.aborted-launch2-20260929T104222/timeline.json` | none | SELF_RUN_SCORE_2026-09-29.md (disclosed adjacent aborted window; false wiring-report incident) |
| `selfrun/state/evidence/20260929T082133-issue-2.aborted-launch2-20260929T104222/verdict.json` | none | SELF_RUN_SCORE_2026-09-29.md (disclosed adjacent aborted window; false wiring-report incident) |
| `selfrun/state/evidence/20260929T082730-issue-2.aborted-launch2-20260929T104222/applied.diff` | none | SELF_RUN_SCORE_2026-09-29.md (disclosed adjacent aborted window; false wiring-report incident) |
| `selfrun/state/evidence/20260929T082730-issue-2.aborted-launch2-20260929T104222/claimed.json` | none | SELF_RUN_SCORE_2026-09-29.md (disclosed adjacent aborted window; false wiring-report incident) |
| `selfrun/state/evidence/20260929T082730-issue-2.aborted-launch2-20260929T104222/cost.json` | none | SELF_RUN_SCORE_2026-09-29.md (disclosed adjacent aborted window; false wiring-report incident) |
| `selfrun/state/evidence/20260929T082730-issue-2.aborted-launch2-20260929T104222/implementer_raw.txt` | none | SELF_RUN_SCORE_2026-09-29.md (disclosed adjacent aborted window; false wiring-report incident) |
| `selfrun/state/evidence/20260929T082730-issue-2.aborted-launch2-20260929T104222/mutations.json` | none | SELF_RUN_SCORE_2026-09-29.md (disclosed adjacent aborted window; false wiring-report incident) |
| `selfrun/state/evidence/20260929T082730-issue-2.aborted-launch2-20260929T104222/timeline.json` | none | SELF_RUN_SCORE_2026-09-29.md (disclosed adjacent aborted window; false wiring-report incident) |
| `selfrun/state/evidence/20260929T084729-issue-2/applied.diff` | none | SELF_RUN_SCORE_2026-09-29.md per-lap/per-issue rows (see its cost table & gate-sequence table) |
| `selfrun/state/evidence/20260929T084729-issue-2/claimed.json` | none | SELF_RUN_SCORE_2026-09-29.md per-lap/per-issue rows (see its cost table & gate-sequence table) |
| `selfrun/state/evidence/20260929T084729-issue-2/cost.json` | none | SELF_RUN_SCORE_2026-09-29.md per-lap/per-issue rows (see its cost table & gate-sequence table) |
| `selfrun/state/evidence/20260929T084729-issue-2/implementer_raw.txt` | none | SELF_RUN_SCORE_2026-09-29.md per-lap/per-issue rows (see its cost table & gate-sequence table) |
| `selfrun/state/evidence/20260929T084729-issue-2/mutations.json` | none | SELF_RUN_SCORE_2026-09-29.md per-lap/per-issue rows (see its cost table & gate-sequence table) |
| `selfrun/state/evidence/20260929T084729-issue-2/review.txt` | none | SELF_RUN_SCORE_2026-09-29.md per-lap/per-issue rows (see its cost table & gate-sequence table) |
| `selfrun/state/evidence/20260929T084729-issue-2/timeline.json` | none | SELF_RUN_SCORE_2026-09-29.md per-lap/per-issue rows (see its cost table & gate-sequence table) |
| `selfrun/state/evidence/20260929T084729-issue-2/verdict.json` | path x9 | SELF_RUN_SCORE_2026-09-29.md per-lap/per-issue rows (see its cost table & gate-sequence table) |
| `selfrun/state/evidence/20260929T084729-issue-2/verify.json` | path x9 | SELF_RUN_SCORE_2026-09-29.md per-lap/per-issue rows (see its cost table & gate-sequence table) |
| `selfrun/state/evidence/20260929T085540-issue-2/applied.diff` | none | SELF_RUN_SCORE_2026-09-29.md per-lap/per-issue rows (see its cost table & gate-sequence table) |
| `selfrun/state/evidence/20260929T085540-issue-2/claimed.json` | none | SELF_RUN_SCORE_2026-09-29.md per-lap/per-issue rows (see its cost table & gate-sequence table) |
| `selfrun/state/evidence/20260929T085540-issue-2/cost.json` | none | SELF_RUN_SCORE_2026-09-29.md per-lap/per-issue rows (see its cost table & gate-sequence table) |
| `selfrun/state/evidence/20260929T085540-issue-2/implementer_raw.txt` | none | SELF_RUN_SCORE_2026-09-29.md per-lap/per-issue rows (see its cost table & gate-sequence table) |
| `selfrun/state/evidence/20260929T085540-issue-2/merge.json` | none | SELF_RUN_SCORE_2026-09-29.md per-lap/per-issue rows (see its cost table & gate-sequence table) |
| `selfrun/state/evidence/20260929T085540-issue-2/mutations.json` | none | SELF_RUN_SCORE_2026-09-29.md per-lap/per-issue rows (see its cost table & gate-sequence table) |
| `selfrun/state/evidence/20260929T085540-issue-2/review.txt` | none | SELF_RUN_SCORE_2026-09-29.md per-lap/per-issue rows (see its cost table & gate-sequence table) |
| `selfrun/state/evidence/20260929T085540-issue-2/timeline.json` | none | SELF_RUN_SCORE_2026-09-29.md per-lap/per-issue rows (see its cost table & gate-sequence table) |
| `selfrun/state/evidence/20260929T085540-issue-2/verdict.json` | none | SELF_RUN_SCORE_2026-09-29.md per-lap/per-issue rows (see its cost table & gate-sequence table) |
| `selfrun/state/evidence/20260929T085540-issue-2/verify.json` | path x7 | SELF_RUN_SCORE_2026-09-29.md per-lap/per-issue rows (see its cost table & gate-sequence table) |
| `selfrun/state/evidence/20260929T090652-issue-3/applied.diff` | none | SELF_RUN_SCORE_2026-09-29.md per-lap/per-issue rows (see its cost table & gate-sequence table) |
| `selfrun/state/evidence/20260929T090652-issue-3/claimed.json` | none | SELF_RUN_SCORE_2026-09-29.md per-lap/per-issue rows (see its cost table & gate-sequence table) |
| `selfrun/state/evidence/20260929T090652-issue-3/cost.json` | none | SELF_RUN_SCORE_2026-09-29.md per-lap/per-issue rows (see its cost table & gate-sequence table) |
| `selfrun/state/evidence/20260929T090652-issue-3/implementer_raw.txt` | none | SELF_RUN_SCORE_2026-09-29.md per-lap/per-issue rows (see its cost table & gate-sequence table) |
| `selfrun/state/evidence/20260929T090652-issue-3/mutations.json` | none | SELF_RUN_SCORE_2026-09-29.md per-lap/per-issue rows (see its cost table & gate-sequence table) |
| `selfrun/state/evidence/20260929T090652-issue-3/review.txt` | none | SELF_RUN_SCORE_2026-09-29.md per-lap/per-issue rows (see its cost table & gate-sequence table) |
| `selfrun/state/evidence/20260929T090652-issue-3/timeline.json` | none | SELF_RUN_SCORE_2026-09-29.md per-lap/per-issue rows (see its cost table & gate-sequence table) |
| `selfrun/state/evidence/20260929T090652-issue-3/verdict.json` | none | SELF_RUN_SCORE_2026-09-29.md per-lap/per-issue rows (see its cost table & gate-sequence table) |
| `selfrun/state/evidence/20260929T091503-issue-3/applied.diff` | none | SELF_RUN_SCORE_2026-09-29.md per-lap/per-issue rows (see its cost table & gate-sequence table) |
| `selfrun/state/evidence/20260929T091503-issue-3/claimed.json` | none | SELF_RUN_SCORE_2026-09-29.md per-lap/per-issue rows (see its cost table & gate-sequence table) |
| `selfrun/state/evidence/20260929T091503-issue-3/cost.json` | none | SELF_RUN_SCORE_2026-09-29.md per-lap/per-issue rows (see its cost table & gate-sequence table) |
| `selfrun/state/evidence/20260929T091503-issue-3/implementer_raw.txt` | none | SELF_RUN_SCORE_2026-09-29.md per-lap/per-issue rows (see its cost table & gate-sequence table) |
| `selfrun/state/evidence/20260929T091503-issue-3/merge.json` | none | SELF_RUN_SCORE_2026-09-29.md per-lap/per-issue rows (see its cost table & gate-sequence table) |
| `selfrun/state/evidence/20260929T091503-issue-3/mutations.json` | none | SELF_RUN_SCORE_2026-09-29.md per-lap/per-issue rows (see its cost table & gate-sequence table) |
| `selfrun/state/evidence/20260929T091503-issue-3/review.txt` | none | SELF_RUN_SCORE_2026-09-29.md per-lap/per-issue rows (see its cost table & gate-sequence table) |
| `selfrun/state/evidence/20260929T091503-issue-3/timeline.json` | none | SELF_RUN_SCORE_2026-09-29.md per-lap/per-issue rows (see its cost table & gate-sequence table) |
| `selfrun/state/evidence/20260929T091503-issue-3/verdict.json` | none | SELF_RUN_SCORE_2026-09-29.md per-lap/per-issue rows (see its cost table & gate-sequence table) |
| `selfrun/state/evidence/20260929T091503-issue-3/verify.json` | path x7 | SELF_RUN_SCORE_2026-09-29.md per-lap/per-issue rows (see its cost table & gate-sequence table) |
| `selfrun/state/evidence/20260929T092544-issue-4/claimed.json` | none | SELF_RUN_SCORE_2026-09-29.md per-lap/per-issue rows (see its cost table & gate-sequence table) |
| `selfrun/state/evidence/20260929T092544-issue-4/cost.json` | none | SELF_RUN_SCORE_2026-09-29.md per-lap/per-issue rows (see its cost table & gate-sequence table) |
| `selfrun/state/evidence/20260929T092544-issue-4/implementer_raw.txt` | none | SELF_RUN_SCORE_2026-09-29.md per-lap/per-issue rows (see its cost table & gate-sequence table) |
| `selfrun/state/evidence/20260929T092544-issue-4/mutations.json` | none | SELF_RUN_SCORE_2026-09-29.md per-lap/per-issue rows (see its cost table & gate-sequence table) |
| `selfrun/state/evidence/20260929T092544-issue-4/timeline.json` | none | SELF_RUN_SCORE_2026-09-29.md per-lap/per-issue rows (see its cost table & gate-sequence table) |
| `selfrun/state/evidence/20260929T092544-issue-4/verdict.json` | none | SELF_RUN_SCORE_2026-09-29.md per-lap/per-issue rows (see its cost table & gate-sequence table) |
| `selfrun/state/evidence/20260929T093416-issue-4/applied.diff` | none | SELF_RUN_SCORE_2026-09-29.md per-lap/per-issue rows (see its cost table & gate-sequence table) |
| `selfrun/state/evidence/20260929T093416-issue-4/claimed.json` | none | SELF_RUN_SCORE_2026-09-29.md per-lap/per-issue rows (see its cost table & gate-sequence table) |
| `selfrun/state/evidence/20260929T093416-issue-4/cost.json` | none | SELF_RUN_SCORE_2026-09-29.md per-lap/per-issue rows (see its cost table & gate-sequence table) |
| `selfrun/state/evidence/20260929T093416-issue-4/implementer_raw.txt` | none | SELF_RUN_SCORE_2026-09-29.md per-lap/per-issue rows (see its cost table & gate-sequence table) |
| `selfrun/state/evidence/20260929T093416-issue-4/merge.json` | none | SELF_RUN_SCORE_2026-09-29.md per-lap/per-issue rows (see its cost table & gate-sequence table) |
| `selfrun/state/evidence/20260929T093416-issue-4/mutations.json` | none | SELF_RUN_SCORE_2026-09-29.md per-lap/per-issue rows (see its cost table & gate-sequence table) |
| `selfrun/state/evidence/20260929T093416-issue-4/review.txt` | none | SELF_RUN_SCORE_2026-09-29.md per-lap/per-issue rows (see its cost table & gate-sequence table) |
| `selfrun/state/evidence/20260929T093416-issue-4/timeline.json` | none | SELF_RUN_SCORE_2026-09-29.md per-lap/per-issue rows (see its cost table & gate-sequence table) |
| `selfrun/state/evidence/20260929T093416-issue-4/verdict.json` | none | SELF_RUN_SCORE_2026-09-29.md per-lap/per-issue rows (see its cost table & gate-sequence table) |
| `selfrun/state/evidence/20260929T093416-issue-4/verify.json` | path x7 | SELF_RUN_SCORE_2026-09-29.md per-lap/per-issue rows (see its cost table & gate-sequence table) |
| `selfrun/state/evidence/20260929T093823-issue-5/applied.diff` | none | SELF_RUN_SCORE_2026-09-29.md per-lap/per-issue rows (see its cost table & gate-sequence table) |
| `selfrun/state/evidence/20260929T093823-issue-5/claimed.json` | none | SELF_RUN_SCORE_2026-09-29.md per-lap/per-issue rows (see its cost table & gate-sequence table) |
| `selfrun/state/evidence/20260929T093823-issue-5/cost.json` | none | SELF_RUN_SCORE_2026-09-29.md per-lap/per-issue rows (see its cost table & gate-sequence table) |
| `selfrun/state/evidence/20260929T093823-issue-5/implementer_raw.txt` | none | SELF_RUN_SCORE_2026-09-29.md per-lap/per-issue rows (see its cost table & gate-sequence table) |
| `selfrun/state/evidence/20260929T093823-issue-5/merge.json` | none | SELF_RUN_SCORE_2026-09-29.md per-lap/per-issue rows (see its cost table & gate-sequence table) |
| `selfrun/state/evidence/20260929T093823-issue-5/mutations.json` | none | SELF_RUN_SCORE_2026-09-29.md per-lap/per-issue rows (see its cost table & gate-sequence table) |
| `selfrun/state/evidence/20260929T093823-issue-5/review.txt` | none | SELF_RUN_SCORE_2026-09-29.md per-lap/per-issue rows (see its cost table & gate-sequence table) |
| `selfrun/state/evidence/20260929T093823-issue-5/timeline.json` | none | SELF_RUN_SCORE_2026-09-29.md per-lap/per-issue rows (see its cost table & gate-sequence table) |
| `selfrun/state/evidence/20260929T093823-issue-5/verdict.json` | none | SELF_RUN_SCORE_2026-09-29.md per-lap/per-issue rows (see its cost table & gate-sequence table) |
| `selfrun/state/evidence/20260929T093823-issue-5/verify.json` | path x7 | SELF_RUN_SCORE_2026-09-29.md per-lap/per-issue rows (see its cost table & gate-sequence table) |
| `selfrun/state/evidence/20260929T094229-issue-6/claimed.json` | none | SELF_RUN_SCORE_2026-09-29.md per-lap/per-issue rows (see its cost table & gate-sequence table) |
| `selfrun/state/evidence/20260929T094229-issue-6/cost.json` | none | SELF_RUN_SCORE_2026-09-29.md per-lap/per-issue rows (see its cost table & gate-sequence table) |
| `selfrun/state/evidence/20260929T094229-issue-6/implementer_raw.txt` | none | SELF_RUN_SCORE_2026-09-29.md per-lap/per-issue rows (see its cost table & gate-sequence table) |
| `selfrun/state/evidence/20260929T094229-issue-6/mutations.json` | none | SELF_RUN_SCORE_2026-09-29.md per-lap/per-issue rows (see its cost table & gate-sequence table) |
| `selfrun/state/evidence/20260929T094229-issue-6/timeline.json` | none | SELF_RUN_SCORE_2026-09-29.md per-lap/per-issue rows (see its cost table & gate-sequence table) |
| `selfrun/state/evidence/20260929T094229-issue-6/verdict.json` | none | SELF_RUN_SCORE_2026-09-29.md per-lap/per-issue rows (see its cost table & gate-sequence table) |
| `selfrun/state/evidence/20260929T094921-issue-6/claimed.json` | none | SELF_RUN_SCORE_2026-09-29.md per-lap/per-issue rows (see its cost table & gate-sequence table) |
| `selfrun/state/evidence/20260929T094921-issue-6/cost.json` | none | SELF_RUN_SCORE_2026-09-29.md per-lap/per-issue rows (see its cost table & gate-sequence table) |
| `selfrun/state/evidence/20260929T094921-issue-6/implementer_raw.txt` | none | SELF_RUN_SCORE_2026-09-29.md per-lap/per-issue rows (see its cost table & gate-sequence table) |
| `selfrun/state/evidence/20260929T094921-issue-6/mutations.json` | none | SELF_RUN_SCORE_2026-09-29.md per-lap/per-issue rows (see its cost table & gate-sequence table) |
| `selfrun/state/evidence/20260929T094921-issue-6/timeline.json` | none | SELF_RUN_SCORE_2026-09-29.md per-lap/per-issue rows (see its cost table & gate-sequence table) |
| `selfrun/state/evidence/20260929T094921-issue-6/verdict.json` | none | SELF_RUN_SCORE_2026-09-29.md per-lap/per-issue rows (see its cost table & gate-sequence table) |
| `selfrun/state/evidence/20260929T095508-issue-6/claimed.json` | none | SELF_RUN_SCORE_2026-09-29.md per-lap/per-issue rows (see its cost table & gate-sequence table) |
| `selfrun/state/evidence/20260929T095508-issue-6/cost.json` | none | SELF_RUN_SCORE_2026-09-29.md per-lap/per-issue rows (see its cost table & gate-sequence table) |
| `selfrun/state/evidence/20260929T095508-issue-6/implementer_raw.txt` | none | SELF_RUN_SCORE_2026-09-29.md per-lap/per-issue rows (see its cost table & gate-sequence table) |
| `selfrun/state/evidence/20260929T095508-issue-6/mutations.json` | none | SELF_RUN_SCORE_2026-09-29.md per-lap/per-issue rows (see its cost table & gate-sequence table) |
| `selfrun/state/evidence/20260929T095508-issue-6/timeline.json` | none | SELF_RUN_SCORE_2026-09-29.md per-lap/per-issue rows (see its cost table & gate-sequence table) |
| `selfrun/state/evidence/20260929T095508-issue-6/verdict.json` | none | SELF_RUN_SCORE_2026-09-29.md per-lap/per-issue rows (see its cost table & gate-sequence table) |
| `selfrun/state/evidence/ntfy/receipts.json` | none | ntfy delivery receipts; no topic literal present |
| `selfrun/state/evidence/ntfy.aborted-launch2-20260929T104222/receipts.json` | none | SELF_RUN_SCORE_2026-09-29.md (disclosed adjacent aborted window; false wiring-report incident) |

## Dogfood run (2026-09-30) additions — 2026-09-30 publication

Source: `~/nightshift-dogfood/` (read-only). Layout mirrors the selfrun/ conventions, namespaced under `dogfood/`:

- `docs/DOGFOOD_SCORE_2026-09-30.md` — the dogfood run's formal score (run window 2026-09-30T05:13:53Z→05:56:45Z, deployment clone f41cadd-era; 2 merged PRs #15/#16, 2 parked, $0.006457, zero undisclosed operator actions).
- `docs/DECISIONS.md` — operator-disclosure record (F3); the score's zero-intervention basis cites its two 2026-09-30 topic-rotation disclosures.
- `dogfood/state/interventions.jsonl` — the scored log (36 rows, window 05:13:53Z→05:56:45Z), copied verbatim (live log, not a rotated snapshot — the run is drained/halted).
- `dogfood/state/state.json` — terminal dispositions (#12/#13 merged, #6/#14 parked retries=3).
- `dogfood/state/evidence/20260930T*-issue-*` (8 dirs) — per-lap evidence incl. the restart-killed #14 a1 dir (timeline only); same file classes as S1/selfrun dirs.
- `dogfood/state/evidence/ntfy/receipts.json` — delivery receipts (9 rows, all HTTP 200); no topic literal present (grep-verified).
- `dogfood/scenarios/issue-{6,12,13,14}.json` — the oracles served from the deployment's own `scenarios-dogfood/` dir.
- Excluded (S1/selfrun precedent): `lap-*.log` (zero-byte), `heartbeat`, `supervisor.lock`, live `lap-result.json` (terminal row superseded by the scored log's row 36), `claims/` (empty at copy time).
- Leak-class inspection: every candidate file grep-scanned pre-copy; only `/home/noor/` paths (rule 5) found (verify.json unit-output listings). No hostnames, loopback ports, ntfy topics, API-key values, or token shapes in the dogfood sources; the score doc + DECISIONS.md were verified literal-clean pre-copy.

Inventory (all rows perl-processed; substitutions recorded per row):

| Path | Redactions applied | Citations / note |
|---|---|---|
| `docs/DOGFOOD_SCORE_2026-09-30.md` | none | dogfood run score (run window 2026-09-30T05:13:53Z→05:56:45Z, deployment clone f41cadd-era); leak-clean, perl no-op |
| `docs/DECISIONS.md` | none | operator-disclosure record (F3); DOGFOOD_SCORE zero-intervention basis; leak-clean, perl no-op |
| `dogfood/scenarios/issue-6.json` | none | DOGFOOD_SCORE_2026-09-30.md (dogfood oracle, red-recheck usage) |
| `dogfood/scenarios/issue-12.json` | none | DOGFOOD_SCORE_2026-09-30.md (oracle `close-failure-not-crash`, K12-RED-GREEN) |
| `dogfood/scenarios/issue-13.json` | none | DOGFOOD_SCORE_2026-09-30.md (oracle `reap-attributes-issue`, K13-RED-GREEN) |
| `dogfood/scenarios/issue-14.json` | none | DOGFOOD_SCORE_2026-09-30.md (dogfood oracle, red-recheck usage) |
| `dogfood/state/interventions.jsonl` | none | DOGFOOD_SCORE_2026-09-30.md scored log (36 rows, 05:13:53Z→05:56:45Z) |
| `dogfood/state/state.json` | none | DOGFOOD_SCORE_2026-09-30.md (dispositions: #12/#13 merged, #6/#14 parked) |
| `dogfood/state/evidence/20260930T051402-issue-6/claimed.json` | none | DOGFOOD_SCORE_2026-09-30.md (#6 a1 killed at mutation-apply; transcription-defect occurrence 5) |
| `dogfood/state/evidence/20260930T051402-issue-6/cost.json` | none | DOGFOOD_SCORE_2026-09-30.md per-lap cost table |
| `dogfood/state/evidence/20260930T051402-issue-6/implementer_raw.txt` | none | DOGFOOD_SCORE_2026-09-30.md per-issue rows |
| `dogfood/state/evidence/20260930T051402-issue-6/mutations.json` | none | DOGFOOD_SCORE_2026-09-30.md per-issue rows |
| `dogfood/state/evidence/20260930T051402-issue-6/timeline.json` | none | DOGFOOD_SCORE_2026-09-30.md per-issue rows |
| `dogfood/state/evidence/20260930T051402-issue-6/verdict.json` | none | DOGFOOD_SCORE_2026-09-30.md per-issue rows |
| `dogfood/state/evidence/20260930T052139-issue-6/applied.diff` | none | DOGFOOD_SCORE_2026-09-30.md (#6 a2 killed at review — no parseable verdict) |
| `dogfood/state/evidence/20260930T052139-issue-6/claimed.json` | none | DOGFOOD_SCORE_2026-09-30.md per-issue rows |
| `dogfood/state/evidence/20260930T052139-issue-6/cost.json` | none | DOGFOOD_SCORE_2026-09-30.md (reviewer 4096-token cap) |
| `dogfood/state/evidence/20260930T052139-issue-6/implementer_raw.txt` | none | DOGFOOD_SCORE_2026-09-30.md per-issue rows |
| `dogfood/state/evidence/20260930T052139-issue-6/mutations.json` | none | DOGFOOD_SCORE_2026-09-30.md per-issue rows |
| `dogfood/state/evidence/20260930T052139-issue-6/review.txt` | none | DOGFOOD_SCORE_2026-09-30.md per-issue rows |
| `dogfood/state/evidence/20260930T052139-issue-6/timeline.json` | none | DOGFOOD_SCORE_2026-09-30.md per-issue rows |
| `dogfood/state/evidence/20260930T052139-issue-6/verdict.json` | none | DOGFOOD_SCORE_2026-09-30.md dated corrections (#6 review taxonomy) |
| `dogfood/state/evidence/20260930T052749-issue-6/applied.diff` | none | DOGFOOD_SCORE_2026-09-30.md (#6 a3 killed at review → PARK) |
| `dogfood/state/evidence/20260930T052749-issue-6/claimed.json` | none | DOGFOOD_SCORE_2026-09-30.md per-issue rows |
| `dogfood/state/evidence/20260930T052749-issue-6/cost.json` | none | DOGFOOD_SCORE_2026-09-30.md (reviewer 4096-token cap) |
| `dogfood/state/evidence/20260930T052749-issue-6/implementer_raw.txt` | none | DOGFOOD_SCORE_2026-09-30.md per-issue rows |
| `dogfood/state/evidence/20260930T052749-issue-6/mutations.json` | none | DOGFOOD_SCORE_2026-09-30.md per-issue rows |
| `dogfood/state/evidence/20260930T052749-issue-6/review.txt` | none | DOGFOOD_SCORE_2026-09-30.md (truncated body carries the fake-gh double-escaping analysis) |
| `dogfood/state/evidence/20260930T052749-issue-6/timeline.json` | none | DOGFOOD_SCORE_2026-09-30.md per-issue rows |
| `dogfood/state/evidence/20260930T052749-issue-6/verdict.json` | none | DOGFOOD_SCORE_2026-09-30.md dated corrections (#6 review taxonomy) |
| `dogfood/state/evidence/20260930T053226-issue-12/applied.diff` | none | DOGFOOD_SCORE_2026-09-30.md (#12 merged first attempt, PR #15 397717e7) |
| `dogfood/state/evidence/20260930T053226-issue-12/claimed.json` | none | DOGFOOD_SCORE_2026-09-30.md per-issue rows |
| `dogfood/state/evidence/20260930T053226-issue-12/cost.json` | none | DOGFOOD_SCORE_2026-09-30.md per-lap cost table |
| `dogfood/state/evidence/20260930T053226-issue-12/implementer_raw.txt` | none | DOGFOOD_SCORE_2026-09-30.md per-issue rows |
| `dogfood/state/evidence/20260930T053226-issue-12/merge.json` | none | DOGFOOD_SCORE_2026-09-30.md (PR #15) |
| `dogfood/state/evidence/20260930T053226-issue-12/mutations.json` | none | DOGFOOD_SCORE_2026-09-30.md per-issue rows |
| `dogfood/state/evidence/20260930T053226-issue-12/review.txt` | none | DOGFOOD_SCORE_2026-09-30.md per-issue rows |
| `dogfood/state/evidence/20260930T053226-issue-12/timeline.json` | none | DOGFOOD_SCORE_2026-09-30.md per-issue rows |
| `dogfood/state/evidence/20260930T053226-issue-12/verdict.json` | none | DOGFOOD_SCORE_2026-09-30.md per-issue rows |
| `dogfood/state/evidence/20260930T053226-issue-12/verify.json` | path x7 | DOGFOOD_SCORE_2026-09-30.md (oracle `close-failure-not-crash`, K12-RED-GREEN) |
| `dogfood/state/evidence/20260930T053953-issue-13/applied.diff` | none | DOGFOOD_SCORE_2026-09-30.md (#13 merged, restart-reconciled, PR #16 1404d6f5) |
| `dogfood/state/evidence/20260930T053953-issue-13/claimed.json` | none | DOGFOOD_SCORE_2026-09-30.md per-issue rows |
| `dogfood/state/evidence/20260930T053953-issue-13/cost.json` | none | DOGFOOD_SCORE_2026-09-30.md per-lap cost table |
| `dogfood/state/evidence/20260930T053953-issue-13/implementer_raw.txt` | none | DOGFOOD_SCORE_2026-09-30.md per-issue rows |
| `dogfood/state/evidence/20260930T053953-issue-13/merge.json` | none | DOGFOOD_SCORE_2026-09-30.md (PR #16) |
| `dogfood/state/evidence/20260930T053953-issue-13/mutations.json` | none | DOGFOOD_SCORE_2026-09-30.md per-issue rows |
| `dogfood/state/evidence/20260930T053953-issue-13/review.txt` | none | DOGFOOD_SCORE_2026-09-30.md per-issue rows |
| `dogfood/state/evidence/20260930T053953-issue-13/timeline.json` | none | DOGFOOD_SCORE_2026-09-30.md dated corrections (#13 restart account; last event 05:41:00Z) |
| `dogfood/state/evidence/20260930T053953-issue-13/verdict.json` | none | DOGFOOD_SCORE_2026-09-30.md per-issue rows |
| `dogfood/state/evidence/20260930T053953-issue-13/verify.json` | path x7 | DOGFOOD_SCORE_2026-09-30.md (oracle `reap-attributes-issue`, K13-RED-GREEN) |
| `dogfood/state/evidence/20260930T054408-issue-14/timeline.json` | none | DOGFOOD_SCORE_2026-09-30.md (#14 a1 restart-killed in flight; dir holds only lap-start + claimed) |
| `dogfood/state/evidence/20260930T054635-issue-14/applied.diff` | none | DOGFOOD_SCORE_2026-09-30.md (#14 a2 killed at review — substantive reject) |
| `dogfood/state/evidence/20260930T054635-issue-14/claimed.json` | none | DOGFOOD_SCORE_2026-09-30.md per-issue rows |
| `dogfood/state/evidence/20260930T054635-issue-14/cost.json` | none | DOGFOOD_SCORE_2026-09-30.md per-lap cost table |
| `dogfood/state/evidence/20260930T054635-issue-14/implementer_raw.txt` | none | DOGFOOD_SCORE_2026-09-30.md per-issue rows |
| `dogfood/state/evidence/20260930T054635-issue-14/mutations.json` | none | DOGFOOD_SCORE_2026-09-30.md per-issue rows |
| `dogfood/state/evidence/20260930T054635-issue-14/review.txt` | none | DOGFOOD_SCORE_2026-09-30.md (criterion-4 regression test absent) |
| `dogfood/state/evidence/20260930T054635-issue-14/timeline.json` | none | DOGFOOD_SCORE_2026-09-30.md per-issue rows |
| `dogfood/state/evidence/20260930T054635-issue-14/verdict.json` | none | DOGFOOD_SCORE_2026-09-30.md per-issue rows |
| `dogfood/state/evidence/20260930T055134-issue-14/applied.diff` | none | DOGFOOD_SCORE_2026-09-30.md (#14 a3 killed at review → PARK) |
| `dogfood/state/evidence/20260930T055134-issue-14/claimed.json` | none | DOGFOOD_SCORE_2026-09-30.md per-issue rows |
| `dogfood/state/evidence/20260930T055134-issue-14/cost.json` | none | DOGFOOD_SCORE_2026-09-30.md per-lap cost table |
| `dogfood/state/evidence/20260930T055134-issue-14/implementer_raw.txt` | none | DOGFOOD_SCORE_2026-09-30.md per-issue rows |
| `dogfood/state/evidence/20260930T055134-issue-14/mutations.json` | none | DOGFOOD_SCORE_2026-09-30.md per-issue rows |
| `dogfood/state/evidence/20260930T055134-issue-14/review.txt` | none | DOGFOOD_SCORE_2026-09-30.md (same criterion-4 reject) |
| `dogfood/state/evidence/20260930T055134-issue-14/timeline.json` | none | DOGFOOD_SCORE_2026-09-30.md per-issue rows |
| `dogfood/state/evidence/20260930T055134-issue-14/verdict.json` | none | DOGFOOD_SCORE_2026-09-30.md per-issue rows |
| `dogfood/state/evidence/ntfy/receipts.json` | none | ntfy delivery receipts (9 rows, all HTTP 200); no topic literal present (grep-verified) |

## Verification block (rerun over the COPY TREE, excluding MANIFEST.md itself)
The manifest necessarily names the redaction patterns (host, old ntfy topic, `/home/noor/`) to document the rules, so it is excluded from its own verification greps. Actual results from the final pass (2026-09-30, whole corpus incl. self-run + dogfood additions; prior passes had identical zeros):

```
cd ~/repos/factory-docs-publication
grep -rInE '\bnixlab\b|\.latif\.se' . --exclude=MANIFEST.md | wc -l   # 0
grep -rInE '127\.0\.0\.1:[0-9]+' . --exclude=MANIFEST.md | wc -l     # 0
grep -rInE 'nightshift-[0-9a-f]{16}' . --exclude=MANIFEST.md | wc -l    # 0
grep -rIn '/home/noor/' . --exclude=MANIFEST.md | wc -l                  # 0
grep -rInE 'SURPLUS_INTELLIGENCE_API_KEY[[:space:]]*[=:][[:space:]]*[A-Za-z0-9"\'_-]{8,}' . --exclude=MANIFEST.md | wc -l   # 0
grep -rInE '(sk-[A-Za-z0-9]{20,}|eyJ[A-Za-z0-9_-]{20,}|Bearer[[:space:]]+[A-Za-z0-9._-]{20,})' . --exclude=MANIFEST.md | wc -l   # 0
find . -type f | wc -l                                                   # 382 (381 corpus + this manifest)
```

Note 2026-09-30 (dated correction): the `find . -type f | wc -l` figure of 382 above is the 2026-09-29 packaging-time count retained as the historical record; the 2026-09-30 dogfood publication raised the staged corpus to 450 files (449 + this manifest). The 2026-09-30 pre-push gate ran the amended pattern greps over the whole staged corpus INCLUDING this manifest (topic/nixlab/latif.se/port//home/noor//key-value/token-shapes: 0 corpus-file hits; MANIFEST rule-doc regex literals non-matching by construction).

Whitelisted, expected non-zero: bare `127.0.0.1` loopback literal (without a port), and the env-var NAME `SURPLUS_INTELLIGENCE_API_KEY` (5 files reference the name only, never a value).
Amended standing rule (2026-09-30, DECISIONS.md): pre-push leak gates run by PATTERN over the whole staged corpus INCLUDING MANIFEST.md (the rule-doc regex literals above are non-matching by construction); the historical greps above are retained as the packaging-time record.

## Publish command (owner runs; NOT executed by packaging)

Repo checkout: `~/nightshift` → `github.com/noor-latif/nightshift`, branch `main`.

```
rsync -a ~/repos/factory-docs-publication/ ~/nightshift/docs/evidence/ && \
cd ~/nightshift && \
git add docs/evidence && \
git commit -m "S1 + self-run evidence corpus (redacted, see docs/evidence/MANIFEST.md)" && \
git push origin main
```

2026-09-30 dogfood publication: rsync staged → `docs/evidence/` per pipeline; jj commit from the canonical jj-colocated repo, `jj git push --bookmark main`.
