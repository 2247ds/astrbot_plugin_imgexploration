"""根据插件配置构建图床列表."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from astrbot.api import logger

from ..constant import DEFAULT_IMAGE_UPLOAD_CHAIN
from .base import ImageHost
from .catbox import CatboxHost
from .uguu import UguuHost

_IMAGE_HOST_BUILDERS = {
    "catbox": CatboxHost,
    "uguu": UguuHost,
}


def _normalize_upload_chain(value: Any) -> list[str]:
    """将配置中的上传链规范化为图床键名列表."""
    if value is None:
        return list(DEFAULT_IMAGE_UPLOAD_CHAIN)
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, (list, tuple)):
        logger.warning("[ImgExploration] 图床上传顺序配置无效，使用默认 Catbox")
        return list(DEFAULT_IMAGE_UPLOAD_CHAIN)

    chain: list[str] = []
    for item in value:
        if not isinstance(item, str):
            continue
        key = item.strip().lower()
        if key and key not in chain:
            chain.append(key)
    return chain


def build_image_hosts(config: Mapping[str, Any]) -> list[ImageHost]:
    """按 ``image_hosts.upload_chain`` 顺序创建图床实例.

    缺失配置时保持旧版行为，使用 Catbox；显式配置空列表时不加载任何图床。
    """
    image_hosts_config = config.get("image_hosts")
    if not isinstance(image_hosts_config, Mapping):
        image_hosts_config = {}

    upload_chain = _normalize_upload_chain(image_hosts_config.get("upload_chain"))
    hosts: list[ImageHost] = []
    for key in upload_chain:
        builder = _IMAGE_HOST_BUILDERS.get(key)
        if builder is None:
            logger.warning(
                f"[ImgExploration] 未找到图床 '{key}'，已跳过；"
                f"当前支持: {', '.join(sorted(_IMAGE_HOST_BUILDERS))}"
            )
            continue
        hosts.append(builder())

    return hosts
