from __future__ import annotations

import json
from unittest.mock import AsyncMock, Mock, patch

from astrbot.core.message.components import Image
from astrbot_plugin_imgexploration.core import image_context, utils
from astrbot_plugin_imgexploration.core.image_context import ImageContextManager
from astrbot_plugin_imgexploration.core.models import SearchResultItem
from astrbot_plugin_imgexploration.main import ImgExplorationPlugin

from tests.helpers import FakeEvent, PluginTestCase


class EHentaiIntegrationTests(PluginTestCase):
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
        trace_enabled=False,
        trace_include=False,
    ):
        return ImgExplorationPlugin(
            Mock(),
            {
                "saucenao": {"enable": sauce_enabled, "api_key": "test-saucenao-key"},
                "google_lens": {"enable": False},
                "ascii2d": {"enable": False},
                "trace_moe": {
                    "enable": trace_enabled,
                    "include_in_default": trace_include,
                },
                "ehentai": {"enable": enabled, "include_in_default": include},
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
                    ["E-Hentai"] if enabled else [],
                )
                defaults, _ = plugin.service.resolve_strategy_names(None)
                self.assertEqual(len(defaults), int(enabled and include))
                for alias in ("eh", "ehentai"):
                    resolved, missing = plugin.service.resolve_strategy_names([alias])
                    self.assertEqual(len(resolved), int(enabled))
                    self.assertEqual(missing, [] if enabled else [alias])
                await plugin.terminate()

    async def test_disabled_strategy_rejects_command(self):
        plugin = self.make_configured_plugin()
        event = FakeEvent(
            [],
            message_str="搜图 eh",
            messages=[Image(file="https://example.com/image")],
        )
        self.assertEqual(len([r async for r in plugin.search_image_cmd(event)]), 1)
        self.assertFalse(event.timeline)
        await plugin.terminate()

    async def test_explicit_only_rejects_no_argument_without_wait(self):
        plugin = self.make_configured_plugin(True)
        with (
            patch.object(plugin._image_wait, "create", new=AsyncMock()) as wait,
            patch.object(plugin.service, "explore", new=AsyncMock()) as explore,
        ):
            messages = [r async for r in plugin.search_image_cmd(FakeEvent([]))]
        self.assertEqual(len(messages), 1)
        wait.assert_not_awaited()
        explore.assert_not_awaited()
        await plugin.terminate()

    async def test_explicit_aliases_search_once_and_send_results(self):
        for alias in ("eh", "ehentai"):
            with self.subTest(alias=alias):
                plugin = self.make_configured_plugin(True, False)
                outcome = [
                    SearchResultItem(
                        title="Gallery",
                        url="https://e-hentai.org/g/1/abc/",
                        source="E-Hentai",
                    )
                ]
                event = FakeEvent(
                    [],
                    message_str=f"搜图 {alias}",
                    messages=[Image(file="https://example.com/image")],
                )
                with (
                    patch.object(
                        plugin.strategies[0],
                        "search",
                        new=AsyncMock(return_value=outcome),
                    ) as search,
                    patch(
                        "astrbot_plugin_imgexploration.main.result_sender.send_search_results",
                        new=AsyncMock(),
                    ) as sender,
                ):
                    self.assertEqual(
                        [r async for r in plugin.search_image_cmd(event)], []
                    )
                    search.assert_awaited_once_with("https://example.com/image")
                    sender.assert_awaited_once()
                await plugin.terminate()

    async def test_default_search_excludes_ehentai(self):
        plugin = self.make_configured_plugin(True, False, sauce_enabled=True)
        providers = {
            strategy.get_service_name(): strategy for strategy in plugin.strategies
        }
        self.assertEqual(set(providers), {"SauceNAO", "E-Hentai"})

        sauce_item = SearchResultItem("Sauce", "https://saucenao.com/1")
        eh_item = SearchResultItem("Gallery", "https://e-hentai.org/g/1/abc/")

        event = FakeEvent(
            [],
            message_str="搜图",
            messages=[Image(file="https://example.com/image")],
        )
        with (
            patch.object(
                providers["SauceNAO"],
                "search",
                new=AsyncMock(return_value=[sauce_item]),
            ) as sauce_search,
            patch.object(
                providers["E-Hentai"],
                "search",
                new=AsyncMock(return_value=[eh_item]),
            ) as eh_search,
            patch(
                "astrbot_plugin_imgexploration.main.result_sender.send_search_results",
                new=AsyncMock(),
            ) as sender,
        ):
            self.assertEqual([r async for r in plugin.search_image_cmd(event)], [])
            sauce_search.assert_awaited_once()
            eh_search.assert_not_awaited()
            self.assertEqual(
                [item.title for item in sender.await_args.args[1]],
                ["Sauce"],
            )
        await plugin.terminate()

    async def test_llm_tool_explicit_and_default_selection(self):
        plugin = self.make_configured_plugin(True, False, sauce_enabled=True)
        providers = {
            strategy.get_service_name(): strategy for strategy in plugin.strategies
        }
        manager = ImageContextManager()
        event = FakeEvent([], message_str="查找图片出处", is_command=False)
        manager.add_image(event, "https://example.com/image")

        eh_item = SearchResultItem("Gallery", "https://e-hentai.org/g/1/abc/")
        sauce_item = SearchResultItem("Sauce", "https://saucenao.com/1")

        with (
            patch(
                "astrbot_plugin_imgexploration.main.get_image_context_manager",
                return_value=manager,
            ),
            patch.object(
                providers["E-Hentai"],
                "search",
                new=AsyncMock(return_value=[eh_item]),
            ) as eh_search,
            patch.object(
                providers["SauceNAO"],
                "search",
                new=AsyncMock(return_value=[sauce_item]),
            ) as sauce_search,
            patch(
                "astrbot_plugin_imgexploration.main.result_sender.send_search_results",
                new=AsyncMock(),
            ),
        ):
            explicit = json.loads(
                await plugin.tool_search_image(event, image_index=-1, strategies="eh")
            )
            self.assertTrue(explicit["success"])
            eh_search.assert_awaited_once_with("https://example.com/image")
            sauce_search.assert_not_awaited()

            eh_search.reset_mock()
            sauce_search.reset_mock()
            default = json.loads(await plugin.tool_search_image(event, image_index=-1))
            self.assertTrue(default["success"])
            sauce_search.assert_awaited_once_with("https://example.com/image")
            eh_search.assert_not_awaited()

        await plugin.terminate()

    async def test_ehentai_inclusion_does_not_change_trace_moe_defaults(self):
        plugin = self.make_configured_plugin(
            True, False, trace_enabled=True, trace_include=False
        )
        self.assertEqual(
            plugin.service.get_available_strategies(),
            ["E-Hentai", "trace.moe"],
        )
        self.assertEqual(plugin.service.resolve_strategy_names(None)[0], [])
        await plugin.terminate()

        plugin = self.make_configured_plugin(
            True, True, trace_enabled=True, trace_include=True
        )
        defaults, _ = plugin.service.resolve_strategy_names(None)
        self.assertEqual(
            [strategy.get_service_name() for strategy in defaults],
            ["E-Hentai", "trace.moe"],
        )
        await plugin.terminate()
