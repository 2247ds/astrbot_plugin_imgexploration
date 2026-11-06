"""Yandex Images provider behavior tests."""

from __future__ import annotations

import unittest

from tests.serpapi_stub_helpers import SerpApiStubEnvironment


class YandexImagesStrategyTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.env = SerpApiStubEnvironment()
        self.addCleanup(self.env.close)
        self.yandex = self.env.load_provider("yandex_images_strategy.py")

    def _strategy_with_statuses(
        self,
        statuses: list[int | Exception],
        payloads: list[dict] | None = None,
        *,
        max_results: int = 5,
        **strategy_options,
    ):
        session = self.env.install_fake_session(statuses, payloads)
        client = self.env.serpapi.SerpApiClient(api_keys=["key-a", "key-b"])
        strategy = self.yandex.YandexImagesStrategy(
            serpapi_client=client,
            max_results=max_results,
            **strategy_options,
        )
        return strategy, session

    async def test_search_options_are_sent_to_serpapi(self) -> None:
        strategy, session = self._strategy_with_statuses(
            [200],
            tab="similar",
            family_mode="strict",
            yandex_domain="yandex.ru",
            no_cache=True,
        )

        await strategy.search("https://example.com/image.jpg")

        query = session.queries[0]
        self.assertEqual(["yandex_images"], query["engine"])
        self.assertEqual(["https://example.com/image.jpg"], query["url"])
        self.assertEqual(["similar"], query["tab"])
        self.assertEqual(["2"], query["family_mode"])
        self.assertEqual(["yandex.ru"], query["yandex_domain"])
        self.assertEqual(["true"], query["no_cache"])

    async def test_default_options_send_russian_domain_and_moderate_family_mode(
        self,
    ) -> None:
        strategy, session = self._strategy_with_statuses([200])

        await strategy.search("https://example.com/image.jpg")

        query = session.queries[0]
        self.assertEqual(["about"], query["tab"])
        self.assertEqual(["1"], query["family_mode"])
        self.assertEqual(["false"], query["no_cache"])
        self.assertEqual(["yandex.ru"], query["yandex_domain"])

    async def test_blank_or_invalid_domain_falls_back_to_default(self) -> None:
        for yandex_domain in ("", "   ", None, "invalid", "yandex.example"):
            with self.subTest(yandex_domain=yandex_domain):
                strategy, session = self._strategy_with_statuses(
                    [200], yandex_domain=yandex_domain
                )

                await strategy.search("https://example.com/image.jpg")

                self.assertEqual(["yandex.ru"], session.queries[0]["yandex_domain"])

    async def test_domain_is_normalized(self) -> None:
        strategy, session = self._strategy_with_statuses(
            [200], yandex_domain=" YANDEX.BY "
        )

        await strategy.search("https://example.com/image.jpg")

        self.assertEqual(["yandex.by"], session.queries[0]["yandex_domain"])

    async def test_family_mode_values_are_mapped(self) -> None:
        for family_mode, expected in (
            ("off", "0"),
            ("Moderate", "1"),
            (" strict ", "2"),
            ("invalid", "1"),
            ("", "1"),
            (None, "1"),
        ):
            with self.subTest(family_mode=family_mode):
                strategy, session = self._strategy_with_statuses(
                    [200], family_mode=family_mode
                )

                await strategy.search("https://example.com/image.jpg")

                self.assertEqual([expected], session.queries[0]["family_mode"])

    async def test_invalid_tab_falls_back_to_default(self) -> None:
        strategy, session = self._strategy_with_statuses([200], tab="invalid")

        await strategy.search("https://example.com/image.jpg")

        self.assertEqual(["about"], session.queries[0]["tab"])

    async def test_about_tab_results_use_nested_thumbnail_and_snippet(self) -> None:
        payload = {
            "image_results": [
                {
                    "title": "First Result",
                    "snippet": "A description of the first result",
                    "link": "https://source.example/1",
                    "source": "source.example",
                    "thumbnail": {
                        "link": "https://thumb.example/1.jpg",
                        "serpapi_link": "https://serpapi.com/thumb/1",
                        "height": 100,
                        "width": 100,
                    },
                },
                {
                    "title": "Missing Link",
                    "thumbnail": {"link": "https://thumb.example/skipped.jpg"},
                },
                {
                    "title": "Second Result",
                    "link": "https://source.example/2",
                    "source": "second.example",
                    "thumbnail": {"serpapi_link": "https://serpapi.com/thumb/2"},
                },
                {
                    "title": "Third Result",
                    "link": "https://source.example/3",
                    "thumbnail": 12345,
                },
            ]
        }
        strategy, session = self._strategy_with_statuses([200], [payload])

        results = await strategy.search("https://example.com/image.jpg")

        self.assertEqual(["key-a"], session.calls)
        self.assertEqual(3, len(results))
        self.assertEqual("First Result", results[0].title)
        self.assertEqual("https://source.example/1", results[0].url)
        self.assertEqual("A description of the first result", results[0].description)
        self.assertEqual("Yandex Images", results[0].source)
        self.assertIsNone(results[0].similarity)
        self.assertIsNone(results[0].domain)
        self.assertEqual("站点: second.example", results[1].description)
        self.assertIsNone(results[2].description)
        # 缩略图只保留 URL，由服务层统一下载
        self.assertEqual(
            ["https://thumb.example/1.jpg", "", ""],
            [result.thumbnail for result in results],
        )
        self.assertEqual(
            [None, None, None], [result.thumbnail_bytes for result in results]
        )

    async def test_similar_tab_results_use_string_thumbnail(self) -> None:
        payload = {
            "images_results": [
                {
                    "position": 1,
                    "thumbnail": "https://thumb.example/similar.jpg",
                    "title": "Similar Image",
                    "snippet": "Similar snippet",
                    "link": "https://source.example/similar",
                    "source": "similar.example",
                    "original": "https://source.example/similar.jpg",
                }
            ]
        }
        strategy, _ = self._strategy_with_statuses([200], [payload], tab="similar")

        results = await strategy.search("https://example.com/image.jpg")

        self.assertEqual(1, len(results))
        self.assertEqual("Similar Image", results[0].title)
        self.assertEqual("https://source.example/similar", results[0].url)
        self.assertEqual("https://thumb.example/similar.jpg", results[0].thumbnail)
        self.assertEqual("Similar snippet", results[0].description)

    async def test_empty_or_missing_result_keys_return_empty_list(self) -> None:
        for payload in (
            {},
            {"image_results": []},
            {"images_results": []},
            {"image_results": "invalid"},
            {"image_results": None, "images_results": None},
        ):
            with self.subTest(payload=payload):
                strategy, _ = self._strategy_with_statuses([200], [payload])

                self.assertEqual([], await strategy.search("https://example.com/i"))

    async def test_results_use_configured_limit(self) -> None:
        matches = [
            {
                "title": f"Result {index}",
                "link": f"https://source.example/{index}",
                "thumbnail": {"link": f"https://thumb.example/{index}.jpg"},
            }
            for index in range(10)
        ]
        strategy, _ = self._strategy_with_statuses(
            [200],
            [{"image_results": matches}],
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
            "not a mapping",
            {"title": "Result 1", "link": "https://source.example/1"},
            {"title": "Result 2", "link": "https://source.example/2"},
        ]
        strategy, _ = self._strategy_with_statuses(
            [200],
            [{"image_results": matches}],
            max_results=2,
        )

        results = await strategy.search("https://example.com/image.jpg")

        self.assertEqual(["Result 0", "Result 1"], [result.title for result in results])

    async def test_no_results_error_returns_empty_result_without_retry(self) -> None:
        strategy, session = self._strategy_with_statuses(
            [200],
            [{"error": "Yandex hasn't returned any results for this query."}],
        )

        result = await strategy.search("https://example.com/image.jpg")

        self.assertEqual([], result)
        self.assertEqual(["key-a"], session.calls)

    async def test_service_name_and_search_validation(self) -> None:
        with self.assertRaises(TypeError):
            self.yandex.YandexImagesStrategy(["key-a"])

        client = self.env.serpapi.SerpApiClient(api_keys=[])
        strategy_no_keys = self.yandex.YandexImagesStrategy(serpapi_client=client)
        self.assertEqual("Yandex Images", strategy_no_keys.get_service_name())
        with self.assertRaises(self.env.models.ProviderSearchError):
            await strategy_no_keys.search("https://example.com/img.jpg")

        strategy = self.yandex.YandexImagesStrategy(
            serpapi_client=self.env.serpapi.SerpApiClient(api_keys=["key-a"])
        )
        with self.assertRaises(self.env.models.ProviderSearchError):
            await strategy.search("base64://abc")
        with self.assertRaises(self.env.models.ProviderSearchError):
            await strategy.search("file:///local.png")


if __name__ == "__main__":
    unittest.main()
