"""第三方图床接口、实现和上传服务."""

from .base import ImageHost, ImageHostError
from .catbox import CatboxHost
from .factory import build_image_hosts
from .service import (
    ImageUploadService,
    close_image_upload_service,
    get_image_upload_service,
    init_image_upload_service,
)
from .uguu import UguuHost

__all__ = [
    "CatboxHost",
    "ImageHost",
    "ImageHostError",
    "ImageUploadService",
    "UguuHost",
    "build_image_hosts",
    "close_image_upload_service",
    "get_image_upload_service",
    "init_image_upload_service",
]
