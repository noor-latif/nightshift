# Mission

**Derived from:** PRD.md (pastebin micro-service)
**Last reconciled with it:** 2026-09-20

## What Pastebin Micro-Service is

A minimal HTTP pastebin: create a paste, read it back, health check. Single Python file,
stdlib only, in-memory storage, for the factory-lab. A user POSTs content and gets an id;
anyone with the id GETs the content back.

Single process, single tenant, no persistence across restarts, no auth — these are
invariants, not gaps.

## Who it is for

The factory itself. This product exists to exercise the factory pipeline end to end.

## What it must never become

- A database-backed service
- A multi-tenant SaaS
- An authenticated service
- A service with any dependency beyond the Python stdlib
- A service that persists data to disk

## Out-of-scope requests the factory must refuse

- "Add SQLite/file persistence" — storage is in-memory by design
- "Add user accounts or API keys" — no auth, ever
- "Add rate limiting" — out of scope for a lab service
- "Add a web UI" — HTTP API only
- "Add metrics/tracing endpoints" beyond /health — health is the only ops surface
- "Switch to FastAPI/Flask" — stdlib only
- "Add paste expiry/TTL" — v1 is permanent-until-restart
