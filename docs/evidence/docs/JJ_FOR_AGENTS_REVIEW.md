# jj for AI Coding Agents — Factory Feasibility Review

*2026-09-24 · research for the 6-module git+gh spike · solo dev, single server, squash-merge-to-main via `gh`*

## §1 Verdict table

| Dimension | Evidence | Implication for the factory |
|---|---|---|
| Agent UX | Top models pass 79–92% of jj-native tasks unprompted (jj-benchmark, 63 tasks); but agents "seem not trained to use it, so it won't be committing there" (Panozzo) | Models handle jj fine with a prompt/skill, but prompts are load-bearing; budget one for the agent |
| Recovery/safety | Auto-snapshot + `jj op log`/`jj undo`/`jj op restore` restore whole repo state — "far more powerful and useful than the git reflog" (zerowidth). Git reflog covers only HEAD moves; jj ops capture `git reset`/import done *by git commands in the workspace* too (docs) | Directly answers our incident classes (stray commits on main, bad resets). Biggest single win |
| gh/CI interop | Colocated = `.git` shared, import/export on every jj command; `gh` works in colocated repos (docs only flag non-colocated repos, issue #1008); `gh pr create` needs a real branch — jj leaves git in detached HEAD, so bookmark+push first (`jj bookmark create f/issue-N -r @- && jj git push`) | gh steps work unchanged; loop must add bookmark+push instead of `git push -u` |
| Headless ergonomics | `--no-graph` + `-T` templates are first-class; revsets give precise machine queries; `jj status` ≈0.01s (Panozzo); snapshot is per-command (no daemon) | Scripting is good. Snapshot-on-every-command is fine at our repo sizes; no UNVERIFIED perf red flags found for medium repos |
| Colocated mixing | Docs: mixing mutating git+jj can diverge branches; historically `jj undo` after a mutating git op didn't re-export refs (issue #922, closed 2023, labeled colocated); git hooks NOT run by jj (docs, #405); `.gitattributes` unsupported (#53) — phantom-mod CRLF case (Gradle blog) | We mutate via git anyway (gh, CI): keep mutations in one lane. No `.gitattributes`-sensitive repos → CRLF risk low. Hooks: run verification explicitly in the spike (we already do) |
| Ecosystem maturity | Experimental per jj README; docs still say "TODO" for branch mapping; no first-class GitHub squash-merge awareness (community: use `jj git fetch` + rebase after squash merge) | Mature enough as a git-compatible front-end; not mature enough as a *forge* integration. E-reality: gh remains the integration point |

## §2 What the community actually says

**Pro:**
- "With jj, every file change is automatically captured (no manual commits needed)... When things go wrong, `jj undo` instantly reverts to any previous state. The operation log tracks everything, making it virtually impossible to lose work. ... let Claude generate messy experimental code → use `jj squash`/`jj split` to shape clean commits afterward." — Kurilyak, quoted at https://www.panozzaj.com/blog/2025/11/22/avoid-losing-work-with-jujutsu-jj-for-ai-coding-agents
- "I've been using jj with Claude Code for months... no fear of breaking things because everything is instantly reversible." — same HN comment thread (id 45055550, via Panozzo)
- "It's far more powerful and useful than the git reflog because of how easy it is to restore the entire repository back to a previous state." — https://zerowidth.com/2025/what-ive-learned-from-jj
- "If I want multiple AI agents working on that stuff, I just make a worktree and get on with it." — HN id 44645239 (via Panozzo)
- TabbyML built a whole 63-task benchmark because "it introduces a very different workflow" — agents can learn it: Sonnet 92%. https://tabbyml.github.io/jj-benchmark/ + HN 47352189
- Ian Bull: `jj new` per unit of work = per-step isolation; commit messages as prompt provenance. https://ianbull.com/posts/jj-vibes

**Contra:**
- Snapshot is NOT background: "jj doesn't have a background daemon watching for file changes... if an agent makes changes and then crashes before any `jj` command runs, those changes won't be in the history." — Panozzo update 2026-01-23 (same URL). Mitigation: agents run jj constantly, or a pre-command hook.
- `jj undo` in colocated repos historically failed to move git refs (branch divergence after undo/import interleaving) — https://github.com/jj-vcs/jj/issues/922 (closed 2023; docs now warn generally about interleaving).
- Gradle: no `.gitattributes`/eol support → persistent phantom diffs on `gradlew.bat`; a reporter "gave up on jj" over six-figure phantom-change counts. https://blog.gradle.org/the-petty-reason-we-didnt-end-up-using-jj-at-gradle
- "somewhat of a mismatch between jj and git models... force pushes invalidate review comments" — zerowidth (same URL). Our squash-merge model sidesteps this (no review thread preservation needed).
- UNVERIFIED: anecdotes of agents surprised by auto-committed working copy / expecting dirty state. All surfaced reports were *pro*-jj for agents; the documented concern is agents trained on git hesitating to use jj at all (Panozzo), not jj breaking git-trained habits.

## §3 Options, honestly weighted

**(a) jj colocated end-to-end in the loop.** Spike modules change: worktree→`jj workspace add`; claim/setup→`jj workspace` + `jj new main`; commit→`jj describe`/`jj commit` (no staging); PR→bookmark+`jj git push`+`gh pr create` (gh unchanged); merge→`gh pr merge --squash --match-head-commit` unchanged; recovery→`jj op log`/`jj op restore` replaces hand-rolled reset scripts (delete a module's worth of recovery code). Cost: +1 module equivalent (jj invocation wrapper, snapshot-guarantee step), −recovery plumbing; all `gh`/verify code identical. Risk: colocated interleaving bugs in a fully-automated mutating loop are the least-tested jj path; issue #922 was exactly this class. Mitigate: all mutations via jj, gh only via remote (merge on GitHub side), `jj git fetch` after merge.

**(b) Hybrid (current): git in the automated loop, jj for human/parallel-agent dev.** Spike unchanged (git CLI + gh exactly as specced); zero new risk; keeps colocated repos where humans work. Cost: the factory gets none of the op-log safety net; stray-commit-on-main incidents recover only via git reflog surgery.

**(c) Skip jj entirely.** Spike as specced; lose nothing except jj advantages; keep colocated adoption ad-hoc.

Recommendation: **(a) is genuinely tempting but (b) is the right spike bet** — the loop's failure surface is already handled by `--match-head-commit` verification + disposable worktrees, and the two structural jj wins (op-log recovery, workspace parallelism) are additive, not blocking. Standardize colocated repos everywhere so agents *can* run `jj op restore` during interactive debugging and you can promote (a) per-repo later without touching the gh contract. Revisit (a) after one month of loop incidents.

## §4 References

1. jj docs, Git compatibility — https://docs.jj-vcs.dev/latest/git-compatibility (hooks #405, .gitattributes #53, colocated caveats, git worktree: No / jj workspace)
2. jj docs, Working with GitHub — https://docs.jj-vcs.dev/latest/github (colocated detached-HEAD + bookmark workflow; gh needs `GIT_DIR` only when NOT colocated, issue #1008)
3. Panozzo, "Avoid Losing Work with Jujutsu (jj) for AI Coding Agents" — https://www.panozzaj.com/blog/2025/11/22/avoid-losing-work-with-jujutsu-jj-for-ai-coding-agents (snapshot caveat, [CC] hooks, HN quotes)
4. zerowidth, "What I've learned from jj" — https://zerowidth.com/2025/what-ive-learned-from-jj (op log vs reflog, colocated interop, forge mismatch)
5. TabbyML jj-benchmark — https://tabbyml.github.io/jj-benchmark/ + https://news.ycombinator.com/item?id=47352189 (agent capability numbers)
6. Ian Bull, "Towards an AI-Native Development Workflow" — https://ianbull.com/posts/jj-vibes
7. jj issue #922 — https://github.com/jj-vcs/jj/issues/922 (colocated undo × git import)
8. Gradle blog — https://blog.gradle.org/the-petty-reason-we-didnt-end-up-using-jj-at-gradle (.gitattributes/eol phantom diffs)
9. jj repo — https://github.com/jj-vcs/jj ("experimental" status)

---
**Verdict rows:** agent UX: good with prompting · recovery: best-in-class (real answer to our incidents) · gh/CI: works unchanged in colocated, bookmark step added · headless: good (`--no-graph`/`-T`/revsets) · colocated: workable, keep mutations single-lane · maturity: fine as git front-end, not as forge layer.

**Top 3 load-bearing facts:**
1. Snapshot happens only on jj commands — no daemon — so agent crash ≠ captured state; needs a hook or agents that run jj every step. https://www.panozzaj.com/blog/2025/11/22/avoid-losing-work-with-jujutsu-jj-for-ai-coding-agents
2. `gh` works against colocated repos unchanged (only non-colocated need `GIT_DIR`); the loop must create/push a bookmark because git sits in detached HEAD. https://docs.jj-vcs.dev/latest/github
3. `jj op log`/`jj op restore` restores whole-repo state including operations done via git commands — strictly stronger than git reflog for our stray-commit/bad-reset incident classes. https://zerowidth.com/2025/what-ive-learned-from-jj + https://docs.jj-vcs.dev/latest/git-compatibility
