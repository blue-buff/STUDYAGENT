"""
Path 5: Search Engine + LLM Question Extraction Pipeline
Configuration module.
"""

import os

# ── Search API Configuration ──────────────────────────────────────────────
# Default search backend: "duckduckgo" (free), "brave", "bing"
SEARCH_BACKEND = os.environ.get("SEARCH_BACKEND", "duckduckgo")

# Brave Search API (free tier: 2,000 queries/month)
BRAVE_API_KEY = os.environ.get("BRAVE_API_KEY", "")

# Bing Web Search API (Azure marketplace, free tier: 1,000 queries/month)
BING_API_KEY = os.environ.get("BING_API_KEY", "")

# Number of search results to fetch
SEARCH_MAX_RESULTS = int(os.environ.get("SEARCH_MAX_RESULTS", "10"))

# Timeout for HTTP requests (seconds)
HTTP_TIMEOUT = int(os.environ.get("HTTP_TIMEOUT", "15"))

# ── LLM Configuration ─────────────────────────────────────────────────────
# Use the existing Anthropic-compatible API (routed through DeepSeek)
ANTHROPIC_BASE_URL = os.environ.get("ANTHROPIC_BASE_URL", "https://api.deepseek.com/anthropic")
ANTHROPIC_AUTH_TOKEN = os.environ.get("ANTHROPIC_AUTH_TOKEN", "")
ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_DEFAULT_SONNET_MODEL", "deepseek-v4-pro")

# Alternative: OpenAI API (for comparison testing)
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o")

# LLM to use for extraction: "claude" or "openai"
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "claude")

# ── Output Configuration ───────────────────────────────────────────────────
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ── Subject/Knowledge Point Definitions ────────────────────────────────────
SUBJECTS = {
    "数学": {
        "grade": "高中",
        "knowledge_points": [
            "集合与逻辑", "函数与导数", "三角函数", "数列", "不等式",
            "解析几何", "立体几何", "概率统计", "向量", "复数",
            "排列组合", "二项式定理", "极坐标与参数方程",
        ],
        "question_types": ["选择题", "填空题", "解答题"],
        "difficulty_levels": ["基础", "中等", "较难", "压轴"],
    },
    "物理": {
        "grade": "高中",
        "knowledge_points": [
            "运动学", "力学", "牛顿定律", "曲线运动", "万有引力",
            "机械能", "动量", "电场", "磁场", "电磁感应",
            "交流电", "热学", "光学", "原子物理",
        ],
        "question_types": ["选择题", "实验题", "计算题"],
        "difficulty_levels": ["基础", "中等", "较难", "压轴"],
    },
    "化学": {
        "grade": "高中",
        "knowledge_points": [
            "物质的量", "离子反应", "氧化还原", "元素化合物",
            "元素周期律", "化学反应与能量", "化学反应速率与平衡",
            "水溶液中的离子平衡", "电化学", "有机化学", "化学实验",
        ],
        "question_types": ["选择题", "填空题", "实验题", "计算题"],
        "difficulty_levels": ["基础", "中等", "较难", "压轴"],
    },
}

# Sites that serve static HTML and contain Chinese high school questions
# zujuan.xkw.com / jyeoo.com are JS-rendered — only usable with Playwright
TARGET_SITES = [
    "zhihu.com",
    "blog.csdn.net",
    "doc88.com",
    "docin.com",
    "wenku.baidu.com",
]

# Sites known to require JS rendering (skip when using requests-based fetcher)
JS_ONLY_SITES = [
    "zujuan.xkw.com",
    "jyeoo.com",
]
