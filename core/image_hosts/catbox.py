"""Catbox 图床实现."""

from __future__ import annotations

import aiohttp

from ..constant import (
    CATBOX_MAX_UPLOAD_BYTES,
    DEFAULT_USER_AGENT,
    HTTP_TIMEOUT_SECONDS,
)
from .base import ImageHost, ImageHostError

CATBOX_UPLOAD_URL = "https://catbox.moe/user/api.php"


class CatboxHost(ImageHost):
    """使用 Catbox 匿名文件上传接口的图床."""

    key = "catbox"
    name = "Catbox"
    max_upload_bytes = CATBOX_MAX_UPLOAD_BYTES

    async def upload(
        self,
        data: bytes,
        *,
        filename: str,
        content_type: str,
    ) -> str:
        if not data:
            raise ImageHostError("图片数据为空")
        if len(data) > self.max_upload_bytes:
            raise ImageHostError("图片超过 Catbox 大小上限")

        # 延迟导入，避免 utils 与图床包之间形成模块级循环依赖。
        from .. import utils as utils_module

        client_timeout = aiohttp.ClientTimeout(total=HTTP_TIMEOUT_SECONDS)
        proxy = utils_module.get_proxy_url()

        try:
            session = await utils_module.get_aiohttp_session()
            form = aiohttp.FormData()
            form.add_field("reqtype", "fileupload")
            form.add_field(
                "fileToUpload",
                data,
                filename=filename,
                content_type=content_type,
            )

            headers = {"User-Agent": DEFAULT_USER_AGENT}
            async with session.post(
                CATBOX_UPLOAD_URL,
                data=form,
                headers=headers,
                timeout=client_timeout,
                proxy=proxy,
            ) as resp:
                if resp.status != 200:
                    raise ImageHostError(f"HTTP {resp.status}")

                url = (await resp.text()).strip()
                # Catbox 直接返回图片 URL，不返回 JSON。
                if not url.startswith("https://"):
                    raise ImageHostError("响应不是有效的 HTTPS 图片地址")
                return url
        except ImageHostError:
            raise
        except Exception as exc:
            # 异常文本可能包含带认证信息的代理地址，只向上抛出异常类型。
            raise ImageHostError(f"上传异常: {type(exc).__name__}") from exc
