"""
Path 8: Document Platform Exam Paper → Structured Questions
Configuration module.
"""

import os

# ── Output ─────────────────────────────────────────────────────────────────
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ── Document Platform Configs ──────────────────────────────────────────────
PLATFORMS = {
    "wenku": {
        "name": "百度文库",
        "domain": "wenku.baidu.com",
        "search_url": "https://wenku.baidu.com/search?word={query}",
        "free_access": "全文档可在线预览（分页），下载需VIP",
        "viewer_type": "HTML5 Canvas + 文本层",
        "text_layer_selector": ".reader-txt, .txt, [class*=reader-txt]",
        "page_container": ".page-container, .reader-page",
        "next_page_btn": ".next-page, .page-next, [class*=next]",
    },
    "doc88": {
        "name": "道客巴巴",
        "domain": "doc88.com",
        "search_url": "https://www.doc88.com/search?q={query}",
        "free_access": "前几页免费预览，全文需登录/积分",
        "viewer_type": "HTML5 图片 + 文本层",
        "text_layer_selector": ".page-txt, .txt-layer, [class*=txt]",
        "page_container": ".page-box, .page-container",
        "next_page_btn": ".next, .page-next",
    },
    "docin": {
        "name": "豆丁网",
        "domain": "docin.com",
        "search_url": "https://www.docin.com/search?q={query}",
        "free_access": "部分文档免费预览，下载需积分",
        "viewer_type": "HTML5 图片 + 文本层",
        "text_layer_selector": ".page-txt, .txt-content, [class*=txt]",
        "page_container": ".page-item, .page-container",
        "next_page_btn": ".next, .page-next",
    },
}

# ── Search Configuration ───────────────────────────────────────────────────
SEARCH_TEMPLATES = [
    "{subject} {knowledge_point} 高考真题 试卷",
    "{subject} {knowledge_point} 模拟试卷 含答案",
    "{subject} {knowledge_point} 高三 试题",
    "高中{subject} {knowledge_point} 练习题",
]

MAX_SEARCH_RESULTS = 10
MAX_PAPERS_TO_FETCH = 5

# ── Playwright Configuration ──────────────────────────────────────────────
PLAYWRIGHT_TIMEOUT = 30_000       # page timeout (ms)
PLAYWRIGHT_WAIT_AFTER_LOAD = 3000 # wait for JS to render (ms)
PLAYWRIGHT_HEADLESS = False       # headful needed for JS-rendered viewers
MAX_PAGES_PER_PAPER = 10          # max pages to scroll through

# ── LLM Configuration ─────────────────────────────────────────────────────
ANTHROPIC_BASE_URL = os.environ.get("ANTHROPIC_BASE_URL", "https://api.deepseek.com/anthropic")
ANTHROPIC_AUTH_TOKEN = os.environ.get("ANTHROPIC_AUTH_TOKEN", "")
ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_DEFAULT_SONNET_MODEL", "deepseek-v4-pro")

# ── Subject Taxonomy (reused from path5) ──────────────────────────────────
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
