# Laptop Migration — nightshift AI-factory spike (2026-09-28)

Transfer of runtime assets from [redacted-host] (read-only pull) to this laptop.
Nothing was launched; this is transfer + verification only.

## Transfer manifest

| Item | [redacted-host] | laptop | match |
|---|---|---|---|
| `~/nightshift` HEAD | `558eb0a9e3d06ab63b23419cf6c3abc9765d5062` | same | ✅ |
| `~/nightshift` files / size | 406 / 2.0M | 406 / 2.0M | ✅ |
| `~/factory-lab/toy-product` HEAD | `9045492e08337a880488ac27073963b937503c44` | same | ✅ |
| toy-product files / size | 352 / 1.7M | 352 / 1.7M | ✅ |
| `state/evidence/` run dirs | 30 | 30 | ✅ |

Method: `rsync -az -p` (rsync present on [redacted-host]). Tool: `git worktree remove
--force` + `prune` for stale `.factory/worktrees/issue-10` on the LAPTOP copy
only (evidence preserved in `~/nightshift/state/evidence/`).

Note: `~/factory-lab/ai-software-factory` (884K, bin/docs/template) still exists
on [redacted-host] only — not requested, not transferred.

## Verification results

- `claimed.diff` of run `20260926T212615-issue-12`: byte-identical (`cmp`) ✅
- ≥3 run dirs spot-checked (incl. `20260925T101308-issue-6`): all contain
  verdict.json, timeline.json, claimed.diff, applied.diff, review.txt, cost.json ✅
- `~/nightshift` tests: `python3 -m unittest discover -s tests` → **78 tests, OK** (3.14.7) ✅
- toy-product tests: `python3 -m unittest app_test` → **15 tests, OK** ✅
- [redacted-host] untouched (read-only ops only); [redacted-host] toy server (PID /tmp/toy-deploy.pid) not killed.

## Secrets status

| Name | Status |
|---|---|
| SURPLUS_INTELLIGENCE_API_KEY | set (secret store) — gateway smoke test `GET /v1/models` → **HTTP 200** ✅ |
| GITHUB_TOKEN | not needed — merge path shells out to `gh` CLI (src/merge.py:36-58), no direct token read |

## Env vars the factory reads (with citations)

- `SURPLUS_INTELLIGENCE_API_KEY` — src/settings.py:8 (constant), read at src/agent.py:119 (`os.environ[...]`)
- `FACTORY_RUNTIME_CANDIDATE` — src/settings.py:31; provenance canary, must be UNSET (src/verify.py:126-127 refuses if set)

Non-env config in src/settings.py: `GITHUB_REPO = "noor-latif/toy-product"` (:5),
`NTFY_URL = https://ntfy.sh/[redacted-ntfy-topic]` (:16-17).

## Laptop readiness

- Python 3.14.7 (≥3.11 required) ✅
- `gh auth status`: logged in as `noor-latif`, active, https protocol ✅
- Port 8642: free ✅
- Disk: `~/nightshift` 2.0M, `~/factory-lab/toy-product` 1.7M (post-prune)

## RESUME CHECKLIST (do NOT do these yet)

1. [owner] Reset `~/nightshift/state/state.json` + `state/claims/` for a fresh run (archive old state first).
2. [owner] Decide deploy target: laptop rig (port 8642 free) vs keep serving from [redacted-host].
3. [mechanical] Re-check `src/settings.py` paths (repo, ntfy, API base) against chosen target.
4. [owner] Queue ≥3 fresh RED-proven issues — current queue is empty.
5. [owner] Single-instance guard + ntfy receipts wiring + reconcile still pending (design decision).
6. [mechanical] Supervisor launch: e.g. `cd ~/nightshift && python3 -m src.supervisor` (confirm entry point before running).
