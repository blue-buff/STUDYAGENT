#!/usr/bin/env python3
"""
配额验证实验 v2：webshot 解释图片路径。
核心问题：题 Detail 页中 embedded 的 webshot explanation URLs 是否受 30 次/天限制？

方法：
  1. 用 Playwright 访问 50+ question detail 页面
  2. 从页面 JS 数据中提取 explanation webshot URL 和 answer_text
  3. 尝试用 requests 下载每个 explanation 图片
  4. 记录成功/失败数，判断是否受限

Usage:
  python3 experiment_webshot.py
"""

import asyncio
import json
import re
import time
import os
import sys
from datetime import datetime, timezone

import requests
from playwright.async_api import async_playwright

STORAGE_STATE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "shared", "storage-state.json"
)
OUTPUT_DIR = os.path.dirname(os.path.abspath(__file__))

# All available question IDs from all papers (56 unique IDs)
ALL_QUESTION_IDS = [
    # Paper 6339985 (17 questions)
    "68956363", "68956364", "68956366", "68956367", "68956368",
    "68956369", "68956370", "68956371", "68956372", "68956373",
    "68956374", "68956375", "68956376", "68956379", "68956383",
    "68956386", "68956390",
    # Paper 6229652 (18 questions)
    "68089130", "68089131", "68089132", "68089133", "68089134",
    "68089135", "68089136", "68089137", "68089138", "68089139",
    "68089140", "68089141", "68089142", "68089143", "68089144",
    "68089152", "68089159", "68089165",
    # Paper 6395321 (21 questions)
    "62977686", "69344856", "69344857", "69344858", "69344859",
    "69344860", "69344861", "69344862", "69344863", "69344864",
    "69344865", "69344866", "69344867", "69344868", "69344869",
    "69344872", "69344875", "69344878", "69344882", "69344886",
    "69344890",
]
TOTAL = len(ALL_QUESTION_IDS)


def build_session(storage_state_path):
    """Build a requests.Session with cookies from storage-state.json."""
    with open(storage_state_path) as f:
        state = json.load(f)

    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    })
    for c in state["cookies"]:
        s.cookies.set(c["name"], c["value"],
                      domain=c.get("domain", ""),
                      path=c.get("path", "/"))
    return s


def download_image(session, url, referer):
    """Download an image and return (success, content_length, content_type)."""
    try:
        headers = {"Referer": referer}
        r = session.get(url, headers=headers, timeout=15, allow_redirects=True)
        content_type = r.headers.get("Content-Type", "")
        content_length = len(r.content)

        # Check if it's a valid image
        if r.status_code == 200 and "image" in content_type:
            # Check for error placeholder images (usually small PNGs)
            if content_length < 500:
                return False, content_length, f"too_small({content_length}b)"
            return True, content_length, content_type
        elif r.status_code == 403:
            return False, content_length, "403_forbidden"
        elif r.status_code == 404:
            return False, content_length, "404_not_found"
        else:
            return False, content_length, f"status_{r.status_code}_{content_type[:30]}"
    except Exception as e:
        return False, 0, str(e)[:80]


async def extract_from_detail_pages():
    """Use Playwright to visit question detail pages and extract data."""
    print(f"提取阶段：访问 {TOTAL} 个题 Detail 页...")
    print("=" * 70)

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"]
        )
        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            storage_state=STORAGE_STATE_PATH,
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        )
        page = await context.new_page()
        await page.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )

        results = []
        successes = 0
        failures = 0

        for i, qid in enumerate(ALL_QUESTION_IDS):
            url = f"https://www.chujuan.cn/question/detail-{qid}.shtml"
            try:
                await page.goto(url, wait_until="networkidle", timeout=20000)
            except Exception as e:
                results.append({
                    "question_id": qid,
                    "error": f"page_load_failed: {e}",
                    "has_explanation_url": False,
                    "has_answer_text": False,
                })
                failures += 1
                print(f"  [{i+1}/{TOTAL}] Q{qid}: PAGE LOAD FAILED")
                continue

            await page.wait_for_timeout(1500)

            html = await page.content()

            # Extract explanation URL
            expl_match = re.search(
                r'"explanation"\s*:\s*"(https://webshot[^"]+)"',
                html
            )
            expl_url = expl_match.group(1).replace("\\u002F", "/") if expl_match else None

            # Extract answer_text
            at_match = re.search(r'"answer_text"\s*:\s*"([^"]*)"', html)
            answer_text = at_match.group(1) if at_match else ""

            # Extract question title for context
            title_match = re.search(r'<title>([^<]+)</title>', html)
            title = title_match.group(1)[:80] if title_match else ""

            # Check if page actually loaded question content
            has_question = "question_id" in html

            result = {
                "question_id": qid,
                "index": i + 1,
                "title": title,
                "has_explanation_url": bool(expl_url),
                "explanation_url": expl_url,
                "has_answer_text": bool(answer_text and answer_text.strip()),
                "answer_text": answer_text[:100] if answer_text else "",
                "page_valid": has_question,
            }

            if has_question and (expl_url or (answer_text and answer_text.strip())):
                successes += 1
                status = "OK"
            else:
                status = "NO_DATA"

            results.append(result)
            print(f"  [{i+1}/{TOTAL}] Q{qid}: expl={'YES' if expl_url else 'no'}, "
                  f"text={'YES' if answer_text else 'no'} [{status}]")

            time.sleep(0.3)  # Be gentle

        await browser.close()

    print(f"\n提取完成: {successes} 成功, {failures}/{TOTAL} 无数据")
    return results


def download_all_explanations(extracted_data):
    """Attempt to download all explanation images."""
    session = build_session(STORAGE_STATE_PATH)

    download_results = []
    success_count = 0
    fail_count = 0
    first_fail_at = None

    print(f"\n下载阶段：尝试下载所有 explanation 图片...")
    print("=" * 70)

    for item in extracted_data:
        qid = item["question_id"]
        idx = item["index"]
        expl_url = item.get("explanation_url")

        if not expl_url:
            item["download_success"] = None
            item["download_detail"] = "no_url"
            download_results.append(item)
            continue

        referer = f"https://www.chujuan.cn/question/detail-{qid}.shtml"
        success, size, detail = download_image(session, expl_url, referer)

        item["download_success"] = success
        item["download_detail"] = detail
        item["download_size"] = size

        if success:
            success_count += 1
            flag = "OK"
        else:
            fail_count += 1
            if first_fail_at is None:
                first_fail_at = idx
            flag = "FAIL"

        print(f"  [{idx}/{TOTAL}] Q{qid}: download {'OK' if success else 'FAIL'} "
              f"({detail}, {size}b) {flag}")

        time.sleep(0.2)

    print(f"\n下载完成: {success_count} 成功, {fail_count} 失败")
    if first_fail_at:
        print(f"首次失败: 第 {first_fail_at} 题")
    return download_results, success_count, fail_count, first_fail_at


async def main():
    print("=" * 70)
    print("配额验证实验 v2: webshot 解释图片路径")
    print(f"时间: {datetime.now(timezone.utc).isoformat()}")
    print(f"测试题数: {TOTAL}")
    print("=" * 70)

    # Phase 1: Extract data from detail pages
    extracted = await extract_from_detail_pages()

    # Phase 2: Download all explanation images
    results, success_cnt, fail_cnt, first_fail = download_all_explanations(extracted)

    # Report
    print("\n" + "=" * 70)
    print("实验结果报告")
    print("=" * 70)

    # Stats
    has_expl_url = sum(1 for r in results if r.get("has_explanation_url"))
    has_answer_text = sum(1 for r in results if r.get("has_answer_text"))
    has_both = sum(1 for r in results if r.get("has_explanation_url") and r.get("has_answer_text"))
    has_expl_no_text = sum(1 for r in results if r.get("has_explanation_url") and not r.get("has_answer_text"))
    has_text_no_expl = sum(1 for r in results if r.get("has_answer_text") and not r.get("has_explanation_url"))

    print(f"\n数据提取统计:")
    print(f"  总题数: {TOTAL}")
    print(f"  有 explanation URL: {has_expl_url}")
    print(f"  有 answer_text: {has_answer_text}")
    print(f"  两者都有: {has_both}")
    print(f"  仅有 explanation (无文字答案): {has_expl_no_text}")
    print(f"  仅有 answer_text (无解释图): {has_text_no_expl}")
    print(f"  无任何数据: {TOTAL - has_expl_url - has_answer_text + has_both}")

    print(f"\n图片下载统计:")
    print(f"  尝试下载: {has_expl_url}")
    print(f"  下载成功: {success_cnt}")
    print(f"  下载失败: {fail_cnt}")
    if first_fail:
        print(f"  首次失败位置: 第 {first_fail} 题")

    # Conclusion
    print(f"\n{'─' * 60}")
    print(f"结论分析:")
    if success_cnt > 30:
        print(f"  >>> 成功下载 {success_cnt} 张 explanation 图片 (>{30})")
        print(f"  >>> webshot 解释图片路径不受 30 次/天 配额限制！")
    elif success_cnt == 0 and has_expl_url > 0:
        print(f"  >>> 有 {has_expl_url} 个 URL 但全部下载失败")
        print(f"  >>> 可能原因：反盗链、cookie 过期、或 webshot 服务器限制")
    elif success_cnt <= 30 and has_expl_url > 30:
        if first_fail and first_fail <= 31:
            print(f"  >>> 第 {first_fail} 题开始失败，接近 30 次限制")
            print(f"  >>> webshot 图片可能受同一配额限制")
        else:
            print(f"  >>> 成功率低但失败位置不明确，需进一步分析")
    else:
        print(f"  >>> 仅有 {has_expl_url} 个 URL，不足以验证配额")

    # Save detailed results — use extracted data directly (before modifications)
    # results list may have serialization issues with large URLs, use summary format
    summary_results = []
    for r in results:
        summary_results.append({
            "question_id": r.get("question_id", ""),
            "index": r.get("index", 0),
            "has_explanation_url": r.get("has_explanation_url", False),
            "has_answer_text": r.get("has_answer_text", False),
            "download_success": r.get("download_success"),
            "download_size": r.get("download_size", 0),
        })

    output = {
        "experiment": "webshot_quota_verification",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_tested": TOTAL,
        "extraction_stats": {
            "has_explanation_url": sum(1 for r in summary_results if r["has_explanation_url"]),
            "has_answer_text": sum(1 for r in summary_results if r["has_answer_text"]),
        },
        "download_stats": {
            "attempted": sum(1 for r in summary_results if r["has_explanation_url"]),
            "succeeded": success_cnt,
            "failed": fail_cnt,
            "first_failure_at": first_fail,
        },
        "results": summary_results,
        "conclusion": (
            "webshot_bypass_confirmed" if success_cnt > 30
            else "webshot_quota_shared" if (first_fail and first_fail <= 31 and has_expl_url > 30)
            else "inconclusive"
        ),
    }

    out_path = os.path.join(OUTPUT_DIR, "experiment_webshot_results.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\n详细结果已保存至: {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
