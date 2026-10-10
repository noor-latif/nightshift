"""Agent: surplus-gateway chat calls via urllib (stdlib only).

Roles: implementer (settings.IMPLEMENTER_MODEL) and reviewer
(settings.REVIEWER_MODEL). Review is fresh-context: its prompt sees only the
diff + acceptance criteria, never implementation reasoning.

Streaming: request stream=true, append SSE chunks to a buffer, parse once at
the end. Retry once on transient errors (5xx / timeout / connection error /
stream ended without finish_reason / reasoning ate the token budget).
404 no_sellers_for_model is PERMANENT — never retried.
"""

import json
import os
import re
import time
import http.client
import urllib.error
import urllib.request

from settings import (
    HTTP_TIMEOUT_S,
    MIN_MAX_TOKENS,
    PROVIDER_PINS,
    SURPLUS_API_KEY_ENV,
    SURPLUS_BASE_URL,
    SURPLUS_CHAT_PATH,
    TRACE_HEADER_ALLOWLIST,
)


class PermanentError(Exception):
    """Gateway said this will never work (e.g. no sellers for model)."""


class TransientError(Exception):
    """Worth one retry."""


def parse_stream(raw):
    """Parse recorded/streamed SSE bytes once at the end.

    Returns {"content", "reasoning", "finish_reason", "usage"} where usage is
    the dict from the stream (contains cost in USD) or None.
    """
    content_parts, reasoning_parts = [], []
    finish_reason, usage = None, None
    metadata = []
    for line in raw.decode("utf-8", errors="replace").splitlines():
        if not line.startswith("data:"):
            continue
        payload = line[len("data:"):].strip()
        if not payload or payload == "[DONE]":
            continue
        try:
            chunk = json.loads(payload)
        except json.JSONDecodeError as e:
            raise TransientError("malformed SSE data line: %s" % e) from e
        identity = {k: chunk[k] for k in ("id", "model", "provider", "system_fingerprint", "created")
                    if k in chunk}
        if identity and identity not in metadata:
            metadata.append(identity)
        if chunk.get("usage"):
            usage = chunk["usage"]
        for choice in chunk.get("choices", []):
            if choice.get("finish_reason"):
                finish_reason = choice["finish_reason"]
            delta = choice.get("delta", {})
            if delta.get("content"):
                content_parts.append(delta["content"])
            if delta.get("reasoning_content"):
                reasoning_parts.append(delta["reasoning_content"])
    if finish_reason is None:
        raise TransientError("Stream ended without finish_reason")
    return {
        "content": "".join(content_parts),
        "reasoning": "".join(reasoning_parts),
        "finish_reason": finish_reason,
        "usage": usage,
        "response_metadata": metadata,
    }


def _raise_for_status_shape(raw):
    """404 with no_sellers_for_model / invalid_request_error = permanent."""
    try:
        body = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        return
    err = body.get("error")
    if not isinstance(err, dict):
        return
    if err.get("code") == "no_sellers_for_model" or err.get("type") == "invalid_request_error":
        raise PermanentError(err.get("message", "invalid request"))




_SECRET_MARKERS = ("authorization", "api_key", "api-key", "apikey",
                   "secret", "password", "cookie", "email")


def _sanitize(obj, secrets=()):
    """Sanitize nested JSON/SSE and embedded credentials, using only call keys."""
    if isinstance(obj, dict):
        return {_sanitize(k, secrets): ("[REDACTED]" if any(m in k.lower() for m in _SECRET_MARKERS)
                    or "token" in k.lower() and isinstance(v, str)
                    else _sanitize(v, secrets)) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize(v, secrets) for v in obj]
    if not isinstance(obj, str):
        return obj
    try:
        parsed = json.loads(obj)
    except (ValueError, TypeError):
        parsed = None
    if isinstance(parsed, (dict, list)):
        return json.dumps(_sanitize(parsed, secrets), ensure_ascii=False)
    if obj.startswith("data:") or "\ndata:" in obj:
        obj = "\n".join("data: " + _sanitize(line[5:].strip(), secrets)
                        if line.startswith("data:") else _sanitize(line, secrets)
                        for line in obj.splitlines())
    for secret in secrets:
        if secret:
            for representation in (secret, json.dumps(secret)[1:-1]):
                obj = obj.replace(representation, "[REDACTED]")
    obj = re.sub(r"(?i)\bbearer\s+[^\s\"'\\,}]+", "Bearer [REDACTED]", obj)
    obj = re.sub(r'''(?i)\b(?:api[_-]?key|token|secret|password)["']?\s*[:=]\s*(?:"[^"]*"|'[^']*'|[^\s,}]+)''',
                 "credential=[REDACTED]", obj)
    return re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", "[REDACTED]", obj)


def _safe_headers(resp):
    """Response headers reduced to the allowlist; auth never included."""
    return {k: resp.headers.get(k) for k in TRACE_HEADER_ALLOWLIST
            if resp.headers.get(k) is not None}


def write_trace(trace_dir, call_id, phase, *, payload_obj=None, raw=None,
                headers=None, error=None, secret_values=(), url=None, **extra):
    """Append one sanitized actual-call trace event to
    <trace_dir>/model-calls.jsonl. Actual outbound request/response bytes as
    sent/received — never reconstructed. A trace-write failure is loud
    (raises): silently dropping evidence is the failure mode this exists
    to prevent. Callers without a trace_dir pass None (no-op, historical
    behavior preserved)."""
    if not trace_dir:
        return
    os.makedirs(trace_dir, exist_ok=True)
    row = {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "call_id": call_id, "phase": phase,
           "url": url or (SURPLUS_BASE_URL.rstrip("/") + SURPLUS_CHAT_PATH)}
    if payload_obj is not None:
        # the actual outbound JSON, sanitized; model/params verbatim
        row["request"] = payload_obj
    if raw is not None:
        body = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else raw
        row["response_body"] = body
    if headers:
        row["response_headers"] = {k: v for k, v in headers.items()
                                   if k.lower() in TRACE_HEADER_ALLOWLIST}
    if error:
        row["error"] = str(error)
    row.update(extra)
    with open(os.path.join(trace_dir, "model-calls.jsonl"), "a") as f:
        json.dump(_sanitize(row, secret_values), f, default=str)
        f.write("\n")


def parse_response(raw):
    """Nonstream Responses text result; usage/served metadata stay actual."""
    body = json.loads(raw)
    status = body.get("status")
    if status == "incomplete" and (body.get("incomplete_details") or {}).get("reason") == "max_output_tokens":
        finish = "length"
    elif status == "completed" and not body.get("error"):
        finish = "stop"
    else:
        raise PermanentError("Responses result not completed: %s" % status)
    content, reasoning = [], []
    for item in body.get("output", []):
        if item.get("type") == "message":
            for part in item.get("content", []):
                if part.get("type") == "output_text":
                    content.append(part["text"])
                elif part.get("type") == "refusal":
                    raise PermanentError("Responses refusal")
        elif item.get("type") == "reasoning":
            reasoning.extend(p["text"] for p in item.get("summary", []) if p.get("type") == "summary_text")
        else:
            raise PermanentError("Responses returned unsupported non-text output")
    usage = body.get("usage")
    if usage is not None:
        usage = dict(usage)
        if "input_tokens" in usage:
            usage["prompt_tokens"] = usage["input_tokens"]
        if "output_tokens" in usage:
            usage["completion_tokens"] = usage["output_tokens"]
    metadata = {k: body[k] for k in ("id", "model", "provider", "created_at", "status", "incomplete_details") if k in body}
    return {"content": "".join(content), "reasoning": "".join(reasoning),
            "finish_reason": finish, "usage": usage, "response_metadata": [metadata]}


def implementer_prompt(issue, criteria, n, _cache={}):
    """One prompt per phase (stdlib re-expression; load-once template)."""
    if "implementer" not in _cache:
        with open(os.path.join(os.path.dirname(__file__), "prompts", "implementer.txt")) as f:
            _cache["implementer"] = f.read()
    body = _cache["implementer"]
    for k, v in {
        "{{title}}": issue["title"],
        "{{body}}": issue.get("body", ""),
        "{{criteria}}": criteria,
        "{{n}}": str(n),
    }.items():
        body = body.replace(k, v)
    return body + (
        "\n\nRegression-test mandate:\n"
        "For every behavior fix, and whenever the acceptance criteria demand a "
        "regression test, your mutation set MUST include a regression test in the "
        "provided files (use a writable provided `tests/` file when that view is "
        "present). The test must drive the fixed behavior and fail on the pre-fix "
        "code. Use only files shown in the provided checkout; do not create or "
        "reference files outside that provided-files view. The acceptance criteria "
        "are the source of truth for WHAT behavior to test; this mandate requires "
        "THAT a failing-pre-fix test accompany the behavior fix.\n"
    )


def reviewer_prompt(diff, criteria, files="", brief="", _cache={}):
    """Fresh context: diff + criteria + post-apply file view (candidate state).
    Never the implementation reasoning. The file view exists so criteria about
    code the diff does not touch are checkable instead of fail-closed. The
    design brief is the same direction the implementer was given, so a
    design-compliance criterion is checkable instead of unverifiable."""
    if "reviewer" not in _cache:
        with open(os.path.join(os.path.dirname(__file__), "prompts", "reviewer.txt")) as f:
            _cache["reviewer"] = f.read()
    body = _cache["reviewer"]
    if brief:
        body = body.replace("acceptance criteria:\n{{criteria}}",
                            "design brief the implementation was given:\n{{brief}}\n\n"
                            "acceptance criteria:\n{{criteria}}")
    for k, v in {"{{diff}}": diff, "{{criteria}}": criteria, "{{files}}": files,
                 "{{brief}}": brief}.items():
        body = body.replace(k, v)
    return body


def chat(messages, model, max_tokens=MIN_MAX_TOKENS, *, reasoning_effort=None,
         api_key=None, opener=None, trace_dir=None, call_id="call",
         base_url=SURPLUS_BASE_URL, api="openai-completions"):
    """Text call with existing retry policy; explicit compatible API route.

    trace_dir set → every actual attempt (request payload, response body,
    allowlisted headers, HTTP errors, transport errors, mid-stream cuts as a
    typed "stream-incomplete" fault with the partial bytes read) is appended
    to <trace_dir>/model-calls.jsonl, sanitized. Requested model/params are
    recorded verbatim; the RESPONSE model, if the gateway echoes one in
    the stream, is recorded separately (requested ≠ served — the GLM
    fallback incident)."""
    if api not in ("openai-completions", "openai-responses"):
        raise ValueError("unsupported text API: %s" % api)
    if not isinstance(model, str) or not model.strip():
        # A blank role model is an operator configuration error, not a
        # request: observed twice as a 120s transport timeout because the
        # gateway had no model to route. Fail before any HTTP call.
        raise ValueError("model must be a non-empty model id (got %r)" % (model,))
    responses = api == "openai-responses"
    url = base_url.rstrip("/") + ("/v1/responses" if responses else SURPLUS_CHAT_PATH)
    api_key = api_key or os.environ[SURPLUS_API_KEY_ENV]
    # key used only inside headers; never logged, never printed
    attempt_max = max_tokens
    trace_secrets = (api_key, os.environ.get(SURPLUS_API_KEY_ENV, ""))
    def trace(phase, **kw):
        write_trace(trace_dir, call_id, phase, secret_values=trace_secrets,
                    url=url, api=api, **kw)

    open_fn = opener.open if opener else urllib.request.urlopen

    for attempt in (1, 2):
        if responses:
            if any(m.get("role") not in ("system", "developer", "user", "assistant")
                   or not isinstance(m.get("content"), str) for m in messages):
                raise ValueError("Responses transport supports text messages only")
            payload_obj = {"model": model, "input": messages, "stream": False,
                           "store": False, "max_output_tokens": attempt_max,
                           **({"provider": PROVIDER_PINS[model]} if model in PROVIDER_PINS else {}),
                           **({"reasoning": {"effort": reasoning_effort}} if reasoning_effort else {})}
        else:
            payload_obj = {
                "model": model, "messages": messages, "max_tokens": attempt_max,
                "stream": True,
                **({"provider": PROVIDER_PINS[model]} if model in PROVIDER_PINS else {}),
                **({"reasoning_effort": reasoning_effort} if reasoning_effort else {}),
            }
        payload = json.dumps(payload_obj).encode()
        trace("request", payload_obj=payload_obj,
              attempt=attempt, requested_model=model)
        req = urllib.request.Request(
            url, payload,
            {"Authorization": "Bearer " + api_key, "Content-Type": "application/json"},
        )
        attempt_started = time.monotonic()
        try:
            with open_fn(req, timeout=HTTP_TIMEOUT_S) as resp:
                hdrs = _safe_headers(resp) if trace_dir else {}
                raw = resp.read()
        except http.client.IncompleteRead as e:
            # The provider cut the SSE body mid-chunk: the request billed but
            # nothing reached the caller. Typed fault at the stream-read
            # boundary — partial bytes actually read, elapsed time, the
            # requested model and the stream id header when the gateway sent
            # one — then the existing bounded retry below, unchanged.
            trace("stream-incomplete", payload_obj=payload_obj, attempt=attempt,
                  raw=e.partial, requested_model=model,
                  partial_bytes=len(e.partial or b""),
                  elapsed_s=round(time.monotonic() - attempt_started, 3),
                  stream_id=hdrs.get("x-request-id") or hdrs.get("request-id"),
                  error="%s: %s" % (type(e).__name__, e))
            if attempt == 2:
                raise TransientError("connection error after retry: %s" % e)
            continue
        except urllib.error.HTTPError as e:
            body = e.read()
            trace("http-error", payload_obj=payload_obj,
                  raw=body, headers=_safe_headers(e) if trace_dir else {}, attempt=attempt,
                  status=e.code, error="HTTP %d" % e.code)
            if e.code < 500:
                _raise_for_status_shape(body)  # may raise PermanentError
                raise TransientError("HTTP %d" % e.code)
            if attempt == 2:
                raise TransientError("HTTP %d after retry" % e.code)
            continue
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            trace("transport-error", payload_obj=payload_obj, attempt=attempt,
                  error="%s: %s" % (type(e).__name__, e))
            if attempt == 2:
                raise TransientError("connection error after retry: %s" % e)
            continue
        try:
            result = parse_response(raw) if responses else parse_stream(raw)
        except (TransientError, PermanentError, ValueError, TypeError, KeyError, AttributeError) as e:
            trace("response-error" if responses else "stream-error", raw=raw, headers=hdrs, attempt=attempt,
                  error="%s: %s" % (type(e).__name__, e))
            if not isinstance(e, TransientError):
                raise  # malformed/unsupported responses retain terminal behavior
            if attempt == 2:
                raise
            continue
        trace("response", raw=raw, headers=hdrs, attempt=attempt,
              requested_model=model, response_metadata=result["response_metadata"],
              finish_reason=result["finish_reason"], usage=result["usage"])
        if result["finish_reason"] == "length":
            # A length finish is incomplete whether or not it contains text.
            # Retry at a larger cap, and never let a second capped completion
            # flow to a caller as though it were complete.
            attempt_max *= 2
            if attempt == 2:
                if result["content"]:
                    raise TransientError(
                        "completion truncated at max_tokens even doubled (%d)" % attempt_max)
                # reasoning ate the budget → preserve the existing null-content contract
                raise TransientError("reasoning exhausted max_tokens even doubled (%d)" % attempt_max)
            continue
        if not (result["content"] or "").strip():
            # finish_reason=stop with zero content deltas: the provider ended
            # the stream normally but delivered reasoning only. Transport
            # defect, not an answer — left alone it reaches the caller as ''
            # and every downstream label for that is a confabulation (observed
            # as a reviewer "no parseable verdict" on a 0-byte review.txt).
            trace("empty-content", attempt=attempt,
                  finish_reason=result["finish_reason"], requested_model=model,
                  reasoning_chars=len(result["reasoning"] or ""),
                  usage=result["usage"],
                  elapsed_s=round(time.monotonic() - attempt_started, 3),
                  error="finish_reason=%s with no content deltas" % result["finish_reason"])
            if attempt == 2:
                raise TransientError(
                    "empty content after retry (finish_reason=%s, reasoning only)"
                    % result["finish_reason"])
            continue
        return result
    raise TransientError("unreachable")  # pragma: no cover
