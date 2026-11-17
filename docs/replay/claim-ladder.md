# Scope and claim ladder

Read when writing the score doc: the scope a `DEPLOY_MODE=none` run exercises, and the pre-registered ladder that fixes the strongest claim the evidence can carry.

## 8. What a replay run does NOT validate

With `DEPLOY_MODE=none` the provenance check is skipped/absent from the verdict (verify.py:351-353, 367-368) and the deploy leg never runs (lap.py:477-478). A replay green validates implementer → mutation-apply → review → verify (unit + holdout scenario) → merge → issue-close ONLY. State this in every score doc — "every gate held" means the exercised scope. Full-ladder deploy validation rests on deploy-mode runs (the dogfood run's scope). (REPLAY_SCORE dated correction.)

## 8a. What a result set supports

Score docs must state the claim level the evidence carries, pre-registered against this ladder — because the 2026-09-30 run's evidence was n=3 easy-tier instances on ONE repo whose holdout oracles were the experts' own test patches path-rewritten: that measures "reproduces a known-good fix under the expert's tests", NOT general expert-level output. Two overclaims were retracted in dated corrections ("every gate held", "no positive memorization flags"); the ladder exists so the next score can't inherit a claim its sample doesn't carry.

- n=1 green, any tier = existence proof on that instance. Claim: "the factory solved this instance blind." Nothing more.
- n≤5, one repo, easy tier, expert-test oracles (the 2026-09-30 run) = capability claim: "reproduces known-good fixes under the expert's own tests, easy-tier, [repo]'s domain, blind property intact" — each green weighted by its memorization flag (§3). Does NOT support: expert-level output generally, cross-repo or cross-tier reliability, unweighted claims.
- RELIABILITY claim ("produces senior-engineer-grade fixes for this class of work, reliably") requires ALL of: ≥20 instances (power, not vibes); ≥3 repos (cross-repo, not one ecosystem); tier spread — easy + medium minimum, per the LOC proxy in §3; a majority-post-cutoff subset or a memorization-controlled comparison (same model, pre- vs post-cutoff divergence measured) — memorization, not capability, can explain greens; ORACLE INDEPENDENCE on a subset — holdout tests authored from the issue spec WITHOUT reading the gold patch, validated red-at-base/green-at-gold — this is what upgrades the claim from "reproduces known-good under expert tests" to "satisfies an independently-authored spec"; unattended basis (§7); pre-registered park attribution (§7).
- "Replaces a senior engineer" additionally requires: deploy-bearing scope (§8), harder tiers, and cost/speed comparison rows vs. the human baseline.

Hard rule: every score doc's header states its supported claim level in ONE line, computed from this ladder, BEFORE the results narrative. Evidence that doesn't reach a rung ⇒ the claim doesn't either. Thresholds (20 / 3 repos / tiers) are this skill's pre-registered defaults; adjust only with a dated disclosure in the score doc.