# 🔍 图片搜索插件（astrbot_plugin_imgexploration）

<div align="center">

**一个支持多引擎、LLM 工具调用的图片溯源搜索插件**

[![License: AGPL](https://img.shields.io/badge/License-AGPL-blue.svg)](https://opensource.org/licenses/agpl-3.0)
[![CI](https://github.com/iona-s/astrbot_plugin_imgexploration/actions/workflows/ci.yml/badge.svg?branch=master)](https://github.com/iona-s/astrbot_plugin_imgexploration/actions/workflows/ci.yml)
![Python Version](https://img.shields.io/badge/Python-%3E%3D3.12%2C%3C4-blue)
![AstrBot](https://img.shields.io/badge/AstrBot-%3E%3D4.25%2C%3C5-green)
![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20Linux-lightgrey)

</div>


本插件完全开源免费，欢迎 Issue 和 PR。

本项目由[FlanChanXwO](https://github.com/FlanChanXwO)创建，感谢他对插件的贡献
现由[iona-s](https://github.com/iona-s)继续维护

---

## 📸 预览

<div align="center">
  <table>
    <tr>
      <td align="center">
        <img src="https://raw.githubusercontent.com/iona-s/astrbot_plugin_imgexploration/master/assets/google_search.png" width="400" alt="谷歌搜图"/>
        <br/>
        <sub>谷歌搜图</sub>
      </td>
      <td align="center">
        <img src="https://raw.githubusercontent.com/iona-s/astrbot_plugin_imgexploration/master/assets/google_search_llm.png" width="400" alt="谷歌LLM搜图"/>
        <br/>
        <sub>谷歌LLM搜图</sub>
      </td>
      <td align="center">
        <img src="https://raw.githubusercontent.com/iona-s/astrbot_plugin_imgexploration/master/assets/sauce_search.png" width="400" alt="sauce搜图"/>
        <br/>
        <sub>sauce搜图</sub>
      </td>
      <td align="center">
        <img src="https://raw.githubusercontent.com/iona-s/astrbot_plugin_imgexploration/master/assets/2d_search.jpg" width="400" alt="2d搜图"/>
        <br/>
        <sub>2d搜图</sub>
      </td>
    </tr>
  </table>
</div>

---

## 📦 安装

### 环境要求

- Python `>=3.12,<4`
- AstrBot `>=4.25,<5`

### 方式一：通过 AstrBot 插件市场安装（推荐）

在 AstrBot 管理面板中搜索 `astrbot_plugin_imgexploration` 并安装。

### 方式二：手动安装

1. 克隆本仓库到 AstrBot 的插件目录：
   ```bash
   cd AstrBot/data/plugins
   git clone https://github.com/iona-s/astrbot_plugin_imgexploration.git
   ```
2. 安装依赖：
   ```bash
   pip install -r requirements.txt
   ```
3. 重启 AstrBot 或重载插件

---

## 🛠️ 配置项

### SauceNAO（`saucenao`）

| 配置项 | 类型 | 说明 | 默认值 |
|--------|------|------|--------|
| `enable` | 布尔值 | 启用 SauceNAO | `true` |
| `api_key` | 字符串 | SauceNAO API Key，必填；未填写时不加载 SauceNAO | 空 |
| `similarity_threshold` | 整数 | 相似度阈值 | `40` |
| `max_results` | 整数 | 最大结果数量 | `3` |

### SerpAPI（`serpapi`）

SerpAPI 相关引擎共享同一组 API Keys 与额度。多个 Key 会按顺序轮询使用；启用多个 SerpAPI 引擎后，每次无参数搜图会额外消耗相应次数的额度。

| 配置项 | 类型 | 说明 | 默认值 |
|--------|------|------|--------|
| `api_keys` | 列表 | SerpAPI API Keys，多个 Key 轮询使用；留空时不加载任何 SerpAPI 引擎 | 空 |

### Google Lens（`google_lens`）

> API Keys 已迁移到顶层 `serpapi.api_keys`。升级后请在「SerpAPI」配置中重新填写，旧 `google_lens.serpapi_keys` 不会自动迁移。

| 配置项 | 类型 | 说明 | 默认值 |
|--------|------|------|--------|
| `enable` | 布尔值 | 启用 Google Lens | `true` |
| `search_type` | 字符串 | 搜索类型：综合、相似图片、精确匹配或商品 | `all` |
| `language` | 字符串 | Google 结果语言代码 | `zh-cn` |
| `country` | 字符串 | 两位国家代码；留空由 Google 自动决定 | 空 |
| `safe_search` | 布尔值 | 严格过滤成人内容 | `false` |
| `auto_crop` | 布尔值 | 自动聚焦图片主体 | `false` |
| `no_cache` | 布尔值 | 绕过 SerpAPI 一小时缓存 | `false` |
| `max_results` | 整数 | 最大结果数量 | `5` |

### Yandex Images（`yandex_images`）

通过 SerpAPI 调用 Yandex 反向搜图，与 Google Lens 共用 `serpapi.api_keys`。默认关闭；启用后无参数搜图会额外消耗一次 SerpAPI 额度。

Yandex 由 SerpAPI 服务器拉取图片，因此该引擎被选中时，插件会先把图片上传到图床并改用图床 URL（即使原图已经是 HTTP URL，例如 QQ 的临时图片地址）。图床上传不可用时会跳过 Yandex，其它引擎不受影响。

| 配置项 | 类型 | 说明 | 默认值 |
|--------|------|------|--------|
| `enable` | 布尔值 | 启用 Yandex Images | `false` |
| `tab` | 字符串 | 结果标签页：`about` 查找图片出处，`similar` 只返回相似图片 | `about` |
| `family_mode` | 字符串 | 安全搜索：`off`、`moderate`、`strict` | `moderate` |
| `yandex_domain` | 字符串 | Yandex 站点：`yandex.ru`、`yandex.com`、`yandex.com.tr`、`yandex.by`、`yandex.kz`、`yandex.uz` | `yandex.ru` |
| `no_cache` | 布尔值 | 绕过 SerpAPI 一小时缓存 | `false` |
| `max_results` | 整数 | 最大结果数量 | `5` |

### Ascii2d（`ascii2d`）

| 配置项 | 类型 | 说明 | 默认值 |
|--------|------|------|--------|
| `enable` | 布尔值 | 启用 Ascii2d | `true` |
| `session_id` | 字符串 | Ascii2d Session ID，必填；未填写时不加载 Ascii2d | 空 |
| `cf_clearance` | 字符串 | Ascii2d cf_clearance（绕过 CF） | 空 |
| `bovw_max_results` | 整数 | 特征检索最大结果数量 | `3` |
| `color_max_results` | 整数 | 色合检索最大结果数量 | `2` |

### E-Hentai / ExHentai（`ehentai`）

将图片上传到 E-Hentai 进行反向搜图。默认关闭，结果可能包含成人内容。可通过 `搜图 eh` 或 `搜图 ehentai` 显式调用。

| 配置项 | 类型 | 说明 | 默认值 |
|--------|------|------|--------|
| `enable` | 布尔值 | 启用 E-Hentai | `false` |
| `use_exhentai` | 布尔值 | 改用 ExHentai，需要有效 Cookie | `false` |
| `cookies` | 字符串 | E-Hentai / ExHentai Cookie，格式为 `key=value; key2=value2`；ExHentai 必填 | 空 |
| `search_covers` | 布尔值 | 搜索封面图片 | `false` |
| `search_similar` | 布尔值 | 搜索相似图片 | `true` |
| `search_exp` | 布尔值 | 扩展搜索 | `false` |
| `include_in_default` | 布尔值 | 参与无参数搜图 | `false` |
| `max_results` | 整数 | 最大结果数量 | `5` |

### trace.moe（`trace_moe`）

| 配置项 | 类型 | 说明 | 默认值 |
|--------|------|------|--------|
| `enable` | 布尔值 | 启用 trace.moe | `false` |
| `include_in_default` | 布尔值 | 参与无参数搜图 | `false` |
| `api_key` | 字符串 | trace.moe API Key，留空使用免费额度 | 空 |
| `similarity_threshold` | 整数 | 相似度阈值 | `90` |
| `cut_borders` | 布尔值 | 搜索前裁去截图黑边 | `true` |
| `max_results` | 整数 | 最大结果数量 | `3` |

### AI 行为配置

| 配置项 | 类型 | 说明 | 默认值 |
|--------|------|------|--------|
| `image_context_isolation` | 字符串 | 图片上下文隔离模式（`session`/`global`） | `session` |
| `max_images_per_session` | 整数 | 每会话最大图片数 | `20` |
| `image_context_ttl_seconds` | 整数 | 图片上下文保留时长（秒），0 表示不过期 | `0` |
| `max_image_context_sessions` | 整数 | 最大图片上下文会话数（LRU 回收） | `200` |
| `enable_llm_tools` | 布尔值 | 是否向模型提供两个 LLM 搜图工具，命令搜图不受影响 | `true` |
| `llm_tool_response_mode` | 字符串 | LLM 搜图结果展示模式，详见 [LLM 工具调用](#llm-工具调用) | `results_with_summary` |

### 命令配置

| 配置项 | 类型 | 说明 | 默认值 |
|--------|------|------|--------|
| `image_wait_timeout_seconds` | 整数 | 单独发送搜图命令后等待图片的秒数，范围 30–120 | `60` |

### 使用限制

| 配置项 | 类型 | 说明 | 默认值 |
|--------|------|------|--------|
| `search_cooldown_seconds` | 整数 | 同一用户两次搜图之间至少间隔的秒数，默认不限制 | `0` |

### 网络配置

| 配置项 | 类型 | 说明 | 默认值 |
|--------|------|------|--------|
| `proxy_url` | 字符串 | 代理服务器 URL | 空 |
| `allow_image_upload` | 布尔值 | 允许上传图片到第三方图床 | `true` |
| `allow_local_file_access` | 布尔值 | 允许读取本地文件 | `false` |
| `image_hosts.upload_chain` | 列表 | 图床上传顺序，当前支持 `catbox`、`uguu` | `["catbox"]` |

---

## ⚠️ 隐私说明

### 本地文件访问

出于安全考虑，插件默认 **禁止** 读取本地文件（`file://` 路径或磁盘路径如 `C:\path`）。

**风险说明：**
- 允许读取本地文件可能导致服务器上任意可访问文件被上传到第三方图床
- 恶意用户可能利用此功能探测服务器文件结构

**如何开启：**
如确需使用本地文件搜图，在配置中设置 `allow_local_file_access = true`。建议仅在受信任的环境中使用。
开启后，单个本地图片最多读取 200 MB，且不会读取远程主机或网络共享（UNC）路径。

### 图床上传

当搜图引擎需要 HTTP URL 时（如 SauceNAO、Google Lens、Yandex Images、trace.moe），如果用户发送的是本地文件、`file://` 路径或 `base64` 图片，插件会按 `upload_chain` 顺序将图片上传到第三方图床以获取公开可访问的 URL。当前内置图床为 **Catbox (catbox.moe)** 和 **Uguu (uguu.se)**。Uguu 单文件最大 128 MiB，上传文件默认保留 3 小时。

Yandex Images 需要外部服务能够直接访问图片，因此只要该引擎被选中，即使原图已经是 HTTP URL（例如 QQ 的带 `rkey` 临时地址），插件也会先把图片上传到图床再发起搜索。

**这意味着：**
- 图片内容会暴露给配置的第三方图床
- 配置多个图床时，前面的图床失败后图片可能被继续上传到后面的图床
- 上传后的图片 URL 可能被他人访问
- Catbox 服务条款请参考：https://catbox.moe
- Uguu 说明请参考：https://uguu.se/api

启用 E-Hentai 时，插件会把待搜索图片直接上传到 E-Hentai / ExHentai 进行反查，
图片内容因此会提交给该站点，与是否启用第三方图床无关。

**如何关闭：**
在配置中设置 `allow_image_upload = false`，此时插件仅支持 HTTP URL 图片搜图，本地图片/base64 图片将被拒绝；需要图床公网地址的 Yandex Images 会被跳过。

**建议：**
- 对隐私敏感的场景，关闭此功能
- 仅使用 HTTP URL 图片进行搜图
- 或将 `upload_chain` 配置为可信的图床顺序

---

## 📝 使用方法

### 命令方式

可以在同一条消息中附带图片、回复一张图片，或先发送命令再发送图片：

```
搜图
搜图 saucenao
搜图 google
搜图 yandex
搜图 ascii2d
搜图 eh
搜图 anime
搜图 saucenao,google
搜图 sauce,2d
搜图 sauce 2d
```

指定多个搜图引擎时，可用英文逗号、中文逗号、顿号或空格分隔。

如果命令消息包含多张图片，固定使用第一张。命令消息同时包含附图和回复时，
优先使用当前消息附带的图片。

回复一条不含图片的消息发送命令时，插件会提示
`回复消息中未找到图片`，且不会进入图片等待。

单独发送有效命令后，插件会等待同一发送者在同一会话中的下一条含图消息。
成功提交的图片会作为本次搜图命令的输入被消费，不会再作为普通聊天消息进入
后续插件或 LLM 处理。
等待期间的纯文本、其他成员和其他会话不会消费该状态；再次发送无图命令会
提示 `当前已进入搜索模式，请直接发送图片`，且不会改变原截止时间或搜索策略。
即使没有收到后续消息，插件也会在截止时间到达后自动发送
`搜图等待已超时`。

**命令别名：**
- `sauce` = `saucenao`
- `2d` = `ascii2d`
- `lens` = `google`
- `yandeximages` = `yandex`
- `ehentai` = `eh`
- `trace`、`tracemoe`、`whatanime` = `anime`

### trace.moe

`搜图 anime` 通过 trace.moe 查询动画截图的番名、集数、文件内时间点和相似度，
需先开启对应配置项。也可以明确让 AI 查找截图出自哪部动画、哪一集。

| `enable` | `include_in_default` | 行为 |
|---|---|---|
| 关闭 | 任意 | 不加载 trace.moe，命令和 AI 均无法调用 |
| 开启 | 关闭 | 仅明确指定 `anime` 时调用 |
| 开启 | 开启 | 无参数 `搜图` 也会调用 |

- 修改开关后需重载插件。
- 低于 90% 的结果通常不可靠；调低阈值后会标注低置信度候选。
- 多集文件显示集数范围；部分 OVA、特典无法识别集数。
- 成人内容隐藏预览图，不发送预览视频。

### E-Hentai / ExHentai

`搜图 eh` 通过 E-Hentai 上传图片并返回匹配的画廊。默认不参与无参数搜图，
需将 `ehentai.include_in_default` 设为 `true` 后才会加入默认搜索。

| `enable` | `include_in_default` | 行为 |
|---|---|---|
| 关闭 | 任意 | 不加载 E-Hentai，命令和 AI 均无法调用 |
| 开启 | 关闭 | 仅明确指定 `eh`/`ehentai` 时调用 |
| 开启 | 开启 | 无参数 `搜图` 也会调用 |

- 结果可能包含成人内容，请确认使用场景适合后再启用。
- 普通模式无需 Cookie；站点要求验证或使用 ExHentai 时需要填写 `cookies`。
- 启用 `use_exhentai` 但没有有效 Cookie 时不会加载该策略。
- Cloudflare 验证、认证失败和限流会作为搜索错误提示，不会显示成“未找到结果”。

### LLM 工具调用

确保使用支持 Function Calling 的模型（如 GPT-4、Claude、DeepSeek 等），然后：

1. 发送一张图片
2. 说"找一下这张图的来源"或"搜图"
3. AI 会自动调用搜图工具

普通图片和图片表情都会保存在会话上下文中；表情默认不会触发搜图，只有用户明确要求查找该表情来源时才会搜索。

尽管有提示词约束，模型对工具的选择仍具有不确定性。
如需彻底关闭可将 `enable_llm_tools` 设为`false` 。

`llm_tool_response_mode` 提供三种展示方式：

- 发送结果并总结（`results_with_summary`，默认）：插件发送结果后，模型补充简短判断，不重复列出结果。
- 仅发送结果（`results_only`）：插件发送带缩略图的搜索结果后结束本轮，模型不再追加回复。
- 仅由模型展示结果（`llm_only`）：插件不发送结果消息，由模型以纯文本完整展示全部结果，并可附带简短分析。

展示模式不会阻止模型选择或调用搜图工具，如需关闭工具请将 `enable_llm_tools`
设为 `false`；它也不影响 `搜图` 命令，命令搜图的结果总是由插件直接发送。

**注意：** 需要使用支持 `tool_use` 的模型。如果日志显示 `does not support tool_use`，请切换模型。

---

## 🔧 获取 API 密钥

### SauceNAO

1. 访问 https://saucenao.com/user.php?page=search-api
2. 注册/登录账号
3. 获取 API Key

### SerpAPI（Google Lens、Yandex Images）

1. 访问 https://serpapi.com
2. 注册账号（免费版每月 250 次）
3. 获取 API Key，填入顶层 `serpapi.api_keys`

> 从旧版本升级时，原先填写在 `google_lens.serpapi_keys` 的 Keys 不会自动迁移，
> 需要重新填写到 `serpapi.api_keys`。

查找原图或转载来源时，可将 Google Lens 的 `search_type` 设为 `exact_matches`；
`all`、`visual_matches` 和 `products` 模式只展示相似图片结果。

Yandex Images 默认关闭，需将 `yandex_images.enable` 设为 `true`，并与 Google Lens
共用同一组 Keys 和额度；`tab` 为 `about` 时查找出处，为 `similar` 时只返回相似图片。

### Ascii2d

1. 用 **Chrome 浏览器**访问 https://ascii2d.net
2. 上传一个图片然后搜索图片随后进行跳转
3. 通过 Cloudflare 验证
4. 打开开发者工具 (F12) → Application → Cookies
5. 复制 `_session_id` Cookie 的值，填入 Ascii2d 的 `session_id`
6. 复制 `cf_clearance` Cookie 的值，填入 Ascii2d 的 `cf_clearance`

### E-Hentai / ExHentai Cookie（可选）

普通 E-Hentai 通常无需 Cookie。使用 ExHentai 时：

1. 在浏览器登录 ExHentai 并完成站点验证
2. 打开开发者工具 (F12) → Application → Cookies
3. 复制所需 Cookie，按 `key=value; key2=value2` 格式填入 `ehentai.cookies`

Cookie 只用于 E-Hentai / ExHentai 请求，不会写入日志。

### trace.moe（可选）

无需 API Key 即可使用。免费额度按出口 IP 共享，官方当前为滚动 24 小时 100 次、
并发 1，同一出口的其他服务也会占用；额度或并发受限时插件会提示稍后再试。
需要更多额度可在 [trace.moe](https://trace.moe) 获取 API Key，
填入 trace.moe 的 `api_key`。接口限制见
[官方文档](https://soruly.github.io/trace.moe-api/)。

---

## 📖 引擎说明

| 引擎 | 特点 | 适用场景 |
|------|------|----------|
| **SauceNAO** | 动漫图片专精，支持 Pixiv、Danbooru 等数据库 | 动漫插画、二次元图片 |
| **Google Lens** | 通用图片搜索，覆盖面广 | 通用图片、商品、风景 |
| **Yandex Images** | Yandex 反向搜图，可查找图片出处或相似图片，默认关闭 | 通用图片、俄语和欧洲站点来源 |
| **Ascii2d** | 二次元插画搜索；色合检索匹配整体配色，特征检索可找到裁剪或修改过的图片 | 动漫插画、Pixiv/X 来源 |
| **E-Hentai** | 上传图片反查画廊，支持 ExHentai，默认关闭；结果可能包含成人内容 | 动漫、漫画和同人画廊 |
| **trace.moe** | 按动画画面定位番剧、集数和时间点，默认关闭 | 动画截图 |

---

## ⚠️ 常见问题

### 1. Ascii2d 返回 403 错误

解决：重新获取cookie，或尝试使用代理

> 目前2d的反爬还是挺强的，后续会优化这个搜图方式

### 2. 图片没有被识别

解决：
- 确保图片发送后有时间被捕获
- 检查日志是否显示"捕获图片到上下文"

---

## 🤝 开发与贡献

欢迎提交 Issue 和 Pull Request。参与开发前请阅读
[贡献指南](CONTRIBUTING.md)。

---

## 📄 开源协议

本项目基于 [AGPL-3.0](LICENSE) 协议开源。

---

## 🙏 致谢

- [AstrBot](https://github.com/AstrBotDevs/AstrBot) - 强大的 AI 助手框架
- [SauceNAO](https://saucenao.com) - 动漫图片搜索引擎
- [SerpAPI](https://serpapi.com) - Google Lens、Yandex Images API 服务
- [Ascii2d](https://ascii2d.net) - 日本图片搜索网站
- [trace.moe](https://trace.moe) - 动画截图搜索引擎
