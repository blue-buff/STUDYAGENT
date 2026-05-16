#!/usr/bin/env python3
"""
配额验证实验：Playwright 点击"显示答案解析"是否受 30 次/天限制。

实验设计：
  1. 用 Playwright 加载 storage-state.json（已验证有效的 chujuan.cn 登录态）
  2. 打开试卷页并监控所有网络请求（尤其 check_ques_parse）
  3. 点击"显示答案解析"按钮
  4. 提取 DOM 中的答案图片 URL
  5. 连续处理多张试卷（共 56 道题目），观察是否有失败

Usage:
  python3 experiment_quota.py
"""

import asyncio
import json
import re
import time
import os
import sys
from datetime import datetime, timezone

# Add parent for playwright if needed
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from playwright.async_api import async_playwright

STORAGE_STATE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "shared", "storage-state.json"
)
BASE_URL = "https://www.chujuan.cn"
OUTPUT_DIR = os.path.dirname(os.path.abspath(__file__))

# Papers to test (total 17+18+21 = 56 questions)
PAPER_IDS = ["6339985", "6229652", "6395321"]


class QuotaExperiment:
    def __init__(self):
        self.network_log = []  # All network requests
        self.check_ques_parse_calls = []  # checkQuesParse API calls
        self.results = []  # Per-question results
        self.paper_results = {}  # Per-paper summary

    def log_network(self, request):
        """Callback for network request monitoring."""
        url = request.url
        method = request.method
        entry = {
            "url": url,
            "method": method,
            "resource_type": request.resource_type,
            "timestamp": time.time(),
        }
        self.network_log.append(entry)

        # Specifically track checkQuesParse calls
        if "check_ques_parse" in url or "checkQuesParse" in url:
            self.check_ques_parse_calls.append(entry)
            print(f"  [NETWORK] checkQuesParse CALL DETECTED: {method} {url[:120]}")

    async def run(self):
        """Run the full experiment."""
        print("=" * 70)
        print("配额验证实验：Playwright 点击路径")
        print(f"时间: {datetime.now(timezone.utc).isoformat()}")
        print(f"存储态: {STORAGE_STATE_PATH}")
        print(f"试卷数: {len(PAPER_IDS)} (IDs: {PAPER_IDS})")
        print("=" * 70)

        if not os.path.exists(STORAGE_STATE_PATH):
            print(f"ERROR: 存储态文件不存在: {STORAGE_STATE_PATH}")
            return

        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                ]
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

            # Monitor ALL network requests
            page.on("request", self.log_network)

            # Process each paper
            for paper_id in PAPER_IDS:
                print(f"\n{'─' * 60}")
                print(f"处理试卷 {paper_id}...")
                paper_result = await self.process_paper(page, paper_id)
                self.paper_results[paper_id] = paper_result

            await browser.close()

        # Final report
        self.print_report()

    async def process_paper(self, page, paper_id):
        """Process a single paper: open → click → extract."""
        url = f"{BASE_URL}/paper/view-{paper_id}.shtml"
        print(f"  打开: {url}")

        try:
            await page.goto(url, wait_until="networkidle", timeout=30000)
        except Exception as e:
            print(f"  ERROR: 页面加载失败: {e}")
            return {"error": str(e), "questions": 0, "answers_extracted": 0}

        await page.wait_for_timeout(2000)

        # Check if page loaded properly
        page_title = await page.title()
        print(f"  页面标题: {page_title[:80]}")

        # Check if "显示答案解析" button exists
        btn_exists = await page.evaluate("""
            () => !!document.querySelector('.J_show_all_explain')
        """)
        print(f"  '显示答案解析' 按钮存在: {btn_exists}")

        # Check if we're on login page
        is_login_page = "登录" in page_title or "login" in page.url.lower()
        if is_login_page:
            print(f"  WARNING: 可能已重定向到登录页！URL: {page.url}")
            return {"error": "redirected_to_login", "questions": 0, "answers_extracted": 0}

        # Click "显示答案解析"
        if btn_exists:
            await page.evaluate("""
                const btn = document.querySelector('.J_show_all_explain');
                if (btn) btn.click();
            """)
            print("  已点击 '显示答案解析'，等待渲染...")
            await page.wait_for_timeout(10000)  # Wait for images to load
        else:
            print("  WARNING: 未找到 '显示答案解析' 按钮")
            # Try alternative selectors
            alt_btns = await page.evaluate("""() => {
                const selectors = [
                    '.J_show_all_explain',
                    '.show-all-explain',
                    '[class*="show_all_explain"]',
                    '[class*="show-explain"]',
                    'button:has-text("答案")',
                    'a:has-text("答案解析")',
                    'span:has-text("显示答案")',
                ];
                return selectors.map(s => ({
                    selector: s,
                    exists: !!document.querySelector(s),
                    text: document.querySelector(s)?.textContent?.trim().substring(0, 30)
                }));
            }""")
            for item in alt_btns:
                print(f"    Alt selector: {item}")

        # Extract webshot image URLs from DOM
        img_data = await page.evaluate("""() => {
            return Array.from(document.querySelectorAll('img'))
                .map(img => ({src: img.src, alt: img.alt || ''}))
                .filter(img => img.src.includes('webshot'));
        }""")

        print(f"  DOM 中 webshot 图片数: {len(img_data)}")

        # Parse images into answer/explanation by question ID
        answer_imgs = {}
        explanation_imgs = {}
        for img in img_data:
            src = img["src"]
            m = re.search(r'_(\d{7,})(an|ex)\.png', src)
            if not m:
                continue
            qid, img_type = m.group(1), m.group(2)
            if img_type == "an":
                answer_imgs.setdefault(qid, []).append(src)
            else:
                explanation_imgs.setdefault(qid, []).append(src)

        # Also try to extract answer_text from page source
        html_content = await page.content()
        answer_texts = {}
        for m in re.finditer(r'"answer_text"\s*:\s*"([^"]*)"', html_content):
            # Find associated question_id near this match
            pos = m.start()
            # Look for question_id before this position
            qid_match = re.search(r'"question_id"\s*:\s*(\d{7,})', html_content[max(0, pos-500):pos])
            at_match = re.search(r'"question_id"\s*:\s*(\d{7,})', html_content[pos:pos+500])
            qid = None
            if qid_match:
                qid = qid_match.group(1)
            elif at_match:
                qid = at_match.group(1)
            if qid and m.group(1):
                answer_texts[qid] = m.group(1)

        # Get all question IDs from page
        all_qids = list(set(
            re.findall(r'"question_id"\s*:\s*(\d{7,})', html_content)
        ))

        questions_with_answers = set(list(answer_imgs.keys()) + list(answer_texts.keys()))
        success_count = len(questions_with_answers)

        print(f"  试题总数(从HTML提取): {len(all_qids)}")
        print(f"  答案图片覆盖题数: {len(answer_imgs)}")
        print(f"  答案文字覆盖题数: {len(answer_texts)}")
        print(f"  有答案的题数(去重): {success_count}")

        paper_result = {
            "paper_id": paper_id,
            "total_questions_in_html": len(all_qids),
            "question_ids": all_qids,
            "answer_image_count": len(answer_imgs),
            "answer_text_count": len(answer_texts),
            "unique_questions_with_answers": success_count,
            "btn_exists": btn_exists,
            "questions_with_answer_images": list(answer_imgs.keys()),
            "questions_with_answer_text": list(answer_texts.keys()),
        }
        return paper_result

    def print_report(self):
        """Print final experiment report."""
        print("\n" + "=" * 70)
        print("实验结果报告")
        print("=" * 70)

        # Paper summaries
        total_q = 0
        total_ans = 0
        for pid, pr in self.paper_results.items():
            q = pr.get("total_questions_in_html", 0)
            a = pr.get("unique_questions_with_answers", 0)
            total_q += q
            total_ans += a
            status = "成功" if pr.get("btn_exists") else "按钮未找到"
            print(f"\n  试卷 {pid}:")
            print(f"    题目数: {q}")
            print(f"    有答案数: {a}")
            print(f"    答案图片: {pr.get('answer_image_count', 0)}")
            print(f"    答案文字: {pr.get('answer_text_count', 0)}")
            print(f"    状态: {status}")
            if pr.get("error"):
                print(f"    错误: {pr['error']}")

        # Network monitoring summary
        print(f"\n  网络监控:")
        print(f"    总请求数: {len(self.network_log)}")
        print(f"    checkQuesParse API 调用数: {len(self.check_ques_parse_calls)}")

        if self.check_ques_parse_calls:
            print(f"\n  *** 发现 checkQuesParse 调用! ***")
            for call in self.check_ques_parse_calls:
                print(f"    - {call['method']} {call['url'][:100]}")
        else:
            print(f"  *** 未检测到任何 checkQuesParse API 调用 ***")

        # Conclusion
        print(f"\n{'─' * 60}")
        print(f"结论:")
        if total_ans > 30:
            print(f"  >>> Playwright 点击路径成功提取了 {total_ans} 道题的答案 (>30)")
            if not self.check_ques_parse_calls:
                print(f"  >>> 未触发 checkQuesParse API 调用")
                print(f"  >>> 结论：Playwright 路径不受 30 次/天 配额限制！")
                print(f"  >>> 原因：答案通过 webshot CDN 图片加载，不走 checkQuesParse API")
            else:
                print(f"  >>> 但触发了 {len(self.check_ques_parse_calls)} 次 checkQuesParse 调用")
                print(f"  >>> 结论：Playwright 路径触发 API 调用，共享配额")
        elif total_ans == 0:
            print(f"  >>> 未能提取任何答案，可能是登录态过期或页面结构变化")
        else:
            print(f"  >>> 仅提取了 {total_ans} 道题答案（可能受限于今日已用配额）")

        # Save detailed results
        output = {
            "experiment": "quota_verification",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "storage_state": STORAGE_STATE_PATH,
            "total_questions_attempted": total_q,
            "total_answers_extracted": total_ans,
            "check_ques_parse_calls": len(self.check_ques_parse_calls),
            "check_ques_parse_details": [
                {"url": c["url"], "method": c["method"]}
                for c in self.check_ques_parse_calls
            ],
            "paper_results": self.paper_results,
            "conclusion": (
                "bypass_confirmed" if (total_ans > 30 and not self.check_ques_parse_calls)
                else "quota_shared" if (total_ans > 0 and self.check_ques_parse_calls)
                else "inconclusive"
            ),
        }

        out_path = os.path.join(OUTPUT_DIR, "experiment_results.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        print(f"\n详细结果已保存至: {out_path}")


async def main():
    experiment = QuotaExperiment()
    await experiment.run()


if __name__ == "__main__":
    asyncio.run(main())
