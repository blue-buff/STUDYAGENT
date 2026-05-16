import re
from urllib.parse import urlparse, parse_qs, urljoin


class URLParser:
    BASE = "https://www.jyeoo.com"

    SUBJECT_ALIASES = {
        "math": "数学", "math2": "高中数学", "math3": "小学数学",
        "physics": "物理", "physics2": "高中物理",
        "chemistry": "化学", "chemistry2": "高中化学",
        "bio": "生物", "bio2": "高中生物",
        "english": "英语", "english2": "高中英语",
        "chinese": "语文", "chinese2": "高中语文",
        "geo": "地理", "geo2": "高中地理",
        "politics": "政治", "politics2": "高中政治",
        "history": "历史", "history2": "高中历史",
        "science": "科学", "it": "信息技术", "general": "通用技术",
    }

    @classmethod
    def parse_subject_path(cls, path: str) -> dict:
        match = re.match(r"^/([a-z]+)(\d)?(/.*)?$", path)
        if not match:
            return {}
        base = match.group(1)
        level_num = match.group(2)
        if level_num == "2":
            level = "senior"
        elif level_num == "3":
            level = "primary"
        else:
            level = "junior"
        return {
            "subject_key": base,
            "level": level,
            "display_name": cls.SUBJECT_ALIASES.get(f"{base}{level_num or ''}", base),
        }

    @classmethod
    def build_search_url(cls, subject: str, level: str = "junior",
                         mode: str = "chapter", **params) -> str:
        suffix = "2" if level == "senior" else "3" if level == "primary" else ""
        path = f"{subject}{suffix}"
        f_val = "1" if mode == "knowledge" else "0"
        url = f"{cls.BASE}/{path}/ques/search?f={f_val}"
        for k, v in params.items():
            if v:
                url += f"&{k}={v}"
        return url

    @classmethod
    def build_detail_url(cls, subject: str, level: str, question_id: str) -> str:
        suffix = "2" if level == "senior" else "3" if level == "primary" else ""
        return f"{cls.BASE}/{subject}{suffix}/ques/detail/{question_id}"

    @classmethod
    def extract_filters_from_url(cls, url: str) -> dict:
        parsed = urlparse(url)
        params = parse_qs(parsed.query)
        return {k: v[0] if len(v) == 1 else v for k, v in params.items()}

    @classmethod
    def identify_url_type(cls, url: str) -> str:
        patterns = [
            (r"/ques/search", "question_search"),
            (r"/ques/detail/([\w-]+)", "question_detail"),
            (r"/paper/search", "paper_search"),
            (r"/paper/recommend", "paper_recommend"),
            (r"/report", "report"),
            (r"/ques/pointtop30", "top_knowledge_points"),
            (r"/ques/topicsearchques", "subject_feature"),
            (r"/featuretopic", "feature_topic"),
            (r"/yoyoai", "ai_assistant"),
            (r"/kejian", "courseware"),
            (r"/eval", "assessment"),
            (r"/homework", "homework"),
            (r"/special/(\w+)", "special_topic"),
        ]
        for pattern, url_type in patterns:
            if re.search(pattern, url):
                return url_type
        return "unknown"

    @classmethod
    def get_all_search_urls(cls) -> list[dict]:
        urls = []
        for key, info in cls.SUBJECT_ALIASES.items():
            is_senior = "高中" in info or key.endswith("2")
            is_primary = "小学" in info or key.endswith("3")
            level = "senior" if is_senior else "primary" if is_primary else "junior"
            base_key = re.sub(r"\d$", "", key)
            urls.append({
                "subject": base_key,
                "level": level,
                "display": info,
                "chapter_url": cls.build_search_url(base_key, level, "chapter"),
                "knowledge_url": cls.build_search_url(base_key, level, "knowledge"),
            })
        return urls
