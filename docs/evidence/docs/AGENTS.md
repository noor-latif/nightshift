# AGENTS.md — Steering doc for agents (and humans) developing the factory itself

This repository's docs govern the **development** of an unattended AI software factory — not the conduct
of the factory's executing agent (its rules live in the product repo's policy chain; see Layout). The
factory is Archon-based, running on remote host [redacted-host], with a tiny pastebin (`~/factory-lab/toy-product`)
as its calibration rig. Doc map: **FACTORY_PLATFORM_VERDICT.md §A–H** is the evidence base (§F/§H record
what actually happened on real laps, including four daemon failure classes and the §H false-green);
**UNATTENDED_FACTORY_PLAN.md** is the build spec (Layers 0–5, phased rollout); **PITFALLS_AND_STRATEGIES.md**
is the failure catalog (P1–P13); **harvest/HARVEST.md** is the licensed reference corpus for the
supervisor; **FIRST_BUILD_VERIFICATION.md** is the acceptance protocol for the current build.

## Layout

- **Local** `~/repos/factory-docs/`: all docs above plus `harvest/` (corpus of verbatim excerpts with
  provenance headers, per-repo license verdicts in `harvest/licenses.md`).
- **Remote [redacted-host]**:
  - Pinned Archon install at `~/.cache/factory/archon/24796870605b0fd576734b79a8d5c781f2b1c1e1` —
    **READ-ONLY. Never edit it.** Harvest from it; cite path:lines; the pinned hash is the citation anchor.
  - Product repo `~/factory-lab/toy-product` — has its own policy chain:
    `AGENTS.md` → `factory/WORKFLOW_POLICY.md` → `FACTORY_RULES.md` → `MIGRATION.md`. Those are the
    **executing agent's** conduct rules (identity-matched evidence, independent review, no gate bypass,
    truthful failure reporting). **Do not duplicate them here — cross-reference them.** Only add rules
    here that govern factory *development*.

## License rules (hard)

- Harvest corpus: MIT/Apache-2.0 sources are copy-eligible **with provenance headers** (repo,
  path:lines, SPDX, verbatim/excerpt marker) — the header format is in HARVEST.md.
- **ai-software-factory is UNLICENSED upstream** (license:null). HARVEST.md records a user directive
  treating it as MIT for this private, non-distributed corpus only — but the safe default stands:
  **never copy verbatim from it**, and never copy verbatim from the deployed `factory/` tree
  (`consumer.py`, `runtime_resource.py`) derived from it. Describe in prose, cite paths. Distribution
  requires upstreaming a LICENSE first.
- **Archon (MIT) ≠ ai-software-factory (unlicensed).** Don't conflate their license status.
- Anything unclear → Escalation below, not a judgment call mid-edit.

## Verification bar (the P9 rule — hard, no exceptions)

- **Never report a gate/calibration as green without a demonstrated red.** A verifier that cannot fail
  green-washes everything downstream (§H: revision assertions passed against a constant literal).
- **Run the thing, don't assert it.** Claims about behavior require execution evidence.
- **Non-trivial logic leaves one runnable check** (assert-based self-check or one small test file).
- **Claims about files require reading them. File size is not content** — the defects.json incident:
  a 3.6KB file that was still `"defects": []` + `_scaffold` marker, reported "appears resolved" twice.
- **A check that can't run is a hold, not a pass** (§F: scaffold shipped failing NO_CHECKS; P9).

## Operational rules (hard-won; each traces to an incident)

- Write scripts locally, then `scp` them. **Never inline nested quotes through ssh+tmux** — quoting
  layers produce silently different commands.
- **Kill by PID file, never `pkill -f`** — `pkill -f "python app.py"` matches the daemon's own argv
  and self-kills it (§H finding 3b; retired `/tmp/launch-lifecycle.sh` carried this landmine).
- **Launch factory laps from the product repo cwd** (`~/factory-lab/toy-product`). Launching from the
  Archon clone registers `coleam00/Archon` as the codebase — wasted lap + stray commit (§H finding 4).
- Scenario/deploy commands run relative to the per-run worktree cwd — no hardcoded `cd` (§H finding 3c).
- Liveness = owner pid + fresh worktree writes, **never the status row** (§F.1: rows `running` for
  hours post-mortem; §H: 2h silent hang).
- Recovery ladder: resume→cancel→abandon; **abandon only on a proven-dead owner with stopped worktree**.
- **Stop-and-report beats improvisation.** When blocked or something contradicts the plan, stop.
- **Budget stops are obeyed** — turn/token/cost exhaustion means stop, never push through.
- `exit 0` inside eval'd scenario setup/teardown kills the node shell before its ok-echo (§H finding 3a).

## Escalation — stop and ask the owner when

- Anything touching **auto-merge enablement** (the owner is the trust gate; Phase 3 mutation calibration
  needs the human-authored defects.json first).
- Anything reaching **prod-ish state**: destructive ops, secrets, anything beyond the toy-product lab.
- **Licenses unclear** (see License rules).
- **Plan contradictions** between verdict/plan/pitfalls docs, or observed behavior that contradicts them.

## Acceptance protocol

The current build (supervisor + provenance-fixed scenarios + schedule.json/selector + merge_mode=auto +
PID-file deploy) is accepted per **FIRST_BUILD_VERIFICATION.md** — pre-launch checklist, during-lap STOP
conditions, post-lap evidence-chain audit, Phase 2 go/no-go. No build ships without walking it.
