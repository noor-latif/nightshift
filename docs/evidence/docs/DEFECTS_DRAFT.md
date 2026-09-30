# Proposed defect set for the toy pastebin (`noor-latif/toy-product`)

Proposal only — `harness/mutations/defects.json` is owner-protected; the owner installs.

## Schema

Followed the scaffold's own `_how_to_write_one` guidance: `id`, `file`, `find` (short exact snippet), `replace`, `why`. The scaffold's `_copy` list is stale (names `app`, `tests`, `.factory`, `pyproject.toml`; the actual layout has `app.py`, `app_test.py`, `harness/`, no `.factory`/`pyproject.toml`) — the draft corrects it to `["app.py", "app_test.py", "harness"]`.

## Summary

| # | id | anchor (app.py) | mutation (one sentence) | must-fail test | criterion attacked |
|---|----|-----------------|-------------------------|----------------|--------------------|
| 1 | `health-revision-is-constant` | :47 | `/health` returns a frozen revision string instead of calling `current_revision()` | `test_health_reports_ok_and_git_revision`, `test_health_reports_factory_runtime_candidate_exactly` | health-revision identity |
| 2 | `paste-id-collides` | :34 | id generation replaced by the constant `"stable-id"` | `test_two_pastes_keep_distinct_ids_and_content`, `test_rapid_sequential_posts_each_resolve_with_own_content` | paste round-trip |
| 3 | `unknown-id-answers-400` | :50-51 | unknown paste id answers 400 "bad paste id" instead of 404 | `test_unknown_id_returns_404`, `test_get_without_id_returns_404` | unknown-id-404 (404↔400 swap) |
| 4 | `body-read-off-by-one` | :74 | body reader consumes `Content-Length - 1` bytes | `test_post_returns_201_with_non_empty_id` (and most of the suite) | paste round-trip (boundary off-by-one) |
| 5 | `non-dict-body-leaks-500` | :66 | the `isinstance(body, dict)` guard is dropped | **new** `test_post_rejects_non_dict_json_body` — must be added with install | malformed-body-400 (error path leaks 500) |
| 6 | `type-guard-reduced-to-truthiness` | :67 | `isinstance(content, str)` weakened to a truthiness check | `test_post_rejects_non_string_content`, `test_post_rejects_missing_content` | nonstring-content-400 |
| 7 | `responses-declared-plain-text` | :82 | every response declares `Content-Type: text/plain` instead of `application/json` | **new** `test_responses_declare_json_content_type` — must be added with install | content-type mishandling (all criteria) |

## Why each defect was chosen

1. **health-revision-is-constant** — mirrors the real §H incident: a build whose health endpoint lies about its revision has unverifiable provenance, and the constant looks plausible in isolation.
2. **paste-id-collides** — silent overwrite on the second write; every single-paste test passes, so only distinct-id assertions catch it. Classic "output that works until the second caller".
3. **unknown-id-answers-400** — a 404↔400 swap on the error path: still an error response, so shallow "non-2xx" checks pass while client retry/monitoring semantics break.
4. **body-read-off-by-one** — boundary off-by-one in the most boring possible place; breaks 100% of creates while reading like a defensible fix.
5. **non-dict-body-leaks-500** — a guard deleted, not added: valid JSON of the wrong shape crashes to 500 instead of 400, an error path that fails open.
6. **type-guard-reduced-to-truthiness** — the archetype of a subtly weakened guard: `not content` accepts `42`, `null`, and `[]` and still blocks only `""`, so the defect hides from anything that tests one non-string value and no others.
7. **responses-declared-plain-text** — content-type mishandling with zero behavioral difference to a body-ignoring client; only a header assertion notices.

## Verification performed (locally, throwaway copies)

- Every `find` anchor matches `app.py` exactly once.
- All seven mutations were applied to a local copy of `app.py` and the real `app_test.py` run against each: every defect fails at least one named test. (A hash-based replacement tool would not drift, but the anchors were also verified against the file as read from [redacted-host].)
- The two new tests (`test_post_rejects_non_dict_json_body`, `test_responses_declare_json_content_type`) were written and verified: they pass against the unmutated app and fail under their defect.

## Install (owner)

```sh
scp ~/repos/factory-docs/DEFECTS_DRAFT.json noor@[redacted-host]:~/factory-lab/toy-product/harness/mutations/defects.json
```

Then on [redacted-host], if installing from the machine holding this repo instead:

```sh
scp DEFECTS_DRAFT.json noor@[redacted-host]:~/factory-lab/toy-product/harness/mutations/defects.json
```

With the same install, add the two new tests from DEFECTS_DRAFT_APPENDIX below to `app_test.py` (`test_post_rejects_non_dict_json_body` in `PasteServiceTest`); without them, defect 5 has no failing test and escapes the gate.

## DEFECTS_DRAFT_APPENDIX — companion tests to add to `app_test.py`

```python
    def test_post_rejects_non_dict_json_body(self) -> None:
        status, body = self.request("POST", "/paste", b"[1, 2]")
        self.assertEqual(status, 400)
        self.assertTrue(json.loads(body)["error"])

    def test_responses_declare_json_content_type(self) -> None:
        _, body = self.request("POST", "/paste", {"content": "ct"})
        paste_id = json.loads(body)["id"]
        req = urllib.request.Request(self.base + f"/paste/{paste_id}")
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.headers["Content-Type"], "application/json")
        req = urllib.request.Request(self.base + "/paste", data=b"{}", method="POST")
        try:
            urllib.request.urlopen(req)
        except urllib.error.HTTPError as e:
            self.assertEqual(e.headers["Content-Type"], "application/json")
```
