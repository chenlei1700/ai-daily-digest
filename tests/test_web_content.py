from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import httpx

from ai_daily_digest.models import Item
from ai_daily_digest.web_content import enrich_item


ARTICLE = " ".join(["This is a verified article about AI evaluation and product quality."] * 8)


class WebContentTests(unittest.TestCase):
    def test_extracts_html_and_records_versioned_evidence(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                request=request,
                headers={"content-type": "text/html", "etag": '"page-v1"'},
                text=f"<html><head><title>Guide</title></head><body><nav>Menu</nav><article>{ARTICLE}</article></body></html>",
            )

        item = Item("ai_evals", "Guide", "https://example.com/guide", "Example")
        with TemporaryDirectory() as tmp, httpx.Client(transport=httpx.MockTransport(handler)) as client:
            ok, reason = enrich_item(item, client, Path(tmp))

        self.assertTrue(ok)
        self.assertEqual(reason, "verified")
        self.assertNotIn("Menu", item.content)
        self.assertEqual(item.provenance["status"], "verified")
        self.assertIn("content_sha256", item.provenance)
        self.assertEqual(item.source_version, 'etag:"page-v1"')

    def test_rejects_broken_link(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(404, request=request, text="missing")

        item = Item("ai_news", "Missing", "https://example.com/missing", "Example")
        with TemporaryDirectory() as tmp, httpx.Client(transport=httpx.MockTransport(handler)) as client:
            ok, reason = enrich_item(item, client, Path(tmp))

        self.assertFalse(ok)
        self.assertEqual(reason, "http_404")
        self.assertEqual(item.provenance["http_status"], 404)

    def test_revalidates_cached_content_with_conditional_request(self):
        calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            if calls == 1:
                return httpx.Response(
                    200,
                    request=request,
                    headers={"content-type": "text/html", "etag": '"page-v1"'},
                    text=f"<article>{ARTICLE}</article>",
                )
            self.assertEqual(request.headers.get("if-none-match"), '"page-v1"')
            return httpx.Response(304, request=request)

        with TemporaryDirectory() as tmp, httpx.Client(transport=httpx.MockTransport(handler)) as client:
            first = Item("ai_evals", "Guide", "https://example.com/guide", "Example")
            second = Item("ai_evals", "Guide", "https://example.com/guide", "Example")
            self.assertTrue(enrich_item(first, client, Path(tmp))[0])
            self.assertTrue(enrich_item(second, client, Path(tmp))[0])

        self.assertEqual(second.provenance["cache_state"], "revalidated")
        self.assertEqual(first.provenance["content_sha256"], second.provenance["content_sha256"])


if __name__ == "__main__":
    unittest.main()
