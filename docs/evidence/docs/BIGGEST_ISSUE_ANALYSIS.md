# BIGGEST_ISSUE_ANALYSIS — nightshift factory-spike, the dominant failure and the fix path

2026-09-28 · Author: biggest-issue subagent · Evidence: local corpus `~/nightshift/state/`
(byte-verified copy of [redacted-host], HEAD 558eb0a), rig `~/factory-lab/toy-product` (HEAD 9045492e),
`~/repos/factory-docs/` reports, `~/repos/factory-docs/CLONE_SURVEY_2026-09-26.md`, `~/repos/reference/openrig`
(Apache-2.0, cloned this session), both OpenRig blog posts, `REPO_UPDATES_DIGEST.md`.
No production code was changed.

## 1. Verdict on the claim: the diff-artifact contract IS the biggest issue — confirmed

**Tally of every judged model attempt, Days 2–5** (runs where the implementer's output was
evaluated by a gate; transport crashes and pre-model crashes excluded):

| Day | Runs judged | Diff-artifact failures | Model-reasoning (valid diff, wrong work) | Greens |
|---|---|---|---|---|
| 2 (deepseek, #6) | 3 | 2 (no diff: narrated bash, DSML leak — L-005) | 1 (test-only diff, review reject)† | 0 |
| 3 (glm, #7) | 2 | 2 (miscounted hunks, fake banners/index — DAY3_REPORT run table) | 0 | 0 |
| 4 (glm, #9/#10) | 4 genuine | 3 (header-less new-file sections, L-008; DAY4 corrected tally) | 1 (153114 verify-fail) | 0 |
| 5 (luna, #10/#12) | 5 genuine (4× #10: 203657/205312/210631/211313; 1× #12: 212615) | 4 (unclassified per Day-5 replay: fabricated adjacency, hunk-count corruption) | 0 | 2 (#13; #12 — refactor-lap green) |
| **Total** | **14** | **11 (79%)** | **2 (14%)** | **2** |

- 11 of 14 judged failures (79%) are the model failing to produce an *applicable* artifact —
  across three model families (deepseek-v4.1-flash, glm-5.3-flash, gpt-6-luna) and three distinct
  sub-classes (no artifact, hunk-arithmetic corruption, fabricated adjacency). DAY3_REPORT
  "The bottleneck, sharpened" isolated the interface, not model competence; Day 5 with a
  stronger model moved the failure sub-class (structure → adjacency) without reducing the rate
  (DAY5_REPORT luna table: 4/5 judged attempts on genuine work were diff-apply failures —
  212214 excluded as a refactor lap on an issue already satisfied by PR #15 mid-incident;
  the 4 failures are unclassified, root cause not established).
- Issue #10 parked solely on this class (4 genuine diff-apply strikes, DAY5 per-issue table);
  #7 (Day 3) parked 100% on it; #6 (Day 2) parked 2 of 3 on it — its third attempt was the
  review-gate false reject, not an artifact failure.
**† Correction (2026-09-29, post-dating the classification above):** Day-2 run 101308
  ("test-only diff, review reject") was itself a FALSE REJECT of the old diff-only reviewer
  prompt — every recorded revision of toy-product's app.py already served the JSON 404 body
  since d538552, so #6's criteria were satisfiable by the base and the reviewer's replayed
  accept was correct given the input (REVIEWER_DISCRIMINATION_REPORT.md, R4a calibration
  note; corroborated by DAY2_REPORT.md:58, "was nearly right — 404+JSON exists"). The same
  gate defect was remediated 2026-09-28. This row was classified as a model-reasoning
  success story ("the system working as designed") before that discovery; the
  classification stands as written at time of writing but is superseded: it is an
  instrument-failure false reject, not model reasoning. The 79% headline and the 11/14
  numerator are UNCHANGED — 101308 sits in the 2/14 model-reasoning bucket, not the
  numerator, so this correction moves no headline number.
- Zero false greens in ~24 runs (S2 intact, DAY5 S-score table) — the gates catch everything;
  the artifact contract is the **throughput ceiling**, not an integrity hole. (The one
  integrity hole in this class — git apply silently dropping header-less sections while
  exiting 0 — was found and closed Day 4, L-008, fix df0d5a1d.)

1. **Diff-artifact contract** (this doc's subject). 11/14 judged failures; recurring by
   construction — no gate can patch it; it requires a contract change (§4).
2. **Supervisor operational reliability** — quantitatively close, qualitatively different:
   ~6 runs (25%) died on instrument/operational defects (D3 transport crash; D5 IdentityMismatch
   204208, non-FF 210034/210455, phantom 213434, worktree leftover 214258) plus 2 Day-4
   instrument false-reds (L-007) and the #10 retry inflation 3→6 from restart races (L-009,
   DAY5 "#10 retries accounting"). All have landed or spec'd fixes (L-007 dc84d4d3, L-008
   df0d5a1d, L-010 558eb0a, L-009 reconcile spec, L-011 pre-merge base check, L-012
   lifecycle rules); several were operator-restart-induced (DAY5: "external restarts
   (me/operator)"). It ranks #2 only because each defect is a one-time bug with a fix, while
   the artifact contract is an interface property that will recur at product scale. The
   single-instance guard is still missing (see OpenRig §3, NEEDLE ADR-028 §4).
3. **Model-reasoning failures** (valid artifact, wrong content): 2/14, both caught by
   review/verify — the system working as designed (L-000).†

## 2. Root cause of the Day-5 "patch does not apply" — forensics on issue #10

Replayed the counted #10 claimed.diffs against their per-run bases, byte-exact. This
doc's own probe covered three of the four (203657, 205312, 210631); 211313 (the fourth
counted #10 run) and 213434 were replayed by the Day-5 corrections pass (see below and
DAY5_REPORT replay section). Findings (repro: contiguous-window probe over
`git show <base>:app.py`, rstrip-tolerant; all commands re-verified on the local corpus):

- **The checkout and prompt were FRESH, not stale.** `worktree_for()` fetches origin/main and
  resets to it every lap (lap.py:70-82); `run()` injects the worktree's root `*.py` into the
  prompt (lap.py:343-345). Run 203657 (20:36Z) got base e6b3db4 (pre-#15-merge); runs 205312 /
  210631 (20:53Z/21:06Z) got base 8935820a, which *contains* `def delete` (PR #15 merged
  20:44Z; DAY5_REPORT PR table). The models' early hunks correctly reference *their own*
  base — 205312's `def delete` context exists only in 8935820a (verified: `git show
  8935820a:app.py:46`), proving the model read the current file, not an old one.
- **The failure is hallucinated context, not line drift.** Line numbers are off by ±1–6
  (claimed -63 vs real 61; -45 vs 46; -67 vs 72) — well within `git apply`'s offset search.
  The killer: in every failed diff, at least one hunk's old-side context **has no contiguous
  window in the base file** — the model splices real lines into fake adjacency (probe:
  205312 hunk3 and 210631 hunk3 windows NOT FOUND in 8935820a; 203657 hunk1 applies at offset
  in isolation but the full patch carries count/whitespace slips — plain AND `--recount -C1`
  both fail, replayed; 211313 hunk3 fails the same way — it requires `wfile.write(body)`
  adjacent to `def _read_body`, an adjacency absent from every revision checked (bf9ca06,
  e6b3db4, 8935820a, 9045492e — Day-5 corrections replay). `--recount` fixes arithmetic;
  `-C1` shrinks required context; neither can repair invented adjacency. The model regenerates
  "what a pastebin server looks like" instead of copying the file it was handed.
- **213434 (phantom #10 run) is the counter-case that proves the ladder's cost:** its hunk 1
  is valid and applies cleanly at offset (verified in isolation, plain tier), but the
  new-file hunk header declares `@@ -0,0 +1,74 @@` against 71 actual `+` lines → tier-1
  "corrupt patch"; the recount tier then fails on a spurious trailing blank context line.
  A three-character count typo killed a patch whose substantive hunk was correct — and the
  in-run record kept only the last tier's generic stderr (lap.py:253, L-014), so this was
  invisible without replay.
- **Corroboration:** luna's new-file sections were byte-perfect in all Day-5 runs (DAY5_REPORT
  luna table: "clean fenced unified diffs… repeated context drift on app.py edits"). New files
  need no anchor reproduction; in-place edits demand byte-exact old context — exactly what
  luna cannot do reliably even with the file in-prompt.

## 3. Reference-repo findings: how everyone else solves implement→artifact→apply

From `~/repos/factory-docs/CLONE_SURVEY_2026-09-26.md` Task 2 (file:line evidence there) + `REPO_UPDATES_DIGEST.md`:

| Repo | Approach | Fit to nightshift (stdlib-only, raw API, no CLIs, <$0.01/lap, evidence-first) |
|---|---|---|
| ai-software-factory | search/replace mutation JSON `{file, find, replace}`, anchor must occur exactly once (survey: `template/harness/mutations/run.py:148-186`) | **High — recommended (§4).** No line numbers, no hunk headers; fails loud (count>1 → reject) instead of silent misapply. **UNLICENSED upstream** (digest §License status): concept-only, clean-room reimplementation, zero code copied — posture unchanged. |
| Archon, symphony, NEEDLE, sortie, gastown, omnara, no_human | agent-native editing (Codex apply_patch / Claude Edit-Write CLIs); no_human explicitly bans hand-authored file mutation (survey: `orchestrator.py:310-317`) | Out of scope — all require agent CLIs/daemons nightshift forbids. Validates the diagnosis: **nobody** consumes model-authored unified diffs. |
| batty | native apply_patch, but recorded **97× apply_patch verification failures** in one session, handled with retry budgets (survey: `factory-of-features-analysis.md:11`) | Anchor-based editing also fails at rate; but failures are cheap, loud, and converge under retry — unlike hunk arithmetic (glm and luna both fail it, differently). |
| no_human (Δ 1c0ecb0) | merge gate blocks when required checks never ran on the head; absence-of-evidence = red | Steal conceptually: dispatch-time RED-oracle re-verify on the fresh base + pre-merge "checks ran on this head" assertion — closes the L-011 mid-lap-main-move class. |
| NEEDLE (Δ ADR-028) | claim = renewable lease with startup capability check, fail-closed | Right model for our stale-claims + missing single-instance guard (L-009; Day-5 duplicate supervisors). |
| Archon (Δ 879c99fe) | typed provider-failure contract `{class, retryAfterMs, evidence}`; retry on class, not error-text | One-file steal for agent.py retry classification (extends L-001/L-002 PERMANENT/transient split). |
| aa-llm-compare (Δ 308b1f9) | cache-write surcharges can exceed not caching | Not applicable — nightshift is single-call-per-lap, no prompt caching; revisit only if retries add caching. |

## 4. Recommendation: replace the unified-diff contract with search/replace mutation JSON

**Decision:** the product build's implementer emits ONLY a JSON array of mutations
`[{"file": "app.py", "find": "<verbatim snippet>", "replace": "<new text>"}]`. The factory
validates, applies, commits, and synthesizes the git diff itself. Clean-room from the
ai-software-factory concept (no code copied).

**Why this beats the alternatives, per the data:**
- *Keep unified diffs + repair ladder:* exhausted. The ladder already handles arithmetic
  (`--recount`, proven in clone-survey Task 1) and short context (`-C1`); the residual
  dominant sub-class — hallucinated adjacency — is unrepairable by any tolerance flag (§2).
- *Full-file contract* (DAY3_REPORT's own proposal): also removes arithmetic, but pays
  16k-token re-emission per file at scale, invites unrelated rewrites the reviewer must
  then catch, and destroys "review the delta" focus. Viable fallback for tiny repos; not
  the product answer.
- *Mutation JSON:* asks the model for the one thing it demonstrably does well (write new
  code: every new-file section was byte-perfect) plus the minimal anchor copy from the
  provided checkout — no line numbers, no counts, no whole-hunk context reconstruction.
  #10's actual edits anchor on `try:\n            body = json.loads(self._read_body())`,
  which exists verbatim in both bases (probe: found at e6b3db4:61, 8935820a:72) — the
  failed runs died on the *surrounding reconstruction*, which this contract never requests.
  Failure becomes loud, cheap, actionable ("anchor occurs 0 times in app.py") instead of
  "patch does not apply".

**Gate changes required (3–5):**
1. `diff-extraction` → `mutation-parse`: strict JSON parse + shape check (array; keys
   file/find/replace; file ∈ provided checkout set). Malformed → fail with the parse error
   (replaces `extract_diff`, lap.py:116-142). DSML/prose leaks die here, as today.
2. `diff-apply` → `mutation-apply`: per mutation, anchor must occur **exactly once**
   (trailing-whitespace-normalized match); 0 or >1 occurrences → fail naming file + anchor
   prefix; apply via ordered `replace(find, replace, 1)`; post-condition: mutated file set ⊆
   `git status --porcelain` (reuses the L-008 declared-vs-applied discipline). No
   auto-repair — an anchor miss is a genuine model failure the gate records, per L-008's
   principle. Replaces `apply_diff` ladder (lap.py:216-263).
3. **Review gate: unchanged.** The factory commits and synthesizes `git diff origin/main
   HEAD` exactly as today (lap.py:372-375 writes applied.diff); the reviewer keeps reading
   a real unified diff — zero review-prompt changes, zero new failure surface.
4. **Verify/merge/deploy/identity: unchanged** — they operate on the worktree and PR, not
   the artifact.
5. **Evidence records:** `claimed.json` (validated mutations) replaces `claimed.diff`;
   keep `implementer_raw.txt`; add per-mutation `{file, anchor_count, applied}` to the
   verdict so the caught-confabulation metric stays gate-attributed (L-007's lesson:
   misattribution corrupts the headline metric).

**Implementer prompt change:** emit only the JSON array; anchor rules stated explicitly
("copy anchors verbatim from the provided files; each anchor must occur exactly once");
checkout injection unchanged (lap.py:343-345).

**Effort:** ~1 day — parse/validate/apply ≈ 80 stdlib lines replacing ~110 (extract_diff +
apply_diff + helpers), one prompt rewrite, plus a regression test replaying #10's edits as
mutations against both bases (the replay harness from §2 is the test).

**Tradeoffs, honestly:** the anchor is still a byte-exact copy task, and a model that
hallucinates context can hallucinate anchors — but the ask shrinks from "reconstruct a hunk
with counts, line numbers, and both-side context" to "quote one snippet you are looking at";
batty's 97× show anchor failures still happen, and converge under retry budgets. Whitespace
normalization at match time is the one tolerance worth building (models drift trailing
whitespace); nothing beyond that.

## 5. OpenRig assessment (repo + both blogs; salt applied — vendor is influencer-adjacent)

Cloned to `~/repos/reference/openrig` (Apache-2.0). Architecture (tmux daemon, agent CLIs,
TUI) is out of scope by nightshift's constraints. What survives scrutiny:

- **Evidence discipline: adopt as reference.** `docker/testbed/runbooks/README.md` —
  "evidence-defined… never asserts from memory… run it, capture the real bytes, verdict
  against them"; hashed per-run evidence dirs; L4-hermetic-fail-closed.md proves the guard
  *inside* the container rather than weakening it. `.evidence/` ships RED-first artifacts
  (`S6-RED-FIRST.md`, `RED-*.txt` at pinned bases). This is nightshift's own RED-first,
  evidence-first mandate (SPIKE_PROD S2) independently confirmed — harvest as methodology
  exemplars.
- **judgments.ts absent-vs-malformed** (`packages/daemon/src/domain/proof/judgments.ts:280`,
  digest §6): absent optional metadata defaults, malformed fails closed. One-line discipline
  for our state/verdict parsers — cheap steal.
- **Refocus intent-chain:** NOT load-bearing for us. Refocus reorients long-lived seats
  after compaction (docs/reference/refocus-channel.md — hooks on UserPromptSubmit/Stop/
  PostCompact); nightshift laps are single-shot with fresh context, and the reviewer already
  re-checks the issue's acceptance criteria every lap. Reconsider only if laps ever become
  long-running sessions.
- **Coordination-failure lens (agent-civilizations):** genuinely useful, not marketing.
  His taxonomy — scope inflation, split-context approvals, goals crossing agents — maps to
  one real nightshift incident: L-011 (main moved mid-lap; two laps raced on the same rig;
  the squash merged onto a base nobody re-checked). His fix shape (the decision-maker needs
  the information the decision depends on) is exactly the pre-merge "checks ran on this
  head" assertion (§3 no_human). Scope inflation: not observed — our issues are small and
  the reviewer gates ambition.
- **Building-blocks taxonomy (software-factory-building-blocks): stress-test FAILS for us.**
  His four blocks (rig/coordination/workflows/workspaces) assume CLI-harness agents; none
  predicts our dominant failure — 79% of judged failures are an *interface* contract (diff
  artifact) and the rest are *process* races (restarts, claims). We built his "workflow"
  (supervisor + gates) and "workspace" (state/evidence dir) as ~300 stdlib lines; his "rig"
  and "coordination" solve a problem we deliberately don't have (he names things we already
  built, or chose not to). Where his framing matches our evidence — deterministic rails,
  fail-closed guards, "never assert from memory" — it matches because those are generic
  engineering virtues, not his architecture. The recursive-self-improvement anecdote
  ("growing not building") is unverifiable vendor narrative; ignore.
- **Verdict: ADOPT as reference corpus** (harvest/), narrow: runbooks/README.md +
  L4-hermetic-fail-closed.md (methodology), judgments.ts absent-vs-malformed pattern
  (code-eligible, Apache-2.0 with NOTICE per harvest/licenses.md rules), and the
  coordination-failure lens applied to our merge-race fixes. Skip: tmux/daemon/TUI,
  Refocus, building-blocks taxonomy. **Also schedule now, OpenRig-adjacent:** the
  single-instance guard their daemon design takes for granted and we lack — a stdlib
  `fcntl.flock` on the state dir at supervisor start (Day-5 duplicate nohup races, L-009;
  NEEDLE ADR-028's lease-with-capability-check is the fuller model).

## 6. Open questions for the owner

1. Mutation ordering semantics: apply array in order, each on the previous result
   (simplest, matches ai-software-factory)? Or independent anchors only?
2. Should the reviewer also see the mutation JSON (intent) or keep seeing only the
   synthesized diff (current behavior, minimal change)?
3. On anchor-miss retries: send the failure back to the implementer with the nearest
   in-file match as feedback? Cheap and evidence-first, but flirts with auto-repair —
   L-008 drew that line at "gates catch, never fix"; owner call.
4. Full-file contract as a per-repo fallback for tiny single-file rigs (DAY3_REPORT's
   original proposal) — keep in the back pocket, or reject for product uniformity?
5. Confirm the ai-software-factory posture stays concepts-only (still unlicensed as of
   2026-09-28, digest §License status) for the clean-room implementation.
6. Refactor-lap risk under the mutation-JSON contract: an implementer can "fix" an
   already-satisfied issue by emitting trivial, anchor-hitting mutations — the gates
   (anchor-exists, review, verify) all pass, exactly as #12's 21:26Z refactor-lap green did
   under the diff contract. The mutation contract doesn't gate this; the dispatch-time
   RED-oracle re-check (L-013: re-run the issue's scenario against fresh main before
   spending a lap; skip + reconcile if GREEN) does. Should that re-check be a hard
   prerequisite for adopting §4, and should mutation-apply evidence record the pre-lap
   scenario verdict so refactor laps are distinguishable in the record?
