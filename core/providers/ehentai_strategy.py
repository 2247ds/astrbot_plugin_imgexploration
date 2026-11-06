"""E-Hentai / ExHentai 搜图策略实现.

下载目标图片后以 multipart 形式上传到 E-Hentai 的图片搜索端点，
再解析返回的画廊列表页面。
"""

from __future__ import annotations

import asyncio
import urllib.parse
import uuid

from astrbot.api import logger
from bs4 import BeautifulSoup
from curl_cffi.requests import AsyncSession

from ..constant import (
    DEFAULT_EHENTAI_MAX_RESULTS,
    EHENTAI_EX_UPLOAD_URL,
    EHENTAI_UPLOAD_URL,
    HTTP_TIMEOUT_SECONDS,
)
from ..models import ProviderSearchError, SearchResultItem
from ..strategy import ImageSearchStrategy
from ..utils import DownloadTooLargeError, download_bytes, get_proxy_url

_NO_RESULT_MARKERS = ("no unfiltered results", "no hits found")
_CLOUDFLARE_MARKERS = ("just a moment", "cf-chl", "challenge-platform")
_MAX_TAGS = 10
_REDIRECT_STATUSES = (301, 302, 303, 307, 308)


def build_multipart_body(
    fields: dict[str, str],
    *,
    file_field: str,
    filename: str,
    file_bytes: bytes,
    content_type: str,
) -> tuple[bytes, str]:
    """构造 multipart/form-data 请求体.

    curl_cffi 的 AsyncSession 不支持 ``files=``，因此直接编码请求体，
    避免依赖不同版本的多部分上传 API。
    """
    boundary = f"----imgexploration{uuid.uuid4().hex}"
    chunks: list[bytes] = []
    for name, value in fields.items():
        chunks.append(f"--{boundary}\r\n".encode())
        chunks.append(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode())
        chunks.append(str(value).encode())
        chunks.append(b"\r\n")
    chunks.append(f"--{boundary}\r\n".encode())
    chunks.append(
        (
            f'Content-Disposition: form-data; name="{file_field}"; '
            f'filename="{filename}"\r\n'
        ).encode()
    )
    chunks.append(f"Content-Type: {content_type}\r\n\r\n".encode())
    chunks.append(file_bytes)
    chunks.append(f"\r\n--{boundary}--\r\n".encode())
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


def parse_cookie_header(raw: str) -> dict[str, str]:
    """将 Cookie 字符串解析为字典.

    Cookie 值本身可能包含 ``=``，因此每段只在第一个 ``=`` 处分割。
    没有键或没有值的段会被忽略。
    """
    cookies: dict[str, str] = {}
    for part in (raw or "").split(";"):
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        key = key.strip()
        value = value.strip()
        if key and value:
            cookies[key] = value
    return cookies


class EHentaiStrategy(ImageSearchStrategy):
    """E-Hentai 图片反查策略.

    支持普通 E-Hentai 与需要 Cookie 的 ExHentai。
    使用 curl_cffi 模拟浏览器 TLS 指纹，降低 Cloudflare 拦截概率。
    """

    IMPERSONATE_BROWSER = "chrome120"

    def __init__(
        self,
        *,
        use_exhentai: bool = False,
        cookies: str = "",
        max_results: int = DEFAULT_EHENTAI_MAX_RESULTS,
        search_covers: bool = False,
        search_similar: bool = True,
        search_exp: bool = False,
    ) -> None:
        """初始化 E-Hentai 策略.

        Args:
            use_exhentai: 是否改为请求 ExHentai
            cookies: E-Hentai / ExHentai Cookie 字符串
            max_results: 最大结果数量
            search_covers: 是否搜索封面图片
            search_similar: 是否搜索相似图片
            search_exp: 是否使用扩展搜索
        """
        self.use_exhentai = use_exhentai is True
        self.max_results = max_results
        self.search_covers = search_covers is True
        self.search_similar = search_similar is True
        self.search_exp = search_exp is True
        self.cookies = parse_cookie_header(cookies)
        self._session: AsyncSession | None = None
        self._session_lock = asyncio.Lock()

    @property
    def _source_name(self) -> str:
        return "ExHentai" if self.use_exhentai else "E-Hentai"

    @property
    def _upload_url(self) -> str:
        return EHENTAI_EX_UPLOAD_URL if self.use_exhentai else EHENTAI_UPLOAD_URL

    def _get_proxies(self) -> dict | None:
        """获取代理配置."""
        proxy_url = get_proxy_url()
        if proxy_url:
            return {"http": proxy_url, "https": proxy_url}
        return None

    async def _get_session(self) -> AsyncSession:
        """获取共享的 AsyncSession 实例."""
        if self._session is not None:
            return self._session

        async with self._session_lock:
            if self._session is None:
                self._session = AsyncSession(
                    impersonate=self.IMPERSONATE_BROWSER,
                    proxies=self._get_proxies(),
                    timeout=HTTP_TIMEOUT_SECONDS,
                )
            return self._session

    async def close(self) -> None:
        """关闭共享的 AsyncSession 并清理资源."""
        async with self._session_lock:
            if self._session is not None:
                await self._session.close()
                self._session = None
                logger.debug(f"[{self._source_name}] AsyncSession 已关闭")

    def get_service_name(self) -> str:
        return "E-Hentai"

    async def search(self, image_url: str) -> list[SearchResultItem]:
        """执行 E-Hentai 图片搜索."""
        if not image_url.startswith(("http://", "https://")):
            logger.warning("[E-Hentai] 仅支持 HTTP URL")
            raise ProviderSearchError("仅支持 HTTP URL")

        if self.use_exhentai and not self.cookies:
            raise ProviderSearchError(
                "ExHentai 需要有效 Cookie",
                user_notice="使用 ExHentai 需要先配置有效的 Cookie。",
            )

        try:
            image_bytes = await download_bytes(image_url)
        except DownloadTooLargeError as exc:
            raise ProviderSearchError(
                "图片体积超过上限",
                user_notice="图片体积过大，E-Hentai 无法上传。",
            ) from exc

        if not image_bytes:
            raise ProviderSearchError(
                "图片下载失败",
                user_notice="图片下载失败，无法上传到 E-Hentai。",
            )

        data = {"f_sfile": "File Search"}
        if self.search_covers:
            data["fs_covers"] = "on"
        if self.search_similar:
            data["fs_similar"] = "on"
        if self.search_exp:
            data["fs_exp"] = "on"
        body, content_type_header = build_multipart_body(
            data,
            file_field="sfile",
            filename="image.jpg",
            file_bytes=image_bytes,
            content_type="application/octet-stream",
        )

        try:
            session = await self._get_session()
            response = await session.post(
                self._upload_url,
                data=body,
                headers={"Content-Type": content_type_header},
                cookies=self.cookies or None,
                allow_redirects=False,
            )
            if getattr(response, "status_code", 0) in _REDIRECT_STATUSES:
                location = response.headers.get("location")
                if location:
                    # 自动跟随会把 multipart Content-Type 带到 GET 上，
                    # E-Hentai 会因此返回 403，所以手动请求结果页。
                    response = await session.get(
                        urllib.parse.urljoin(self._upload_url, location),
                        headers={"Referer": self._upload_url},
                        cookies=self.cookies or None,
                        allow_redirects=True,
                    )
        except ProviderSearchError:
            raise
        except Exception as exc:
            logger.warning(f"[E-Hentai] 请求异常: {type(exc).__name__}")
            raise ProviderSearchError("E-Hentai 请求异常") from exc

        status = getattr(response, "status_code", 0)
        if status != 200:
            raise self._status_error(status)

        try:
            results = self._parse_html(
                response.text,
                response_url=str(getattr(response, "url", "") or ""),
                max_results=self.max_results,
            )
        except ProviderSearchError:
            raise
        except Exception as exc:
            logger.warning(f"[E-Hentai] 解析响应失败: {type(exc).__name__}")
            raise ProviderSearchError("E-Hentai 响应解析失败") from exc

        logger.info(f"[{self._source_name}] 搜索完成，获取 {len(results)} 条结果")
        return results

    def _status_error(self, status: int) -> ProviderSearchError:
        if status in (401, 403):
            return ProviderSearchError(
                f"E-Hentai 返回 HTTP {status}",
                user_notice=(
                    f"{self._source_name} 访问被拒绝，请检查 Cookie 或稍后重试。"
                ),
            )
        if status == 429:
            return ProviderSearchError(
                "E-Hentai 返回 HTTP 429",
                user_notice="E-Hentai 请求过于频繁，请稍后再试。",
            )
        return ProviderSearchError(f"E-Hentai 返回 HTTP {status}")

    def _parse_html(
        self,
        html: str,
        *,
        response_url: str,
        max_results: int,
    ) -> list[SearchResultItem]:
        """解析 E-Hentai 结果页.

        只有明确的无结果页面返回空列表；其他无法识别的页面都按失败处理。
        """
        text = html or ""
        lowered = text.lower()

        if any(marker in lowered for marker in _NO_RESULT_MARKERS):
            return []

        if any(marker in lowered for marker in _CLOUDFLARE_MARKERS):
            raise ProviderSearchError(
                "E-Hentai 返回 Cloudflare 验证页面",
                user_notice="E-Hentai 触发了 Cloudflare 验证，请稍后重试或配置 Cookie。",
            )

        soup = BeautifulSoup(text, "html.parser")
        container = soup.select_one(".itg")
        if container is None:
            if self.use_exhentai:
                raise ProviderSearchError(
                    "ExHentai 未返回可识别结果页",
                    user_notice="ExHentai 认证失败或页面异常，请检查 Cookie。",
                )
            raise ProviderSearchError("无法识别 E-Hentai 响应页面")

        rows = container.select("tr")
        if not rows:
            rows = container.select(".gl1t")

        results: list[SearchResultItem] = []
        for row in rows:
            if len(results) >= max_results:
                break
            item = self._parse_row(row, response_url)
            if item is not None:
                results.append(item)

        if not results:
            raise ProviderSearchError("E-Hentai 结果页面结构不兼容")

        return results

    def _parse_row(
        self,
        row,
        response_url: str,
    ) -> SearchResultItem | None:
        """解析单个画廊结果行，缺少标题或有效链接时返回 None."""
        title_element = row.select_one(".glink, .gllink")
        if title_element is None:
            return None

        title = title_element.get_text(" ", strip=True)
        if not title:
            return None

        gallery_link = title_element.find_parent("a")
        href = gallery_link.get("href") if gallery_link is not None else None
        if not href:
            fallback = row.select_one("a[href]")
            href = fallback.get("href") if fallback is not None else None
        url = self._absolute_url(response_url, href)
        if url is None:
            return None

        thumbnail = ""
        image = row.select_one(".glthumb img, .gl1e img, .gl3t img")
        if image is not None:
            thumbnail = (
                self._absolute_url(
                    response_url,
                    image.get("data-src") or image.get("src") or "",
                )
                or ""
            )

        type_text = self._first_text(row, ".cs, .cn")
        date_text = self._first_text(row, "[id^='posted']")
        pages_text = self._pages_text(row)

        tags: list[str] = []
        for tag_element in row.select("div.gt, div.gtl"):
            tag = str(tag_element.get("title") or "").strip()
            if tag:
                tags.append(tag)
            if len(tags) >= _MAX_TAGS:
                break

        description_parts: list[str] = []
        if type_text:
            description_parts.append(f"类型: {type_text}")
        if pages_text:
            description_parts.append(f"页数: {pages_text}")
        if date_text:
            description_parts.append(f"上传: {date_text}")

        description = " · ".join(description_parts) or None
        if tags:
            tag_line = "标签: " + "、".join(tags)
            description = f"{description}\n{tag_line}" if description else tag_line

        return SearchResultItem(
            title=title,
            url=url,
            thumbnail=thumbnail,
            thumbnail_bytes=None,
            source=self._source_name,
            similarity=None,
            description=description,
            domain=None,
        )

    @staticmethod
    def _first_text(row, selector: str) -> str:
        element = row.select_one(selector)
        return element.get_text(" ", strip=True) if element is not None else ""

    @staticmethod
    def _pages_text(row) -> str:
        for element in row.select(".gl4c div"):
            text = element.get_text(" ", strip=True)
            if "pages" not in text.lower():
                continue
            parts = text.split()
            if parts and parts[0].isdigit():
                return parts[0]
        return ""

    @staticmethod
    def _absolute_url(base_url: str, value: object) -> str | None:
        if not isinstance(value, str):
            return None
        value = value.strip()
        if not value:
            return None
        absolute = urllib.parse.urljoin(base_url or "", value)
        if absolute.startswith(("http://", "https://")):
            return absolute
        return None
