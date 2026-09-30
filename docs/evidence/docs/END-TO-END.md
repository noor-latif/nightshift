# Runtime scenarios

Observable journeys for the pastebin service. Shared runtime verification owns execution
and evidence.

## A person creates a paste and reads it back

1. POST /paste with {"content": "factory smoke test"}.
2. Expect 201 and an id in the response body.
3. GET /paste/<that id>.
4. Expect 200 and content exactly "factory smoke test".

**What would make this fail:** a different id than returned, content mutated or empty,
non-201/200 status codes, or the id not resolving.

## An unknown paste 404s

1. GET /paste/does-not-exist-123.
2. Expect 404.

**What would make this fail:** 200 with empty content, 500, or a hang.

## Health check reports ok and revision

1. GET /health.
2. Expect 200, status "ok", and a non-empty revision string.

**What would make this fail:** missing revision, non-ok status, or non-200.
