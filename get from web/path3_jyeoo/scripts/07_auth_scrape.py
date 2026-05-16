#!/usr/bin/env python3
"""
07_auth_scrape.py — 使用已保存的 cookie 提取章节树 + 抓取题目
一次性完成：章节结构 → 题目列表 → 题目详情
"""
import sys, json, re, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from playwright.sync_api import sync_playwright
from jyeoo.utils import setup_logging, ensure_dir, logger

OUTPUT = Path(__file__).parent.parent / "output"
STATE = OUTPUT / "auth" / "state.json"
DELAY = 2  # seconds between requests


def main():
    setup_logging()

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--single-process", "--disable-gpu"],
        )
        context = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            storage_state=str(STATE),
            locale="zh-CN",
        )
        page = context.new_page()

        # === PHASE 1: Extract dynamic chapter tree ===
        logger.info("=" * 60)
        logger.info("PHASE 1: Extracting dynamic chapter trees")
        logger.info("=" * 60)

        tree_output = OUTPUT / "knowledge_trees"
        ensure_dir(tree_output)

        subjects = [
            ("math", "初中数学"),
            ("math2", "高中数学"),
            ("physics", "初中物理"),
            ("chemistry", "初中化学"),
        ]

        all_chapters = {}

        for subj, name in subjects:
            logger.info(f"\n{name} (/{subj}/)")
            url = f"https://www.jyeoo.com/{subj}/ques/search?f=0"
            page.goto(url, wait_until="networkidle", timeout=30000)
            page.wait_for_timeout(DELAY * 1000)

            # Extract chapter tree from divTree
            chapters = page.evaluate("""() => {
                let tree = document.querySelector('#divTree');
                if (!tree) return [];
                let result = [];
                function walk(el, level, parentId) {
                    for (let child of el.children) {
                        if (child.tagName === 'LI' || child.tagName === 'A') {
                            let name = child.textContent.trim().replace(/\\s+/g, ' ');
                            let href = child.getAttribute('href') || child.getAttribute('data-url') || '';
                            let id = child.getAttribute('data-id') || child.getAttribute('id') || '';
                            // Extract chapter ID from href
                            let chMatch = href.match(/chapterOrPointNo=([^&]+)/);
                            if (chMatch) id = chMatch[1];
                            if (name && name.length < 80 && !name.includes('目录树错误')) {
                                result.push({name, id, href, level});
                            }
                        }
                        if (child.children && child.children.length > 0) {
                            walk(child, level + 1, '');
                        }
                    }
                }
                walk(tree, 0, '');
                return result;
            }""")

            logger.info(f"  DivTree nodes: {len(chapters)}")
            for ch in chapters[:10]:
                logger.info(f"    {'  ' * ch['level']}{ch['name']}")

            # Try zTree API for full depth
            ztree_nodes = page.evaluate("""() => {
                try {
                    if (typeof $ !== 'undefined' && $.fn.zTree) {
                        let treeObj = $.fn.zTree.getZTreeObj('divTree');
                        if (treeObj) {
                            let nodes = treeObj.transformToArray(treeObj.getNodes());
                            return nodes.map(n => ({
                                name: n.name,
                                id: n.id || n.chapterOrPointNo || '',
                                level: n.level,
                                isParent: n.isParent,
                                children: n.children ? n.children.length : 0
                            }));
                        }
                    }
                } catch(e) {}
                return [];
            }""")

            if ztree_nodes:
                logger.info(f"  zTree nodes: {len(ztree_nodes)}")
                for zn in ztree_nodes[:10]:
                    logger.info(f"    {'  ' * zn['level']}{zn['name']} (id={zn['id'][:30]})")
                chapters = ztree_nodes

            all_chapters[subj] = {"name": name, "chapters": chapters}

            # Save screenshot of the loaded tree
            page.screenshot(path=str(OUTPUT / f"tree_{subj}.png"))

            time.sleep(DELAY)

        # Save chapter trees
        with open(tree_output / "dynamic_chapters.json", "w", encoding="utf-8") as f:
            json.dump(all_chapters, f, ensure_ascii=False, indent=2)
        logger.info(f"\nChapter trees saved to {tree_output / 'dynamic_chapters.json'}")

        # === PHASE 2: Scrape questions ===
        logger.info("\n" + "=" * 60)
        logger.info("PHASE 2: Scraping questions")
        logger.info("=" * 60)

        q_output = OUTPUT / "sample_questions"
        ensure_dir(q_output)
        questions = []

        # Click on chapters and get questions
        for subj, name in [("math", "初中数学"), ("math2", "高中数学")]:
            if len(questions) >= 50:
                break

            url = f"https://www.jyeoo.com/{subj}/ques/search?f=0"
            page.goto(url, wait_until="networkidle", timeout=30000)
            page.wait_for_timeout(DELAY * 1000)

            # Click on chapter nodes to load questions
            clicked = page.evaluate("""() => {
                let tree = document.querySelector('#divTree');
                if (!tree) return 0;
                let links = tree.querySelectorAll('a');
                let count = 0;
                for (let a of links) {
                    if (a.textContent.trim() && count < 3) {
                        a.click();
                        count++;
                    }
                }
                return count;
            }""")

            logger.info(f"  Clicked {clicked} chapters, waiting for questions...")
            page.wait_for_timeout(3000)

            # Get all question detail links
            for attempt in range(3):
                detail_urls = page.evaluate("""() => {
                    let urls = [];
                    document.querySelectorAll('a[href*="/ques/detail/"]').forEach(a => {
                        let text = a.textContent.trim().substring(0, 150);
                        if (text && text.length > 5) {
                            urls.push({url: a.href, text: text});
                        }
                    });
                    return urls;
                }""")

                if detail_urls:
                    logger.info(f"  Found {len(detail_urls)} question links on attempt {attempt+1}")
                    break
                page.wait_for_timeout(2000)

            if not detail_urls:
                logger.warning(f"  No question links found for {name}")
                continue

            # Visit detail pages and extract data
            for i, qlink in enumerate(detail_urls[:15]):
                if len(questions) >= 50:
                    break

                detail_url = qlink["url"]
                logger.info(f"  [{i+1}/{min(15, len(detail_urls))}] {detail_url[-80:]}")

                page.goto(detail_url, wait_until="networkidle", timeout=30000)
                page.wait_for_timeout(1500)

                q_data = page.evaluate("""() => {
                    function getText(sel) {
                        let el = document.querySelector(sel);
                        return el ? el.innerText.trim().substring(0, 5000) : '';
                    }
                    return {
                        question: getText('.fieldtip-question') || getText('.question-content') || getText('.ques-content') || getText('.timu'),
                        answer: getText('.fieldtip-answer') || getText('.answer-content') || getText('.answer_detail'),
                        analysis: getText('.fieldtip-analysis') || getText('.analysis-content') || getText('.jiexi'),
                    };
                }""")

                if not q_data or not q_data.get("question"):
                    # Fallback: get all text from main content area
                    q_data = page.evaluate("""() => {
                        let main = document.querySelector('.main, #main, .content, #content, article');
                        if (!main) main = document.body;
                        let text = main.innerText.substring(0, 6000);
                        // Try to parse out question / answer / analysis sections
                        let parts = {question: text, answer: '', analysis: ''};
                        let qMatch = text.match(/(?:题目|试题|题干)[：:]\\s*([\\s\\S]*?)(?:答案|解答|解析|分析|考点)/);
                        if (qMatch) parts.question = qMatch[1].trim();
                        let aMatch = text.match(/(?:答案|解答)[：:]\\s*([\\s\\S]*?)(?:解析|分析|考点|试题|来源)/);
                        if (aMatch) parts.answer = aMatch[1].trim();
                        let xMatch = text.match(/(?:解析|分析)[：:]\\s*([\\s\\S]*?)(?:来源|试题|考点|$/);
                        if (xMatch) parts.analysis = xMatch[1].trim();
                        return parts;
                    }""")

                if q_data and q_data.get("question"):
                    q_id = re.search(r"/detail/([\w-]+)", detail_url)
                    question = {
                        "subject": name,
                        "source_url": detail_url,
                        "source_id": q_id.group(1) if q_id else "",
                        "question_text": q_data.get("question", ""),
                        "answer_text": q_data.get("answer", ""),
                        "analysis": q_data.get("analysis", ""),
                    }
                    questions.append(question)
                    logger.info(f"    q={len(question['question_text'])}c, a={len(question['answer_text'])}c, x={len(question['analysis'])}c")

                time.sleep(DELAY)

        # Save questions
        for q in questions:
            sid = q["source_id"][:20] or "unknown"
            with open(q_output / f"{sid}.json", "w", encoding="utf-8") as f:
                json.dump(q, f, ensure_ascii=False, indent=2)

        with open(q_output / "all_questions.json", "w", encoding="utf-8") as f:
            json.dump(questions, f, ensure_ascii=False, indent=2)

        logger.info(f"\nSaved {len(questions)} questions to {q_output}")

        # Stats
        subjects_set = set(q["subject"] for q in questions)
        has_answer = sum(1 for q in questions if q["answer_text"])
        has_analysis = sum(1 for q in questions if q["analysis"])
        logger.info(f"Subjects: {subjects_set}")
        logger.info(f"With answer: {has_answer}/{len(questions)}")
        logger.info(f"With analysis: {has_analysis}/{len(questions)}")

        browser.close()


if __name__ == "__main__":
    main()
