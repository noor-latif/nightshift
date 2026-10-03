# Prerequisites for the Götalands Trafikskola frontend slice (2026-10-02)

Authorized kernel prerequisite work in the existing isolated jj workspace
`factory-spike-gts-prereq`, base `ac75bdd`. No website implementation,
launch, upstream push, paid calls, or model-setting/prewalk changes.

## Trusted launch configuration

`FACTORY_NATIVE_CONFIG` is JSON from the launch environment, not a candidate
file. Example planning configuration only; these npm commands were **not run**:

```json
{
  "prepare": [["npm", "ci"]],
  "verify": [["npm", "run", "test:guard"], ["npm", "run", "test"],
             ["npm", "run", "tokens:check"], ["npm", "run", "build"]],
  "suite": ["npm", "run", "test"],
  "task_kind": "enhancement",
  "merge_mode": "review"
}
```

Commands are nonempty argv arrays of nonempty strings, executed without a
shell. Missing keys preserve the Python default; explicit null, empty or
malformed command values fail configuration parsing. Native verification
requires `suite` to designate exactly one verify command. Invalid or null
`task_kind`/`merge_mode` are rejected rather than silently defaulted.

## Native verification

`verify_candidate` executes native commands directly and retains structured
statuses. `run_unit_tests` remains the historical Python oracle returning
`(ok, bounded_output)` with a nonzero discovered-test requirement; native
execution is not squeezed through that bool/string contract.

Each native command records argv, exit (null if unavailable), status,
monotonic duration, timeout and spawn-error fields, full stdout/stderr artifact
paths, and at most 8000 characters of report output. Lap artifacts live under
`baseline-commands`/`verify-commands` in its durable evidence directory.
Standalone callers without an evidence directory get retained temporary
artifact paths. Timeout/spawn inability is HOLD; nonzero exit is fail. HOLD
has explicit precedence over fail, independent of argv ordering.

Only the designated suite is TAP-parsed, against full stdout, not a tail or
build/guard output. Exactly one authoritative Node `# tests N` line with an
integer N > 0 is required; zero, missing, invalid or duplicate totals fail
even at exit zero. `# pass`/`# fail` are not test totals. Preparation uses the
same execution/evidence contract and propagates HOLD without flattening it.

## Actual sanitized model-call traces

`agent.chat(trace_dir=..., call_id=...)` appends actual request payloads and
received response bodies/events to `model-calls.jsonl`. No request headers
are recorded. Response headers are allowlisted. HTTP errors (including
401/402 bodies), transport errors and stream parse errors are traced.
Malformed JSON is traced and raised **without a newly introduced retry**;
existing transient/incomplete-stream retry behavior remains.

Sanitization traverses nested JSON, SSE chunk JSON and text; removes
credential-bearing keys, email fields/addresses, embedded bearer credentials,
and the exact supplied API key plus the configured key value. It never
scans arbitrary private environment variables. Numeric usage fields such
as `prompt_tokens` and request `max_tokens` remain actual values. Sanitized
JSON/SSE may be reserialized; original secret bytes are never persisted by
the trace writer. Trace-write failures raise rather than silently losing
proof. Request/response URL reflects the actual configured chat endpoint.

Requested model is distinct from response metadata (actual model/provider/id,
timestamps/status when present), finish reason and usage. Missing served-model
metadata stays missing: no attribution or self-identity claim is invented.
No fallback was added. Existing completions remains the default for both roles.

## Explicit compatible role transport

`IMPLEMENTER_API`/`REVIEWER_API` accept `openai-completions` or
`openai-responses`; `REVIEWER_REASONING_EFFORT` supplies explicit reviewer
effort. Invalid API values fail configuration. The minimal Responses route
reuses the existing urllib transport, errors, traces and bounded retry policy:
`POST /v1/responses`, text-only `input` messages, `stream=false`, `store=false`,
`max_output_tokens`, and nested `reasoning.effort`. No SDK/tools/framework.
Completed output text is normalized to existing content/reasoning/finish/usage
fields. Incomplete max-output-token results use the existing length retry;
failed/pending/refused/unsupported output never becomes a completion. Malformed
JSON or shapes retain actual response-error evidence and raise without retry.
Original usage fields remain; actual input/output counts also map to the
existing prompt/completion token names. Provider cost extensions are retained,
not invented. API source: [OpenAI Responses create reference](https://developers.openai.com/api/reference/resources/responses/methods/create),
queried through Context7 during implementation.

Catalog snapshot `prerequisite-proof/catalog-snapshot-2026-10-02.json`
confirms exact `claude-sonnet-5.5` (completions) and `gpt-6.1-sol` (Responses),
not runtime health or paid-service availability. Approved per-run role values:
`IMPLEMENTER_MODEL=claude-sonnet-5.5 IMPLEMENTER_API=openai-completions`,
`REVIEWER_MODEL=gpt-6.1-sol REVIEWER_API=openai-responses
REVIEWER_REASONING_EFFORT=medium`. No live model call or persisted role/model
override was made. Existing Luna-high implementer/GLM reviewer defaults stay
unchanged; optional routine helper is not a mandatory third call.

## Enhancement and review containment

Enhancements skip dispatch's bug RED recheck only. The **direct lap** executes
real baseline preparation/native suite and global scenarios before any model
call or mutation, saves `baseline.json`, and stops on non-pass. Issue-specific
acceptance scenarios run on the candidate, not the baseline. Bug dispatch
RED behavior is unchanged. Owner visual acceptance is outside text review.

After reviewer acceptance and real candidate verification, review mode stops
locally: no push, PR, merge, deploy or issue close. `awaiting-review` is terminal
in selector/supervisor bookkeeping and is never counted as merged. Before
cleanup, the product repository retains a unique `review/<run-id>` git branch
pointing to the actual candidate commit. `merge.json` locates the repository,
ref, commit, source tree, changed paths and `applied.diff`, explicitly reports
`pushed=false`, `merged=false`, `pr=null`, and provides read-only inspection
and owner-selected detached-worktree argv. The result file locates the evidence
directory. Cleanup removes only the factory worktree, not the retained ref.
No arbitrary source-copy cleanup workaround is used.
Tracked source must remain identical to HEAD after baseline/candidate gates;
otherwise the lap fails closed before model work or review retention/merge.
Retained changed paths come from the committed base-to-HEAD diff. The existing
post-verification wall-clock check precedes review retention and push.

## Exercised proof versus pending work

The correction smoke uses stdlib localhost HTTP plus an isolated temporary
product git fixture: actual baseline, mutations, commit, streamed completions
implementer and nonstream Responses-medium reviewer, native commands and issue
scenario, review stop,
cleanup and source retrieval from the retained ref. It also exercises bad
baseline refusal before chat, invalid configuration, authoritative suite
boundaries, full artifacts/capped report, timeout partial output, order-independent
HOLD, recursive HTTP error-body secrecy, Responses malformed-shape/failed-body
evidence and output-limit retry, plus tracked-source drift refusal. This is a
synthetic local transport fixture, **not** proof of actual Sonnet/Sol service.

Proof directory:
`~/repos/factory-docs/gotalandstrafikskola-trial/prerequisite-proof/kernel-correction-evidence/`.
The first smoke failed its candidate acceptance due to the fixture's stale
Python bytecode; both failure evidence and corrected successful run remain.
The corrected fixture disables bytecode writing; it does not weaken gates.
Exact command/output/hashes and reviewed local jj revision are saved separately.
Earlier `smoke-output.txt`/18-check claims are historical partial evidence,
not readiness evidence for this corrected contract.

Permanent behavioral regressions were added following existing unittest
conventions. **They were not executed: owner permission is required.**
No site tests, builds, installs, browser, remote provisioning, paid API, push,
or launch was performed. Real product baseline, least-privilege execution,
runtime provider health/cost, operator captures and final site acceptance
remain pending; catalog/API routing metadata is established, but kernel fixture
proof does not certify website readiness.

## Integrated into the canonical checkout (2026-10-03)

The saved chain above was integrated into `~/repos/factory-spike` on top of
`main` = `ac75bdda` using jj only (local; no push/merge). Historical defaults
are unchanged, so an unconfigured run keeps the historical Python gate, the
`gh` task path and the edit-only mutation contract. Local-task/create/native/
review knobs are the opt-in layer described above; the canonical fresh-session
entrypoint is `python3 src/lap.py <issue>` from that checkout (see the repo
README). A fresh canonical subprocess lap — external task file, allowlisted
create, native enhancement baseline + suite, reviewer design context, review
stop — passes against a localhost fixture; evidence and hashes are in
`~/repos/factory-docs/kormotorn-trial/FRESH-RUN-INTEGRATION.md`.

Comment correction: the catalog declares `maxTokensField
"max_completion_tokens"` for the approved implementer, and the gateway
documents `max_tokens`/`max_completion_tokens` as aliases, so the earlier
"wrong field causes an empty completion" causal claim is retracted; the knob is
per-role configurability, not a proven root cause.

## Known limits

- A model that answers a tiny health/hello prompt is **not** thereby proven able
  to complete a full task. A successful short response does not establish enough
  usable output budget; hidden reasoning can consume the whole cap.
- Before declaring a call successful, inspect the retained trace: check the
  finish reason **and** the visible content. A usage-only stream with no
  choice/finish is not a completion, and `length`/partial output is not a
  complete candidate. The kernel already fails closed on both; never treat
  either as a pass or silently substitute another model.
- `max_tokens` and `max_completion_tokens` are documented aliases; the field
  name is not an established root cause of an empty completion (see the
  correction above). Callers cannot assert the exact upstream adapted cap when
  the gateway reports an adaptation header.
