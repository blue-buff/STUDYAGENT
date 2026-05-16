import json
import re
from bs4 import BeautifulSoup
from .session_mgr import SessionManager
from .config import get_config
from .models import SiteStructure
from .utils import logger, random_delay


class SubjectAnalyzer:
    def __init__(self, session_mgr: SessionManager):
        self.sess = session_mgr
        self.config = get_config()
        self.base = self.config.base_url

    def analyze_homepage(self) -> dict:
        logger.info("Analyzing homepage...")
        resp = self.sess.get(self.base)
        if not resp:
            logger.error("Failed to fetch homepage")
            return {}
        soup = BeautifulSoup(resp.text, "lxml")
        subjects = self._extract_subject_links(soup)
        logger.info(f"Found {len(subjects)} subject entries from homepage")
        return subjects

    def _extract_subject_links(self, soup: BeautifulSoup) -> dict:
        subjects = {}
        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            text = a.get_text(strip=True)
            if not text:
                continue
            match = re.match(r"^/([a-z]+2?\d?)(/.*)?$", href)
            if not match:
                continue
            path_base = match.group(1)
            if self._is_subject_path(path_base):
                if path_base not in subjects:
                    subjects[path_base] = {"name": text, "links": set()}
                subjects[path_base]["links"].add(href)
        for k in subjects:
            subjects[k]["links"] = sorted(subjects[k]["links"])
        return subjects

    def _is_subject_path(self, path: str) -> bool:
        known = {"math", "math2", "math3", "physics", "physics2", "physics3",
                 "chemistry", "chemistry2", "chemistry3",
                 "bio", "bio2", "bio3", "english", "english2", "english3",
                 "chinese", "chinese2", "chinese3",
                 "geo", "geo2", "politics", "politics2",
                 "history", "history2", "science", "it", "general"}
        return path in known

    def analyze_subject_page(self, subject_path: str) -> dict:
        url = f"{self.base}/{subject_path}/ques/search"
        logger.info(f"Analyzing subject page: {url}")
        random_delay(self.config.request_delay["min"], self.config.request_delay["max"])
        resp = self.sess.get(url, referer=self.base)
        if not resp:
            return {"error": f"Failed to fetch {url}"}

        soup = BeautifulSoup(resp.text, "lxml")
        result = {
            "url": url,
            "status": resp.status_code,
            "title": self._get_title(soup),
            "filters": self._extract_filters(soup),
            "embedded_data": self._extract_embedded_json(soup),
            "scripts": self._extract_script_urls(soup),
        }
        grade_tabs = self._extract_grade_tabs(soup)
        if grade_tabs:
            result["grade_tabs"] = grade_tabs
        return result

    def _get_title(self, soup: BeautifulSoup) -> str:
        title_tag = soup.find("title")
        return title_tag.get_text(strip=True) if title_tag else ""

    def _extract_filters(self, soup: BeautifulSoup) -> dict:
        filters = {}
        filter_areas = soup.find_all(["div", "ul"], class_=re.compile(r".*(filter|type|difficulty|grade).*", re.I))
        for area in filter_areas:
            items = []
            for item in area.find_all(["a", "li", "span", "option"]):
                text = item.get_text(strip=True)
                href = item.get("href", "")
                val = item.get("data-value") or item.get("value") or ""
                if text and len(text) < 20:
                    items.append({"text": text, "value": val, "href": href})
            if items:
                cls = " ".join(area.get("class", []))
                filters[cls] = items
        return filters

    def _extract_embedded_json(self, soup: BeautifulSoup) -> list[dict]:
        results = []
        for script in soup.find_all("script"):
            text = script.string or ""
            json_matches = re.findall(r'(?:var|let|const)\s+\w+\s*=\s*(\[.*?\]|\{.*?\});?\s*\n', text,
                                      re.DOTALL)
            for m in json_matches:
                try:
                    results.append(json.loads(m))
                except (json.JSONDecodeError, ValueError):
                    pass
            inline_json = re.findall(r'(\{[^}]*"code"[^}]*\})', text)
            for m in inline_json:
                try:
                    results.append(json.loads(m))
                except (json.JSONDecodeError, ValueError):
                    pass
        return results

    def _extract_script_urls(self, soup: BeautifulSoup) -> list[str]:
        urls = []
        for script in soup.find_all("script", src=True):
            urls.append(script["src"])
        for link in soup.find_all("link", href=True):
            href = link["href"]
            if any(href.endswith(ext) for ext in (".js", ".css")):
                urls.append(href)
        return urls

    def _extract_grade_tabs(self, soup: BeautifulSoup) -> list[dict]:
        tabs = []
        for el in soup.find_all(["a", "li", "span"], class_=re.compile(r".*(grade|nianji|tab).*", re.I)):
            text = el.get_text(strip=True)
            data_val = el.get("data-value") or el.get("data-id") or ""
            if text and len(text) < 15:
                tabs.append({"text": text, "value": data_val})
        if not tabs:
            for el in soup.select("[data-grade], [data-level]"):
                text = el.get_text(strip=True)
                if text:
                    tabs.append({
                        "text": text,
                        "value": el.get("data-grade") or el.get("data-level", "")
                    })
        return tabs

    def analyze_question_detail(self, detail_url: str) -> dict:
        logger.info(f"Analyzing question detail: {detail_url}")
        random_delay(self.config.request_delay["min"], self.config.request_delay["max"])
        resp = self.sess.get(detail_url, referer=f"{self.base}/math/ques/search")
        if not resp:
            return {"error": f"Failed to fetch {detail_url}"}

        soup = BeautifulSoup(resp.text, "lxml")
        result = {
            "url": detail_url,
            "status": resp.status_code,
            "title": self._get_title(soup),
            "question_text": self._extract_question_text(soup),
            "answer_text": self._extract_answer_text(soup),
            "analysis_text": self._extract_analysis_text(soup),
            "metadata": self._extract_question_meta(soup),
            "knowledge_points": self._extract_kp_tags(soup),
        }
        return result

    def _extract_question_text(self, soup: BeautifulSoup) -> str:
        for cls in ("fieldtip-question", "question-content", "ques-content", "timu",
                     "detail-content", "exam-content"):
            el = soup.find("div", class_=re.compile(rf".*{cls}.*", re.I))
            if el:
                return el.get_text("\n", strip=True)
        main = soup.find("div", class_=re.compile(r".*(question|ques|timu|detail).*", re.I))
        if main:
            return main.get_text("\n", strip=True)[:2000]
        return ""

    def _extract_answer_text(self, soup: BeautifulSoup) -> str:
        for cls in ("fieldtip-answer", "answer-content", "answer_detail", "daan",
                     "ques-answer", "detail-answer"):
            el = soup.find("div", class_=re.compile(rf".*{cls}.*", re.I))
            if el:
                return el.get_text("\n", strip=True)
        for text in ("答案", "解答", "【答案】"):
            el = soup.find(string=re.compile(text))
            if el:
                parent = el.find_parent("div")
                if parent:
                    return parent.get_text("\n", strip=True)[:2000]
        return ""

    def _extract_analysis_text(self, soup: BeautifulSoup) -> str:
        for cls in ("fieldtip-analysis", "analysis-content", "analysis_detail", "jiexi",
                     "detail-analysis", "ques-analysis"):
            el = soup.find("div", class_=re.compile(rf".*{cls}.*", re.I))
            if el:
                return el.get_text("\n", strip=True)
        for text in ("解析", "分析", "考点", "【解析】"):
            el = soup.find(string=re.compile(text))
            if el:
                parent = el.find_parent("div")
                if parent:
                    return parent.get_text("\n", strip=True)[:2000]
        return ""

    def _extract_question_meta(self, soup: BeautifulSoup) -> dict:
        meta = {}
        for el in soup.find_all(["span", "div", "a", "li"], class_=re.compile(r".*(type|difficulty|grade|year|source).*", re.I)):
            text = el.get_text(strip=True)
            cls = " ".join(el.get("class", []))
            if text and len(text) < 50:
                key = "type" if "type" in cls else "difficulty" if "diff" in cls else \
                      "grade" if "grade" in cls else "year" if "year" in cls else \
                      "source" if "source" in cls else "other"
                if key not in meta:
                    meta[key] = text
        return meta

    def _extract_kp_tags(self, soup: BeautifulSoup) -> list[str]:
        kps = []
        for a in soup.find_all("a", href=re.compile(r"(point|knowledge|zhishidian|tag)")):
            text = a.get_text(strip=True)
            if text and len(text) < 30:
                kps.append(text)
        for span in soup.find_all("span", class_=re.compile(r".*(tag|point|knowledge|label).*", re.I)):
            text = span.get_text(strip=True)
            if text and len(text) < 30 and text not in kps:
                kps.append(text)
        return kps
