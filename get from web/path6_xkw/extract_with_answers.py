#!/usr/bin/env python3
"""
整卷提取 + 答案（需 chujuan.cn 登录 cookie）。
步骤1：requests 提取题目文本/选项/知识点
步骤2：Playwright 点击"显示答案解析"，获取所有答案图片 URL
步骤3：requests 逐题获取 answer_text（选择题/填空题）

Usage:
  python3 extract_with_answers.py --paper-id 6339985 --cookie-file cookies.txt
"""
import asyncio
import json
import re
import time
import os
import sys
import argparse
from datetime import datetime, timezone

import requests
from playwright.async_api import async_playwright

BASE_URL = "https://www.chujuan.cn"

QTYPE_MAP = {
    "1": "单选题", "2": "多选题", "3": "判断题",
    "4": "填空题", "5": "计算题", "6": "解答题", "7": "解答题",
    "8": "阅读理解", "25": "作图题", "28": "综合题",
    "102": "实践探究题", "106": "证明题",
}
XD_MAP = {"1": "小学", "2": "初中", "3": "高中"}
CHID_MAP = {
    "2": "语文", "3": "数学", "4": "英语", "5": "科学",
    "6": "物理", "7": "化学", "8": "历史", "9": "政治",
    "10": "地理", "11": "生物", "14": "信息技术", "15": "通用技术",
    "1015": "思想政治",
}

CROSS_DOMAIN_COOKIES = {"_sync_login_identity", "jump_url", "macId1", "device"}


def parse_cookie_string(s):
    jar = {}
    for item in s.split(";"):
        item = item.strip()
        if "=" in item:
            n, v = item.split("=", 1)
            jar[n.strip()] = v.strip()
    return jar


def build_session(cookies_dict):
    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    })
    for n, v in cookies_dict.items():
        dom = ".chujuan.cn" if n in CROSS_DOMAIN_COOKIES else "www.chujuan.cn"
        s.cookies.set(n, v, domain=dom)
    return s


def fetch(session, url, label=""):
    for attempt in range(3):
        try:
            r = session.get(url, timeout=20, allow_redirects=True)
            r.encoding = r.apparent_encoding or "utf-8"
            if r.status_code == 200:
                return r.text
        except Exception as e:
            print(f"  [{label}] Error: {e}, retry {attempt+1}")
        time.sleep(1 + attempt)
    return None


def extract_json_around(html, pos, max_back=15000, max_forward=30000):
    depth = 0
    start = pos
    while start > max(0, pos - max_back):
        start -= 1
        if html[start] == '}':
            depth += 1
        elif html[start] == '{':
            if depth == 0:
                break
            depth -= 1
    if depth != 0 or html[start] != '{':
        return None
    depth = 0
    end = start
    while end < min(len(html), start + max_forward):
        if html[end] == '{':
            depth += 1
        elif html[end] == '}':
            depth -= 1
            if depth == 0:
                end += 1
                break
        end += 1
    return html[start:end] if depth == 0 else None


def html_to_text(html_str):
    if not html_str:
        return ""
    text = re.sub(r"<[^>]+>", "", html_str)
    for entity, char in [("&nbsp;", " "), ("&amp;", "&"), ("&lt;", "<"),
                          ("&gt;", ">"), ("&quot;", '"'), ("&#39;", "'"),
                          ("&emsp;", "  ")]:
        text = text.replace(entity, char)
    return re.sub(r"\s+", " ", text).strip()


def extract_knowledge(q):
    knowledge = []
    kinfo = q.get("knowledge_info", {})
    if isinstance(kinfo, dict):
        for k in kinfo.values():
            if isinstance(k, dict):
                name = k.get("knowledge_name") or k.get("name", "")
                if name:
                    knowledge.append(name)
    elif isinstance(kinfo, list):
        for k in kinfo:
            if isinstance(k, dict):
                name = k.get("knowledge_name") or k.get("name", "")
                if name:
                    knowledge.append(name)
    if not knowledge:
        tknow = q.get("t_knowledge", [])
        if isinstance(tknow, list):
            for item in tknow:
                if isinstance(item, list):
                    for node in item:
                        if isinstance(node, dict):
                            name = node.get("name", "")
                            if name:
                                knowledge.append(name)
    return knowledge


# ── Phase 1: requests-based extraction ──────────────────
def phase1_extract(session, paper_id):
    """Extract paper metadata + question text/options via requests."""
    url = f"{BASE_URL}/paper/view-{paper_id}.shtml"
    html = fetch(session, url, f"paper-{paper_id}")
    if not html:
        return None, [], []

    meta = {}
    for key, pattern in [
        ("xd", r'"xd"\s*:\s*(\d+)'),
        ("chid", r'"chid"\s*:\s*(\d+)'),
        ("title", r'"title"\s*:\s*"((?:[^"\\]|\\.)*)"'),
        ("paper_type", r'"paper_type"\s*:\s*"([^"]*)"'),
        ("xkName", r'"xkName"\s*:\s*"([^"]*)"'),
        ("xdName", r'"xdName"\s*:\s*"([^"]*)"'),
        ("year", r'"year"\s*:\s*(\d+)'),
    ]:
        m = re.search(pattern, html)
        meta[key] = m.group(1).replace('\\"', '"') if m else ""

    question_ids = list(dict.fromkeys(
        re.findall(r"/question/detail-(\d+)\.shtml", html)
    ))

    questions = {}
    covered = set()
    for m in re.finditer(r'"question_id"\s*:\s*(\d{7,})', html):
        qid = m.group(1)
        pos = m.start()
        if any(abs(pos - p) < 200 for p in covered):
            continue
        json_str = extract_json_around(html, pos)
        if not json_str:
            continue
        covered.add(pos)
        try:
            obj = json.loads(json_str)
            if "question_id" in obj and ("title" in obj or "question_text" in obj):
                questions[qid] = obj
        except json.JSONDecodeError:
            pass

    # Enrich with answer_text and explanation from individual detail pages
    for qid, q in questions.items():
        need_at = not q.get("answer_text")
        need_expl = not q.get("explanation")
        if not need_at and not need_expl:
            continue
        detail_html = fetch(session, f"{BASE_URL}/question/detail-{qid}.shtml", f"q-{qid}")
        if not detail_html:
            continue
        if need_at:
            at = re.search(r'"answer_text"\s*:\s*"([^"]*)"', detail_html)
            if at and at.group(1):
                q["answer_text"] = at.group(1)
        if need_expl:
            expl = re.search(r'"explanation"\s*:\s*"(https://webshot[^"]+ex\.png[^"]*)"', detail_html)
            if expl:
                q["explanation"] = expl.group(1)
        time.sleep(0.2)

    return meta, questions, question_ids


# ── Phase 2: Playwright-based answer image extraction ──
async def phase2_playwright(paper_id, storage_state_path):
    """Click '显示答案解析' and extract answer/explanation image URLs from DOM."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"]
        )
        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            storage_state=storage_state_path,
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        )
        page = await context.new_page()
        await page.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )

        url = f"{BASE_URL}/paper/view-{paper_id}.shtml"
        await page.goto(url, wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(2000)

        # Click "显示答案解析" via JS
        await page.evaluate("""
            const btn = document.querySelector('.J_show_all_explain');
            if (btn) btn.click();
        """)
        print("  Clicked '显示答案解析', waiting for images...")
        await page.wait_for_timeout(8000)

        # Extract img srcs directly from DOM (images are dynamically loaded,
        # not present in page.content() HTML)
        img_data = await page.evaluate("""() => {
            return Array.from(document.querySelectorAll('img'))
                .map(img => img.src)
                .filter(src => src.includes('webshot'));
        }""")

        answer_images = {}
        explanation_images = {}
        for src in img_data:
            m = re.search(r'_(\d{7,})(an|ex)\.png', src)
            if not m:
                continue
            qid, img_type = m.group(1), m.group(2)
            sort_m = re.search(r'sort=(\d+)', src)
            pid_m = re.search(r'parent_id=(\d*)', src)
            entry = {
                "url": src,
                "sort": int(sort_m.group(1)) if sort_m else 0,
                "parent_id": pid_m.group(1) if pid_m else "0",
            }
            if img_type == "an":
                answer_images.setdefault(qid, []).append(entry)
            else:
                explanation_images.setdefault(qid, []).append(entry)

        print(f"  Answer images: {len(answer_images)} questions, "
              f"{sum(len(v) for v in answer_images.values())} total")
        print(f"  Explanation images: {len(explanation_images)} questions, "
              f"{sum(len(v) for v in explanation_images.values())} total")

        await browser.close()
        return answer_images, explanation_images


# ── Merge & Output ──────────────────────────────────────
def merge_and_output(paper_id, meta, questions, answer_images, explanation_images):
    batch_ts = str(int(time.time() * 1000))
    main_qs = {k: v for k, v in questions.items() if not v.get("parent_id")}
    sub_qs = {k: v for k, v in questions.items() if v.get("parent_id")}

    results = []
    for i, (qid, q) in enumerate(sorted(main_qs.items()), 1):
        qtype = str(q.get("question_type", ""))
        type_name = QTYPE_MAP.get(qtype, qtype)

        question_text = html_to_text(q.get("question_text") or q.get("title", ""))
        options = q.get("options")
        if options and isinstance(options, dict):
            opts = [f"{l}. {html_to_text(options[l])}" for l in sorted(options.keys())]
            question_text += "\n" + "\n".join(opts)

        answer_text = q.get("answer_text", "")
        difficulty = q.get("difficult_name", "")
        source = q.get("question_source") or q.get("paper_title") or meta.get("title", "")
        knowledge = extract_knowledge(q)

        # Answer images (from Playwright or from detail page extraction)
        ans_imgs = answer_images.get(qid, [])
        expl_imgs = explanation_images.get(qid, [])

        # Also include explanation URL from detail page if not already captured
        detail_expl = q.get("explanation", "")
        if detail_expl and not expl_imgs:
            expl_imgs = [{"url": detail_expl, "sort": 0, "parent_id": "0"}]

        # Sub-question answers
        sub_answers = []
        for sqid, sq in sorted(sub_qs.items()):
            if str(sq.get("parent_id")) == str(qid):
                sat = sq.get("answer_text", "")
                if sat:
                    sub_answers.append({"sub_qid": sqid, "answer_text": sat})

        # Build sub-question answer text if main answer is missing
        if not answer_text and sub_answers:
            answer_text = "; ".join(
                f"({a['sub_qid']}) {a['answer_text']}" for a in sub_answers
            )

        results.append({
            "id": f"q_{batch_ts}_{i}",
            "index": str(i).zfill(3),
            "questionPath": "",
            "answerPath": ans_imgs[0]["url"] if ans_imgs else "",
            "images": [],
            "source": source,
            "questionType": type_name,
            "difficulty": difficulty,
            "scoreRate": None,
            "knowledgeKeywords": knowledge,
            "questionText": question_text,
            "answerText": answer_text,
            "answerImages": [img["url"] for img in ans_imgs],
            "explanationImages": [img["url"] for img in expl_imgs],
            "answerLocked": not bool(answer_text),
            "questionId": str(qid),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    grade = XD_MAP.get(meta.get("xd", "3"), "高中")
    subject = CHID_MAP.get(meta.get("chid", "3"), "数学")

    return {
        "options": {
            "timestamp": batch_ts,
            "knowledgeId": "",
            "knowledgePoint": "",
            "grade": grade,
            "subject": subject,
            "type": "整卷",
            "paperType": meta.get("paper_type", ""),
            "paperId": str(paper_id),
            "paperTitle": meta.get("title", ""),
            "year": int(meta["year"]) if meta.get("year") else None,
            "order": "最新",
            "source": "paper",
        },
        "results": results,
    }


# ── Storage state builder ───────────────────────────────
def build_storage_state(cookies_dict, path="pw_state.json"):
    state = {"cookies": [], "origins": []}
    for name, value in cookies_dict.items():
        domain = ".chujuan.cn" if name in CROSS_DOMAIN_COOKIES else "www.chujuan.cn"
        state["cookies"].append({
            "name": name, "value": value, "domain": domain,
            "path": "/", "httpOnly": True, "secure": False, "sameSite": "Lax",
        })
    with open(path, "w") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    return path


# ── Main ─────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="整卷提取 + 答案")
    parser.add_argument("--paper-id", required=True)
    parser.add_argument("--cookie")
    parser.add_argument("--cookie-file")
    parser.add_argument("--output")
    parser.add_argument("--no-playwright", action="store_true",
                        help="Skip Playwright (only requests extraction)")
    args = parser.parse_args()

    # Load cookies
    cookies = {}
    if args.cookie_file:
        with open(args.cookie_file) as f:
            text = f.read().strip()
            cookies = parse_cookie_string(text) if "=" in text else json.loads(text)
    elif args.cookie:
        cookies = parse_cookie_string(args.cookie)
    else:
        print("ERROR: Need --cookie or --cookie-file")
        sys.exit(1)

    session = build_session(cookies)

    # Phase 1: requests
    print(f"=== Phase 1: requests extraction (paper {args.paper_id}) ===")
    meta, questions, qids = phase1_extract(session, args.paper_id)
    if not meta:
        print("Failed to extract paper!")
        sys.exit(1)

    main_qs = {k: v for k, v in questions.items() if not v.get("parent_id")}
    with_at = sum(1 for q in main_qs.values() if q.get("answer_text"))
    print(f"  Title: {meta.get('title','')[:80]}")
    print(f"  Questions: {len(main_qs)} main, {len(questions)} total")
    print(f"  With answer_text: {with_at}/{len(main_qs)}")

    # Phase 2: Playwright for answer images
    answer_images, explanation_images = {}, {}
    if not args.no_playwright:
        print(f"\n=== Phase 2: Playwright answer images ===")
        state_path = build_storage_state(cookies, f"pw_state_{args.paper_id}.json")
        answer_images, explanation_images = asyncio.run(
            phase2_playwright(args.paper_id, state_path)
        )

    # Merge
    output = merge_and_output(
        args.paper_id, meta, questions, answer_images, explanation_images
    )

    out_path = args.output or f"paper_{args.paper_id}_with_answers.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    # Stats
    types = {}
    for r in output["results"]:
        t = r["questionType"]
        types[t] = types.get(t, 0) + 1
    with_ans = sum(1 for r in output["results"] if not r["answerLocked"])
    with_imgs = sum(1 for r in output["results"] if r["answerImages"])

    print(f"\n=== Results ===")
    print(f"Saved {len(output['results'])} questions to {out_path}")
    print(f"Types: {json.dumps(types, ensure_ascii=False)}")
    print(f"With answer_text: {with_ans}/{len(output['results'])}")
    print(f"With answer_images: {with_imgs}/{len(output['results'])}")


if __name__ == "__main__":
    main()
