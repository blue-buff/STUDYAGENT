#!/usr/bin/env python3
"""
03_fetch_questions.py — 抓取可公开访问的题目数据
基于静态 HTML 解析，尝试获取题目详情（题干+答案+解析）
不启动浏览器，仅用 requests + BeautifulSoup
"""
import json
import sys
import re
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from bs4 import BeautifulSoup
from jyeoo.config import get_config
from jyeoo.session_mgr import SessionManager
from jyeoo.subject_analyzer import SubjectAnalyzer
from jyeoo.url_parser import URLParser
from jyeoo.utils import setup_logging, random_delay, ensure_dir, safe_filename, logger

OUTPUT_DIR = Path(__file__).parent.parent / "output" / "sample_questions"


def main():
    setup_logging()
    config = get_config()
    sess = SessionManager()
    analyzer = SubjectAnalyzer(sess)

    ensure_dir(OUTPUT_DIR)

    # Step 1: Collect question detail URLs from search pages
    logger.info("=" * 60)
    logger.info("Step 1: Collecting question detail URLs from search pages")
    logger.info("=" * 60)

    all_question_urls = []
    search_pages = [
        ("初中数学", f"{config.base_url}/math/ques/search"),
        ("高中数学", f"{config.base_url}/math2/ques/search"),
        ("初中物理", f"{config.base_url}/physics/ques/search"),
        ("高中物理", f"{config.base_url}/physics2/ques/search"),
        ("初中化学", f"{config.base_url}/chemistry/ques/search"),
        ("高中化学", f"{config.base_url}/chemistry2/ques/search"),
    ]

    for name, url in search_pages:
        logger.info(f"Scanning: {name} ({url})")
        random_delay(config.request_delay["min"], config.request_delay["max"])
        resp = sess.get(url, referer=config.base_url)
        if not resp:
            logger.warning(f"  Failed to fetch {url}")
            continue

        soup = BeautifulSoup(resp.text, "lxml")
        question_links = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if re.search(r"/ques/detail/", href):
                full_url = href if href.startswith("http") else f"{config.base_url}{href}"
                question_links.append({
                    "url": full_url,
                    "text": a.get_text(strip=True)[:100],
                    "subject": name,
                })
        logger.info(f"  Found {len(question_links)} question detail links")
        all_question_urls.extend(question_links[:10])  # take first 10 from each

    logger.info(f"Total question URLs collected: {len(all_question_urls)}")

    # Step 2: Fetch question details
    logger.info("=" * 60)
    logger.info("Step 2: Fetching question details")
    logger.info("=" * 60)

    questions = []
    for i, q_info in enumerate(all_question_urls):
        logger.info(f"[{i+1}/{len(all_question_urls)}] {q_info['url']}")
        random_delay(config.request_delay["min"], config.request_delay["max"])

        detail = analyzer.analyze_question_detail(q_info["url"])
        if detail and "error" not in detail:
            question_data = {
                "subject": q_info["subject"],
                "source_url": q_info["url"],
                "source_id": re.search(r"/detail/([\w-]+)", q_info["url"]).group(1) if re.search(r"/detail/([\w-]+)", q_info["url"]) else "",
                "grade": "",
                "knowledge_points": detail.get("knowledge_points", []),
                "question_type": detail.get("metadata", {}).get("type", ""),
                "difficulty": detail.get("metadata", {}).get("difficulty", ""),
                "year": detail.get("metadata", {}).get("year", ""),
                "question_text": detail.get("question_text", ""),
                "answer_text": detail.get("answer_text", ""),
                "analysis": detail.get("analysis_text", ""),
            }
            questions.append(question_data)

            text_len = len(question_data["question_text"])
            answer_len = len(question_data["answer_text"])
            analysis_len = len(question_data["analysis"])
            logger.info(f"  question={text_len} chars, answer={answer_len} chars, "
                        f"analysis={analysis_len} chars, kps={question_data['knowledge_points']}")
        else:
            logger.warning(f"  Failed to parse detail: {detail.get('error', 'unknown')}")

        # Limit to prevent overload
        if len(questions) >= 30:
            logger.info("Reached 30 questions, stopping")
            break

    # Step 3: Save results
    logger.info("=" * 60)
    logger.info(f"Step 3: Saving {len(questions)} questions")
    logger.info("=" * 60)

    for i, q in enumerate(questions):
        sid = q["source_id"][:16] if q["source_id"] else f"q{i+1:03d}"
        subject_dir = OUTPUT_DIR / safe_filename(q["subject"])
        ensure_dir(subject_dir)
        path = subject_dir / f"{sid}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(q, f, ensure_ascii=False, indent=2)

    # Save all questions in one file too
    all_path = OUTPUT_DIR / "all_questions.json"
    with open(all_path, "w", encoding="utf-8") as f:
        json.dump(questions, f, ensure_ascii=False, indent=2)

    logger.info(f"Questions saved to {OUTPUT_DIR}")
    logger.info(f"  Individual files: {len(questions)}")
    logger.info(f"  Combined file: {all_path}")

    # Step 4: Statistics
    if questions:
        subjects = set(q["subject"] for q in questions)
        has_text = sum(1 for q in questions if q["question_text"])
        has_answer = sum(1 for q in questions if q["answer_text"])
        has_analysis = sum(1 for q in questions if q["analysis"])
        has_kps = sum(1 for q in questions if q["knowledge_points"])

        logger.info(f"\nStatistics:")
        logger.info(f"  Subjects covered: {subjects}")
        logger.info(f"  With question text: {has_text}/{len(questions)}")
        logger.info(f"  With answer text: {has_answer}/{len(questions)}")
        logger.info(f"  With analysis text: {has_analysis}/{len(questions)}")
        logger.info(f"  With knowledge points: {has_kps}/{len(questions)}")


if __name__ == "__main__":
    main()
