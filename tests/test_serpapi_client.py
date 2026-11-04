"""SerpAPI transport client behavior tests."""

from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from tests.serpapi_stub_helpers import SerpApiStubEnvironment


class SerpApiClientTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.env = SerpApiStubEnvironment()
        self.addCleanup(self.env.close)

    def _client(self, keys: list[str] | None = None):
        return self.env.serpapi.SerpApiClient(api_keys=keys)

    async def test_successful_searches_rotate_keys(self) -> None:
        client = self._client(["key-a", "key-b", "key-c"])
        session = self.env.install_fake_session([200, 200, 200], [{}, {}, {}])

        for _ in range(3):
            await client.search(engine="google_lens", params={"url": "https://x"})

        self.assertEqual(["key-a", "key-b", "key-c"], session.calls)

    async def test_http_429_keeps_exhausted_key_out_of_later_searches(self) -> None:
        client = self._client(["key-a", "key-b", "key-c"])
        session = self.env.install_fake_session([429, 200, 200, 200], [{}, {}, {}])

        for _ in range(3):
            await client.search(engine="google_lens", params={"url": "https://x"})

        self.assertEqual(["key-a", "key-b", "key-c", "key-b"], session.calls)

    async def test_all_keys_exhausted_fail_without_repeating_warnings(self) -> None:
        client = self._client(["key-a", "key-b", "key-c"])
        session = self.env.install_fake_session([429, 429, 429])

        with self.assertRaises(self.env.models.ProviderSearchError):
            await client.search(engine="google_lens", params={"url": "https://x"})

        self.assertEqual(["key-a", "key-b", "key-c"], session.calls)

        logger = Mock()
        with (
            patch.object(self.env.serpapi, "logger", logger),
            self.assertRaises(self.env.models.ProviderSearchError),
        ):
            await client.search(engine="google_lens", params={"url": "https://x"})

        logger.warning.assert_not_called()

    async def test_non_quota_http_error_fails_without_exhausting_key(self) -> None:
        client = self._client(["key-a", "key-b", "key-c"])
        session = self.env.install_fake_session([500, 200, 200, 200], [{}, {}, {}])

        with self.assertRaises(self.env.models.ProviderSearchError):
            await client.search(engine="google_lens", params={"url": "https://x"})

        self.assertEqual(["key-a"], session.calls)
        for _ in range(3):
            await client.search(engine="google_lens", params={"url": "https://x"})
        self.assertEqual(["key-a", "key-b", "key-c", "key-a"], session.calls)

    async def test_network_error_only_tries_first_key(self) -> None:
        client = self._client(["key-a", "key-b", "key-c"])
        session = self.env.install_fake_session([TimeoutError()])

        with self.assertRaises(self.env.models.ProviderSearchError):
            await client.search(engine="google_lens", params={"url": "https://x"})

        self.assertEqual(["key-a"], session.calls)

    async def test_quota_payload_retries_with_next_key(self) -> None:
        client = self._client(["key-a", "key-b"])
        session = self.env.install_fake_session(
            [200, 200],
            [
                {"error": "API key has exceeded its quota"},
                {"visual_matches": []},
            ],
        )

        result = await client.search(engine="google_lens", params={"url": "https://x"})

        self.assertEqual({"visual_matches": []}, result)
        self.assertEqual(["key-a", "key-b"], session.calls)

    async def test_non_quota_payload_error_is_typed_and_logged(self) -> None:
        full_key = "serpapi-value-key-a"
        client = self._client([full_key])
        self.env.install_fake_session(
            [200],
            [{"error": "Google Lens hasn't returned any results for this query."}],
        )
        logger = Mock()

        with (
            patch.object(self.env.serpapi, "logger", logger),
            self.assertRaises(self.env.serpapi.SerpApiErrorPayloadError) as raised,
        ):
            await client.search(engine="google_lens", params={"url": "https://x"})

        self.assertEqual(
            "Google Lens hasn't returned any results for this query.",
            raised.exception.message,
        )
        self.assertTrue(
            any(
                "SerpAPI 错误" in str(call.args[0])
                for call in logger.error.call_args_list
            )
        )
        self.assertNotIn(full_key, str(logger.mock_calls))

    async def test_empty_api_keys_fail_without_request(self) -> None:
        client = self._client([])
        session = self.env.install_fake_session([])

        with self.assertRaises(self.env.models.ProviderSearchError):
            await client.search(engine="google_lens", params={"url": "https://x"})

        self.assertEqual([], session.calls)


if __name__ == "__main__":
    unittest.main()
