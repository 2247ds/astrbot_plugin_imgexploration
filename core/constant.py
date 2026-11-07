"""图片搜索插件常量定义."""

# ==============================================================================
# 网络请求相关
# ==============================================================================

# HTTP 请求超时时间 (秒)
HTTP_TIMEOUT_SECONDS = 30

# 下载图片超时时间 (秒)
IMAGE_DOWNLOAD_TIMEOUT = 20

# 单次下载内容上限 (字节)，防止异常大的响应耗尽内存
MAX_DOWNLOAD_BYTES = 20 * 1024 * 1024

# 本地图片读取上限 (字节)
MAX_LOCAL_IMAGE_BYTES = 200 * 1024 * 1024

# Catbox 图床单文件上传上限 (字节)
CATBOX_MAX_UPLOAD_BYTES = MAX_LOCAL_IMAGE_BYTES

# 图床上传顺序默认值；缺失或迁移前的配置继续使用 Catbox
DEFAULT_IMAGE_UPLOAD_CHAIN = ("catbox",)

# 请求搜图 API、下载图片和上传图床时使用的浏览器 User-Agent
DEFAULT_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/156.0.0.0 Safari/537.36"

# 是否允许上传图片到第三方图床、读取本地文件的默认值
DEFAULT_ALLOW_IMAGE_UPLOAD = True
DEFAULT_ALLOW_LOCAL_FILE_ACCESS = False

# ==============================================================================
# 图片上下文
# ==============================================================================

DEFAULT_IMAGE_CONTEXT_ISOLATION = "session"
DEFAULT_MAX_IMAGES_PER_SESSION = 20
DEFAULT_IMAGE_CONTEXT_TTL_SECONDS = 0
DEFAULT_MAX_IMAGE_CONTEXT_SESSIONS = 200

# LLM 搜图结果展示模式默认值，与旧版关闭静默模式时的行为一致
DEFAULT_LLM_TOOL_RESPONSE_MODE = "results_with_summary"

# ==============================================================================
# SauceNAO 策略
# ==============================================================================

# SauceNAO API 地址
SAUCENAO_BASE_URL = "https://saucenao.com/search.php"

# SauceNAO 默认结果上限
DEFAULT_SAUCENAO_MAX_RESULTS = 3

# SauceNAO 默认相似度阈值 (%)
DEFAULT_SAUCENAO_SIMILARITY_THRESHOLD = 40

# ==============================================================================
# SerpAPI 通用
# ==============================================================================

# SerpAPI 基础 URL
SERPAPI_BASE_URL = "https://serpapi.com"

# SerpAPI 额度耗尽缓存 TTL（秒）
QUOTA_CACHE_TTL = 60

# ==============================================================================
# Google Lens 策略
# ==============================================================================

# Google Lens 默认结果上限
DEFAULT_GOOGLE_LENS_MAX_RESULTS = 5

# Google Lens 搜索选项默认值；搜索类型与旧版不发送 type 时 SerpAPI 的默认值一致
DEFAULT_GOOGLE_LENS_SEARCH_TYPE = "all"
DEFAULT_GOOGLE_LENS_LANGUAGE = "zh-cn"
DEFAULT_GOOGLE_LENS_COUNTRY = ""
DEFAULT_GOOGLE_LENS_SAFE_SEARCH = False
DEFAULT_GOOGLE_LENS_AUTO_CROP = False
DEFAULT_GOOGLE_LENS_NO_CACHE = False

# ==============================================================================
# Yandex Images 策略
# ==============================================================================

# Yandex Images 默认关闭，避免升级后默认搜图额外消耗 SerpAPI 额度
DEFAULT_ENABLE_YANDEX_IMAGES = False

# Yandex Images 是否参与无参数默认搜图
DEFAULT_YANDEX_IMAGES_INCLUDE_IN_DEFAULT = False

# Yandex Images 默认结果上限
DEFAULT_YANDEX_IMAGES_MAX_RESULTS = 5

# Yandex Images 搜索选项默认值；family_mode 与 SerpAPI 默认的 moderate 一致
DEFAULT_YANDEX_IMAGES_TAB = "about"
DEFAULT_YANDEX_IMAGES_FAMILY_MODE = "moderate"
DEFAULT_YANDEX_IMAGES_DOMAIN = "yandex.ru"
DEFAULT_YANDEX_IMAGES_NO_CACHE = False

# ==============================================================================
# Ascii2d 策略
# ==============================================================================

# Ascii2d 基础 URL
ASCII2D_BASE_URL = "https://ascii2d.net"

# Ascii2d 搜索 URL
ASCII2D_SEARCH_URI_URL = f"{ASCII2D_BASE_URL}/search/uri"

# Ascii2d 默认结果上限
DEFAULT_ASCII2D_BOVW_MAX_RESULTS = 3
DEFAULT_ASCII2D_COLOR_MAX_RESULTS = 2

# ==============================================================================
# E-Hentai 策略
# ==============================================================================

# 初始候选端点；需用真实表单/响应核验，尤其注意 ExHentai 的 upld 前缀
EHENTAI_UPLOAD_URL = "https://upld.e-hentai.org/image_lookup.php"
EHENTAI_EX_UPLOAD_URL = "https://upld.exhentai.org/upld/image_lookup.php"

DEFAULT_ENABLE_EHENTAI = False
DEFAULT_EHENTAI_USE_EXHENTAI = False
DEFAULT_EHENTAI_SEARCH_COVERS = False
DEFAULT_EHENTAI_SEARCH_SIMILAR = True
DEFAULT_EHENTAI_SEARCH_EXP = False
DEFAULT_EHENTAI_INCLUDE_IN_DEFAULT = False
DEFAULT_EHENTAI_MAX_RESULTS = 5

# ==============================================================================
# trace.moe
# ==============================================================================

TRACE_MOE_SEARCH_URL = "https://api.trace.moe/search"
DEFAULT_ENABLE_TRACE_MOE = False
DEFAULT_TRACE_MOE_INCLUDE_IN_DEFAULT = False
DEFAULT_TRACE_MOE_SIMILARITY_THRESHOLD = 90
DEFAULT_TRACE_MOE_CUT_BORDERS = True
DEFAULT_TRACE_MOE_MAX_RESULTS = 3

# ==============================================================================
# 策略名称映射
# ==============================================================================

# 策略别名映射 (别名小写 -> get_service_name() 返回值，查找时不区分大小写)
STRATEGY_ALIAS_MAP = {
    "saucenao": "SauceNAO",
    "sauce": "SauceNAO",
    "google": "Google Lens",
    "googlelens": "Google Lens",
    # 命令参数按空白分隔时，“Google Lens” 会被拆成 google 和 lens
    "lens": "Google Lens",
    "yandex": "Yandex Images",
    "yandeximages": "Yandex Images",
    "ascii2d": "Ascii2d",
    "ascii": "Ascii2d",
    "2d": "Ascii2d",
    "ehentai": "E-Hentai",
    "eh": "E-Hentai",
    "anime": "trace.moe",
    "trace": "trace.moe",
    "tracemoe": "trace.moe",
    "whatanime": "trace.moe",
}
