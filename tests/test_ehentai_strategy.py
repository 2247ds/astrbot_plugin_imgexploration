from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from astrbot_plugin_imgexploration.core.constant import (
    EHENTAI_EX_UPLOAD_URL,
    EHENTAI_UPLOAD_URL,
)
from astrbot_plugin_imgexploration.core.models import ProviderSearchError
from astrbot_plugin_imgexploration.core.providers.ehentai_strategy import (
    EHentaiStrategy,
    parse_cookie_header,
)
from astrbot_plugin_imgexploration.core.utils import DownloadTooLargeError

_FIXTURES = Path(__file__).parent / "fixtures" / "ehentai"
_RESPONSE_URL = "https://e-hentai.org/?f_search=test"


def _load_fixture(name: str) -> str:
    return (_FIXTURES / name).read_text(encoding="utf-8")


def _response(
    text: str,
    *,
    status: int = 200,
    url: str = _RESPONSE_URL,
) -> MagicMock:
    response = MagicMock()
    response.status_code = status
    response.text = text
    response.url = url
    return response


class EHentaiStrategyTests(unittest.IsolatedAsyncioTestCase):
    def _session(self) -> MagicMock:
        session = MagicMock()
        session.post = AsyncMock()
        session.close = AsyncMock()
        return session

    async def _run_search(
        self,
        strategy: EHentaiStrategy,
        response: MagicMock | None = None,
        *,
        image_bytes: bytes | None = b"image-bytes",
        image_url: str = "https://example.com/target.jpg",
        session: MagicMock | None = None,
    ):
        session = session or self._session()
        if response is not None:
            session.post.return_value = response
        with (
            patch(
                "astrbot_plugin_imgexploration.core.providers.ehentai_strategy.download_bytes",
                new=AsyncMock(return_value=image_bytes),
            ) as download,
            patch.object(strategy, "_get_session", new=AsyncMock(return_value=session)),
        ):
            try:
                return await strategy.search(image_url), session, download
            except ProviderSearchError as exc:
                return exc, session, download

    def test_init_and_cookie_parsing(self) -> None:
        with self.assertRaises(TypeError):
            EHentaiStrategy(True)

        strategy = EHentaiStrategy(
            cookies=" a=1 ; b = 2 ; bad ; empty= ; nested=x=y ",
            max_results=7,
            search_covers=True,
            search_similar=False,
            search_exp=True,
        )
        self.assertEqual(strategy.get_service_name(), "E-Hentai")
        self.assertEqual(strategy.max_results, 7)
        self.assertTrue(strategy.search_covers)
        self.assertFalse(strategy.search_similar)
        self.assertTrue(strategy.search_exp)
        self.assertEqual(
            strategy.cookies,
            {"a": "1", "b": "2", "nested": "x=y"},
        )
        self.assertEqual(parse_cookie_header(""), {})
        self.assertEqual(parse_cookie_header(" ; ; "), {})

    def test_proxy_building(self) -> None:
        strategy = EHentaiStrategy()
        with patch(
            "astrbot_plugin_imgexploration.core.providers.ehentai_strategy.get_proxy_url",
            return_value="http://127.0.0.1:7890",
        ):
            self.assertEqual(
                strategy._get_proxies(),
                {"http": "http://127.0.0.1:7890", "https": "http://127.0.0.1:7890"},
            )
        with patch(
            "astrbot_plugin_imgexploration.core.providers.ehentai_strategy.get_proxy_url",
            return_value=None,
        ):
            self.assertIsNone(strategy._get_proxies())

    async def test_rejects_non_http_url(self) -> None:
        strategy = EHentaiStrategy()
        for image_url in ("base64://abc", "file:///local.jpg", ""):
            with (
                self.subTest(image_url=image_url),
                self.assertRaises(ProviderSearchError),
            ):
                await strategy.search(image_url)

    async def test_download_failures_do_not_post(self) -> None:
        cases = (
            (None, "下载失败"),
            (b"", "下载失败"),
        )
        for image_bytes, expected in cases:
            with self.subTest(image_bytes=image_bytes):
                strategy = EHentaiStrategy()
                with (
                    patch(
                        "astrbot_plugin_imgexploration.core.providers.ehentai_strategy.download_bytes",
                        new=AsyncMock(return_value=image_bytes),
                    ),
                    patch.object(
                        strategy, "_get_session", new=AsyncMock()
                    ) as get_session,
                    self.assertRaises(ProviderSearchError) as raised,
                ):
                    await strategy.search("https://example.com/target.jpg")
                self.assertIn(expected, raised.exception.user_notice or "")
                get_session.assert_not_awaited()

        strategy = EHentaiStrategy()
        with (
            patch(
                "astrbot_plugin_imgexploration.core.providers.ehentai_strategy.download_bytes",
                new=AsyncMock(side_effect=DownloadTooLargeError),
            ),
            patch.object(strategy, "_get_session", new=AsyncMock()) as get_session,
            self.assertRaises(ProviderSearchError) as raised,
        ):
            await strategy.search("https://example.com/target.jpg")
        self.assertIn("体积过大", raised.exception.user_notice or "")
        get_session.assert_not_awaited()

    async def test_exhentai_requires_valid_cookie_before_download(self) -> None:
        for cookies in ("", " ; ", "invalid"):
            with self.subTest(cookies=cookies):
                strategy = EHentaiStrategy(use_exhentai=True, cookies=cookies)
                with (
                    patch(
                        "astrbot_plugin_imgexploration.core.providers.ehentai_strategy.download_bytes",
                        new=AsyncMock(),
                    ) as download,
                    self.assertRaises(ProviderSearchError) as raised,
                ):
                    await strategy.search("https://example.com/target.jpg")
                download.assert_not_awaited()
                self.assertIn("Cookie", raised.exception.user_notice or "")

    async def test_multipart_fields_switch_and_endpoint(self) -> None:
        response = _response(_load_fixture("result_page.html"))
        strategy = EHentaiStrategy(
            search_covers=True,
            search_similar=False,
            search_exp=True,
            cookies="a=1; b=2; bad",
        )

        result, session, _ = await self._run_search(strategy, response)

        self.assertIsInstance(result, list)
        session.post.assert_awaited_once()
        args, kwargs = session.post.await_args
        self.assertEqual(args[0], EHENTAI_UPLOAD_URL)
        self.assertNotIn("files", kwargs)

        body = kwargs["data"]
        self.assertIsInstance(body, bytes)
        content_type = kwargs["headers"]["Content-Type"]
        self.assertTrue(content_type.startswith("multipart/form-data; boundary="))
        boundary = content_type.split("boundary=", 1)[1]
        self.assertIn(
            b'Content-Disposition: form-data; name="f_sfile"\r\n\r\nFile Search\r\n',
            body,
        )
        self.assertIn(b'Content-Disposition: form-data; name="fs_covers"', body)
        self.assertIn(b'Content-Disposition: form-data; name="fs_exp"', body)
        self.assertNotIn(b'Content-Disposition: form-data; name="fs_similar"', body)
        self.assertIn(b'name="sfile"; filename="image.jpg"', body)
        self.assertIn(
            b"Content-Type: application/octet-stream\r\n\r\nimage-bytes",
            body,
        )
        self.assertTrue(body.startswith(f"--{boundary}\r\n".encode()))
        self.assertTrue(body.endswith(f"\r\n--{boundary}--\r\n".encode()))

        self.assertEqual(kwargs["cookies"], {"a": "1", "b": "2"})
        self.assertTrue(kwargs["allow_redirects"])

    async def test_default_similar_switch(self) -> None:
        response = _response(_load_fixture("result_page.html"))
        strategy = EHentaiStrategy()

        _, session, _ = await self._run_search(strategy, response)

        _, kwargs = session.post.await_args
        self.assertNotIn("files", kwargs)
        self.assertIn(
            b'Content-Disposition: form-data; name="fs_similar"', kwargs["data"]
        )
        self.assertIn(b'Content-Disposition: form-data; name="f_sfile"', kwargs["data"])
        self.assertNotIn(b'name="fs_covers"', kwargs["data"])
        self.assertNotIn(b'name="fs_exp"', kwargs["data"])
        self.assertIsNone(kwargs["cookies"])

    async def test_exhentai_endpoint_and_source(self) -> None:
        response = _response(_load_fixture("result_page.html"))
        strategy = EHentaiStrategy(use_exhentai=True, cookies="ipb_member_id=1")

        result, session, _ = await self._run_search(strategy, response)

        args, _ = session.post.await_args
        self.assertEqual(args[0], EHENTAI_EX_UPLOAD_URL)
        self.assertTrue(all(item.source == "ExHentai" for item in result))

    async def test_parse_result_page_and_urljoin(self) -> None:
        strategy = EHentaiStrategy()
        response = _response(_load_fixture("result_page.html"))

        results, _, _ = await self._run_search(strategy, response)

        self.assertEqual(
            [item.title for item in results],
            ["Sample Gallery One", "Sample Gallery Two", "Sample Gallery Three"],
        )
        self.assertEqual(
            [item.url for item in results],
            [
                "https://e-hentai.org/g/111/aaaaaaaaaa/",
                "https://e-hentai.org/g/222/bbbbbbbbbb/",
                "https://e-hentai.org/g/333/cccccccccc/",
            ],
        )
        self.assertEqual(
            [item.thumbnail for item in results],
            [
                "https://ehgt.org/t/111/thumb.jpg",
                "https://e-hentai.org/t/222/thumb.jpg",
                "https://e-hentai.org/t/333/thumb.jpg",
            ],
        )
        self.assertTrue(all(item.source == "E-Hentai" for item in results))
        self.assertTrue(all(item.thumbnail_bytes is None for item in results))

        description = results[0].description or ""
        self.assertEqual(
            description.splitlines()[0],
            "类型: Doujinshi · 页数: 32 · 上传: 2023-01-05 12:00",
        )
        self.assertEqual(
            description.splitlines()[1],
            "标签: artist:someone、female:example",
        )
        self.assertIsNone(results[1].description)

    async def test_grid_layout_fallback(self) -> None:
        strategy = EHentaiStrategy()
        response = _response(_load_fixture("grid_results.html"))

        results, _, _ = await self._run_search(strategy, response)

        self.assertEqual([item.title for item in results], ["Grid Gallery"])
        self.assertEqual(
            results[0].thumbnail,
            "https://ehgt.org/t/444/thumb.jpg",
        )

    async def test_max_results_truncates_valid_rows(self) -> None:
        strategy = EHentaiStrategy(max_results=2)
        response = _response(_load_fixture("result_page.html"))

        results, _, _ = await self._run_search(strategy, response)

        self.assertEqual(
            [item.title for item in results],
            ["Sample Gallery One", "Sample Gallery Two"],
        )

    async def test_only_explicit_no_result_page_returns_empty(self) -> None:
        strategy = EHentaiStrategy()
        response = _response(_load_fixture("no_results.html"))

        results, _, _ = await self._run_search(strategy, response)

        self.assertEqual(results, [])

    async def test_no_hits_found_marker_returns_empty(self) -> None:
        strategy = EHentaiStrategy()
        response = _response("<html><body><p>No hits found</p></body></html>")

        results, _, _ = await self._run_search(strategy, response)

        self.assertEqual(results, [])

    async def test_parse_exception_is_normalized(self) -> None:
        strategy = EHentaiStrategy()
        response = _response("<html></html>")

        with patch.object(
            strategy, "_parse_html", side_effect=ValueError("internal detail")
        ):
            result, _, _ = await self._run_search(strategy, response)

        self.assertIsInstance(result, ProviderSearchError)
        self.assertNotIn("internal detail", str(result))

    async def test_cloudflare_page_is_failure(self) -> None:
        strategy = EHentaiStrategy()
        response = _response(_load_fixture("cloudflare.html"))

        result, _, _ = await self._run_search(strategy, response)

        self.assertIsInstance(result, ProviderSearchError)
        self.assertIn("Cloudflare", result.user_notice or "")

    async def test_exhentai_unrecognized_page_reports_auth_failure(self) -> None:
        strategy = EHentaiStrategy(use_exhentai=True, cookies="ipb_member_id=1")
        response = _response(_load_fixture("ex_unauthenticated.html"))

        result, _, _ = await self._run_search(strategy, response)

        self.assertIsInstance(result, ProviderSearchError)
        self.assertIn("Cookie", result.user_notice or "")

    async def test_unknown_page_and_incompatible_container_are_failures(self) -> None:
        cases = (
            "<html><body><p>Unknown page</p></body></html>",
            '<table class="itg"><tr><th>Title</th></tr></table>',
            '<table class="itg"><tr><td><div class="glink">No link</div></td></tr></table>',
        )
        for html in cases:
            with self.subTest(html=html):
                strategy = EHentaiStrategy()
                result, session, _ = await self._run_search(strategy, _response(html))
                self.assertIsInstance(result, ProviderSearchError)
                session.post.assert_awaited_once()

    async def test_http_status_errors(self) -> None:
        cases = (
            (401, True),
            (403, True),
            (429, True),
            (500, False),
        )
        for status, has_notice in cases:
            with self.subTest(status=status):
                strategy = EHentaiStrategy()
                result, _, _ = await self._run_search(
                    strategy, _response("error", status=status)
                )
                self.assertIsInstance(result, ProviderSearchError)
                self.assertEqual(bool(result.user_notice), has_notice)
                self.assertIn(str(status), str(result))
        strategy = EHentaiStrategy()
        result, _, _ = await self._run_search(strategy, _response("error", status=429))
        self.assertIn("频繁", result.user_notice or "")

    async def test_request_exception_is_normalized_without_sensitive_logs(self) -> None:
        strategy = EHentaiStrategy(cookies="secret_cookie=super-secret-value")
        session = self._session()
        session.post.side_effect = TimeoutError(
            "proxy http://user:password@127.0.0.1:7890 failed"
        )

        with patch(
            "astrbot_plugin_imgexploration.core.providers.ehentai_strategy.logger"
        ) as strategy_logger:
            result, _, _ = await self._run_search(
                strategy,
                session=session,
                image_url="https://example.com/private-target.jpg?token=secret",
            )

        self.assertIsInstance(result, ProviderSearchError)
        self.assertNotIn("super-secret-value", str(result))
        logged = " ".join(
            str(call.args[0])
            for call in strategy_logger.warning.call_args_list
            if call.args
        )
        self.assertNotIn("super-secret-value", logged)
        self.assertNotIn("password", logged)
        self.assertNotIn("private-target.jpg", logged)

    async def test_successful_logs_do_not_include_cookie_or_target_url(self) -> None:
        strategy = EHentaiStrategy(cookies="secret_cookie=super-secret-value")
        response = _response(_load_fixture("result_page.html"))

        with patch(
            "astrbot_plugin_imgexploration.core.providers.ehentai_strategy.logger"
        ) as strategy_logger:
            await self._run_search(
                strategy,
                response,
                image_url="https://example.com/private-target.jpg",
            )

        logged = " ".join(
            str(call.args[0])
            for call in (
                strategy_logger.debug.call_args_list
                + strategy_logger.info.call_args_list
                + strategy_logger.warning.call_args_list
            )
            if call.args
        )
        self.assertNotIn("super-secret-value", logged)
        self.assertNotIn("private-target.jpg", logged)

    async def test_close_is_idempotent(self) -> None:
        strategy = EHentaiStrategy()
        session = self._session()

        with patch(
            "astrbot_plugin_imgexploration.core.providers.ehentai_strategy.AsyncSession",
            return_value=session,
        ):
            first = await strategy._get_session()
            second = await strategy._get_session()
            self.assertIs(first, second)

            await strategy.close()
            await strategy.close()
            session.close.assert_awaited_once()
            self.assertIsNone(strategy._session)

            recreated = await strategy._get_session()
            self.assertIs(recreated, session)
