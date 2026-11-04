"""图床上传编排与全局服务实例."""

from __future__ import annotations

import threading
from collections.abc import Sequence
from urllib.parse import urlsplit

from astrbot.api import logger

from .base import ImageHost, ImageHostError
from .catbox import CatboxHost


def _is_valid_http_url(value: object) -> bool:
    """检查图床返回值是否是可直接使用的 HTTP(S) URL."""
    if not isinstance(value, str):
        return False
    value = value.strip()
    if not value:
        return False
    try:
        parsed = urlsplit(value)
    except ValueError:
        return False
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


class ImageUploadService:
    """按顺序尝试图床并隔离单次失败."""

    def __init__(self, hosts: Sequence[ImageHost]) -> None:
        self._hosts = tuple(hosts)

    @property
    def hosts(self) -> tuple[ImageHost, ...]:
        """当前已配置的图床顺序."""
        return self._hosts

    async def upload(
        self,
        data: bytes,
        *,
        filename: str = "image.jpg",
        content_type: str = "image/jpeg",
    ) -> str | None:
        """上传图片，返回第一个成功图床的 HTTP(S) URL.

        单个图床失败不会中断后续图床；全部失败时返回 None。
        """
        if not data:
            return None

        for host in self._hosts:
            if len(data) > host.max_upload_bytes:
                logger.debug(
                    f"[ImgExploration] 图片超过图床 {host.name} 大小上限，跳过该图床"
                )
                continue

            try:
                url = await host.upload(
                    data,
                    filename=filename,
                    content_type=content_type,
                )
            except ImageHostError as exc:
                logger.warning(f"[ImgExploration] 图床 {host.name} 上传失败: {exc}")
                continue
            except Exception as exc:
                logger.warning(
                    f"[ImgExploration] 图床 {host.name} 未预期异常: "
                    f"{type(exc).__name__}"
                )
                continue

            if _is_valid_http_url(url):
                return url.strip()

            logger.warning(f"[ImgExploration] 图床 {host.name} 返回了无效的图片 URL")

        return None

    async def close(self) -> None:
        """关闭所有图床；单个关闭失败不会阻止其他图床清理."""
        errors: list[Exception] = []
        for host in self._hosts:
            try:
                await host.close()
            except Exception as exc:
                errors.append(exc)

        if errors:
            raise errors[0]


_upload_service: ImageUploadService | None = None
_upload_service_lock = threading.Lock()


def _default_image_hosts() -> list[ImageHost]:
    return [CatboxHost()]


def init_image_upload_service(
    hosts: Sequence[ImageHost] | None = None,
) -> ImageUploadService:
    """初始化全局图床服务；未传入图床时使用默认 Catbox."""
    global _upload_service
    service = ImageUploadService(
        list(hosts) if hosts is not None else _default_image_hosts()
    )
    with _upload_service_lock:
        _upload_service = service
    return service


def get_image_upload_service() -> ImageUploadService:
    """获取全局图床服务，尚未初始化时使用默认 Catbox."""
    global _upload_service
    with _upload_service_lock:
        if _upload_service is None:
            _upload_service = ImageUploadService(_default_image_hosts())
        return _upload_service


async def close_image_upload_service() -> None:
    """关闭并清除全局图床服务."""
    global _upload_service
    with _upload_service_lock:
        service = _upload_service
        _upload_service = None
    if service is not None:
        await service.close()
