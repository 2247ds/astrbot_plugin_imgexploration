from __future__ import annotations

from unittest.mock import AsyncMock, Mock, patch

from astrbot.core.message.components import Image
from astrbot_plugin_imgexploration.core import image_context, utils
from astrbot_plugin_imgexploration.core.models import SearchResultItem
from astrbot_plugin_imgexploration.main import ImgExplorationPlugin

from tests.helpers import FakeEvent, PluginTestCase


class YandexIntegrationTests(PluginTestCase):
    def setUp(self):
        super().setUp()
        # 真实插件初始化会修改模块级全局状态，测试结束后恢复原值
        for module, name in (
            (utils, "_proxy_url"),
            (utils, "_allow_image_upload"),
            (utils, "_allow_local_file_access"),
            (image_context, "_image_context_manager"),
        ):
            patcher = patch.object(module, name, getattr(module, name))
            patcher.start()
            self.addCleanup(patcher.stop)

    def make_configured_plugin(
        self,
        enabled=False,
        include=False,
        *,
        sauce_enabled=False,
    ):
        return ImgExplorationPlugin(
            Mock(),
            {
                "saucenao": {"enable": sauce_enabled, "api_key": "test-saucenao-key"},
                "google_lens": {"enable": False},
                "ascii2d": {"enable": False},
                "trace_moe": {"enable": False},
                "ehentai": {"enable": False},
                "serpapi": {"api_keys": ["test-serpapi-key"]},
                "yandex_images": {
                    "enable": enabled,
                    "include_in_default": include,
                },
                "config_version": 2,
            },
        )

    async def test_enable_and_default_switches(self):
        for enabled, include in (
            (False, False),
            (False, True),
            (True, False),
            (True, True),
        ):
            with self.subTest(enabled=enabled, include=include):
                plugin = self.make_configured_plugin(enabled, include)
                self.assertEqual(
                    plugin.service.get_available_strategies(),
                    ["Yandex Images"] if enabled else [],
                )
                defaults, _ = plugin.service.resolve_strategy_names(None)
                self.assertEqual(len(defaults), int(enabled and include))
                for alias in ("yandex", "yandeximages"):
                    resolved, missing = plugin.service.resolve_strategy_names([alias])
                    self.assertEqual(len(resolved), int(enabled))
                    self.assertEqual(missing, [] if enabled else [alias])
                await plugin.terminate()

    async def test_non_boolean_include_value_does_not_join_default(self):
        plugin = self.make_configured_plugin(True, "true")
        defaults, _ = plugin.service.resolve_strategy_names(None)
        self.assertEqual(defaults, [])
        resolved, missing = plugin.service.resolve_strategy_names(["yandex"])
        self.assertEqual(len(resolved), 1)
        self.assertEqual(missing, [])
        await plugin.terminate()

    async def test_default_search_includes_yandex_alongside_other_engines(self):
        plugin = self.make_configured_plugin(True, True, sauce_enabled=True)
        defaults, _ = plugin.service.resolve_strategy_names(None)
        self.assertEqual(
            sorted(strategy.get_service_name() for strategy in defaults),
            ["SauceNAO", "Yandex Images"],
        )
        await plugin.terminate()

    async def test_disabled_strategy_rejects_command(self):
        plugin = self.make_configured_plugin()
        event = FakeEvent(
            [],
            message_str="搜图 yandex",
            messages=[Image(file="https://example.com/image")],
        )
        self.assertEqual(len([r async for r in plugin.search_image_cmd(event)]), 1)
        self.assertFalse(event.timeline)
        await plugin.terminate()

    async def test_explicit_command_and_default_search(self):
        for include in (False, True):
            with self.subTest(include=include):
                plugin = self.make_configured_plugin(True, include)
                provider = plugin.strategies[0]
                outcome = [SearchResultItem("出处", "https://example.com/page")]
                event = FakeEvent(
                    [],
                    message_str="搜图" if include else "搜图 yandex",
                    messages=[Image(file="https://example.com/image")],
                )
                with (
                    patch(
                        "astrbot_plugin_imgexploration.core.service."
                        "get_publicly_hosted_image_url",
                        new=AsyncMock(return_value="https://img.example.com/hosted"),
                    ),
                    patch.object(
                        provider, "search", new=AsyncMock(return_value=outcome)
                    ) as search,
                    patch(
                        "astrbot_plugin_imgexploration.main.result_sender.send_search_results",
                        new=AsyncMock(),
                    ) as sender,
                ):
                    self.assertEqual(
                        [r async for r in plugin.search_image_cmd(event)], []
                    )
                    search.assert_awaited_once_with("https://img.example.com/hosted")
                    sender.assert_awaited_once()
                await plugin.terminate()
