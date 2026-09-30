# Surplus Gateway Smoke Test — 2026-09-24

Endpoint: `https://api.surplusintelligence.ai` ([OI]-compatible, `/v1/models`, `/v1/chat/completions`).
Auth: `Authorization: Bearer $SURPLUS_INTELLIGENCE_API_KEY` (key: [redacted-host] `~/.bashrc:30` and `~/factory-lab/toy-product/.factory/run.env`; never echoed).

## 1. Model discovery — GET /v1/models → 200, 419 models

Exact ids (deepseek/glm subset):

| Question | Answer |
|---|---|
| `deepseek-v4.1-flash` exists? | **Yes** (exact id `deepseek-v4.1-flash`) |
| `glm-5.3-flash` exists? | **Yes** (exact id `glm-5.3-flash`) |
| Effort-suffix convention? | No `:high`-style effort suffixes. Suffixes seen: `:web` (web-grounded variants), `-fast`, date suffixes (`-0731`, `-0813`), and `e2ee-` prefixed variants. |
| Other relevant ids | `deepseek-v4-flash`, `deepseek-v4-pro`, `glm-5.3`, `glm-5.2`, `glm-5.1`, `glm-5.1-non-thinking`, `glm-4.7-thinking`, plus `:web` variants of most |

Note: one model id in the list is the empty string `""` — harmless, but don't crash on it when enumerating.

## 2. Non-streaming chat — deepseek-v4.1-flash

| Metric | Value |
|---|---|
| Status | 200 |
| Latency | 1.93s (2.62s first attempt) |
| Content | `OK`, finish_reason `stop` |
| Usage | prompt_tokens 26, completion_tokens 13, total 39, `cost: 0.00001`, `buyer_cost_micro: 0` |

**Gotcha:** deepseek-v4.1-flash is a reasoning model — response has `reasoning_content` separate from `content`. With `max_tokens: 16` the budget was eaten by reasoning → `content: null`, finish_reason `length`. **The agent module must set a generous max_tokens and read `content` not `reasoning_content`.**

## 3. Streaming chat — deepseek-v4.1-flash (stream: true, SSE)

Status 200, SSE chunks arrive, finish_reason `stop`, assembled text `OK`, total 2.03s. Usage arrives in the stream too (prompt 26, completion 15, cost 1e-05). Note: reasoning streamed collapsed to few content chunks in this trivial case (1 content chunk) — for real prompts expect many reasoning-only chunks before content chunks; filter by `delta.content`.

## 4. Comparison — glm-5.3-flash (non-streaming)

| Metric | Value |
|---|---|
| Status | 200 |
| Latency | 3.14s |
| Content | `OK`, finish_reason `stop` (also reasoning model) |
| Usage | prompt 8, completion 7, cost 0.00001, buyer_cost_micro 0 |

## 5. Error path — nonexistent model id

Status **404**, body:

```json
{"error":{"type":"invalid_request_error","code":"no_sellers_for_model","message":"No available sellers for model 'totally-not-a-model-xyz'. ...","request_id":"01M388JJW6TBW62N4MXCYDY4BY"},"request_id":"..."}
```

Classification for the agent module: `error.code == "no_sellers_for_model"` (or `type == "invalid_request_error"`) → permanent, don't retry. Transient = 5xx / timeouts / connection errors.

## Chat-call incantation (no key inline)

```bash
curl -sS https://api.surplusintelligence.ai/v1/chat/completions \
  -H "Authorization: Bearer $SURPLUS_INTELLIGENCE_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"deepseek-v4.1-flash","messages":[{"role":"user","content":"hi"}],"max_tokens":512}'
```

```python
r = urllib.request.Request(
    "https://api.surplusintelligence.ai/v1/chat/completions",
    json.dumps(payload).encode(),
    {"Authorization": f"Bearer {os.environ['SURPLUS_INTELLIGENCE_API_KEY']}", "Content-Type": "application/json"})
```

## Verdict — agent module can rely on:

- `deepseek-v4.1-flash` and `glm-5.3-flash` are live exact ids on the gateway; auth works via `SURPLUS_INTELLIGENCE_API_KEY` sourced from [redacted-host] `~/.bashrc`.
- Chat responses are OpenAI-compatible (`choices[0].message.content`, `finish_reason`, `usage` with prompt/completion/total tokens + `cost` in USD + `buyer_cost_micro`); both target models are reasoning models — allocate max_tokens ≥ 512 and read `content` only.
- Streaming is real SSE with usage in-stream and a terminal `finish_reason`; filter `delta.content` (reasoning arrives as reasoning_content deltas).
- Missing model → 404 with `code: "no_sellers_for_model"`: classify as permanent, retry only 5xx/network errors.
