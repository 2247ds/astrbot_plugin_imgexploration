"""Google Lens 搜图策略实现.

通过共享的 SerpAPI 客户端调用 Google Lens 进行图片搜索。
"""

from __future__ import annotations

from astrbot.api import logger

from ..constant import (
    DEFAULT_GOOGLE_LENS_AUTO_CROP,
    DEFAULT_GOOGLE_LENS_COUNTRY,
    DEFAULT_GOOGLE_LENS_LANGUAGE,
    DEFAULT_GOOGLE_LENS_MAX_RESULTS,
    DEFAULT_GOOGLE_LENS_NO_CACHE,
    DEFAULT_GOOGLE_LENS_SAFE_SEARCH,
    DEFAULT_GOOGLE_LENS_SEARCH_TYPE,
)
from ..models import SearchResultItem
from ..serpapi import SerpApiClient
from ..utils import normalize_bool
from .serpapi_strategy_base import SerpApiStrategyBase

GOOGLE_LENS_SEARCH_TYPES = {
    "all",
    "exact_matches",
    "products",
    "visual_matches",
}


class GoogleLensStrategy(SerpApiStrategyBase):
    """Google Lens 搜图策略.

    使用 SerpAPI 的 google_lens 引擎进行图片搜索。
    多 API Key 轮询和额度缓存由共享的 SerpApiClient 负责。
    """

    def __init__(
        self,
        *,
        serpapi_client: SerpApiClient,
        max_results: int = DEFAULT_GOOGLE_LENS_MAX_RESULTS,
        search_type: str = DEFAULT_GOOGLE_LENS_SEARCH_TYPE,
        language: str = DEFAULT_GOOGLE_LENS_LANGUAGE,
        country: str = DEFAULT_GOOGLE_LENS_COUNTRY,
        safe_search: bool | str = DEFAULT_GOOGLE_LENS_SAFE_SEARCH,
        auto_crop: bool | str = DEFAULT_GOOGLE_LENS_AUTO_CROP,
        no_cache: bool | str = DEFAULT_GOOGLE_LENS_NO_CACHE,
    ) -> None:
        """初始化 Google Lens 策略.

        Args:
            serpapi_client: 所有 SerpAPI 引擎共享的传输客户端
            max_results: 最大结果数量
            search_type: Google Lens 搜索类型
            language: 搜索结果语言代码
            country: 搜索结果国家代码，留空时由 Google 决定
            safe_search: 是否启用严格的成人内容过滤；关闭时使用 Google 默认处理
            auto_crop: 是否让 Google 自动裁剪图片主体
            no_cache: 是否绕过 SerpAPI 一小时缓存
        """
        super().__init__(
            serpapi_client=serpapi_client,
            no_cache=normalize_bool(no_cache, default=DEFAULT_GOOGLE_LENS_NO_CACHE),
        )
        self.max_results = max_results
        normalized_search_type = str(search_type or "").strip().lower()
        self.search_type = (
            normalized_search_type
            if normalized_search_type in GOOGLE_LENS_SEARCH_TYPES
            else DEFAULT_GOOGLE_LENS_SEARCH_TYPE
        )
        self.language = (
            str(language or "").strip().lower() or DEFAULT_GOOGLE_LENS_LANGUAGE
        )
        self.country = str(country or "").strip().lower()
        self.safe_search = normalize_bool(
            safe_search, default=DEFAULT_GOOGLE_LENS_SAFE_SEARCH
        )
        self.auto_crop = normalize_bool(
            auto_crop, default=DEFAULT_GOOGLE_LENS_AUTO_CROP
        )

    def get_service_name(self) -> str:
        return "Google Lens"

    def _engine(self) -> str:
        return "google_lens"

    def _build_params(self, image_url: str) -> dict[str, object]:
        """构造 Google Lens 引擎专属参数."""
        params: dict[str, object] = {
            "url": image_url,
            "type": self.search_type,
            "hl": self.language,
            "auto_crop": str(self.auto_crop).lower(),
        }
        if self.country:
            params["country"] = self.country
        # 关闭时不发送 safe，保持 Google 默认的模糊处理
        if self.safe_search:
            params["safe"] = "active"
        return params

    def _parse_response(self, data: dict) -> list[SearchResultItem]:
        """解析 Google Lens 响应，跳过缺少标题或链接的项."""
        results: list[SearchResultItem] = []
        result_key = (
            "visual_matches"
            if self.search_type in {"all", "products"}
            else self.search_type
        )
        matches = data.get(result_key, [])
        if isinstance(matches, list):
            for match in matches:
                if len(results) >= self.max_results:
                    break
                try:
                    title = match.get("title", "")
                    link = match.get("link", "")
                    source = match.get("source", "")
                    thumbnail = match.get("thumbnail", "")

                    if not title or not link:
                        continue

                    results.append(
                        SearchResultItem(
                            title=title,
                            url=link,
                            thumbnail=thumbnail,
                            thumbnail_bytes=None,  # 缩略图由服务层统一下载
                            source="Google Lens",
                            similarity=None,
                            # 站点名加标签，避免在结果中显示为无说明的一行
                            description=f"站点: {source}" if source else None,
                            domain=None,
                        )
                    )
                except Exception as e:
                    logger.warning(f"[GoogleLens] 解析结果项失败: {e}")

        logger.info(f"[GoogleLens] 搜索完成，获取 {len(results)} 条结果")
        return results
