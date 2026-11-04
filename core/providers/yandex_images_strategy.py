"""Yandex Images 反向搜图策略实现.

通过共享的 SerpAPI 客户端调用 Yandex Images 进行图片搜索。
"""

from __future__ import annotations

from astrbot.api import logger

from ..constant import (
    DEFAULT_YANDEX_IMAGES_DOMAIN,
    DEFAULT_YANDEX_IMAGES_FAMILY_MODE,
    DEFAULT_YANDEX_IMAGES_MAX_RESULTS,
    DEFAULT_YANDEX_IMAGES_NO_CACHE,
    DEFAULT_YANDEX_IMAGES_TAB,
)
from ..models import SearchResultItem
from ..serpapi import SerpApiClient
from ..utils import normalize_bool
from .serpapi_strategy_base import SerpApiStrategyBase

YANDEX_IMAGES_TABS = {"about", "similar"}

# SerpAPI 的 family_mode 取值：0 关闭、1 适中、2 严格
YANDEX_IMAGES_FAMILY_MODES = {
    "off": "0",
    "moderate": "1",
    "strict": "2",
}


class YandexImagesStrategy(SerpApiStrategyBase):
    """Yandex Images 反向搜图策略.

    使用 SerpAPI 的 yandex_images 引擎进行图片搜索。
    多 API Key 轮询和额度缓存由共享的 SerpApiClient 负责。
    """

    def __init__(
        self,
        *,
        serpapi_client: SerpApiClient,
        max_results: int = DEFAULT_YANDEX_IMAGES_MAX_RESULTS,
        tab: str = DEFAULT_YANDEX_IMAGES_TAB,
        family_mode: str = DEFAULT_YANDEX_IMAGES_FAMILY_MODE,
        yandex_domain: str = DEFAULT_YANDEX_IMAGES_DOMAIN,
        no_cache: bool | str = DEFAULT_YANDEX_IMAGES_NO_CACHE,
    ) -> None:
        """初始化 Yandex Images 策略.

        Args:
            serpapi_client: 所有 SerpAPI 引擎共享的传输客户端
            max_results: 最大结果数量
            tab: 结果标签页，about 为图片出处，similar 为相似图片
            family_mode: 安全搜索级别，off、moderate 或 strict
            yandex_domain: Yandex 域名，留空时由 SerpAPI 决定
            no_cache: 是否绕过 SerpAPI 一小时缓存
        """
        super().__init__(
            serpapi_client=serpapi_client,
            no_cache=normalize_bool(no_cache, default=DEFAULT_YANDEX_IMAGES_NO_CACHE),
        )
        self.max_results = max_results
        normalized_tab = str(tab or "").strip().lower()
        self.tab = (
            normalized_tab
            if normalized_tab in YANDEX_IMAGES_TABS
            else DEFAULT_YANDEX_IMAGES_TAB
        )
        normalized_family_mode = str(family_mode or "").strip().lower()
        self.family_mode = (
            normalized_family_mode
            if normalized_family_mode in YANDEX_IMAGES_FAMILY_MODES
            else DEFAULT_YANDEX_IMAGES_FAMILY_MODE
        )
        self.yandex_domain = str(yandex_domain or "").strip().lower()

    def get_service_name(self) -> str:
        return "Yandex Images"

    def _engine(self) -> str:
        return "yandex_images"

    def _build_params(self, image_url: str) -> dict[str, object]:
        """构造 Yandex Images 引擎专属参数."""
        params: dict[str, object] = {
            "url": image_url,
            "tab": self.tab,
            "family_mode": YANDEX_IMAGES_FAMILY_MODES[self.family_mode],
        }
        if self.yandex_domain:
            params["yandex_domain"] = self.yandex_domain
        return params

    def _parse_response(self, data: dict) -> list[SearchResultItem]:
        """解析 Yandex Images 响应，跳过缺少标题或链接的项.

        about 标签页返回 ``image_results``，similar 标签页返回 ``images_results``。
        """
        results: list[SearchResultItem] = []
        matches = data.get("image_results") or data.get("images_results") or []
        if isinstance(matches, list):
            for match in matches:
                if len(results) >= self.max_results:
                    break
                try:
                    title = match.get("title", "")
                    link = match.get("link", "")
                    source = match.get("source", "")
                    snippet = match.get("snippet", "")

                    if not title or not link:
                        continue

                    # about 标签页的 thumbnail 是对象，similar 标签页是字符串
                    thumbnail = match.get("thumbnail", "")
                    if isinstance(thumbnail, dict):
                        thumbnail = thumbnail.get("link", "")
                    if not isinstance(thumbnail, str):
                        thumbnail = ""

                    if snippet:
                        description = snippet
                    elif source:
                        description = f"站点: {source}"
                    else:
                        description = None

                    results.append(
                        SearchResultItem(
                            title=title,
                            url=link,
                            thumbnail=thumbnail,
                            thumbnail_bytes=None,  # 缩略图由服务层统一下载
                            source="Yandex Images",
                            similarity=None,
                            description=description,
                            domain=None,
                        )
                    )
                except Exception as e:
                    logger.warning(f"[YandexImages] 解析结果项失败: {e}")

        logger.info(f"[YandexImages] 搜索完成，获取 {len(results)} 条结果")
        return results
