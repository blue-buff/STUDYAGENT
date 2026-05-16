import json
import re
from pathlib import Path
from bs4 import BeautifulSoup
from .session_mgr import SessionManager
from .config import get_config
from .models import KnowledgePoint
from .utils import logger, random_delay, ensure_dir


class KnowledgeTreeExtractor:
    def __init__(self, session_mgr: SessionManager):
        self.sess = session_mgr
        self.config = get_config()
        self.base = self.config.base_url

    def extract_book_tree(self, subject_path: str) -> list[dict]:
        """Extract the JYE_BOOK_TREE_HOLDER structure — editions and grade/books.
        This data is embedded in static HTML (hidden ul)."""
        url = f"{self.base}/{subject_path}/ques/search"
        logger.info(f"Extracting book tree from: {url}")
        random_delay(self.config.request_delay["min"], self.config.request_delay["max"])
        resp = self.sess.get(url, referer=self.base)
        if not resp:
            logger.error(f"Failed to fetch {url}")
            return []
        soup = BeautifulSoup(resp.text, "lxml")
        holder = soup.find("ul", id="JYE_BOOK_TREE_HOLDER")
        if not holder:
            logger.warning("JYE_BOOK_TREE_HOLDER not found")
            return []
        editions = []
        for li in holder.find_all("li", recursive=False):
            ek = li.get("ek", "")
            nm = li.get("nm", "")
            edition = {"ek": ek, "name": nm, "grades": []}
            inner_ul = li.find("ul")
            if inner_ul:
                for grade_li in inner_ul.find_all("li", recursive=False):
                    edition["grades"].append({
                        "bk": grade_li.get("bk", ""),
                        "gd": grade_li.get("gd", ""),
                        "name": grade_li.get("nm", ""),
                    })
            editions.append(edition)
        logger.info(f"Extracted {len(editions)} editions, "
                    f"{sum(len(e['grades']) for e in editions)} grade/books")
        return editions

    def extract_from_page(self, subject_path: str, mode: str = "chapter") -> KnowledgePoint | None:
        f_val = "0" if mode == "chapter" else "1"
        url = f"{self.base}/{subject_path}/ques/search?f={f_val}"
        logger.info(f"Extracting knowledge tree from: {url}")
        random_delay(self.config.request_delay["min"], self.config.request_delay["max"])
        resp = self.sess.get(url, referer=self.base)
        if not resp:
            logger.error(f"Failed to fetch {url}")
            return None

        soup = BeautifulSoup(resp.text, "lxml")
        tree = self._parse_tree_from_html(soup)
        if not tree:
            tree = self._try_extract_from_scripts(soup)
        if not tree:
            tree = self._try_extract_from_api_pattern(url, resp.text)
        return tree

    def _parse_tree_from_html(self, soup: BeautifulSoup) -> KnowledgePoint | None:
        for tree_cls in ("tree", "ztree", "catalog-tree", "knowledge-tree",
                          "chapter-tree", "point-tree", "subject-tree"):
            tree_el = soup.find(["ul", "div"], class_=re.compile(rf".*{tree_cls}.*", re.I))
            if tree_el:
                logger.info(f"Found tree element: {tree_cls}")
                return self._parse_ul_tree(tree_el)
        for tree_id in ("tree", "treeDemo", "catalogTree", "knowledgeTree",
                         "chapterTree", "pointTree"):
            tree_el = soup.find(["ul", "div"], id=tree_id)
            if tree_el:
                logger.info(f"Found tree element by id: {tree_id}")
                return self._parse_ul_tree(tree_el)
        return None

    def _parse_ul_tree(self, ul_el, parent_id: str | None = None, level: int = 0,
                       max_depth: int = 5) -> KnowledgePoint | None:
        root = None
        for li in ul_el.find_all("li", recursive=False):
            a_tag = li.find("a", href=True)
            if not a_tag:
                span_tag = li.find("span")
                name = span_tag.get_text(strip=True) if span_tag else ""
                node_id = ""
                a_tag = li.find("a")
            else:
                name = a_tag.get_text(strip=True)
                href = a_tag.get("href", "")
                node_id = self._extract_id_from_href(href)
            if not name:
                continue
            node = KnowledgePoint(id=node_id, name=name, parent_id=parent_id, level=level)
            child_ul = li.find("ul", recursive=False)
            if child_ul and level < max_depth:
                child_tree = self._parse_ul_tree(child_ul, node_id or name, level + 1, max_depth)
                if child_tree:
                    node.children = child_tree.children if child_tree else []
            if root is None:
                root = node
            else:
                if root.children:
                    root.children.append(node)
                else:
                    root = KnowledgePoint(id="root", name="root", level=-1)
                    root.children.append(node)
        return root

    def _extract_id_from_href(self, href: str) -> str:
        if not href or href == "#" or href.startswith("javascript:"):
            return ""
        patterns = [
            r"(?:pointid|point_id|point|knowledgeid|kpid|chapterid|nodeid|node_id|id)[=/](\w+)",
            r"/(\w{8,}-(?:\w{4,}-)*\w{4,})",
            r"[?&](?:id|pid)=(\w+)",
        ]
        for pat in patterns:
            m = re.search(pat, href, re.I)
            if m:
                return m.group(1)
        return re.sub(r"^.*/", "", href)

    def _try_extract_from_scripts(self, soup: BeautifulSoup) -> KnowledgePoint | None:
        for script in soup.find_all("script"):
            text = script.string or ""
            for pattern in [
                r'(?:var|let|const)\s+(?:zNodes|treeData|treeNodes|knowledgeData|pointData)\s*=\s*(\[.*?\]);',
                r'(?:treeData|knowledgeTree|chapterData)\s*[:=]\s*(\[.*?\]);',
                r'"knowledgePoints?"\s*:\s*(\[.*?\])',
                r'"chapters?"\s*:\s*(\[.*?\])',
            ]:
                m = re.search(pattern, text, re.DOTALL)
                if m:
                    try:
                        data = json.loads(m.group(1))
                        return self._parse_json_tree(data)
                    except (json.JSONDecodeError, ValueError):
                        continue
        return None

    def _parse_json_tree(self, data, parent_id: str | None = None, level: int = 0) -> KnowledgePoint | None:
        if isinstance(data, list):
            root = None
            for item in data:
                node = self._parse_json_node(item, parent_id, level)
                if node:
                    if root is None:
                        root = node
                    else:
                        if not hasattr(root, '_siblings'):
                            root._siblings = []
                        root._siblings.append(node)
            return root
        elif isinstance(data, dict):
            return self._parse_json_node(data, parent_id, level)
        return None

    def _parse_json_node(self, item: dict, parent_id: str | None, level: int) -> KnowledgePoint | None:
        name = item.get("name") or item.get("title") or item.get("label") or ""
        node_id = str(item.get("id") or item.get("value") or item.get("key") or "")
        if not name:
            return None
        node = KnowledgePoint(id=node_id, name=name, parent_id=parent_id, level=level)
        children = item.get("children") or item.get("sub") or item.get("nodes") or item.get("items") or []
        if children and isinstance(children, list):
            for child in children:
                if isinstance(child, dict):
                    cn = self._parse_json_node(child, node_id, level + 1)
                    if cn:
                        node.children.append(cn)
        return node

    def _try_extract_from_api_pattern(self, url: str, html: str) -> KnowledgePoint | None:
        api_patterns = re.findall(r'(?:url|href|src|api|ajax|action)\s*[:=]\s*["\']([^"\']*(?:tree|chapter|point|knowledge|catalog|zNodes)[^"\']*)["\']',
                                  html, re.I)
        if api_patterns:
            logger.info(f"Found potential API endpoints: {api_patterns[:5]}")
        return None

    def save_tree(self, tree: KnowledgePoint | None, subject: str, level: str, output_dir: Path):
        if not tree:
            logger.warning(f"No tree to save for {subject}/{level}")
            return
        ensure_dir(output_dir)
        filename = f"{subject}_{level}.json"
        path = output_dir / filename
        with open(path, "w", encoding="utf-8") as f:
            json.dump(tree.to_dict(), f, ensure_ascii=False, indent=2)
        logger.info(f"Knowledge tree saved to {path}")

    def load_tree(self, subject: str, level: str, input_dir: Path) -> KnowledgePoint | None:
        filename = f"{subject}_{level}.json"
        path = input_dir / filename
        if not path.exists():
            return None
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return self._dict_to_kp(data)

    def _dict_to_kp(self, data: dict) -> KnowledgePoint | None:
        if not data:
            return None
        node = KnowledgePoint(
            id=data.get("id", ""),
            name=data.get("name", ""),
            parent_id=data.get("parent_id"),
            level=data.get("level", 0),
        )
        for child in data.get("children", []):
            cn = self._dict_to_kp(child)
            if cn:
                node.children.append(cn)
        return node
