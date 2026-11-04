"""SerpAPI 通用传输层.

封装 SerpAPI 的认证、Key 轮询、额度耗尽缓存和 HTTP 请求处理。
各搜图引擎只负责构造引擎参数和解析响应，不直接处理传输细节。
"""

from __future__ import annotations

import asyncio
import json
import time
import urllib.parse

import aiohttp
from astrbot.api import logger

from .constant import HTTP_TIMEOUT_SECONDS, QUOTA_CACHE_TTL, SERPAPI_BASE_URL
from .models import ProviderSearchError
from .utils import get_aiohttp_session, get_proxy_url


class SerpApiErrorPayloadError(Exception):
    """SerpAPI 响应 payload 中携带错误信息.

    该异常不继承 ProviderSearchError，避免上层把可解释的 payload 错误
    误当作不可恢复的提供商失败。策略基类会将错误措辞转换为结果或用户错误。
    """

    def __init__(self, message: str) -> None:
        """初始化 payload 错误.

        Args:
            message: SerpAPI 返回的错误描述
        """
        self.message = message
        super().__init__(message)


class _SerpApiQuotaExhaustedError(RuntimeError):
    """内部异常：当前 Key 的额度已耗尽."""

    def __init__(self, api_key: str, status: int | None = None) -> None:
        self.api_key = api_key
        self.status = status
        key_suffix = api_key[-4:] if api_key else ""
        super().__init__(f"SerpAPI key exhausted: ...{key_suffix} (status={status})")


class SerpApiClient:
    """SerpAPI 传输层客户端.

    所有 SerpAPI 引擎共享同一个客户端实例，因此 Key 轮询指针和额度缓存
    也在各引擎之间共享。客户端不持有 aiohttp session，session 由插件统一
    创建和关闭。
    """

    def __init__(self, api_keys: list[str] | None = None) -> None:
        """初始化 SerpAPI 客户端.

        Args:
            api_keys: SerpAPI API Key 列表；空条目会被忽略
        """
        self._api_keys = [
            key.strip()
            for key in (api_keys or [])
            if isinstance(key, str) and key.strip()
        ]
        self._current_key_index = 0
        self._key_lock = asyncio.Lock()
        # 额度缓存: {api_key: (searches_left, timestamp)}
        self._quota_cache: dict[str, tuple[int, float]] = {}

    @property
    def api_keys(self) -> list[str]:
        """返回配置的 Key 列表副本."""
        return list(self._api_keys)

    async def search(
        self,
        *,
        engine: str,
        params: dict[str, object],
        no_cache: bool = False,
        log_tag: str = "SerpAPI",
    ) -> dict:
        """发起一次 SerpAPI 搜索请求.

        Args:
            engine: SerpAPI 引擎名称，例如 google_lens
            params: 引擎专属请求参数，不包含 api_key/engine/no_cache
            no_cache: 是否绕过 SerpAPI 缓存
            log_tag: 日志前缀，例如 GoogleLens

        Returns:
            SerpAPI 返回的 JSON 对象

        Raises:
            SerpApiErrorPayloadError: 响应 payload 携带可解释的业务错误
            ProviderSearchError: 网络、HTTP、解析或全部 Key 耗尽等终态失败
        """
        if not self._api_keys:
            logger.warning(f"[{log_tag}] 未配置 SerpAPI Key，跳过搜索")
            raise ProviderSearchError("未配置 SerpAPI Key")

        # 仅在额度耗尽时尝试下一个 Key；网络或服务端错误与 Key 无关，
        # 换 Key 重试只会叠加等待时间
        for attempt in range(len(self._api_keys)):
            try:
                return await self._request_with_key(
                    engine=engine,
                    params=params,
                    no_cache=no_cache,
                    log_tag=log_tag,
                )
            except _SerpApiQuotaExhaustedError as e:
                if not e.api_key:
                    # 所有 Key 都处于额度耗尽缓存中，无需继续尝试
                    break
                logger.warning(
                    f"[{log_tag}] Key ...{e.api_key[-4:]} 额度已耗尽，"
                    f"尝试使用下一个可用 Key (尝试 {attempt + 1}/{len(self._api_keys)})"
                )
                continue
            except (ProviderSearchError, SerpApiErrorPayloadError):
                raise
            except Exception as e:
                # 异常文本可能包含带 api_key 的请求 URL，因此只记录异常类型
                logger.error(f"[{log_tag}] 搜索失败: {type(e).__name__}")
                raise ProviderSearchError(f"搜索失败: {type(e).__name__}") from e

        logger.error(f"[{log_tag}] 所有 API Key 已耗尽")
        raise ProviderSearchError("所有 API Key 已耗尽")

    async def _request_with_key(
        self,
        *,
        engine: str,
        params: dict[str, object],
        no_cache: bool,
        log_tag: str,
    ) -> dict:
        """使用当前选中的 Key 发起一次请求."""
        api_key = await self._select_key_optimistically()
        if not api_key:
            raise _SerpApiQuotaExhaustedError("", status=None)

        logger.info(f"[{log_tag}] 使用 Key ...{api_key[-4:]} 开始搜索")

        query = {
            "api_key": api_key,
            "engine": engine,
            "no_cache": str(no_cache).lower(),
            **params,
        }
        url = f"{SERPAPI_BASE_URL}/search?{urllib.parse.urlencode(query)}"

        session = await get_aiohttp_session()
        timeout = aiohttp.ClientTimeout(total=HTTP_TIMEOUT_SECONDS)
        proxy = get_proxy_url()

        async with session.get(url, timeout=timeout, proxy=proxy) as resp:
            if resp.status != 200:
                # 处理额度耗尽错误：标记当前 key 耗尽，并抛出异常让上层重试
                if resp.status in (401, 403, 429):
                    await self._mark_key_exhausted(api_key)
                    raise _SerpApiQuotaExhaustedError(api_key, status=resp.status)
                logger.error(f"[{log_tag}] API 返回错误: HTTP {resp.status}")
                raise ProviderSearchError(f"API 返回错误: HTTP {resp.status}")

            text = await resp.text()
            data = json.loads(text)

        if not isinstance(data, dict):
            raise TypeError("SerpAPI response is not a JSON object")

        if "error" in data:
            error_msg_value = data.get("error", "")
            error_msg = (
                error_msg_value
                if isinstance(error_msg_value, str)
                else str(error_msg_value)
            )
            if "api key" in error_msg.lower() or "exceeded" in error_msg.lower():
                await self._mark_key_exhausted(api_key)
                raise _SerpApiQuotaExhaustedError(api_key, status=None)

            logger.error(f"[{log_tag}] SerpAPI 错误: {error_msg}")
            raise SerpApiErrorPayloadError(error_msg)

        return data

    async def _select_key_optimistically(self) -> str | None:
        """乐观选择 API Key，不预先检查额度.

        使用轮询方式选择 Key，额度错误在实际请求时处理。
        使用缓存避免短时间内重复检查已知耗尽的 Key。

        Returns:
            可用的 API Key，如果没有则返回 None
        """
        if not self._api_keys:
            return None

        async with self._key_lock:
            # 清理过期的额度缓存
            now = time.time()
            expired_keys = [
                key
                for key, (_, timestamp) in self._quota_cache.items()
                if now - timestamp > QUOTA_CACHE_TTL
            ]
            for key in expired_keys:
                del self._quota_cache[key]

            start_idx = self._current_key_index % len(self._api_keys)

            for offset in range(len(self._api_keys)):
                idx = (start_idx + offset) % len(self._api_keys)
                key = self._api_keys[idx]

                cached = self._quota_cache.get(key)
                if cached:
                    searches_left, _ = cached
                    if searches_left <= 0:
                        continue  # 缓存显示已耗尽，跳过

                self._current_key_index = (idx + 1) % len(self._api_keys)
                return key

            return None

    async def _mark_key_exhausted(self, api_key: str) -> None:
        """标记 API Key 已耗尽.

        Args:
            api_key: 已耗尽的 API Key
        """
        async with self._key_lock:
            self._quota_cache[api_key] = (0, time.time())
            logger.debug(f"[SerpAPI] 已标记 Key ...{api_key[-4:]} 为耗尽状态")
