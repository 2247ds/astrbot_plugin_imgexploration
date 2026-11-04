"""SerpAPI 搜图策略通用基类.

负责策略层的输入校验、传输调用、payload 错误解释和解析异常归一化。
具体引擎只需实现引擎名、参数构造和响应解析。
"""

from __future__ import annotations

from abc import abstractmethod

from astrbot.api import logger

from ..models import ProviderSearchError, SearchResultItem
from ..serpapi import SerpApiClient, SerpApiErrorPayloadError
from ..strategy import ImageSearchStrategy


class SerpApiStrategyBase(ImageSearchStrategy):
    """SerpAPI 搜图策略基类.

    ``no_cache`` 由子类按引擎默认值归一化后传入，基类只接受 bool。
    基类不持有 aiohttp session；共享 session 由插件统一创建和关闭，因此
    ``close()`` 继承接口的空实现，不需要额外清理资源。
    """

    def __init__(
        self,
        *,
        serpapi_client: SerpApiClient,
        no_cache: bool,
    ) -> None:
        """初始化策略基类.

        Args:
            serpapi_client: 所有 SerpAPI 引擎共享的传输客户端
            no_cache: 是否绕过 SerpAPI 缓存（已归一化的 bool）
        """
        self.serpapi_client = serpapi_client
        self.no_cache = no_cache

    async def search(self, image_url: str) -> list[SearchResultItem]:
        """执行一次 SerpAPI 搜索.

        Args:
            image_url: 图片 URL 地址

        Returns:
            搜索结果列表；成功但无结果时返回空列表
        """
        log_tag = self._log_tag()

        if not self.serpapi_client.api_keys:
            logger.warning(f"[{log_tag}] 未配置 SerpAPI Key，跳过搜索")
            raise ProviderSearchError("未配置 SerpAPI Key")

        if not image_url.startswith(("http://", "https://")):
            logger.warning(f"[{log_tag}] SerpAPI 不支持本地文件")
            raise ProviderSearchError("SerpAPI 不支持本地文件")

        try:
            data = await self.serpapi_client.search(
                engine=self._engine(),
                params=self._build_params(image_url),
                no_cache=self.no_cache,
                log_tag=log_tag,
            )
        except SerpApiErrorPayloadError as e:
            return self._interpret_payload_error(e.message)
        except ProviderSearchError:
            raise
        except Exception as e:
            # 异常文本可能包含带 api_key 的请求 URL，因此只记录异常类型
            logger.error(f"[{log_tag}] 搜索失败: {type(e).__name__}")
            raise ProviderSearchError(f"搜索失败: {type(e).__name__}") from e

        # 保留原策略 search() 的 catch-all 语义：解析阶段的未知异常
        # 统一归一化为 ProviderSearchError
        try:
            return self._parse_response(data)
        except ProviderSearchError:
            raise
        except Exception as e:
            logger.error(f"[{log_tag}] 搜索失败: {type(e).__name__}")
            raise ProviderSearchError(f"搜索失败: {type(e).__name__}") from e

    def _interpret_payload_error(self, message: str) -> list[SearchResultItem]:
        """将 SerpAPI payload 错误转换为搜索结果或用户错误.

        默认把「没有匹配结果」视为成功空结果，其余错误视为提供商失败。
        子类可覆写以扩展特定引擎的错误措辞。

        Args:
            message: SerpAPI 返回的错误描述

        Returns:
            空结果列表（成功无匹配）

        Raises:
            ProviderSearchError: payload 错误不是成功无结果
        """
        if "hasn't returned any results" in message.lower():
            return []
        raise ProviderSearchError(f"SerpAPI 错误: {message}")

    def _log_tag(self) -> str:
        """获取日志前缀，保持现有 ``[GoogleLens]`` 等日志格式."""
        return self.get_service_name().replace(" ", "")

    @abstractmethod
    def _engine(self) -> str:
        """返回 SerpAPI 引擎名称."""

    @abstractmethod
    def _build_params(self, image_url: str) -> dict[str, object]:
        """构造引擎专属请求参数."""

    @abstractmethod
    def _parse_response(self, data: dict) -> list[SearchResultItem]:
        """解析引擎响应."""
