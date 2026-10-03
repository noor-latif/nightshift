# nightshift

Time-boxed spike answering one question: can our own code run factory laps
(issue → implement → verify → merge → deploy) unattended, with zero human
interventions and zero false greens. The evidence ledger is published
under `docs/evidence/` (MANIFEST.md is the index).

## Layout

- `src/` — eight modules: `settings.py` (literal config values only),
  `supervisor` (tick loop), `selector` (issue claim), `agent` (surplus LLM
  calls), `lap` (issue→merge chain), `verify` (oracle-first probes),
  `merge` (squash + tree-equality), `deploy` (PID-file launch +
  identity read-back).
- `scenarios/` — HTTP scenario probes for the toy-product rig.
- `tests/` — stdlib unittest; run offline, no network/ssh/gh/API key needed.
  The supervisor test's child process strips `NTFY_TOPIC` (a fixture once
  posted to the operator's real topic); this is a child-env fix, not a
  general network restriction — other clones are not presumed fixed.

## Run

    python3 -m unittest discover -s tests

Python 3 stdlib only. No pip dependencies. The historical lap path still
targets a remote host over ssh; local operator laps run the same entrypoint
directly (below). Scope: time-boxed spike — issue → implement → verify →
merge → deploy laps, zero human interventions, zero false greens.

## Local lap — canonical entrypoint

This checkout, `~/repos/factory-spike`, is the canonical source. Other
clones/workspaces (`~/nightshift`, trial workspaces) are not it.

    cd ~/repos/factory-spike
    set -a; . env.sh; set +a          # export the lap env first (caller-owned)
    scripts/run-lap.sh <issue-number> # detached; prints pid, log path, tail cmd

Paid laps go through `scripts/run-lap.sh`, never a bare `python3 src/lap.py`:
the launcher `setsid`+`nohup`s the child into its own session, so an agent
command timeout kills the launcher, not the open model stream. **NEVER wrap a
lap in a command with a short deadline** — a 300s command deadline once killed
a lap mid-stream and the request still billed. The launcher sources nothing
itself, so the caller MUST have exported the lap env first (as above). An
optional second argument names the logfile (default
`state/lap-<issue>-<timestamp>.log`).

A fresh session gets the current behavior by running that path; nothing is
inherited from another clone or from a previous session's environment. The
local task input, new-file creation, native command config and review/
enhancement modes are opt-in through the launch env. Sanitized model-call
traces, the blank-model guard and the reviewer design context are always
active, not gated. An unconfigured run keeps the historical task source
(`gh`), the edit-only mutation capability and the historical gate defaults —
it is not byte-for-byte the old behavior.

- `FACTORY_TASK_FILE=<abs path>` — read `{title, body}` from a trusted file
  outside the checkout instead of GitHub. Unset = the `gh` issue path.
- `FACTORY_NEW_FILES=<rel,rel>` — allowlist of plain relative paths the lap
  may create (a create mutation is
  `{"file":..., "create": true, "find": "", "replace": "<whole file>"}`);
  escape/symlink/already-exists are rejected. An entry containing an fnmatch
  glob character (`*`, `?`, `[`) is a pattern instead of one path, e.g.
  `FACTORY_NEW_FILES=index.html,styles.css,page.js,assets/*` authorizes any
  path matching those patterns. `*` also crosses `/`, so a bare `*` entry
  authorizes any plain relative create. Glob entries are still plain relative
  paths: `..` segments, absolute and `~` entries are rejected either way
  (`assets/../*` never authorizes anything). Empty = edit-only.
- `FACTORY_NATIVE_CONFIG=<json>` — trusted native commands:
  `{"verify": [[argv...], ...], "suite": [argv...], "prepare": [[argv...]],
  "task_kind": "bug|enhancement", "merge_mode": "auto|review"}`. The suite is
  the one verify argv whose authoritative TAP `# tests N` (N > 0) is parsed.
  Unset = the historical Python gate.
- `merge_mode: "review"` — stop after local verification: retain a local
  `review/<run-id>` ref and `merge.json`, no push/PR/merge/deploy/close.
- `REVIEWER_API`/`IMPLEMENTER_API` (`openai-completions|openai-responses`),
  `REVIEWER_REASONING_EFFORT`, `IMPLEMENTER_MAX_TOKENS_FIELD`,
  `FACTORY_HTTP_TIMEOUT_S`, `COST_CEILING_USD` — per-role transport and caps;
  defaults unchanged.

Do not run the supervisor (`src/supervisor.py`) expecting a local trial: it
dispatches real model calls and remote writes. Configuration details, native
gate contract and the exercised proof are in
`docs/PREREQUISITES_2026-10-02.md`.

For reference-led Sonnet website work, read
[`docs/SONNET_WEBSITE_PLAN.md`](docs/SONNET_WEBSITE_PLAN.md): integrated
safeguards versus proposed routing/usage/browser improvements, stage-specific
effort and budgets, and the owner taste gate. It is a plan, not an automatic
paid launch or a change to model-role/provider defaults.
