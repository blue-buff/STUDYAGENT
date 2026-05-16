#!/usr/bin/env python3
"""
02_extract_knowledge_tree.py — 提取各学科的知识点树结构
从题目搜索页的静态 HTML 中提取章节/知识点层级
不启动浏览器，仅用 requests + BeautifulSoup
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from jyeoo.config import get_config
from jyeoo.session_mgr import SessionManager
from jyeoo.knowledge_tree import KnowledgeTreeExtractor
from jyeoo.url_parser import URLParser
from jyeoo.utils import setup_logging, ensure_dir, logger

OUTPUT_DIR = Path(__file__).parent.parent / "output" / "knowledge_trees"


def main():
    setup_logging()
    config = get_config()
    sess = SessionManager()
    extractor = KnowledgeTreeExtractor(sess)

    ensure_dir(OUTPUT_DIR)

    # Subjects to extract: focus on math first, then try physics and chemistry
    targets = [
        # (subject_path, level_name, display)
        ("math", "junior", "初中数学"),
        ("math2", "senior", "高中数学"),
        ("math3", "primary", "小学数学"),
        ("physics", "junior", "初中物理"),
        ("physics2", "senior", "高中物理"),
        ("chemistry", "junior", "初中化学"),
        ("chemistry2", "senior", "高中化学"),
    ]

    results = {}

    for path, level, display in targets:
        logger.info(f"\n{'=' * 60}")
        logger.info(f"Extracting knowledge tree: {display} (/{path}/)")
        logger.info(f"{'=' * 60}")

        # Try both chapter mode (f=0) and knowledge point mode (f=1)
        for mode, mode_name in [("chapter", "章节"), ("knowledge", "知识点")]:
            tree = extractor.extract_from_page(path, mode)
            if tree:
                logger.info(f"  [{mode_name}] Tree extracted: {tree.name if tree else 'empty'}")
                if tree.children:
                    logger.info(f"    Children: {len(tree.children)}")
                    for child in tree.children[:5]:
                        logger.info(f"      - {child.name} (id={child.id})")
                extractor.save_tree(tree, path, mode, OUTPUT_DIR)
            else:
                logger.warning(f"  [{mode_name}] No tree found in static HTML (likely JS-rendered)")

        # Also save the raw HTML snippet for later analysis
        from bs4 import BeautifulSoup
        import re
        from jyeoo.utils import random_delay

        random_delay(config.request_delay["min"], config.request_delay["max"])
        resp = sess.get(f"{config.base_url}/{path}/ques/search",
                        referer=config.base_url)
        if resp:
            soup = BeautifulSoup(resp.text, "lxml")
            # Look for any tree-related data in script tags
            tree_data_found = False
            for script in soup.find_all("script"):
                text = script.string or ""
                # Search for tree data variables
                for pattern in [r'var\s+(\w*(?:tree|Tree|Nodes|nodes|Data|data|point|chapter)\w*)\s*=\s*',
                                r'(?:setting|settingData|zNodes|treeNodes)\s*[:=]']:
                    m = re.search(pattern, text)
                    if m:
                        logger.info(f"  Found potential tree variable in JS: {m.group(0)[:80]}")
                        tree_data_found = True
            if not tree_data_found:
                logger.info(f"  No tree data variables found in <script> tags (needs JS rendering)")

    logger.info(f"\nKnowledge trees saved to {OUTPUT_DIR}")
    logger.info(f"Files: {list(OUTPUT_DIR.glob('*.json'))}")


if __name__ == "__main__":
    main()
