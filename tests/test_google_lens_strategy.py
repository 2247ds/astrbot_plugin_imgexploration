"""Google Lens provider behavior tests."""

from __future__ import annotations

import unittest

from tests.serpapi_stub_helpers import SerpApiStubEnvironment


class GoogleLensStrategyTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.env = SerpApiStubEnvironment()
        self.addCleanup(self.env.close)

    def _strategy_with_statuses(
        self,
        statuses: list[int | Exception],
        payloads: list[dict] | None = None,
        *,
        max_results: int = 5,
        **strategy_options,
    ):
        session = self.env.install_fake_session(statuses, payloads)
        client = self.env.serpapi.SerpApiClient(api_keys=["key-a", "key-b", "key-c"])
        strategy = self.env.google_lens.GoogleLensStrategy(
            serpapi_client=client,
            max_results=max_results,
            **strategy_options,
        )
        return strategy, session

    async def test_search_options_are_sent_to_serpapi(self) -> None:
        strategy, session = self._strategy_with_statuses(
            [200],
            search_type="exact_matches",
            language="ja",
            country="jp",
            safe_search=True,
            auto_crop=True,
            no_cache=True,
        )

        await strategy.search("https://example.com/image.jpg")

        query = session.queries[0]
        self.assertEqual(["google_lens"], query["engine"])
        self.assertEqual(["https://example.com/image.jpg"], query["url"])
        self.assertEqual(["exact_matches"], query["type"])
        self.assertEqual(["ja"], query["hl"])
        self.assertEqual(["jp"], query["country"])
        self.assertEqual(["active"], query["safe"])
        self.assertEqual(["true"], query["auto_crop"])
        self.assertEqual(["true"], query["no_cache"])

    async def test_successful_result_parsing_keeps_thumbnail_urls(self) -> None:
        payload = {
            "visual_matches": [
                {
                    "title": "First Result",
                    "link": "https://source.example/1",
                    "source": "Example Source",
                    "thumbnail": "https://thumb.example/1.jpg",
                },
                {
                    "title": "Missing Link",
                    "thumbnail": "https://thumb.example/skipped.jpg",
                },
                {
                    "title": "Second Result",
                    "link": "https://source.example/2",
                    "thumbnail": "https://thumb.example/2.jpg",
                },
            ]
        }
        strategy, session = self._strategy_with_statuses([200], [payload])

        results = await strategy.search("https://example.com/image.jpg")

        self.assertEqual(["key-a"], session.calls)
        self.assertEqual(2, len(results))
        self.assertEqual("First Result", results[0].title)
        self.assertEqual("https://source.example/1", results[0].url)
        self.assertEqual("站点: Example Source", results[0].description)
        self.assertEqual("Second Result", results[1].title)
        self.assertIsNone(results[1].description)
        # 缩略图只保留 URL，由服务层统一下载
        self.assertEqual(
            ["https://thumb.example/1.jpg", "https://thumb.example/2.jpg"],
            [result.thumbnail for result in results],
        )
        self.assertEqual([None, None], [result.thumbnail_bytes for result in results])

    async def test_visual_matches_use_configured_limit(self) -> None:
        matches = [
            {
                "title": f"Result {index}",
                "link": f"https://source.example/{index}",
                "thumbnail": f"https://thumb.example/{index}.jpg",
            }
            for index in range(10)
        ]
        strategy, _ = self._strategy_with_statuses(
            [200],
            [{"visual_matches": matches}],
            max_results=3,
        )

        results = await strategy.search("https://example.com/image.jpg")

        self.assertEqual(
            [f"Result {index}" for index in range(3)],
            [result.title for result in results],
        )

    async def test_invalid_matches_do_not_count_toward_limit(self) -> None:
        matches = [
            {"title": "Result 0", "link": "https://source.example/0"},
            {"title": "Missing Link"},
            {"title": "Result 1", "link": "https://source.example/1"},
            {"title": "Result 2", "link": "https://source.example/2"},
        ]
        strategy, _ = self._strategy_with_statuses(
            [200],
            [{"visual_matches": matches}],
            max_results=2,
        )

        results = await strategy.search("https://example.com/image.jpg")

        self.assertEqual(["Result 0", "Result 1"], [result.title for result in results])

    async def test_string_boolean_options_are_normalized(self) -> None:
        strategy, session = self._strategy_with_statuses(
            [200],
            safe_search="false",
            auto_crop="false",
            no_cache="false",
        )

        await strategy.search("https://example.com/image.jpg")

        query = session.queries[0]
        self.assertNotIn("safe", query)
        self.assertEqual(["false"], query["auto_crop"])
        self.assertEqual(["false"], query["no_cache"])

    async def test_exact_matches_response_is_parsed(self) -> None:
        payload = {
            "exact_matches": [
                {
                    "title": "Original Source",
                    "link": "https://source.example/original",
                    "source": "Example",
                    "thumbnail": "https://thumb.example/original.jpg",
                }
            ],
            "visual_matches": [
                {
                    "title": "Visual Match",
                    "link": "https://source.example/visual",
                }
            ],
        }
        strategy, _ = self._strategy_with_statuses(
            [200],
            [payload],
            search_type="exact_matches",
        )

        results = await strategy.search("https://example.com/image.jpg")

        self.assertEqual(1, len(results))
        self.assertEqual("Original Source", results[0].title)
        self.assertEqual("https://source.example/original", results[0].url)
        self.assertEqual("https://thumb.example/original.jpg", results[0].thumbnail)
        self.assertIsNone(results[0].thumbnail_bytes)

    async def test_invalid_search_type_falls_back_to_default(self) -> None:
        strategy, _ = self._strategy_with_statuses([200], search_type="invalid")

        await strategy.search("https://example.com/image.jpg")

        self.assertEqual("all", strategy.search_type)

    async def test_products_response_uses_visual_matches(self) -> None:
        payload = {
            "visual_matches": [
                {
                    "title": "Product Match",
                    "link": "https://shop.example/product",
                }
            ]
        }
        strategy, _ = self._strategy_with_statuses(
            [200],
            [payload],
            search_type="products",
        )

        results = await strategy.search("https://example.com/image.jpg")

        self.assertEqual(["Product Match"], [result.title for result in results])

    async def test_no_results_error_returns_empty_result_without_retry(self) -> None:
        strategy, session = self._strategy_with_statuses(
            [200],
            [{"error": "Google Lens hasn't returned any results for this query."}],
        )

        result = await strategy.search("https://example.com/image.jpg")

        self.assertEqual([], result)
        self.assertEqual(["key-a"], session.calls)

    async def test_service_name_and_search_validation(self) -> None:
        with self.assertRaises(TypeError):
            self.env.google_lens.GoogleLensStrategy(["key-a"])

        client = self.env.serpapi.SerpApiClient(api_keys=[])
        strategy_no_keys = self.env.google_lens.GoogleLensStrategy(
            serpapi_client=client
        )
        self.assertEqual(strategy_no_keys.get_service_name(), "Google Lens")
        with self.assertRaises(self.env.models.ProviderSearchError):
            await strategy_no_keys.search("https://example.com/img.jpg")

        strategy = self.env.google_lens.GoogleLensStrategy(
            serpapi_client=self.env.serpapi.SerpApiClient(api_keys=["key-a"])
        )
        with self.assertRaises(self.env.models.ProviderSearchError):
            await strategy.search("base64://abc")
        with self.assertRaises(self.env.models.ProviderSearchError):
            await strategy.search("file:///local.png")


if __name__ == "__main__":
    unittest.main()
