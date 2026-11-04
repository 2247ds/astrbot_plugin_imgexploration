"""Shared stub helpers for SerpAPI provider tests.

The provider tests load the production modules by file path so they stay
independent of AstrBot and of the test package's import setup. This helper keeps
all temporary modules and patched session functions scoped to one test and
restores them afterwards.
"""

from __future__ import annotations

import contextlib
import importlib.util
import json
import sys
import types
import urllib.parse
from pathlib import Path
from typing import Any

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
CORE_ROOT = PLUGIN_ROOT / "core"
PACKAGE_NAME = "serpapi_test_plugin"

_MODULE_NAMES = (
    "astrbot",
    "astrbot.api",
    "aiohttp",
    PACKAGE_NAME,
    f"{PACKAGE_NAME}.core",
    f"{PACKAGE_NAME}.core.providers",
)


class _Logger:
    """Minimal logger stub; tests can patch its methods with Mock."""

    def __getattr__(self, _name: str):
        return lambda *args, **kwargs: None


class FakeResponse:
    """Minimal aiohttp response used by SerpAPI client tests."""

    def __init__(self, status: int, payload: dict | None = None) -> None:
        self.status = status
        self.payload = payload if payload is not None else {}

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def text(self) -> str:
        return json.dumps(self.payload)


class FakeSession:
    """Fake aiohttp session returning scripted statuses and payloads."""

    def __init__(
        self,
        statuses: list[int | Exception],
        payloads: list[dict] | None = None,
    ) -> None:
        self.statuses = iter(statuses)
        self.payloads = iter(payloads or [])
        self.calls: list[str] = []
        self.queries: list[dict[str, list[str]]] = []
        self.urls: list[str] = []

    def get(self, url: str, **kwargs):
        query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        self.calls.append(query.get("api_key", [""])[0])
        self.queries.append(query)
        self.urls.append(url)
        status = next(self.statuses)
        if isinstance(status, Exception):
            raise status
        return FakeResponse(status, next(self.payloads, None))


def load_module_from_path(module_name: str, module_path: Path) -> types.ModuleType:
    """Load a production module by file path under a temporary module name."""
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load module: {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


class SerpApiStubEnvironment:
    """Temporary AstrBot/aiohttp stub environment for SerpAPI strategy tests.

    Use one instance per test and call :meth:`close` in teardown. The production
    modules are loaded by path and all temporary ``sys.modules`` entries and
    patched session hooks are restored by :meth:`close`.
    """

    def __init__(self) -> None:
        self._saved_modules = {
            name: sys.modules.get(name) for name in self._temporary_names()
        }
        self._restored_attributes: list[tuple[object, str, Any]] = []
        self._install_stub_modules()
        self.constant = self._load_core_module("constant")
        self.models = self._load_core_module("models")
        self.strategy = self._load_core_module("strategy")
        self.utils = self._load_core_module("utils")
        self.serpapi = self._load_core_module("serpapi")
        self.serpapi_base = load_module_from_path(
            f"{PACKAGE_NAME}.core.providers.serpapi_strategy_base",
            CORE_ROOT / "providers" / "serpapi_strategy_base.py",
        )
        self.google_lens = load_module_from_path(
            f"{PACKAGE_NAME}.core.providers.google_lens_strategy",
            CORE_ROOT / "providers" / "google_lens_strategy.py",
        )

    def _temporary_names(self) -> tuple[str, ...]:
        return (
            *_MODULE_NAMES,
            f"{PACKAGE_NAME}.core.constant",
            f"{PACKAGE_NAME}.core.models",
            f"{PACKAGE_NAME}.core.strategy",
            f"{PACKAGE_NAME}.core.utils",
            f"{PACKAGE_NAME}.core.serpapi",
            f"{PACKAGE_NAME}.core.providers.serpapi_strategy_base",
            f"{PACKAGE_NAME}.core.providers.google_lens_strategy",
        )

    def _install_stub_modules(self) -> None:
        astrbot = types.ModuleType("astrbot")
        astrbot_api = types.ModuleType("astrbot.api")
        astrbot_api.logger = _Logger()
        sys.modules["astrbot"] = astrbot
        sys.modules["astrbot.api"] = astrbot_api

        aiohttp = types.ModuleType("aiohttp")
        aiohttp.ClientTimeout = lambda **kwargs: kwargs
        aiohttp.ClientSession = object
        sys.modules["aiohttp"] = aiohttp

        package = types.ModuleType(PACKAGE_NAME)
        package.__path__ = []
        sys.modules[PACKAGE_NAME] = package

        core_package = types.ModuleType(f"{PACKAGE_NAME}.core")
        core_package.__path__ = []
        sys.modules[f"{PACKAGE_NAME}.core"] = core_package

        providers_package = types.ModuleType(f"{PACKAGE_NAME}.core.providers")
        providers_package.__path__ = []
        sys.modules[f"{PACKAGE_NAME}.core.providers"] = providers_package

    def _load_core_module(self, name: str) -> types.ModuleType:
        return load_module_from_path(
            f"{PACKAGE_NAME}.core.{name}",
            CORE_ROOT / f"{name}.py",
        )

    def load_provider(self, filename: str) -> types.ModuleType:
        """Load an additional provider strategy module by file name."""
        module_name = f"{PACKAGE_NAME}.core.providers.{Path(filename).stem}"
        module = load_module_from_path(
            module_name,
            CORE_ROOT / "providers" / filename,
        )
        self._saved_modules.setdefault(module_name, None)
        return module

    def install_fake_session(
        self,
        statuses: list[int | Exception],
        payloads: list[dict] | None = None,
        *,
        module: types.ModuleType | None = None,
    ) -> FakeSession:
        """Install a scripted fake session on a SerpAPI module."""
        target = module or self.serpapi
        session = FakeSession(statuses, payloads)

        async def get_session():
            return session

        self._restore_attributes(target, "get_aiohttp_session")
        target.get_aiohttp_session = get_session
        self._restore_attributes(target, "get_proxy_url")
        target.get_proxy_url = lambda: None
        return session

    def _restore_attributes(self, module: types.ModuleType, name: str) -> None:
        if any(
            owner is module and attr == name
            for owner, attr, _ in self._restored_attributes
        ):
            return
        self._restored_attributes.append((module, name, getattr(module, name, None)))

    def close(self) -> None:
        """Restore patched attributes and saved ``sys.modules`` entries."""
        for module, name, original in reversed(self._restored_attributes):
            if original is None:
                with contextlib.suppress(AttributeError):
                    delattr(module, name)
            else:
                setattr(module, name, original)
        self._restored_attributes.clear()

        for name, module in self._saved_modules.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module
        self._saved_modules.clear()


def load_serpapi_modules() -> SerpApiStubEnvironment:
    """Create a stub environment with SerpAPI client, base, and Google Lens."""
    return SerpApiStubEnvironment()
