"""图床接口、工厂和上传编排测试."""

from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from astrbot_plugin_imgexploration.core import utils
from astrbot_plugin_imgexploration.core.image_hosts import uguu as uguu_module
from astrbot_plugin_imgexploration.core.image_hosts.base import (
    ImageHost,
    ImageHostError,
)
from astrbot_plugin_imgexploration.core.image_hosts.catbox import CatboxHost
from astrbot_plugin_imgexploration.core.image_hosts.factory import build_image_hosts
from astrbot_plugin_imgexploration.core.image_hosts.service import (
    ImageUploadService,
    close_image_upload_service,
    get_image_upload_service,
    init_image_upload_service,
)
from astrbot_plugin_imgexploration.core.image_hosts.uguu import UguuHost


class _FakeFormData:
    def __init__(self) -> None:
        self.fields: list[tuple[str, object, dict[str, object]]] = []

    def add_field(self, name: str, value: object, **kwargs: object) -> None:
        self.fields.append((name, value, kwargs))


class _FakeHost(ImageHost):
    def __init__(
        self,
        key: str,
        *,
        result: str = "https://example.com/image.jpg",
        error: Exception | None = None,
        max_upload_bytes: int = 1024,
    ) -> None:
        self.key = key
        self.name = key
        self.max_upload_bytes = max_upload_bytes
        self.result = result
        self.error = error
        self.upload_calls = 0
        self.closed = False

    async def upload(
        self,
        data: bytes,
        *,
        filename: str,
        content_type: str,
    ) -> str:
        self.upload_calls += 1
        if self.error is not None:
            raise self.error
        return self.result

    async def close(self) -> None:
        self.closed = True


class ImageUploadServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_uses_next_host_after_expected_failure(self) -> None:
        first = _FakeHost("first", error=ImageHostError("quota"))
        second = _FakeHost("second", result="https://example.com/second.jpg")
        service = ImageUploadService([first, second])

        result = await service.upload(b"image")

        self.assertEqual(result, "https://example.com/second.jpg")
        self.assertEqual(first.upload_calls, 1)
        self.assertEqual(second.upload_calls, 1)

    async def test_stops_after_first_success(self) -> None:
        first = _FakeHost("first", result="https://example.com/first.jpg")
        second = _FakeHost("second")
        service = ImageUploadService([first, second])

        result = await service.upload(b"image")

        self.assertEqual(result, "https://example.com/first.jpg")
        self.assertEqual(first.upload_calls, 1)
        self.assertEqual(second.upload_calls, 0)

    async def test_invalid_url_falls_through_to_next_host(self) -> None:
        first = _FakeHost("first", result="not-a-url")
        second = _FakeHost("second", result="https://example.com/second.jpg")
        service = ImageUploadService([first, second])

        result = await service.upload(b"image")

        self.assertEqual(result, "https://example.com/second.jpg")
        self.assertEqual(first.upload_calls, 1)
        self.assertEqual(second.upload_calls, 1)

    async def test_skips_host_for_oversized_image(self) -> None:
        first = _FakeHost("first", max_upload_bytes=2)
        second = _FakeHost("second", result="https://example.com/second.jpg")
        service = ImageUploadService([first, second])

        result = await service.upload(b"image")

        self.assertEqual(result, "https://example.com/second.jpg")
        self.assertEqual(first.upload_calls, 0)
        self.assertEqual(second.upload_calls, 1)

    async def test_empty_image_and_no_hosts_return_none(self) -> None:
        host = _FakeHost("first")
        service = ImageUploadService([host])

        self.assertIsNone(await service.upload(b""))
        self.assertEqual(host.upload_calls, 0)
        self.assertIsNone(await ImageUploadService([]).upload(b"image"))

    async def test_close_calls_all_hosts(self) -> None:
        first = _FakeHost("first")
        second = _FakeHost("second")
        service = ImageUploadService([first, second])

        await service.close()

        self.assertTrue(first.closed)
        self.assertTrue(second.closed)


class BuildImageHostsTests(unittest.TestCase):
    def test_missing_or_empty_config_defaults_to_catbox(self) -> None:
        for config in ({}, {"image_hosts": {}}):
            with self.subTest(config=config):
                hosts = build_image_hosts(config)
                self.assertEqual(len(hosts), 1)
                self.assertIsInstance(hosts[0], CatboxHost)

    def test_explicit_empty_chain_loads_no_hosts(self) -> None:
        self.assertEqual(
            build_image_hosts({"image_hosts": {"upload_chain": []}}),
            [],
        )

    def test_chain_is_normalized_and_unknown_hosts_are_skipped(self) -> None:
        hosts = build_image_hosts(
            {
                "image_hosts": {
                    "upload_chain": [" Catbox ", "catbox", "missing", 1],
                }
            }
        )

        self.assertEqual(len(hosts), 1)
        self.assertIsInstance(hosts[0], CatboxHost)

    def test_single_string_chain_is_supported(self) -> None:
        hosts = build_image_hosts({"image_hosts": {"upload_chain": "catbox"}})

        self.assertEqual(len(hosts), 1)
        self.assertIsInstance(hosts[0], CatboxHost)

    def test_uguu_can_be_loaded_from_chain(self) -> None:
        hosts = build_image_hosts({"image_hosts": {"upload_chain": ["catbox", "uguu"]}})

        self.assertEqual([host.key for host in hosts], ["catbox", "uguu"])
        self.assertIsInstance(hosts[1], UguuHost)


class UguuHostTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def _session_returning(response: object) -> MagicMock:
        context = AsyncMock()
        context.__aenter__.return_value = response
        session = MagicMock()
        session.post.return_value = context
        return session

    async def test_upload_uses_documented_form_and_parses_json(self) -> None:
        response = AsyncMock()
        response.status = 200
        response.json = AsyncMock(
            return_value={
                "success": True,
                "files": [{"url": "https://files.uguu.se/example.jpg"}],
            }
        )
        session = self._session_returning(response)

        with (
            patch.object(
                utils,
                "get_aiohttp_session",
                new=AsyncMock(return_value=session),
            ),
            patch.object(uguu_module.aiohttp, "FormData", _FakeFormData),
        ):
            url = await UguuHost().upload(
                b"image",
                filename="example.jpg",
                content_type="image/jpeg",
            )

        self.assertEqual(url, "https://files.uguu.se/example.jpg")
        call_kwargs = session.post.call_args.kwargs
        self.assertEqual(call_kwargs["params"], {"output": "json"})
        form = call_kwargs["data"]
        self.assertEqual(form.fields[0][0], "files[]")
        self.assertEqual(form.fields[0][1], b"image")

    async def test_upload_rejects_failed_or_malformed_json(self) -> None:
        for payload in (
            {"success": False, "description": "Rate limit"},
            {"success": True, "files": []},
            {"success": True, "files": [{"url": ""}]},
            [],
        ):
            with self.subTest(payload=payload):
                response = AsyncMock()
                response.status = 200
                response.json = AsyncMock(return_value=payload)
                session = self._session_returning(response)

                with (
                    patch.object(
                        utils,
                        "get_aiohttp_session",
                        new=AsyncMock(return_value=session),
                    ),
                    patch.object(uguu_module.aiohttp, "FormData", _FakeFormData),
                    self.assertRaises(ImageHostError),
                ):
                    await UguuHost().upload(
                        b"image",
                        filename="example.jpg",
                        content_type="image/jpeg",
                    )

    async def test_upload_rejects_http_error_and_oversized_file(self) -> None:
        response = AsyncMock()
        response.status = 500
        session = self._session_returning(response)

        with (
            patch.object(
                utils,
                "get_aiohttp_session",
                new=AsyncMock(return_value=session),
            ),
            patch.object(uguu_module.aiohttp, "FormData", _FakeFormData),
            self.assertRaises(ImageHostError),
        ):
            await UguuHost().upload(
                b"image",
                filename="example.jpg",
                content_type="image/jpeg",
            )

        large_bytes = MagicMock()
        large_bytes.__len__.return_value = 129 * 1024 * 1024
        with self.assertRaises(ImageHostError):
            await UguuHost().upload(
                large_bytes,
                filename="example.jpg",
                content_type="image/jpeg",
            )


class GlobalImageUploadServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_init_get_and_close_global_service(self) -> None:
        host = _FakeHost("custom")
        service = init_image_upload_service([host])

        self.assertIs(get_image_upload_service(), service)
        await close_image_upload_service()
        self.assertTrue(host.closed)

        fallback = get_image_upload_service()
        self.assertIsInstance(fallback.hosts[0], CatboxHost)
        await close_image_upload_service()
