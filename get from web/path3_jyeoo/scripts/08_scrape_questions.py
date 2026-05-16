#!/usr/bin/env python3
"""
08_scrape_questions.py — 按章节抓取菁优网题目详情
URL 规则: q={bk_GUID}~{chapter_GUID}~
"""
import sys, json, re, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from playwright.sync_api import sync_playwright
from jyeoo.utils import setup_logging, ensure_dir, logger

OUTPUT = Path(__file__).parent.parent / "output"
STATE = OUTPUT / "auth" / "state.json"


def scrape_subject(page, subj, name, max_questions=40):
    """Scrape questions from a subject by clicking chapters and extracting detail pages."""
    questions = []
    url = f"https://www.jyeoo.com/{subj}/ques/search?f=0"
    page.goto(url, wait_until="networkidle", timeout=30000)
    page.wait_for_timeout(3000)

    # Get all chapter links from divTree
    chapters = page.evaluate("""() => {
        let tree = document.querySelector('#divTree');
        if (!tree) return [];
        let result = [];
        let links = tree.querySelectorAll('a');
        for (let a of links) {
            let text = a.textContent.trim();
            // Chapter links start with "第" (e.g., "第1章 有理数")
            if (text.startsWith('第') && text.includes('章')) {
                result.push({text: text, element: true});
            }
        }
        return result;
    }""")

    logger.info(f"  Found {len(chapters)} chapters")

    for ch in chapters[:8]:  # limit chapters
        if len(questions) >= max_questions:
            break

        ch_name = ch["text"]
        logger.info(f"  Clicking: {ch_name}")

        # Click chapter in divTree
        clicked = page.evaluate("""(chName) => {
            let tree = document.querySelector('#divTree');
            if (!tree) return false;
            let links = tree.querySelectorAll('a');
            for (let a of links) {
                if (a.textContent.trim() === chName) {
                    a.click();
                    return true;
                }
            }
            return false;
        }""", ch_name)

        if not clicked:
            logger.warning(f"    Failed to click")
            continue

        page.wait_for_timeout(3000)

        # Extract question detail URLs from the loaded list
        detail_urls = page.evaluate("""() => {
            let urls = [];
            document.querySelectorAll('a[href*="/ques/detail/"]').forEach(a => {
                let url = a.href;
                if (!urls.find(u => u.url === url)) {
                    urls.push({url: url, text: a.textContent.trim().substring(0, 80)});
                }
            });
            return urls;
        }""")

        logger.info(f"    Questions visible: {len(detail_urls)}")

        # Visit each question detail page
        for i, qlink in enumerate(detail_urls[:5]):  # 5 per chapter
            if len(questions) >= max_questions:
                break

            detail_url = qlink["url"]
            qid = re.search(r"/detail/([\w-]+)", detail_url)
            qid = qid.group(1) if qid else "unknown"

            logger.info(f"    [{i+1}] {qid[:24]}...")

            page.goto(detail_url, wait_until="networkidle", timeout=30000)
            page.wait_for_timeout(1500)

            # Extract question data
            q_data = page.evaluate("""() => {
                // Try specific selectors for jyeoo question detail page
                let q = '', a = '', x = '', kps = [], meta = {};

                // Question text
                for (let sel of ['.fieldtip-question', '.question-content', '.ques-content',
                                  '.timu', '#question', '.detail-question']) {
                    let el = document.querySelector(sel);
                    if (el && el.innerText.trim().length > 10) {
                        q = el.innerText.trim();
                        break;
                    }
                }

                // Answer text
                for (let sel of ['.fieldtip-answer', '.answer-content', '.answer_detail',
                                  '#answer', '.detail-answer']) {
                    let el = document.querySelector(sel);
                    if (el && el.innerText.trim().length > 1) {
                        a = el.innerText.trim();
                        break;
                    }
                }

                // Analysis
                for (let sel of ['.fieldtip-analysis', '.analysis-content', '.analysis_detail',
                                  '.jiexi', '#analysis', '.detail-analysis']) {
                    let el = document.querySelector(sel);
                    if (el && el.innerText.trim().length > 1) {
                        x = el.innerText.trim();
                        break;
                    }
                }

                // Knowledge points
                document.querySelectorAll('a[href*="point"], a[href*="knowledge"], .tag span, .knowledge-item').forEach(el => {
                    let t = el.textContent.trim();
                    if (t && t.length < 40 && !kps.includes(t)) kps.push(t);
                });

                // Options
                let options = [];
                document.querySelectorAll('.option-item, label.option, .choice-item, .exam-item__cnt label').forEach(el => {
                    let t = el.textContent.trim();
                    if (t && t.length > 1 && t.length < 300) options.push(t);
                });

                return {question: q, answer: a, analysis: x, knowledgePoints: kps, options: options, meta: meta};
            }""")

            if q_data and q_data.get("question"):
                # If still empty, try fallback
                if len(q_data["question"]) < 10:
                    fallback = page.evaluate("""() => {
                        let body = document.body.innerText.substring(0, 6000);
                        let parts = {q: body, a: '', x: ''};
                        // Try to split by section headers
                        for (let [label, key] of [['答案', 'a'], ['解答', 'a'], ['解析', 'x'], ['分析', 'x']]) {
                            let idx = body.indexOf(label);
                            if (idx > 0) {
                                let nextIdx = body.indexOf('\\n', idx + 50);
                                parts[key] = body.substring(idx, nextIdx > 0 ? nextIdx : undefined).trim();
                            }
                        }
                        return parts;
                    }""")
                    if fallback and len(fallback.get("q", "")) > 10:
                        q_data["question"] = fallback["q"]
                        q_data["answer"] = fallback.get("a", q_data["answer"])
                        q_data["analysis"] = fallback.get("x", q_data["analysis"])

            if q_data and q_data.get("question", "").strip():
                question = {
                    "subject": name,
                    "chapter": ch_name,
                    "source_url": detail_url,
                    "source_id": qid,
                    "question_text": q_data["question"],
                    "answer_text": q_data.get("answer", ""),
                    "analysis": q_data.get("analysis", ""),
                    "knowledge_points": q_data.get("knowledgePoints", []),
                    "options": q_data.get("options", []),
                }
                questions.append(question)
                logger.info(f"      q={len(question['question_text'])}c, a={len(question['answer_text'])}c, "
                            f"x={len(question['analysis'])}c, kps={len(question['knowledge_points'])}")
            else:
                logger.warning(f"      No question text found")

            time.sleep(2)

        # Go back to search page for next chapter
        page.goto(url, wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(2000)

    return questions


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

        all_questions = []

        for subj, name in [("math", "初中数学"), ("math2", "高中数学"),
                            ("physics", "初中物理"), ("chemistry", "初中化学")]:
            logger.info(f"\n{'='*60}")
            logger.info(f"SCRAPING: {name} (/{subj}/)")
            logger.info(f"{'='*60}")
            qs = scrape_subject(page, subj, name, max_questions=15)
            all_questions.extend(qs)
            logger.info(f"  Got {len(qs)} questions from {name}")

        browser.close()

    # Save results
    q_output = OUTPUT / "sample_questions"
    ensure_dir(q_output)

    for q in all_questions:
        sid = q["source_id"][:30]
        with open(q_output / f"{sid}.json", "w", encoding="utf-8") as f:
            json.dump(q, f, ensure_ascii=False, indent=2)

    with open(q_output / "all_questions.json", "w", encoding="utf-8") as f:
        json.dump(all_questions, f, ensure_ascii=False, indent=2)

    # Stats
    logger.info(f"\n{'='*60}")
    logger.info(f"FINAL: {len(all_questions)} questions")
    subjects = set(q["subject"] for q in all_questions)
    has_answer = sum(1 for q in all_questions if q["answer_text"])
    has_analysis = sum(1 for q in all_questions if q["analysis"])
    has_kps = sum(1 for q in all_questions if q["knowledge_points"])
    logger.info(f"Subjects: {subjects}")
    logger.info(f"With answer: {has_answer}/{len(all_questions)}")
    logger.info(f"With analysis: {has_analysis}/{len(all_questions)}")
    logger.info(f"With knowledge points: {has_kps}/{len(all_questions)}")
    logger.info(f"Saved to {q_output}")

    # Print one sample
    if all_questions:
        logger.info(f"\nSample question:")
        q = all_questions[0]
        logger.info(f"  Subject: {q['subject']}")
        logger.info(f"  Chapter: {q.get('chapter', '')}")
        logger.info(f"  Question: {q['question_text'][:200]}...")
        logger.info(f"  Answer: {q['answer_text'][:200]}...")


if __name__ == "__main__":
    main()
