#!/usr/bin/env python3
"""
05_dynamic_chapter_tree.py — 用 Playwright 动态展开章节树，提取完整章节/知识点层级
不登录也可运行。先打数学，再扩展物理化学。
"""
import sys, json, re, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from playwright.sync_api import sync_playwright
from jyeoo.config import get_config
from jyeoo.utils import setup_logging, ensure_dir, logger

OUTPUT_DIR = Path(__file__).parent.parent / "output" / "knowledge_trees"


def extract_tree_from_page(page, subject_path, bk_guid, edition_name):
    """Navigate to a book page and extract the chapter tree."""
    url = f"https://www.jyeoo.com/{subject_path}/ques/search?f=0&bk={bk_guid}"
    logger.info(f"  Loading: {url}")
    page.goto(url, wait_until="domcontentloaded", timeout=30000)

    # Wait for the chapter tree to render
    page.wait_for_timeout(2000)

    # The tree is rendered in #divTree or loaded via JS
    tree_div = page.query_selector("#divTree")
    if not tree_div:
        logger.warning(f"    #divTree not found")
        return None

    # Extract tree nodes using zTree API if available
    tree_data = page.evaluate("""() => {
        // Try zTree getNodes
        if (typeof $.fn.zTree !== 'undefined') {
            let treeObj = $.fn.zTree.getZTreeObj('divTree');
            if (treeObj) {
                let nodes = treeObj.getNodes();
                // Convert to plain objects
                return JSON.parse(JSON.stringify(nodes));
            }
        }
        // Try window tree variables
        if (window.treeData) return window.treeData;
        if (window.zNodes) return window.zNodes;
        if (window.chapterTree) return window.chapterTree;
        return null;
    }""")

    if tree_data:
        return tree_data

    # Fallback: extract from DOM
    logger.info("    Tree API not found, extracting from DOM...")
    items = page.evaluate("""() => {
        let items = [];
        let tree = document.querySelector('#divTree');
        if (!tree) return items;
        function walk(el, level) {
            for (let child of el.children) {
                if (child.tagName === 'A' || child.tagName === 'SPAN') {
                    let name = child.textContent.trim();
                    let href = child.getAttribute('href') || '';
                    let id = child.getAttribute('data-id') || '';
                    if (name && name.length < 100) {
                        items.push({name, href, id, level});
                    }
                }
                if (child.children) walk(child, level + 1);
            }
        }
        walk(tree, 0);
        return items;
    }""")

    return items if items else None


def main():
    setup_logging()
    config = get_config()
    ensure_dir(OUTPUT_DIR)

    # Load the book tree from stage 1
    book_tree_path = OUTPUT_DIR / "chapter_trees.json"
    if not book_tree_path.exists():
        logger.error("chapter_trees.json not found. Run parse_chapter_trees.py first.")
        return

    with open(book_tree_path) as f:
        book_trees = json.load(f)

    # Pick math subjects for now
    subjects_to_process = [
        # (path, display, bk_sample)
        ("math", "初中数学", None),
        ("math2", "高中数学", None),
    ]

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox",
                  "--disable-gpu", "--single-process"],
        )
        context = browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent=config.user_agent,
        )
        page = context.new_page()

        for subj_path, display, _ in subjects_to_process:
            logger.info(f"\n{'='*60}")
            logger.info(f"Processing: {display} (/{subj_path}/)")
            logger.info(f"{'='*60}")

            if subj_path not in book_trees:
                logger.warning(f"  No book tree for {subj_path}")
                continue

            editions = book_trees[subj_path]["editions"]
            # Take first 3 editions to test
            for edition in editions[:3]:
                ek = edition["ek"]
                ename = edition["name"]
                logger.info(f"  版本: {ename} (ek={ek})")

                # Take first grade/book from this edition
                grades = edition["grades"]
                if not grades:
                    continue

                # Process up to 2 grades per edition for testing
                all_chapters = {}
                for grade in grades[:2]:
                    bk = grade["bk"]
                    gname = grade["name"]
                    logger.info(f"    {gname} (bk={bk[:20]}...)")

                    chapters = extract_tree_from_page(page, subj_path, bk, ename)
                    if chapters:
                        all_chapters[gname] = {
                            "bk": bk,
                            "gd": grade["gd"],
                            "chapters": chapters,
                        }
                        logger.info(f"      Extracted {_count_nodes(chapters)} nodes")

                    time.sleep(3)  # Delay between requests

                # Save per-edition results
                if all_chapters:
                    fname = f"{subj_path}_{ek}_{ename}.json"
                    out_path = OUTPUT_DIR / fname
                    with open(out_path, "w", encoding="utf-8") as f:
                        json.dump(all_chapters, f, ensure_ascii=False, indent=2)
                    logger.info(f"    Saved to {out_path}")

        browser.close()

    logger.info(f"\nDone. Output in {OUTPUT_DIR}")


def _count_nodes(data):
    if isinstance(data, list):
        total = len(data)
        for item in data:
            if isinstance(item, dict):
                for key in ("children", "nodes", "sub"):
                    if key in item and isinstance(item[key], list):
                        total += _count_nodes(item[key])
        return total
    return 0


if __name__ == "__main__":
    main()
