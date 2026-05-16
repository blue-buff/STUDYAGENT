#!/usr/bin/env python3
"""
06_scrape_questions.py — 用 Playwright 动态抓取题目详情（题干+答案+解析）
优先不登录抓取（参考项目说详情页不需要登录）
从章节树出发，浏览题目列表，获取题目详情，输出统一 JSON
"""
import sys, json, re, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from playwright.sync_api import sync_playwright
from jyeoo.config import get_config
from jyeoo.utils import setup_logging, ensure_dir, safe_filename, logger

OUTPUT_DIR = Path(__file__).parent.parent / "output" / "sample_questions"
MAX_SCREENSHOTS = 50  # limit to keep total under 100MB


def main():
    setup_logging()
    config = get_config()
    ensure_dir(OUTPUT_DIR)

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox",
                  "--disable-gpu", "--single-process"],
        )

        # Try loading saved cookies if available
        auth_file = OUTPUT_DIR.parent / "auth" / "state.json"
        context_args = {
            "viewport": {"width": 1280, "height": 800},
            "user_agent": config.user_agent,
        }
        if auth_file.exists():
            context_args["storage_state"] = str(auth_file)
            logger.info("Using saved login state")
        else:
            logger.info("No login state found - browsing anonymously")

        context = browser.new_context(**context_args)
        page = context.new_page()

        # Step 1: Navigate to chapter and collect question IDs
        questions = []
        subjects_to_try = [
            ("math2", "高中数学", "c0432701-d7a0-441a-bd2c-705026c94501", "人教版2024八年级上"),
            ("math", "初中数学", "f856283e-e8ab-47c9-906a-7705781aa643", "人教版八年级上"),
        ]

        for subj_path, display, bk_guid, desc in subjects_to_try:
            if len(questions) >= 30:
                break

            logger.info(f"\n{'='*60}")
            logger.info(f"Searching questions: {display} - {desc}")
            logger.info(f"{'='*60}")

            url = f"https://www.jyeoo.com/{subj_path}/ques/search?f=0&bk={bk_guid}"
            logger.info(f"Loading: {url}")
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(3000)

            # Try to find question links
            question_urls = page.evaluate("""() => {
                let urls = [];
                let links = document.querySelectorAll('a[href*="/ques/detail/"]');
                for (let a of links) {
                    urls.push({
                        url: a.href,
                        text: a.textContent.trim().substring(0, 100)
                    });
                }
                return urls;
            }""")

            logger.info(f"  Found {len(question_urls)} question detail links on listing page")

            if not question_urls:
                # Try alternative selectors
                # Maybe questions are loaded as divs with data attributes
                ques_data = page.evaluate("""() => {
                    let ids = [];
                    document.querySelectorAll('[id*="ques"], [data-quesid], [data-qid]').forEach(el => {
                        ids.push(el.outerHTML.substring(0, 200));
                    });
                    return ids;
                }""")
                logger.info(f"  Alternative question elements: {len(ques_data)}")
                for qd in ques_data[:3]:
                    logger.info(f"    {qd}")

                # Try clicking chapter nodes to load questions
                logger.info("  Trying to click first chapter node...")
                clicked = page.evaluate("""() => {
                    let tree = document.querySelector('#divTree');
                    if (!tree) return false;
                    let firstLink = tree.querySelector('a');
                    if (firstLink) {
                        firstLink.click();
                        return true;
                    }
                    return false;
                }""")
                if clicked:
                    logger.info("  Clicked chapter node, waiting for questions...")
                    page.wait_for_timeout(2000)
                    question_urls = page.evaluate("""() => {
                        let urls = [];
                        let links = document.querySelectorAll('a[href*="/ques/detail/"]');
                        for (let a of links) {
                            urls.push({url: a.href, text: a.textContent.trim().substring(0, 100)});
                        }
                        return urls;
                    }""")
                    logger.info(f"  After click: {len(question_urls)} question links")

            # Step 2: Fetch question details
            for i, q in enumerate(question_urls[:15]):
                if len(questions) >= 30:
                    break

                detail_url = q["url"]
                if not detail_url.startswith("http"):
                    detail_url = f"https://www.jyeoo.com{detail_url}"

                logger.info(f"  [{i+1}/{min(15, len(question_urls))}] Fetching: {detail_url}")
                page.goto(detail_url, wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(2000)

                # Extract question data
                q_data = parse_question_page(page, detail_url, display)
                if q_data:
                    questions.append(q_data)
                    logger.info(f"    OK: question={len(q_data['question_text'])} chars, "
                                f"answer={len(q_data['answer_text'])} chars")
                else:
                    logger.warning("    Failed to parse question")

                time.sleep(2)

        # Step 3: Try physics and chemistry search pages to find questions
        for subj_path, display in [("physics", "初中物理"), ("physics2", "高中物理"),
                                    ("chemistry", "初中化学"), ("chemistry2", "高中化学")]:
            if len(questions) >= 30:
                break

            logger.info(f"\nQuick scan: {display} (/{subj_path}/)")
            url = f"https://www.jyeoo.com/{subj_path}/ques/search"
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(2000)

            detail_urls = page.evaluate("""() => {
                let urls = [];
                document.querySelectorAll('a[href*="/ques/detail/"]').forEach(a => {
                    urls.push(a.href);
                });
                return urls;
            }""")
            logger.info(f"  Found {len(detail_urls)} detail links")

        browser.close()

    # Step 4: Save questions
    logger.info(f"\n{'='*60}")
    logger.info(f"Saving {len(questions)} questions")
    logger.info(f"{'='*60}")

    for q in questions:
        sid = q.get("source_id", "")[:24] or "unknown"
        fname = safe_filename(f"{sid}.json")
        path = OUTPUT_DIR / fname
        with open(path, "w", encoding="utf-8") as f:
            json.dump(q, f, ensure_ascii=False, indent=2)

    all_path = OUTPUT_DIR / "all_questions.json"
    with open(all_path, "w", encoding="utf-8") as f:
        json.dump(questions, f, ensure_ascii=False, indent=2)

    logger.info(f"Saved to {OUTPUT_DIR}")
    logger.info(f"  Individual: {len(questions)} files")
    logger.info(f"  Combined: {all_path}")

    # Stats
    if questions:
        has_text = sum(1 for q in questions if q.get("question_text"))
        has_answer = sum(1 for q in questions if q.get("answer_text"))
        has_analysis = sum(1 for q in questions if q.get("analysis"))
        logger.info(f"Stats: text={has_text}/{len(questions)}, "
                     f"answer={has_answer}/{len(questions)}, "
                     f"analysis={has_analysis}/{len(questions)}")


def parse_question_page(page, url, subject_display):
    """Extract question data from a detail page."""
    data = page.evaluate("""() => {
        function getText(selector) {
            let el = document.querySelector(selector);
            return el ? el.innerText.trim() : '';
        }
        function getTextByContent(keyword) {
            // Find element containing keyword and get parent text
            let walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
            let node;
            while (node = walker.nextNode()) {
                if (node.textContent.includes(keyword)) {
                    let parent = node.parentElement;
                    if (parent) return parent.innerText.trim();
                }
            }
            return '';
        }

        let result = {};

        // Question text — try multiple selectors
        result.question = getText('.fieldtip-question') ||
                          getText('.question-content') ||
                          getText('.ques-content') ||
                          getText('.timu') ||
                          getText('.detail-content');

        // Answer text
        result.answer = getText('.fieldtip-answer') ||
                        getText('.answer-content') ||
                        getText('.answer_detail') ||
                        getText('.daan');

        // Analysis
        result.analysis = getText('.fieldtip-analysis') ||
                          getText('.analysis-content') ||
                          getText('.analysis_detail') ||
                          getText('.jiexi');

        // Knowledge points / tags
        result.knowledgePoints = [];
        document.querySelectorAll('a[href*="point"], a[href*="knowledge"], span.tag, span.knowledge').forEach(el => {
            let t = el.textContent.trim();
            if (t && t.length < 30 && !result.knowledgePoints.includes(t)) {
                result.knowledgePoints.push(t);
            }
        });

        // Metadata: type, difficulty, year, grade
        result.meta = {};
        let metaSpans = document.querySelectorAll('span[class*="type"], span[class*="diff"], span[class*="grade"], span[class*="year"]');
        metaSpans.forEach(el => {
            let cls = el.className;
            let text = el.textContent.trim();
            if (cls.includes('type')) result.meta.type = text;
            if (cls.includes('diff')) result.meta.difficulty = text;
            if (cls.includes('grade')) result.meta.grade = text;
            if (cls.includes('year')) result.meta.year = text;
        });

        // Options (A/B/C/D for multiple choice)
        result.options = [];
        document.querySelectorAll('label.option, div.option-item, li.option').forEach(el => {
            let text = el.textContent.trim();
            if (text && text.length < 200) result.options.push(text);
        });

        return result;
    }""")

    if not data or not data.get("question"):
        # Try fallback: get all visible text
        data = page.evaluate("""() => {
            let main = document.querySelector('article, main, .main, .content, #content');
            if (!main) main = document.body;
            return {question: main.innerText.substring(0, 3000)};
        }""")

    if not data or not data.get("question"):
        return None

    # Extract question ID from URL
    qid_match = re.search(r"/detail/([\w-]+)", url)
    qid = qid_match.group(1) if qid_match else ""

    return {
        "subject": subject_display,
        "grade": data.get("meta", {}).get("grade", ""),
        "knowledge_points": data.get("knowledgePoints", []),
        "question_type": data.get("meta", {}).get("type", ""),
        "difficulty": data.get("meta", {}).get("difficulty", ""),
        "year": data.get("meta", {}).get("year", ""),
        "question_text": data.get("question", ""),
        "answer_text": data.get("answer", ""),
        "analysis": data.get("analysis", ""),
        "options": data.get("options", []),
        "source_url": url,
        "source_id": qid,
    }


if __name__ == "__main__":
    main()
