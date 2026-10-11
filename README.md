# nightshift

Time-boxed spike answering one question: can our own code run factory laps
(issue → implement → verify → merge → deploy) unattended, with zero human
interventions and zero false greens. The evidence ledger is published
under `docs/evidence/` (MANIFEST.md is the index).

## Status and trust model — read this before running anything

This is a **spike**, published because its evidence ledger is worth reading. It
is not hardened software, and it is not sandboxed.

- **Native commands run unsandboxed, as you.** Every `prepare`, `verify` and
  `suite` argv — and everything the qualifier dry-runs — is executed through
  `subprocess` as the invoking user with that user's full permissions. There is
  no container, no namespace, no seccomp filter and no filesystem jail around
  them. A command you configure, or that a candidate repo's documentation leads
  you to configure, can do anything your account can do: read `~/.ssh`, read
  your env, delete files, use the network. The only containment in the design is
  the **per-repo trust model**: you read a repo's build/test commands and decide
  to run them. (`unshare -rn` appears in `qualify.py` only as the opt-in G5
  dead-egress *probe*; it never wraps a lap's own commands.) The reasoning, and
  the microVM path reserved for hostile-repo mode, are in
  `SANDBOX-MICROVM-VS-NIX_2026-10-07.md` in the working docs tree.
- **Model calls go through the surplus gateway.** `src/agent.py` speaks the
  gateway's OpenAI-compatible API (`SURPLUS_BASE_URL` + `/v1/chat/completions`,
  or `/v1/responses` per role); `agent.chat()` is the only egress. A missing
  or rotated key, or a gateway outage, ends the lap at `gate=gateway` — it never
  turns into a green.
- **Cost is a gate, not a report.** `COST_CEILING_USD` (default $0.01) is
  enforced at runtime: cumulative recorded spend past it raises and fails the
  lap with `gate=cost`. Recorded spend is a *lower* bound — a call whose response
  carried no usage block is recorded as a row with `usage: null` and
  `missing_usage: true` rather than dropped.
- **Recipes are operator-side.** The kernel reads its gate config from the
  **launch env** (`FACTORY_NATIVE_CONFIG`), never from the checkout, so a recipe
  inside a candidate repo cannot point verify at `/bin/true`. The recipe store is
  the trust anchor.

The working reports behind this spike (field tests, lap runs, defect
post-mortems) live in `~/repos/factory-docs/`; `docs/evidence/` here is the
frozen, redacted ledger that ships with the repo.

### Gate order inside a lap

Within a lap the two quality gates run in a fixed order: **mechanical
verification first, LLM review second** (implement → mutation-apply → commit
→ verify → review → merge). A candidate that fails the native verify ends
there — no reviewer call is spent on a candidate the oracle already rejected.
A candidate that passes verify is then reviewed with the mechanical result
inlined into the reviewer prompt as a receipt (suite status/count, oracle
verdicts); the reviewer's remit is what the oracle does not cover, and
overriding an executed result requires quoting deciding text and arguing why
the mechanical result does not decide the criterion. Nothing merges unless
both gates pass. The order is deliberate: a verified-clean candidate was once
false-rejected by the reviewer ahead of the oracle's own control verdict, and
the review literature shows evidence-quote rubrics amplify such false
rejections — execution evidence belongs in the loop before judgment, not
after it.

## Layout

- `src/` — nine modules: `settings.py` (literal config values only),
  `supervisor` (tick loop), `selector` (issue claim), `agent` (surplus LLM
  calls), `lap` (issue→merge chain), `verify` (oracle-first probes),
  `merge` (squash + tree-equality), `deploy` (PID-file launch +
  identity read-back), `qualify.py` (per-repo build/test distillation).
- `src/prompts/` — the three role prompts (`implementer.txt`, `reviewer.txt`,
  `qualifier.txt`). They are files, not string literals, so what a model is told
  is reviewable in the diff.
- `scripts/` — the two entrypoints: `run-lap.sh` (detached paid lap) and
  `qualify.sh` (recipe distillation).
- `scenarios/` — HTTP scenario probes for the toy-product rig.
- `tests/` — stdlib unittest; run offline, no network/ssh/gh/API key needed.
  The supervisor test's child process strips `NTFY_TOPIC` (a fixture once
  posted to the operator's real topic); this is a child-env fix, not a
  general network restriction — other clones are not presumed fixed.

## Tools

`tools/preflight_instance.py <task-file> <env-file> <repo-at-base>` is the
required step before banking any instance: it refuses (non-zero, with the
reason) an instance whose `SCOPE_PATHS` a `CODE_PATHS` glob cannot reach,
whose `CODE_PATHS` view exceeds `CHECKOUT_CHAR_BUDGET`, or whose `CODE_PATHS`
matches no file — the three authoring defects that make an oracle unreachable
regardless of the model's code.

## Run

    python3 -m unittest discover -s tests

Python 3 stdlib only. No pip dependencies. There is one lap path: the
supervisor and the lap run on the rig itself, so the deploy script is
executed locally with `bash` — no ssh hop. Scope: time-boxed spike —
issue → implement → verify → merge → deploy laps, zero human interventions,
zero false greens.

## Qualify a repo (distil its recipe) — the step before any lap

A lap needs a trusted `FACTORY_NATIVE_CONFIG`: the prepare/verify/suite argv for
one repo at one pinned base commit. `src/qualify.py` produces it — deterministic
by default (**zero model calls**), with one optional paid proposal.

    # 1. deterministic pass over a clone (free): dry-runs every proposed argv
    #    in a throwaway worktree at the pinned base and grades G1-G11
    scripts/qualify.sh ~/path/to/clone --netns --probe --out /tmp/recipe.json

    # 2. let the qualifier model propose commands the docs state but the
    #    deterministic layer cannot infer (ONE call; every proposal is
    #    re-run and bound, or discarded)
    scripts/qualify.sh ~/path/to/clone --agent --out /tmp/recipe.json

    # 3. read it, then emit the launch env the kernel already trusts
    scripts/qualify.sh ~/path/to/clone --render          # human view
    scripts/qualify.sh ~/path/to/clone --emit-env -      # export lines

Exit status is 0 for `go`/`partial` and 1 for `no-go`; the JSON printed on the
default path carries `status`, `gap`, `gate` and the recipe path. A recipe is a
`nightshift.recipe/1` document whose `gate` table is the evidence for its
verdict: G1/G2 dry-run the argv, G3 binds the test total through the kernel's own
parser, G3b/G4/G5 probe collection, determinism and dead-egress hermeticity,
G6/G7/G8 check build hygiene, argv provenance and that the emitted config parses
under `settings.py`, G9 A/B-tests hook neutralisation, G10 the adapter, G11 that
every clone in the chain is deep enough to resolve the base. The four task-level
keys (`FACTORY_TASK_FILE`, `CODE_PATHS`, `FACTORY_NEW_FILES`, `SCENARIOS_DIR`)
are emitted commented out: they are the operator's to author, never the model's.

Honest limits of the gate table, today: every `skip` carries the reason it was
not measured. The enum: `skip(G3)` (blocked by G3 failing), `skip(no-netns)`
(`--netns` not requested), `skip(no-probe)` (`--probe` not requested or no
probe configured), `skip(no-hooks)` (no installed hooks: the G9 A/B would be
vacuous), `skip(no-hooks-ab)` (`--no-hooks-ab`), `skip(no-escape)` (poisoned
hooks but no escape env declared), `skip(no-commands)` (no build/test commands
were proposed or seeded), `skip(no-dry-run)` (`--no-dry-run`: static pass
only), `skip(no-adapter)` (no adapter to probe), `skip(operator)` (the seed
disables the adapter probe), `skip(bad-probe)` (the declared collection probe
is malformed), `skip(no-measure)` (unreachable in practice; kept honest). A
skip is recorded *instead of* a measurement, never as one — the marker says
what was missing, not what passed. G9 never passes vacuously: a clone with no
installed hooks reports `skip(no-hooks)` — the A/B would pass both legs. The
`network` field flows through from the qualifier proposal when the operator
seed does not pin one; it stays seed > proposal > `--netns`-derived >
`unknown`. Read `gate` as "measured green" only where it says `pass` **and**
the corresponding receipt exists under the evidence dir.

## Local lap — canonical entrypoint

This checkout, `~/repos/factory-spike`, is the canonical source. Other
clones/workspaces (`~/nightshift`, trial workspaces) are not it.

    cd ~/repos/factory-spike
    set -a; . env.sh; set +a          # export the lap env first (caller-owned)
    scripts/run-lap.sh <issue-number> # detached; prints lap pid, pidfile, log, progress/stop cmds

On a first run, copy `env.example.sh` to `env.sh` and fill it in (the template
lists every variable the lap reads, with its default).

Paid laps go through `scripts/run-lap.sh`, never a bare `python3 src/lap.py`:
the launcher `setsid`+`nohup`s the child into its own session, so an agent
command timeout kills the launcher, not the open model stream. **NEVER wrap a
lap in a command with a short deadline** — a 300s command deadline once killed
a lap mid-stream and the request still billed. The launcher sources nothing
itself, so the caller MUST have exported the lap env first (as above). An
optional second argument names the logfile (default
`state/lap-<issue>-<timestamp>.log`).

`setsid` forks (util-linux 2.42.2 forks even in the foreground, so `--fork`
changes nothing), which means the launcher's own `$!` is a transient wrapper
that is already gone while the lap runs and can neither be watched nor killed.
The child therefore publishes its own pid: the setsid'd `bash -c` writes `$$`
to `<logfile>.pid` (covered by the `*.pid` ignore rule) and then `exec`s the
lap, so that pidfile holds the live lap process. The launcher prints that real
pid and the working stop command `kill "$(cat <logfile>.pid)"`; it exits
non-zero if the child never publishes a live pid.

The logfile is crash capture only — `src/lap.py` writes nothing to stdout, so
`tail -f <logfile>` is NOT live progress (it stays empty on a healthy lap).
Progress lives in the evidence dir, `state/evidence/<timestamp>-issue-<n>/
timeline.json` (one row per gate), and the terminal artifact is
`state/lap-result.json`. To wait for the end:

    while [ ! -s state/lap-result.json ]; do sleep 5; done; cat state/lap-result.json

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
  "suite_runner": "tap|pytest", "suite_timeout_s": 600,
  "task_kind": "bug|enhancement", "merge_mode": "auto|review"}`. The suite is
  the one verify argv whose authoritative total (N > 0) is parsed; the runner
  picks the parser and defaults to `tap`, so omitting it keeps the historical
  Node TAP contract unchanged. `suite_timeout_s` (60..3600, default 600)
  replaces the timeout for the suite argv only; prepare and non-suite verify
  commands keep 600. Unset = the historical Python gate.
- `merge_mode: "review"` — stop after local verification: retain a local
  `review/<run-id>` ref and `merge.json`, no push/PR/merge/deploy/close.
- `REVIEWER_API`/`IMPLEMENTER_API` (`openai-completions|openai-responses`),
  `REVIEWER_REASONING_EFFORT`,
  `FACTORY_HTTP_TIMEOUT_S`, `COST_CEILING_USD` — per-role transport and caps;
  defaults unchanged.

Authoritative suite totals, one parser per runner. The zero-tests signature is
always a FAIL — never a pass and never a HOLD:

- `tap` (default) — suite `node --test --test-reporter=tap`; total = exactly
  one `# tests N` line with N > 0. Missing, zero or duplicate `# tests` lines
  are unknown.
- `pytest` — suite `python3 -m pytest -q -p no:cacheprovider`; total = exactly
  one summary line ending `in X.XXs` that carries `N passed`, N >= 1. Exit 5
  with `no tests ran`, `collected 0 items`, and an all-skipped summary (no
  `passed` count) are all zero-tests signatures.

A pytest instance, copy-paste shape:

    {
      "verify": [["python3", "-m", "pytest", "-q", "-p", "no:cacheprovider"]],
      "suite":  ["python3", "-m", "pytest", "-q", "-p", "no:cacheprovider"],
      "suite_runner": "pytest",
      "suite_timeout_s": 900,
      "task_kind": "bug",
      "merge_mode": "auto"
    }

`suite_runner` selects a parser, never a command: it is a closed enum, not a
shell fragment and not a path into the checkout. pytest is a candidate-side
runner invoked by argv — the harness's own suite stays stdlib `unittest`
(`python3 -m unittest discover -s tests`), so the kernel keeps its "no pip
dependencies" property.

Do not run the supervisor (`src/supervisor.py`) expecting a local trial: it
dispatches real model calls and remote writes. Configuration details, native
gate contract and the exercised proof are in
`docs/PREREQUISITES_2026-10-02.md`.

For reference-led Sonnet website work, read
[`docs/SONNET_WEBSITE_PLAN.md`](docs/SONNET_WEBSITE_PLAN.md): integrated
safeguards versus proposed routing/usage/browser improvements, stage-specific
effort and budgets, and the owner taste gate. It is a plan, not an automatic
paid launch or a change to model-role/provider defaults.
