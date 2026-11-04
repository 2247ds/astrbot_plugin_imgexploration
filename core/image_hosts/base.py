"""第三方图床接口定义."""

from __future__ import annotations

from abc import ABC, abstractmethod


class ImageHostError(Exception):
    """图床预期上传失败异常.

    表示图床未配置、拒绝请求、返回错误或网络不可用等可预期失败。
    上传编排层可以捕获此异常并尝试下一个图床。
    """


class ImageHost(ABC):
    """第三方图床抽象基类.

    每个图床实现只负责一次上传，并在成功时返回可直接访问的 HTTP(S) URL。
    图床选择、顺序和失败降级由 ``ImageUploadService`` 统一处理。
    """

    key: str
    name: str
    max_upload_bytes: int

    @abstractmethod
    async def upload(
        self,
        data: bytes,
        *,
        filename: str,
        content_type: str,
    ) -> str:
        """上传图片并返回 HTTP(S) URL.

        Raises:
            ImageHostError: 图床预期失败。
        """

    async def close(self) -> None:
        """释放图床持有的资源；默认实现不做任何操作."""
        return None
