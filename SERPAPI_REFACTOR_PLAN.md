# SerpAPI 分离重构任务清单

> 状态：待执行
> 依据：master @ `0a29d34`（`core/providers/google_lens_strategy.py` 319 行，SerpAPI 传输层与 Google Lens 引擎逻辑混杂）
> 目标：把 SerpAPI 传输层从 Google Lens 策略中分离，以同一客户端复用新增 Yandex Images / Bing Reverse Image 反搜图引擎
> 说明：本文件是执行清单，完成后可删除或归档；文中 `[ ]` 为待办项，完成即勾选

---

## 0. 已定决策（不再讨论）

| # | 决策 | 结论 |
|---|---|---|
| 1 | Key 归属 | 顶层 `serpapi` 组单池 `api_keys`，全部 SerpAPI 引擎共享一个 `SerpApiClient` 实例（共享轮询指针与额度缓存） |
| 2 | `no_cache` | 保留在各引擎配置组，按调用传入客户端 |
| 3 | 新引擎默认启用 | `false`（opt-in，避免升级后默认搜图额外消耗付费额度） |
| 4 | 参与默认搜图 | 启用即参与，不增加 `include_in_default` |
| 5 | 服务名/别名 | `"Yandex Images"` / `"Bing Reverse Image"`；别名 `yandex`/`yandeximages`、`bing`/`bingreverseimage` |
| 6 | 客户端单测 | 新增 `tests/test_serpapi_client.py`，传输层用例从策略测试迁入，避免三引擎重复覆盖 |
| 7 | 兼容策略 | 不兼容旧版本、不做配置迁移（升级后需在 `serpapi.api_keys` 重新填写 Keys） |

## 1. 明确不做（范围外）

- 配置迁移、`ENGINE_CONFIG_VERSION` 升版、旧值保留回滚
- 共享客户端的增强：401/403/429 分级、额度缓存 TTL 调整、并发选择去重（维持现有语义）
- 分页（Yandex `p`、Bing `next_page_token`/`count`）、裁剪（`crop`/`cat` 等）、`async` 模式、图片上传类参数
- 修改 `ImageSearchStrategy` 接口、`core/service.py` 的聚合方式、图床链路

## 2. 测试改造硬点（先看这张表）

| 文件 | 位置 | 现状 | 必须改动 |
|---|---|---|---|
| `tests/test_google_lens_strategy.py` | `_strategy_with_statuses()` / `test_service_name_and_search_validation()` | `GoogleLensStrategy(api_keys=[...])`、`GoogleLensStrategy(["key-a"])` | 先构造 `SerpApiClient` 再注入；TypeError 断言保留（位置参数仍非法） |
| `tests/test_plugin_configuration.py` | `_patch_strategy_dependencies()`、`test_build_strategies_*` | patch 名单无 `SerpApiClient`；断言 `api_keys=[...]` | 增加 patch 名；断言改为 `serpapi_client=<client>`；补旧配置诊断 warning 用例 |
| `tests/test_logging.py` | `test_google_lens_errors_do_not_log_api_keys()` | 构造 `GoogleLensStrategy(api_keys=...)`；patch `...google_lens_strategy.get_aiohttp_session` | 构造客户端；patch 路径改为 `...core.serpapi.get_aiohttp_session`（旧符号已不存在，否则 `AttributeError`） |
| `tests/test_plugin_imports.py` | `_EXPECTED_CORE_MODULES` | 无新模块 | 追加 `core.serpapi`、`core.providers.serpapi_strategy_base` |

---

## 3. 阶段 1：抽取客户端与策略骨架 + 配置归并

### 3.1 新增 `core/serpapi.py`（传输层，引擎无关）

- [ ] `class SerpApiErrorPayloadError(Exception)`，带 `.message` 属性；**不继承** `ProviderSearchError`（避免上层 `except ProviderSearchError` 误吞）
- [ ] `class SerpApiClient`，构造 `api_keys: list[str] | None`，公开只读属性 `api_keys`
- [ ] `async def search(*, engine, params, no_cache=False, log_tag="SerpAPI") -> dict`
  - [ ] `params` 只含引擎专属参数；客户端按 `api_key`、`engine`、`params`、`no_cache` 合并后 `urlencode` 请求
  - [ ] Key 轮询指针 + `asyncio.Lock`；额度缓存 `_quota_cache`，TTL 用 `constant.QUOTA_CACHE_TTL`
  - [ ] 仅额度耗尽换 Key 重试（401/403/429 与 payload 中 `API key`/`exceeded`）；网络/服务端错误不换 Key、不标记耗尽
  - [ ] 终态失败抛 `ProviderSearchError`（HTTP 非 200（非额度）/网络/JSON 解析/全部 Key 耗尽）
  - [ ] payload 非额度错误：先 `logger.error("[{tag}] SerpAPI 错误: {msg}")` 再抛 `SerpApiErrorPayloadError`（日志保留，不得省略）
  - [ ] 日志只出现 `key[-4:]` 与异常类型名，不出现完整 Key、请求 URL
  - [ ] 不持有 aiohttp session（复用 `utils.get_aiohttp_session`），因此无 `close()` 资源需要清理
- [ ] 单次请求异常的类型化日志：`logger.error("[{tag}] 搜索失败: {类型名}")` 后包装为 `ProviderSearchError`

### 3.2 新增 `core/providers/serpapi_strategy_base.py`

- [ ] `class SerpApiStrategyBase(ImageSearchStrategy)`，构造 `(*, serpapi_client: SerpApiClient, no_cache: bool)`
  - [ ] `no_cache` 视为**已归一化**的 bool；基类不引用任何引擎常量、不自行归一化、不设引擎默认值
- [ ] `search()` 顺序固定：`client.api_keys` 为空 → 非 http(s) URL → `client.search()` → `SerpApiErrorPayloadError` 交 `_interpret_payload_error()` → `_parse_response()`
- [ ] `_parse_response()` 外包 try/except：保留原 `search()` 的 catch-all 语义，未知异常归一化为 `ProviderSearchError("搜索失败: 类型名")`
- [ ] `_interpret_payload_error()` 默认实现：命中 `"hasn't returned any results"` → `[]`（空结果≠失败）；其余 → `ProviderSearchError("SerpAPI 错误: msg")`；允许子类覆写扩展措辞
- [ ] `_log_tag()` 默认 `get_service_name().replace(" ", "")`（维持 `[GoogleLens]` 等现有日志前缀）
- [ ] 抽象钩子：`_engine()` / `_build_params(image_url)` / `_parse_response(data)`；`get_service_name()` 由子类实现
- [ ] 类文档写明：`close()` 继承空实现的原因（无持有资源，session 由插件统一关闭）

### 3.3 瘦身 `core/providers/google_lens_strategy.py`

- [ ] 继承 `SerpApiStrategyBase`；构造签名 `serpapi_client=`, `no_cache: bool | str = DEFAULT_GOOGLE_LENS_NO_CACHE`，并 `super().__init__(serpapi_client=..., no_cache=normalize_bool(no_cache, default=DEFAULT_GOOGLE_LENS_NO_CACHE))`
- [ ] 保留 `GOOGLE_LENS_SEARCH_TYPES`、`search_type`/`language`/`country`/`safe_search`/`auto_crop` 归一化与参数构造（`url`/`type`/`hl`/`auto_crop`/`country`/`safe`）
- [ ] 保留响应解析：`visual_matches`/`exact_matches`/`products`、跳过缺 title/link、`max_results` 截断、`description="站点: {source}"`、逐项解析失败 warning、完成日志
- [ ] 删除 `_normalize_bool`、Key 轮询/额度缓存/HTTP/请求循环等全部传输层代码

### 3.4 归一化函数下沉 `core/utils.py`

- [ ] 新增公开 `normalize_bool(value: object, *, default: bool) -> bool`（逻辑与现 `_normalize_bool` 一致）
- [ ] `google_lens_strategy.py` 改为 `from ..utils import normalize_bool`
- [ ] 确认无其他模块以下划线名跨模块导入该函数

### 3.5 配置与 schema

- [ ] `_conf_schema.json`：新增顶层 `serpapi` 组（置于 `google_lens` 之前）
  - [ ] `api_keys`（list，默认 `[]`），hint 说明：三引擎共享额度、多 Key 轮询、启用多个引擎会让每次默认搜图额外消耗相应次数
- [ ] `_conf_schema.json`：`google_lens` 组删除 `serpapi_keys`；隐形 `api_keys` 组删除 `serpapi_keys`
- [ ] `core/constant.py`：新增 `QUOTA_CACHE_TTL = 60`；`SERPAPI_BASE_URL` 移入 `# SerpAPI 通用` 小节
- [ ] `core/config.py::build_strategies`：清洗 `serpapi.api_keys` → 构造唯一 `SerpApiClient` → 注入 `GoogleLensStrategy(serpapi_client=client, ...)`；无 Keys 时对已启用引擎输出「SerpAPI Keys 未配置，跳过 xx 策略」
- [ ] `core/config.py`：`LEGACY_ENGINE_CONFIG_KEYS` 删除 `("api_keys","serpapi_keys")` 映射（其余引擎迁移逻辑不动）
- [ ] `core/config.py`：新增旧配置诊断——`google_lens.serpapi_keys` 非空且 `serpapi.api_keys` 为空时 `logger.warning` 提示迁移到 `serpapi.api_keys`；**只提示、不迁移**

### 3.6 测试

- [ ] 新增 `tests/serpapi_stub_helpers.py`（供全部 SerpAPI 策略测试共用）
  - [ ] 提供按文件路径加载 `core/serpapi.py` 与 `serpapi_strategy_base.py` 的 loader，封装 `sys.modules` 保存/恢复
  - [ ] 提供 aiohttp/astrbot 桩与 fake session 安装/重置入口，测试结束恢复 `get_aiohttp_session`，避免跨文件模块状态泄漏
  - [ ] 文件本身**不 import** `astrbot`、不 import `tests.helpers`（保持 stub 测试可独立运行）
- [ ] 新增 `tests/test_serpapi_client.py`（传输层行为）
  - [ ] 成功请求按 Key 轮换（`key-a → key-b → key-c`）
  - [ ] HTTP 429 标记耗尽并换 Key；后续请求跳过已耗尽 Key
  - [ ] 全部 Key 耗尽 → `ProviderSearchError`，且不重复打 warning
  - [ ] 非额度 HTTP 500 → `ProviderSearchError`，不换 Key、不标记耗尽
  - [ ] 网络异常 → 只尝试第一个 Key
  - [ ] payload `API key ... exceeded` → 换 Key 重试
  - [ ] payload 非额度错误 → 抛 `SerpApiErrorPayloadError` 且记录 error 日志
  - [ ] 空 `api_keys` → 直接失败
- [ ] 改造 `tests/test_google_lens_strategy.py`
  - [ ] `_strategy_with_statuses` 改为构造 `SerpApiClient` + `GoogleLensStrategy(serpapi_client=...)`
  - [ ] 保留引擎专属用例：参数下发（`type`/`hl`/`country`/`safe`/`auto_crop`/`no_cache`、`engine=google_lens`）、三种响应解析、`max_results` 与无效项计数、无结果措辞→`[]`、服务名、URL 校验、空 Key 失败
  - [ ] 删除已迁入客户端测试的传输层用例
- [ ] 改造 `tests/test_plugin_configuration.py`：见第 2 节表格；另补 schema 默认值与代码常量一致性断言
- [ ] 改造 `tests/test_logging.py`：见第 2 节表格，断言「日志不含任何 API Key」不变
- [ ] 改造 `tests/test_plugin_imports.py`：白名单追加两个新模块

### 3.7 文档

- [ ] README：新增「SerpAPI（`serpapi`）」配置节；Google Lens 表删除 Keys 行并注明共享；升级提示（重新填写 Keys）
- [ ] CHANGELOG：标注 breaking——`serpapi_keys` 从 `google_lens` 迁至 `serpapi.api_keys`，不自动迁移
- [ ] AGENTS.md：Repository Map 增补 `core/serpapi.py`、`core/providers/serpapi_strategy_base.py`、`tests/serpapi_stub_helpers.py`、`tests/test_serpapi_client.py`

### 3.8 验收与提交

- [ ] `python -m pytest tests/test_serpapi_client.py tests/test_google_lens_strategy.py tests/test_plugin_configuration.py tests/test_logging.py tests/test_plugin_imports.py -q`
- [ ] `python -m pytest --cov=astrbot_plugin_imgexploration --cov-branch --cov-report=term-missing`
- [ ] `pre-commit run --all-files`
- [ ] 提交 A：`refactor: 抽取 SerpAPI 通用客户端与策略基类`
- [ ] 提交 B：`refactor: SerpAPI Keys 迁移至共享配置组`

---

## 4. 阶段 2：Yandex Images 反搜图引擎

### 4.1 常量与别名（`core/constant.py`）

- [ ] `DEFAULT_YANDEX_IMAGES_MAX_RESULTS = 5`
- [ ] `DEFAULT_YANDEX_IMAGES_TAB = "about"`
- [ ] `DEFAULT_YANDEX_IMAGES_FAMILY_MODE = "moderate"`
- [ ] `DEFAULT_YANDEX_IMAGES_DOMAIN = ""`
- [ ] `STRATEGY_ALIAS_MAP` 增 `yandex`、`yandeximages` → `"Yandex Images"`（不添加 `images` 这类通用 token）

### 4.2 新增 `core/providers/yandex_images_strategy.py`

- [ ] `get_service_name() -> "Yandex Images"`，`_engine() -> "yandex_images"`
- [ ] `_build_params`：`url`、`tab`；`family_mode` **总是显式下发**（`off→"0"`、`moderate→"1"`、`strict→"2"`，非法值回落 `moderate`）；`yandex_domain` 非空才下发
- [ ] `_parse_response`：兼容 `image_results` **与** `images_results` 两个键（`data.get("image_results") or data.get("images_results")`）
- [ ] 结果项：`title`/`link`/`source`；`thumbnail` 为嵌套对象，取 `thumbnail["link"]`（非 dict 时置空）；`description` 取 `snippet`，无则 `f"站点: {source}"`；`similarity=None`；`domain=None`（`source` 本身即域名）
- [ ] 跳过缺 `title` 或 `link` 项，按 `max_results` 截断；空列表返回 `[]`（成功无结果）
- [ ] 逐项解析异常仅 warning，不影响其余项

### 4.3 配置装配

- [ ] `_conf_schema.json` 新增 `yandex_images` 组：`enable`(false)、`tab`(options: about/similar，hint 说明 similar=相似图而非出处)、`family_mode`(options: off/moderate/strict，hint 说明默认 moderate)、`yandex_domain`(默认空，hint 示例 `yandex.ru`)、`no_cache`(false)、`max_results`(5)
- [ ] hint 增加「启用后无参数搜图会额外消耗一次 SerpAPI 额度」
- [ ] `build_strategies()`：与 Google Lens 共用同一 `SerpApiClient`，启用且 Keys 存在才加载

### 4.4 文案（`main.py`）

- [ ] `_NO_DEFAULT_STRATEGIES_MESSAGE` 示例补充新引擎（如需）
- [ ] `search_image_cmd` docstring：用法示例与别名行补 `yandex`
- [ ] `tool_search_image` 的 `strategies` 参数描述补 `yandex`

### 4.5 测试

- [ ] 新增 `tests/test_yandex_images_strategy.py`（复用 `tests/serpapi_stub_helpers.py`）
  - [ ] 参数下发：`engine=yandex_images`、`url`、`tab`、`family_mode` 取值映射、`yandex_domain` 省略
  - [ ] 响应解析：`image_results` 与 `images_results` 均可解析、嵌套 `thumbnail.link`、`snippet`/`站点: source` 描述
  - [ ] 空数组 → `[]`；缺字段项跳过；`max_results` 截断
  - [ ] payload 无结果措辞 → `[]`；服务名；非 HTTP URL → `ProviderSearchError`
- [ ] `tests/test_plugin_configuration.py`：新增装配用例（共用 client、默认值、enable=false 不加载）
- [ ] `tests/test_service.py` 或新增用例：`搜图 yandex` 别名解析命中

### 4.6 文档与验收

- [ ] README：配置表、引擎说明表、命令用法与别名、致谢
- [ ] `metadata.yaml`：`desc` 补充新引擎
- [ ] CHANGELOG 记录新引擎
- [ ] AGENTS.md：Map 与测试清单补充
- [ ] `python -m pytest tests/test_yandex_images_strategy.py tests/test_plugin_configuration.py tests/test_service.py -q` 通过
- [ ] 提交：`feat: 新增 Yandex Images 搜图引擎（SerpAPI）`

---

## 5. 阶段 3：Bing Reverse Image 引擎

### 5.1 常量与别名

- [ ] `DEFAULT_BING_REVERSE_IMAGE_MAX_RESULTS = 5`、`DEFAULT_BING_REVERSE_IMAGE_MKT = ""`
- [ ] `STRATEGY_ALIAS_MAP` 增 `bing`、`bingreverseimage` → `"Bing Reverse Image"`

### 5.2 新增 `core/providers/bing_reverse_image_strategy.py`

- [ ] `get_service_name() -> "Bing Reverse Image"`，`_engine() -> "bing_reverse_image"`
- [ ] `_build_params`：**`image_url`**（注意不是 `url`）；`mkt` 非空才下发；不发送 `count`（明确取舍：默认拉约 35 条后在本地按 `max_results` 截断）
- [ ] `_parse_response`：解析 `related_content`；`title`/`link`/`thumbnail`/`source`/`domain`，`SearchResultItem.domain` 填 `domain`（`result_sender` 会展示「域名: …」）
- [ ] `image_info` 暂不并入结果（待第 7 节实测确认语义后再决定）
- [ ] 跳过缺 `title` 或 `link` 项；空数组返回 `[]`

### 5.3 配置、文案、测试、文档

- [ ] `_conf_schema.json` 新增 `bing_reverse_image` 组：`enable`(false)、`mkt`(默认空，hint 示例 `en-US`/`zh-CN`)、`no_cache`(false)、`max_results`(5)
- [ ] hint 必须写明：图片宽高需各 ≤ 4000px（SerpAPI 侧限制，插件不预检）；启用后默认搜图额外消耗一次额度
- [ ] `build_strategies()` 注入同一 `SerpApiClient`
- [ ] `main.py` 三处文案补 `bing`
- [ ] 新增 `tests/test_bing_reverse_image_strategy.py`：参数（`image_url`/`mkt`）、`related_content` 解析、`domain` 落位、空数组、缺字段跳过、截断、服务名、URL 校验
- [ ] `tests/test_plugin_configuration.py` 装配用例 + 别名解析用例
- [ ] README/`metadata.yaml`/CHANGELOG/AGENTS.md 同步
- [ ] `python -m pytest tests/test_bing_reverse_image_strategy.py tests/test_plugin_configuration.py tests/test_service.py -q` 通过
- [ ] 提交：`feat: 新增 Bing 反搜图引擎（SerpAPI）`

---

## 6. 阶段 4：收尾

- [ ] 全量 `python -m pytest --cov=astrbot_plugin_imgexploration --cov-branch --cov-report=term-missing`
- [ ] `pre-commit run --all-files`（逐条复核自动修复）
- [ ] AGENTS.md Verification 小节补充新测试文件
- [ ] CHANGELOG 版本条目、`metadata.yaml` 版本号定稿
- [ ] 删除或归档本任务清单
- [ ] 提交：`docs: 更新仓库地图与文档，发布新版本`

---

## 7. 实测任务（需要真实 SerpAPI Key，在阶段 2/3 实施期间完成）

- [ ] Google Lens / Yandex / Bing 各请求一次成功样例，记录真实响应键与字段形态
- [ ] 各引擎「无结果」时的 payload 错误文案，固化为测试夹具或匹配列表（必要时覆写 `_interpret_payload_error`）
- [ ] 各引擎额度耗尽时的错误文案与 HTTP 状态，确认客户端识别规则有效
- [ ] Yandex 反搜图确认返回键是 `image_results` 还是 `images_results`（两项都保留兼容）
- [ ] Bing `image_info` 语义（输入图信息 / 最优匹配），决定是否并入首条结果
- [ ] Bing 超过 4000px 时的报错形态，确认按「引擎失败」上报且不误判为无结果

---

## 8. 提交序列总览

```
1. refactor: 抽取 SerpAPI 通用客户端与策略基类
2. refactor: SerpAPI Keys 迁移至共享配置组        (breaking，需重填 Keys)
3. feat: 新增 Yandex Images 搜图引擎（SerpAPI）
4. feat: 新增 Bing 反搜图引擎（SerpAPI）
5. docs: 更新仓库地图与文档，发布新版本
```

每个提交独立可发布、可回退；阶段 1 的两个提交均为纯结构调整，阶段 2/3 为增量功能且互不依赖。
