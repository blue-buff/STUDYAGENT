#!/usr/bin/env python3
"""
组卷网 (zujuan.xkw.com) 题目抓取工具
复用 shared/storage-state.json 登录态，输入知识点ID → 输出 JSON 题目列表

用法：
  # 先登录（只需一次）
  python login.py

  # 抓取题目
  python scrape.py -k zsd27977 -l 5                # 交集运算, 5道
  python scrape.py -k zsd27977 -t t1 -d d3 -l 3    # 单选题 + 适中难度
  python scrape.py -k zsd27977 -t t3 -l 5 -y 2025  # 填空题 + 2025年

  # 也可用 cookie 免扫码
  python scrape.py -k zsd27977 --cookie "key1=val1; key2=val2"

输出结构：
  output/{timestamp}/
    ├── results.json      # 完整元数据 + 图片相对路径
    ├── 001/
    │   ├── question.png  # 题目截图
    │   └── answer.png    # 答案图片（需登录）
    └── ...
"""

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path

import aiohttp

try:
    from playwright.async_api import async_playwright
except ImportError:
    print("pip install playwright && python -m playwright install chromium")
    sys.exit(1)

# ─────────────────────────────────────────────
# 路径配置
# ─────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).resolve().parent
OUTPUT_DIR = PROJECT_ROOT / "output"
SHARED_DIR = Path("/Users/song/project/STUDYAGENT/get from web/shared")
STORAGE_STATE = SHARED_DIR / "storage-state.json"
MAX_SCREENSHOT_MB = 200

# ─────────────────────────────────────────────
# URL 构建
# ─────────────────────────────────────────────

BASE_URL = "https://zujuan.xkw.com"

TYPE_CODES = {
    "high": {"t1": "2701", "t2": "2704", "t3": "2702", "t4": "2703"},
    "middle": {"t1": "1101", "t2": "1104", "t3": "1102", "t4": "1103"},
}
TYPE_NAMES = {"t1": "单选题", "t2": "多选题", "t3": "填空题", "t4": "解答题"}
DIFF_NAMES = {"d1": "容易", "d2": "较易", "d3": "适中", "d4": "较难", "d5": "困难"}
ORDER_CODES = {"latest": "o2", "hot": "o1", "comprehensive": "o0"}
ORDER_NAMES = {"latest": "最新", "hot": "最热", "comprehensive": "综合"}
GRADE_PREFIX = {"high": "gzsx", "middle": "czsx"}


def build_url(knowledge_id, grade="high", qtype=None, difficulty=None, year=None,
              order="latest", page=None, multi_count=None, fill_count=None):
    prefix = GRADE_PREFIX[grade]
    kid = knowledge_id.replace("zsd", "")
    parts = []

    if qtype and qtype in TYPE_CODES[grade]:
        base = TYPE_CODES[grade][qtype]
        if qtype == "t2" and multi_count is not None:
            suffix = "03" if multi_count >= 4 else f"0{multi_count}"
            parts.append(f"qt{base}{suffix}")
        elif qtype == "t3" and fill_count is not None:
            suffix = "03" if fill_count >= 3 else f"0{fill_count}"
            parts.append(f"qt{base}{suffix}")
        else:
            parts.append(f"qt{base}")

    if difficulty:
        parts.append(f"d{difficulty[1]}")
    if year is not None:
        parts.append(f"y{year}")

    order_code = ORDER_CODES.get(order, "o2")
    if page and page > 1:
        parts.append(f"{order_code}p{page}")
    else:
        parts.append(order_code)

    url = f"{BASE_URL}/{prefix}/zsd{kid}/"
    if parts:
        url += "".join(parts) + "/"
    return url


# ─────────────────────────────────────────────
# 抓取引擎
# ─────────────────────────────────────────────

class ZujuanScraper:
    def __init__(self, storage_state=None, cookie=None, headless=True, output_dir=None):
        self.storage_state = storage_state
        self.cookie = cookie
        self.headless = headless
        self.output_dir = Path(output_dir or OUTPUT_DIR)
        self.total_bytes = 0
        self.browser = None
        self.context = None
        self.page = None

    async def start(self):
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(
            headless=self.headless,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )

        # 优先使用 storage-state.json
        if self.storage_state and Path(self.storage_state).exists():
            self.context = await self.browser.new_context(
                viewport={"width": 1920, "height": 1080},
                storage_state=str(self.storage_state),
            )
            print(f"已加载登录态: {self.storage_state}")
        else:
            self.context = await self.browser.new_context(
                viewport={"width": 1920, "height": 1080},
            )
            if self.cookie:
                await self._inject_cookies()

        self.page = await self.context.new_page()

    async def _inject_cookies(self):
        cookies = []
        for part in self.cookie.split(";"):
            part = part.strip()
            if "=" not in part:
                continue
            name, _, value = part.partition("=")
            cookies.append({
                "name": name.strip(),
                "value": value.strip().strip('"'),
                "domain": ".xkw.com",
                "path": "/",
            })
        if cookies:
            await self.context.add_cookies(cookies)
            print(f"已注入 {len(cookies)} 个 Cookie")

    async def check_login(self):
        await self.page.goto(BASE_URL, wait_until="domcontentloaded")
        await self.page.wait_for_timeout(2000)
        return await self.page.query_selector("a.login-btn") is None

    async def scrape(self, knowledge_id, grade="high", qtype=None, difficulty=None,
                     year=None, order="latest", limit=10, page=None,
                     multi_count=None, fill_count=None):
        url = build_url(knowledge_id, grade, qtype, difficulty, year, order, page,
                        multi_count, fill_count)
        print(f"URL: {url}")

        await self.page.goto(url, wait_until="domcontentloaded")
        await self.page.wait_for_timeout(3000)

        # 在当前页面检查登录状态（不导航离开！）
        logged_in = await self.page.query_selector("a.login-btn") is None
        print(f"登录状态: {'已登录' if logged_in else '未登录'}")

        await self._scroll_to_load()

        timestamp = str(int(time.time() * 1000))
        batch_dir = self.output_dir / timestamp
        batch_dir.mkdir(parents=True, exist_ok=True)

        handles = await self.page.query_selector_all("div.tk-quest-item.quesroot")
        total = len(handles)
        count = min(total, limit)

        if total == 0:
            debug_path = batch_dir / "page_debug.html"
            debug_path.write_text(await self.page.content(), encoding="utf-8")
            print(f"未找到题目，页面已保存到 {debug_path}")
            return {"metadata": self._build_meta(timestamp, knowledge_id, grade, qtype,
                                                  difficulty, order, url), "results": []}

        print(f"共 {total} 道题，抓取 {count} 道 | 输出: {batch_dir}")

        tasks = []
        for i in range(count):
            idx_str = f"{i + 1:03d}"
            question_dir = batch_dir / idx_str
            question_dir.mkdir(parents=True, exist_ok=True)

            question_path = question_dir / "question.png"
            handle = handles[i]

            try:
                await handle.evaluate("el => el.scrollIntoView({behavior: 'instant', block: 'start'})")
                await self.page.wait_for_timeout(200)

                cnt_handle = await handle.query_selector("div.exam-item__cnt")
                if not cnt_handle:
                    print(f"  第 {i + 1} 题: 无题目内容区，跳过")
                    continue

                await cnt_handle.screenshot(path=str(question_path))
                self.total_bytes += question_path.stat().st_size if question_path.exists() else 0
                self._check_size()

                extra = await self._extract_extra_info(handle)

                # 答案（需登录）
                answer_src = None
                if logged_in:
                    wrapper = await handle.query_selector("div.wrapper.quesdiv")
                    if wrapper:
                        await wrapper.click()
                    for _ in range(15):
                        await self.page.wait_for_timeout(100)
                        answer_src = await handle.evaluate(
                            "el => { const img = el.querySelector('div.exam-item__opt > div.item.answer img'); return img ? img.src : null; }"
                        )
                        if answer_src:
                            break

                task = {
                    "index": idx_str,
                    "questionPath": f"{idx_str}/question.png",
                    "answerPath": "",
                    "answerSrc": answer_src,
                    "source": extra.get("source"),
                    "questionType": extra.get("questionType"),
                    "difficulty": extra.get("difficulty"),
                    "scoreRate": extra.get("scoreRate"),
                    "knowledgeKeywords": extra.get("knowledgeKeywords", []),
                    "scrapedAt": time.strftime("%Y-%m-%dT%H:%M:%S"),
                }
                tasks.append(task)

                status = "✓" if answer_src else ("⚠ 未登录" if not logged_in else "✗ 无答案")
                print(f"  第 {i + 1}/{count}: {status}")

            except Exception as e:
                print(f"  第 {i + 1} 题失败: {e}")

        # 下载答案图片
        if logged_in:
            await self._download_answers(batch_dir, tasks)

        # 保存 JSON
        output = {
            "metadata": self._build_meta(timestamp, knowledge_id, grade, qtype,
                                          difficulty, order, url),
            "results": tasks,
        }
        json_path = batch_dir / "results.json"
        json_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n结果已保存: {json_path}")
        print(f"总截图大小: {self._format_bytes(self.total_bytes)}")

        return output

    async def _download_answers(self, batch_dir, tasks):
        answer_tasks = [t for t in tasks if t.get("answerSrc")]
        if not answer_tasks:
            return

        print(f"下载答案图片 ({len(answer_tasks)} 张)...")
        async with aiohttp.ClientSession() as session:
            async def download_one(t):
                dest = batch_dir / t["index"] / "answer.png"
                try:
                    await self._download_image(session, t["answerSrc"], dest)
                    if dest.exists():
                        t["answerPath"] = f"{t['index']}/answer.png"
                        self.total_bytes += dest.stat().st_size
                        self._check_size()
                except Exception as e:
                    print(f"    答案下载失败 [{t['index']}]: {e}")
                    t["answerPath"] = ""

            await asyncio.gather(*[download_one(t) for t in answer_tasks])

    def _check_size(self):
        if self.total_bytes > MAX_SCREENSHOT_MB * 1024 * 1024:
            print(f"⚠ 警告：截图总量已达 {self._format_bytes(self.total_bytes)}，超过 {MAX_SCREENSHOT_MB}MB 上限")

    @staticmethod
    def _build_meta(timestamp, knowledge_id, grade, qtype, difficulty, order, url):
        return {
            "timestamp": timestamp,
            "knowledgeId": knowledge_id,
            "grade": grade,
            "type": TYPE_NAMES.get(qtype, ""),
            "difficulty": DIFF_NAMES.get(difficulty, ""),
            "order": ORDER_NAMES.get(order, "最新"),
            "url": url,
            "scrapedAt": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }

    async def _extract_extra_info(self, handle):
        extra = {"knowledgeKeywords": []}
        try:
            info = await handle.evaluate("""
                el => {
                    const additional = el.querySelector('div.ques-additional');
                    if (!additional) return {};
                    const result = { knowledgeKeywords: [] };
                    const sourceAnchor = additional.querySelector('span.addi-msg > a');
                    if (sourceAnchor) result.source = sourceAnchor.getAttribute('title');
                    const leftMsg = additional.querySelector('div.msg-box > div.left-msg');
                    if (leftMsg) {
                        leftMsg.querySelectorAll('span.addi-info > span.info-cnt').forEach(span => {
                            const text = span.textContent.trim();
                            if (text.includes('题型') || text.includes('题类') ||
                                (text.includes('题') && !text.includes('('))) {
                                const parts = text.split(':');
                                result.questionType = parts[1] ? parts[1].trim() : text;
                            } else {
                                const match = text.match(/^(.+?)\\(([0-9.]+)\\)$/);
                                if (match) { result.difficulty = match[1].trim(); result.scoreRate = parseFloat(match[2]); }
                            }
                        });
                        const kwList = leftMsg.querySelectorAll('div.knowledge-list-wrapper > div.knowledge-list > a');
                        kwList.forEach(a => { const title = a.getAttribute('title'); if (title) result.knowledgeKeywords.push(title); });
                    }
                    return result;
                }
            """)
            extra.update(info)
        except Exception:
            pass
        return extra

    async def _scroll_to_load(self):
        for _ in range(3):
            await self.page.evaluate("() => window.scrollTo(0, document.body.scrollHeight)")
            await self.page.wait_for_timeout(1000)
        await self.page.evaluate("() => window.scrollTo(0, 0)")
        await self.page.wait_for_timeout(500)

    async def _download_image(self, session, url, dest_path):
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "https://zujuan.xkw.com/",
        }
        for attempt in range(3):
            try:
                async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                    if resp.status in (301, 302):
                        url = resp.headers.get("Location", url)
                        continue
                    if resp.status != 200:
                        raise Exception(f"HTTP {resp.status}")
                    dest_path.write_bytes(await resp.read())
                    return
            except Exception as e:
                if attempt == 2:
                    raise

    async def close(self):
        if self.browser:
            await self.browser.close()
        if hasattr(self, "playwright"):
            await self.playwright.stop()

    @staticmethod
    def _format_bytes(b):
        for unit in ["B", "KB", "MB", "GB"]:
            if b < 1024:
                return f"{b:.1f} {unit}"
            b /= 1024
        return f"{b:.1f} GB"


# ─────────────────────────────────────────────
# 知识点搜索（直接读 SQLite，不依赖浏览器）
# ─────────────────────────────────────────────

def search_knowledge(query, grade="high", db_path=None):
    """搜索知识点，返回 [(id, name, level), ...]"""
    import sqlite3
    if db_path is None:
        db_path = os.path.expanduser("~/.zujuan-scraper/knowledge-tree.db")
    conn = sqlite3.connect(db_path)
    rows = conn.execute(
        "SELECT id, name, level, parent_id FROM knowledge_nodes WHERE name LIKE ? AND grade = ? ORDER BY level, pos",
        (f"%{query}%", grade)
    ).fetchall()
    conn.close()
    return rows


# ─────────────────────────────────────────────
# 函数式接口
# ─────────────────────────────────────────────

async def scrape(knowledge_id, grade="high", qtype=None, difficulty=None, year=None,
                 order="latest", limit=10, page=None, output_dir=None,
                 storage_state=None, cookie=None, headless=True):
    """
    可编程调用的抓取函数。

    参数:
        knowledge_id: 知识点ID (如 "zsd27977")
        grade: "high" | "middle"
        qtype: "t1"=单选 "t2"=多选 "t3"=填空 "t4"=解答 (可选)
        difficulty: "d1"~"d5" (可选)
        year: 2023-2026 或 -1 (可选)
        order: "latest" | "hot" | "comprehensive"
        limit: 抓取数量 (默认10)
        page: 分页页码 (可选)
        output_dir: 输出目录 (默认 ./output)
        storage_state: storage-state.json 路径 (默认 shared/storage-state.json)
        cookie: Cookie 字符串 (storage_state 不可用时使用)
        headless: 是否无头模式

    返回:
        dict: {"metadata": {...}, "results": [...]}
    """
    if storage_state is None:
        storage_state = str(STORAGE_STATE)

    scraper = ZujuanScraper(
        storage_state=storage_state if Path(storage_state).exists() else None,
        cookie=cookie,
        headless=headless,
        output_dir=output_dir,
    )

    try:
        await scraper.start()
        return await scraper.scrape(
            knowledge_id=knowledge_id, grade=grade, qtype=qtype,
            difficulty=difficulty, year=year, order=order,
            limit=limit, page=page,
        )
    finally:
        await scraper.close()


# ─────────────────────────────────────────────
# CLI 入口
# ─────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="组卷网题目抓取工具")
    parser.add_argument("-k", "--knowledge", required=True, help="知识点ID (如 zsd27977)")
    parser.add_argument("-g", "--grade", default="high", choices=["high", "middle"])
    parser.add_argument("-t", "--type", dest="qtype", choices=["t1", "t2", "t3", "t4"])
    parser.add_argument("-d", "--difficulty", choices=["d1", "d2", "d3", "d4", "d5"])
    parser.add_argument("-y", "--year", type=int)
    parser.add_argument("-r", "--order", default="latest", choices=list(ORDER_CODES))
    parser.add_argument("-l", "--limit", type=int, default=10)
    parser.add_argument("-p", "--page", type=int)
    parser.add_argument("--cookie", help="Cookie 字符串（备用）")
    parser.add_argument("--no-headless", action="store_true")
    parser.add_argument("--output-dir")
    parser.add_argument("--storage-state", help="storage-state.json 路径")

    args = parser.parse_args()

    asyncio.run(scrape(
        knowledge_id=args.knowledge,
        grade=args.grade,
        qtype=args.qtype,
        difficulty=args.difficulty,
        year=args.year,
        order=args.order,
        limit=args.limit,
        page=args.page,
        output_dir=args.output_dir,
        storage_state=args.storage_state,
        cookie=args.cookie,
        headless=not args.no_headless,
    ))


if __name__ == "__main__":
    main()
