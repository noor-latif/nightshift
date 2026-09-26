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
import urllib.error
import urllib.request

from settings import (
    MIN_MAX_TOKENS,
    PROVIDER_PINS,
    SURPLUS_API_KEY_ENV,
    SURPLUS_BASE_URL,
    SURPLUS_CHAT_PATH,
)


class PermanentError(Exception):
    """Gateway said this will never work (e.g. no sellers for model)."""


class TransientError(Exception):
    """Worth one retry."""


def chat_url(base_url=SURPLUS_BASE_URL):
    return base_url.rstrip("/") + SURPLUS_CHAT_PATH


def parse_stream(raw):
    """Parse recorded/streamed SSE bytes once at the end.

    Returns {"content", "reasoning", "finish_reason", "usage"} where usage is
    the dict from the stream (contains cost in USD) or None.
    """
    content_parts, reasoning_parts = [], []
    finish_reason, usage = None, None
    for line in raw.decode("utf-8", errors="replace").splitlines():
        if not line.startswith("data:"):
            continue
        payload = line[len("data:"):].strip()
        if not payload or payload == "[DONE]":
            continue
        chunk = json.loads(payload)
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
    return body


def reviewer_prompt(diff, criteria, _cache={}):
    """Fresh context: ONLY diff + criteria. Never the implementation reasoning."""
    if "reviewer" not in _cache:
        with open(os.path.join(os.path.dirname(__file__), "prompts", "reviewer.txt")) as f:
            _cache["reviewer"] = f.read()
    body = _cache["reviewer"]
    for k, v in {"{{diff}}": diff, "{{criteria}}": criteria}.items():
        body = body.replace(k, v)
    return body


def chat(messages, model, max_tokens=MIN_MAX_TOKENS, *, api_key=None, opener=None,
         base_url=SURPLUS_BASE_URL):
    """One chat completion, streaming, with exactly one transient retry."""
    api_key = api_key or os.environ[SURPLUS_API_KEY_ENV]
    # key used only inside headers; never logged, never printed
    attempt_max = max_tokens

    open_fn = opener.open if opener else urllib.request.urlopen

    for attempt in (1, 2):
        payload = json.dumps({
            "model": model,
            "messages": messages,
            "max_tokens": attempt_max,
            "stream": True,
            **({"provider": PROVIDER_PINS[model]} if model in PROVIDER_PINS else {}),
        }).encode()
        req = urllib.request.Request(
            chat_url(base_url), payload,
            {"Authorization": "Bearer " + api_key, "Content-Type": "application/json"},
        )
        try:
            with open_fn(req, timeout=120) as resp:
                raw = resp.read()
        except urllib.error.HTTPError as e:
            body = e.read()
            if e.code < 500:
                _raise_for_status_shape(body)  # may raise PermanentError
                raise TransientError("HTTP %d" % e.code)
            if attempt == 2:
                raise TransientError("HTTP %d after retry" % e.code)
            continue
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            if attempt == 2:
                raise TransientError("connection error after retry: %s" % e)
            continue
        try:
            result = parse_stream(raw)
        except TransientError:
            if attempt == 2:
                raise
            continue
        if result["finish_reason"] == "length" and not result["content"]:
            # reasoning ate the budget → double tokens, never accept null content
            attempt_max *= 2
            if attempt == 2:
                raise TransientError("reasoning exhausted max_tokens even doubled (%d)" % attempt_max)
            continue
        return result
    raise TransientError("unreachable")  # pragma: no cover
