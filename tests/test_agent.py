import json
import http.client
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from agent import (  # noqa: E402
    PermanentError,
    TransientError,
    chat,
    parse_stream,
    reviewer_prompt,
)


FIX = os.path.join(os.path.dirname(__file__), "fixtures")


def load(name):
    with open(os.path.join(FIX, name), "rb") as f:
        return f.read()


class FakeResp:
    def __init__(self, raw):
        self._raw = raw

    def read(self):
        return self._raw

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class FakeOpener:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def open(self, req, timeout=None):
        self.calls.append(req)
        r = self.responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


class TestParseStream(unittest.TestCase):
    def test_reasoning_and_content_split_with_usage(self):
        got = parse_stream(load("sse_stream.txt"))
        self.assertEqual(got["content"], "OK")
        self.assertEqual(got["reasoning"], "thinking...")
        self.assertEqual(got["finish_reason"], "stop")
        self.assertEqual(got["usage"]["cost"], 0.00001)
        self.assertEqual(got["usage"]["prompt_tokens"], 26)

    def test_stream_without_finish_reason_is_transient(self):
        with self.assertRaises(TransientError):
            parse_stream(load("sse_truncated.txt"))


class TestChat(unittest.TestCase):
    def test_incomplete_read_retried_then_succeeds(self):
        # cut stream mid-body: same transient class as "ended without
        # finish_reason"; must not escape chat() as a lap crash
        class CutResp:
            def __init__(self):
                self.calls = 0

            def read(self):
                self.calls += 1
                raise http.client.IncompleteRead(b"partial", 700657)

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        cut = CutResp()
        op = FakeOpener([cut, FakeResp(load("sse_stream.txt"))])
        got = chat([{"role": "user", "content": "x"}], "m", api_key="k", opener=op)
        self.assertEqual(got["content"], "OK")
        self.assertEqual(cut.calls, 1)
        self.assertEqual(len(op.calls), 2)

    def test_key_in_header_not_in_url_or_error(self):
        op = FakeOpener([FakeResp(load("sse_stream.txt"))])
        chat([{"role": "user", "content": "hi"}], "m", api_key="sekrit", opener=op)
        self.assertNotIn("sekrit", op.calls[0].full_url)
        self.assertEqual(op.calls[0].get_header("Authorization"), "Bearer sekrit")

    def test_pinned_model_adds_provider_allow_list(self):
        import agent

        agent.PROVIDER_PINS["m"] = "family-id"
        try:
            op = FakeOpener([FakeResp(load("sse_stream.txt"))])
            chat([{"role": "user", "content": "x"}], "m", api_key="k", opener=op)
        finally:
            del agent.PROVIDER_PINS["m"]
        sent = json.loads(op.calls[0].data)
        self.assertEqual(sent["provider"], "family-id")

    def test_pinned_model_list_pin_passes_through(self):
        import agent

        agent.PROVIDER_PINS["m"] = ["family-id", "openrouter"]
        try:
            op = FakeOpener([FakeResp(load("sse_stream.txt"))])
            chat([{"role": "user", "content": "x"}], "m", api_key="k", opener=op)
        finally:
            del agent.PROVIDER_PINS["m"]
        sent = json.loads(op.calls[0].data)
        self.assertEqual(sent["provider"], ["family-id", "openrouter"])

    def test_unpinned_model_has_no_provider_key(self):
        op = FakeOpener([FakeResp(load("sse_stream.txt"))])
        chat([{"role": "user", "content": "x"}], "m", api_key="k", opener=op)
        sent = json.loads(op.calls[0].data)
        self.assertNotIn("provider", sent)

    def test_permanent_no_sellers_not_retried(self):
        body = b'{"error":{"type":"invalid_request_error","code":"no_sellers_for_model","message":"nope"}}'

        class Err(Exception):
            code = 404

            def read(self):
                return body

        import urllib.error

        op = FakeOpener([urllib.error.HTTPError("u", 404, "nf", {}, Err())])
        with self.assertRaises(PermanentError):
            chat([{"role": "user", "content": "x"}], "m", api_key="k", opener=op)
        self.assertEqual(len(op.calls), 1)  # exactly one attempt

    def test_transient_5xx_retried_once(self):
        import urllib.error

        class Err(Exception):
            code = 502

            def read(self):
                return b"{}"

        op = FakeOpener([
            urllib.error.HTTPError("u", 502, "bad", {}, Err()),
            FakeResp(load("sse_stream.txt")),
        ])
        got = chat([{"role": "user", "content": "x"}], "m", api_key="k", opener=op)
        self.assertEqual(got["content"], "OK")
        self.assertEqual(len(op.calls), 2)

    def test_null_content_length_doubles_max_tokens_then_succeeds(self):
        # gotcha 3: reasoning ate the budget → finish_reason length + null content
        starved = (
            b'data: {"choices":[{"delta":{"reasoning_content":"long thought"}}]}\n'
            b'data: {"choices":[{"delta":{},"finish_reason":"length"}]}\n'
            b"data: [DONE]\n"
        )
        op = FakeOpener([FakeResp(starved), FakeResp(load("sse_stream.txt"))])
        got = chat([{"role": "user", "content": "x"}], "m",
                   max_tokens=16, api_key="k", opener=op)
        self.assertEqual(got["content"], "OK")
        self.assertEqual(len(op.calls), 2)
        self.assertIn(b'"max_tokens": 32', op.calls[1].data)
        self.assertIn(b'"max_tokens": 16', op.calls[0].data)

    def test_stream_ended_transient_retried_once(self):
        op = FakeOpener([FakeResp(load("sse_truncated.txt")), FakeResp(load("sse_stream.txt"))])
        got = chat([{"role": "user", "content": "x"}], "m", api_key="k", opener=op)
        self.assertEqual(got["finish_reason"], "stop")

    def test_stream_ended_twice_raises(self):
        op = FakeOpener([FakeResp(load("sse_truncated.txt")), FakeResp(load("sse_truncated.txt"))])
        with self.assertRaises(TransientError):
            chat([{"role": "user", "content": "x"}], "m", api_key="k", opener=op)


class TestReviewerPrompt(unittest.TestCase):
    def test_fresh_context_no_implementation_reasoning(self):
        p = reviewer_prompt("+def add(a,b): return a+b", "returns sum", )
        self.assertIn("+def add", p)
        self.assertIn("returns sum", p)
        # the reviewer template must not carry implementation reasoning fields
        self.assertNotIn("reasoning", p.lower().replace("reasoning.", ""))


if __name__ == "__main__":
    unittest.main()
