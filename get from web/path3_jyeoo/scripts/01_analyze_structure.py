#!/usr/bin/env python3
"""
01_analyze_structure.py — 静态分析菁优网全站学科结构和 URL 规则
不启动浏览器，仅用 requests + BeautifulSoup 分析 HTML
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from jyeoo.config import get_config
from jyeoo.session_mgr import SessionManager
from jyeoo.subject_analyzer import SubjectAnalyzer
from jyeoo.url_parser import URLParser
from jyeoo.models import SiteStructure
from jyeoo.utils import setup_logging, random_delay, ensure_dir, logger

OUTPUT_DIR = Path(__file__).parent.parent / "output"


def main():
    setup_logging()
    config = get_config()
    sess = SessionManager()
    analyzer = SubjectAnalyzer(sess)

    structure = SiteStructure(base_url=config.base_url)
    structure.url_patterns = {
        "search_chapter": "/{subject}/ques/search?f=0",
        "search_knowledge": "/{subject}/ques/search?f=1",
        "detail": "/{subject}/ques/detail/{question_id}",
        "paper_search": "/{subject}/paper/search",
        "report": "/{subject}/report",
        "level_suffix": {"junior": "", "senior": "2", "primary": "3"},
        "top_knowledge": "/{subject}/ques/pointtop30?f=1",
    }

    # Step 1: Analyze homepage
    logger.info("=" * 60)
    logger.info("Step 1: Analyzing homepage for subject links")
    logger.info("=" * 60)
    subject_links = analyzer.analyze_homepage()
    if subject_links:
        logger.info(f"Found {len(subject_links)} subject paths on homepage")
        for path, info in sorted(subject_links.items()):
            parsed = URLParser.parse_subject_path(f"/{path}")
            display = parsed.get("display_name", path)
            logger.info(f"  /{path}/ → {display} ({parsed.get('level', '?')})")
            structure.subjects.append({
                "path": path,
                "display_name": display,
                "level": parsed.get("level", "unknown"),
                "subject_key": parsed.get("subject_key", path),
                "links": info.get("links", []),
            })
    else:
        logger.warning("Homepage did not yield subject links, using URLParser's built-in list")
        for entry in URLParser.get_all_search_urls():
            structure.subjects.append({
                "path": entry["subject"],
                "display_name": entry["display"],
                "level": entry["level"],
                "subject_key": entry["subject"],
                "chapter_url": entry["chapter_url"],
                "knowledge_url": entry["knowledge_url"],
            })

    # Step 2: Analyze math subject pages
    logger.info("=" * 60)
    logger.info("Step 2: Analyzing math subject pages")
    logger.info("=" * 60)

    for level, path in [("junior", "math"), ("senior", "math2"), ("primary", "math3")]:
        logger.info(f"--- Analyzing {level} math: /{path}/ ---")
        result = analyzer.analyze_subject_page(path)
        if result and "error" not in result:
            logger.info(f"  Title: {result.get('title', 'N/A')}")
            filters = result.get("filters", {})
            logger.info(f"  Filter areas found: {len(filters)}")
            grade_tabs = result.get("grade_tabs", [])
            logger.info(f"  Grade tabs: {[g['text'] for g in grade_tabs]}")
            embedded = result.get("embedded_data", [])
            logger.info(f"  Embedded JSON data blocks: {len(embedded)}")
            if embedded:
                for i, block in enumerate(embedded):
                    logger.info(f"    Block {i}: keys={list(block.keys()) if isinstance(block, dict) else f'list[{len(block)}]'}")

            # Save full analysis result
            ensure_dir(OUTPUT_DIR)
            detail_path = OUTPUT_DIR / f"subject_analysis_{path}.json"
            with open(detail_path, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
            logger.info(f"  Full analysis saved to {detail_path}")

            # Extract filter structure
            for filter_key, items in filters.items():
                if items:
                    logger.info(f"  Filter [{filter_key}]: {[i['text'] for i in items[:10]]}")
        else:
            logger.warning(f"  Failed to analyze /{path}/: {result.get('error', 'unknown')}")

    # Step 3: Analyze chemistry and physics pages
    for path in ["physics", "physics2", "chemistry", "chemistry2"]:
        logger.info(f"--- Quick check: /{path}/ ---")
        result = analyzer.analyze_subject_page(path)
        if result and "error" not in result:
            logger.info(f"  OK: {result.get('title', 'N/A')}")
            structure.subjects.append({
                "path": path,
                "display_name": result.get("title", path),
                "level": "senior" if path.endswith("2") else "junior",
                "status": "accessible",
            })
        else:
            logger.warning(f"  Not accessible: {path}")

    # Step 4: Try to find question detail pages
    logger.info("=" * 60)
    logger.info("Step 3: Searching for question detail page URLs")
    logger.info("=" * 60)

    # Try math search page to find question links
    math_url = f"{config.base_url}/math/ques/search"
    logger.info(f"Fetching {math_url} to find question links...")
    random_delay(config.request_delay["min"], config.request_delay["max"])
    resp = sess.get(math_url)
    if resp:
        from bs4 import BeautifulSoup
        import re
        soup = BeautifulSoup(resp.text, "lxml")
        question_links = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if re.search(r"/ques/detail/", href):
                full_url = href if href.startswith("http") else f"{config.base_url}{href}"
                question_links.append({"url": full_url, "text": a.get_text(strip=True)})
        logger.info(f"Found {len(question_links)} question detail links")
        structure.url_patterns["sample_question_links"] = question_links[:20]

        # Try to parse a question detail page if available
        if question_links:
            logger.info("--- Analyzing first question detail page ---")
            detail = analyzer.analyze_question_detail(question_links[0]["url"])
            if detail and "error" not in detail:
                logger.info(f"  Question text: {detail.get('question_text', '')[:200]}")
                logger.info(f"  Answer text: {detail.get('answer_text', '')[:200]}")
                logger.info(f"  Analysis: {detail.get('analysis_text', '')[:200]}")
                logger.info(f"  Knowledge points: {detail.get('knowledge_points', [])}")
                logger.info(f"  Metadata: {detail.get('metadata', {})}")
                ensure_dir(OUTPUT_DIR)
                with open(OUTPUT_DIR / "sample_question_detail.json", "w", encoding="utf-8") as f:
                    json.dump(detail, f, ensure_ascii=False, indent=2)
                logger.info("  Detail saved to output/sample_question_detail.json")
    else:
        logger.warning("Could not fetch math search page")

    # Step 5: Detect login requirements and anti-bot observations
    structure.login_required_for = [
        "question_detail_maybe_free",  # reference projects say detail pages don't need login
        "search_all_results",          # may need login for full access
        "paper_generation",            # 组卷 needs login
    ]
    structure.anti_bot_observations = [
        "Reference projects report: backend serves fake question data when scraping detected",
        "Reference projects report: API-based auto-login (api.jyeoo.com) → account banned",
        "Reference projects report: detail pages accessible without login",
        "Reference projects report: ~100 requests per account per session rate limit",
        "Manual login via QQ OAuth required for authenticated access",
        "Login page /home/login returns 404 — login is likely modal/popup on main page",
    ]

    # Step 6: Build final structure
    structure.filters = {
        "question_types": list(config.question_types.keys()),
        "difficulty_levels": list(config.difficulty_levels.keys()),
        "grade_levels": config.grade_levels,
    }

    # Save output
    ensure_dir(OUTPUT_DIR)
    output_path = OUTPUT_DIR / "site_structure.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(structure.to_dict(), f, ensure_ascii=False, indent=2)
    logger.info(f"\nSite structure saved to {output_path}")
    logger.info(f"Total subjects cataloged: {len(structure.subjects)}")

    return structure


if __name__ == "__main__":
    main()
