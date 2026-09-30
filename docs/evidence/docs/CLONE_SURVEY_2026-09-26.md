# Clone Survey & Patch Replay Report — 2026-09-26 [reconstructed 2026-09-28 from the director's pre-wipe read; original /tmp file lost to machine restart]

## Task 1 — Replay of failed Day-3 patches with `git apply --recount`

Setup: throwaway detached worktree at `bf9ca06` in `/tmp/replay-checkout` on [redacted-host] (removed after). Patches: `~/nightshift/state/evidence/20260926T041334-issue-7/claimed.diff` (p1) and `.../20260926T041715-issue-7/claimed.diff` (p2). Both are hand-written (fabricated) unified diffs — p1 even begins with a literal `commit <sha>` line and fake index lines; p2 has a trailing markdown fence + prose ("**Acceptance criteria check:** …") after the last hunk.

| variant | p1 (041334) | p2 (041715) |
|---|---|---|
| `git apply --check` | **fail** `corrupt patch at /tmp/p1.diff:20` | **fail** `patch fragment without header at /tmp/p2.diff:17` |
| `--check --recount` | **pass** (exit 0) | **pass** (exit 0, `warning: recount: unexpected line: \`\`\``) |
| `--check --recount -C1` | **pass** | **pass** (same warning) |
| `--check --3way` | fail (same as plain) | fail (same as plain) |
| apply `--recount` + unit suite | **19 tests OK** (suite_exit=0) | applies, but **18 tests, 1 FAILURE** |
| apply `--recount -C1` + suite | 19 tests OK | same 1 failure |

### p2 suite failure — root cause investigated, NOT a patch-application defect
The failing test is `content_length_test.ContentLengthHeaderTest.test_non_numeric_content_length_returns_400_json`, asserting `resp.status == 201` on the follow-up request `self._post_with_header(b'{"content": "after"}', "16")`. That body is **20 bytes**, but the test sends `Content-Length: 16`, so the server reads only 16 bytes → invalid JSON → 400. Verified independently:
- Unpatched base tree + same mismatched request: 400 `"invalid JSON body"` too (reproduced via direct `http.client` probe).
- Patched tree with correct `Content-Length: 20`: **201** — the patched server code is correct.
- The apply itself was clean: `_InvalidContentLength` class, `do_POST` rewrite, and `_read_body` rewrite all landed byte-correct; `--recount`'s only complaint was the trailing ``` fence line, which it skips harmlessly.

So p2's suite failure is a **bug in the agent's test code** (self-inconsistent test fixture), not in the diff arithmetic and not something `--recount`/`-C1` could or should fix.

### Verdict
**`--recount` alone makes BOTH patches apply cleanly** (with `-C1` unnecessary). It closes the hunk-header arithmetic failure class completely: both failed patches fail plain, pass with `--recount`, and p1's resulting tree passes the full suite. `-C1` adds nothing here. `--3way` does not help (it still parses the same corrupt headers). The residual risk is not application but **artifact hygiene**: both patches carry non-diff garbage (a `commit <sha>` banner line, a fenced code block + acceptance prose). `--recount` tolerates the trailing junk with a warning, but a pre-apply lint that strips everything outside `diff --git … ` blocks (or instructs the model to emit raw diffs only) is a cheap second gate. Option (b) (full-file contract) would also work but trad[LINE TRUNCATED IN SURVIVING READ — FULL TEXT LOST]

## Task 2 — Artifact-contract survey of local factory clones

| repo | artifact contract | evidence (file:line) | tolerance/fuzz in apply | shared failure mode? |
|---|---|---|---|---|
| ai-software-factory | **search/replace mutation JSON** (`{file, find, replace}`, anchor must occur exactly once; applied with `body.replace(find, replace, 1)`) | `template/harness/mutations/run.py:148-186`; `template/factory/runtime_host.py:198-201`; `bin/test_consumer.py:690-696` | Rejects ambiguous anchors (`count > 1` → fail loudly) rather than fuzzing | No diffs emitted at all → immune; fails loudly on anchor mismatch instead of silently misapplying |
| Archon | **agent-native tool edits** (Claude Code / Codex CLIs run headless with their own Edit/Write/apply_patch tools; workflows dispatch prompts, no custom patch pipeline found) | `packages/core/src/orchestrator/orchestrator-agent.ts` (subprocess provider, :2522 providerKey==='claude'); bundled workflow prompts in `packages/workflows/src/defaults/bundled-defaults.generated.ts` | N/A — editor is the CLI's native tool with its own verification | Immune by construction |
| symphony | **agent-native (Codex app-server)** — orchestrator dispatches Codex sessions, `applyPatchApproval` passthrough | `elixir/lib/symphony_elixir/codex/app_server.ex:646`; `elixir/WORKFLOW.md` (workspace-write sandbox, :36-38) | Native Codex apply_patch tooling | Immune |
| NEEDLE | **agent-native** — headless `claude -p … --dangerously-skip-permissions`; prompt is deterministic function of bead; agent edits with its own tools | `README.md:55, 249-263, 371`; `src/prompt/mod.rs:64-73` (workspace hygiene, not diff format) | None custom; exit-code outcome table in README:265 | Immune |
| sortie | **agent-native** — Claude Code headless print-mode adapter, permission bypass, fork-per-turn skeleton | `docs/claude-code-adapter-notes.md:1-27`; `WORKFLOW.md` implementer prompt (:85-140, plain prose "Write the code") | None custom | Immune |
| gastown | **agent-native** — multi-agent orchestration over Claude/Codex/Copilot CLIs; workers implement directly in workspace | `README.md:3,50,137,633` | None custom | Immune |
| no_human | **agent-native tool-call edits, explicitly enforced** — gate message instructs: use Write/Edit tool, "not a Bash heredoc or redirect"; reviewer reads `git diff` for review only | `src/no_human/core/orchestrator.py:310-317`; unified diff only consumed, not produced (`orchestrator.py:15863,15888`; `vcs/comment_poster.py:28`) | Edit-tool trust, no patch application | Immune; the closest to our failure class and they banned hand-authored file mutation explicitly |
| batty | **agent-native `apply_patch`** (Codex tool) + anti-narration rules; completion gated on `git diff --stat` | `src/team/templates/batty_engineer.md:64-69`; `src/shim/classifier.rs:152,285,330`; `src/team/watcher/codex.rs:661,682` | Codex's apply_patch (str-context based, fuzzy-free but not hunk-header based) | **Had a sibling failure**: `planning/factory-of-features-analysis.md:11` — **97 × `apply_patch verification failed`** in one session; treated as top gap (#3), added retry budgets/escalation. Not hunk-header miscounts, but the same class of "agent's edit artifact rejected by the apply tool" |
| omnara | **agent-native `apply_patch`** (OpenAI responses API; profile even says "the tool call will fail if it didn't work — don't re-read") | `internal/model/openairesponses/input.go:361-362`; `examples/cli-agent/agent-profile.yaml:70` | Native tool verifies itself | Immune |

**Nobody else hand-writes unified diffs for a machine to `git apply`** — that contract is unique to our factory among the surveyed clones. The dominant pattern is native edit tooling (Codex `apply_patch`, Claude Edit/Write). Batty is the only repo with recorded incidents of edit-apply failures (97 apply_patch verification failures), handled with retry budgets rather than tolerance flags. No repo in the survey shows hunk-header-miscount incidents because no repo consumes model-authored unified diffs.

## Task 3 — aa-llm-compare

`~/repos/aa-llm-compare` is a small dependency-free Python CLI (`aa_fetch.py` + `test_aa_fetch.py`) that scrapes Artificial Analysis' Next.js RSC flight payload (`GET /models/<slug>` + `RSC: 1` header, no auth) to compare models on index, price, throughput, latency spread, and eval scores — its stated value is warning about misleading benchmark comparisons. It references `glm-5-3-flash` extensively as a catalog anchor/default slug and includes `deepseek-v4-1-flash` in comparison examples and dedup checks (`aa_fetch.py:82, 530, 535, 573`), but it contains **nothing about diff/edit-format capabilities** of either model — the only "diff" hits are `difflib.get_close_matches` for typo-tolerant slug lookup (:184) and prose about statistical differences[LINE TRUNCATED IN SURVIVING READ — FULL TEXT LOST]
