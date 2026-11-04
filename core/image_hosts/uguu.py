"""Uguu 图床实现."""

from __future__ import annotations

import aiohttp

from ..constant import DEFAULT_USER_AGENT, HTTP_TIMEOUT_SECONDS
from .base import ImageHost, ImageHostError

UGUU_UPLOAD_URL = "https://uguu.se/upload"
UGUU_MAX_UPLOAD_BYTES = 128 * 1024 * 1024


class UguuHost(ImageHost):
    """使用 Uguu 上传接口的临时图床.

    Uguu 的公开实例限制单文件最大 128 MiB，文件默认保留 3 小时。
    """

    key = "uguu"
    name = "Uguu"
    max_upload_bytes = UGUU_MAX_UPLOAD_BYTES

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
            raise ImageHostError("图片超过 Uguu 大小上限")

        # 延迟导入，避免 utils 与图床包之间形成模块级循环依赖。
        from .. import utils as utils_module

        client_timeout = aiohttp.ClientTimeout(total=HTTP_TIMEOUT_SECONDS)
        proxy = utils_module.get_proxy_url()

        try:
            session = await utils_module.get_aiohttp_session()
            form = aiohttp.FormData()
            form.add_field(
                "files[]",
                data,
                filename=filename,
                content_type=content_type,
            )

            headers = {"User-Agent": DEFAULT_USER_AGENT}
            async with session.post(
                UGUU_UPLOAD_URL,
                params={"output": "json"},
                data=form,
                headers=headers,
                timeout=client_timeout,
                proxy=proxy,
            ) as resp:
                if resp.status != 200:
                    raise ImageHostError(f"HTTP {resp.status}")

                payload = await resp.json()
                if not isinstance(payload, dict) or payload.get("success") is not True:
                    raise ImageHostError("Uguu API 返回失败")

                files = payload.get("files")
                if not isinstance(files, list) or not files:
                    raise ImageHostError("Uguu 响应缺少文件信息")

                first_file = files[0]
                if not isinstance(first_file, dict):
                    raise ImageHostError("Uguu 响应文件信息格式无效")

                url = first_file.get("url")
                if not isinstance(url, str) or not url.strip():
                    raise ImageHostError("Uguu 响应缺少图片 URL")
                return url.strip()
        except ImageHostError:
            raise
        except Exception as exc:
            # 异常文本可能包含带认证信息的代理地址，只向上抛出异常类型。
            raise ImageHostError(f"上传异常: {type(exc).__name__}") from exc
