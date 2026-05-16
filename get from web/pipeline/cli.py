#!/usr/bin/env python3
"""
题目检索工具 — 面向人类和 Agent 的统一 CLI

设计原则：
  - 所有子命令默认输出人类可读文本，--json 输出结构化 JSON 供 Agent 使用
  - 每个功能模块同时暴露为 Python 函数，Agent 可直接 import 调用
  - 输出 Schema 稳定，字段含义明确

用法：
  # 人类用
  python3 cli.py discover math --zone exam
  python3 cli.py extract 6339985
  python3 cli.py search 数学 -k 导数 -t 单选题 -n 5

  # Agent 用（JSON 输出）
  python3 cli.py discover math --json
  python3 cli.py search 数学 -k 导数 -t 单选题 -n 5 --json
  python3 cli.py search 数学 -k 导数 --has-answer --json

  # 管线操作
  python3 cli.py ingest 6339985          # 发现→拆卷→入库，一条命令
  python3 cli.py stats                   # 题库统计
"""

import argparse
import json
import logging
import os
import re
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from collections import Counter
from urllib.parse import urljoin

# 抑制 requests/urllib3 的警告，避免污染 JSON 输出
logging.captureWarnings(True)

import requests
from bs4 import BeautifulSoup

# ── 路径 ──
BASE_DIR = Path(__file__).resolve().parent  # resolve() 跟随软链接，拿到真实路径
PROJECT_DIR = BASE_DIR.parent
SHARED_DIR = PROJECT_DIR / "shared"
DB_PATH = BASE_DIR / "questions.db"

# 也支持环境变量覆盖（方便全局安装）
if os.environ.get("TIKU_SHARED_DIR"):
    SHARED_DIR = Path(os.environ["TIKU_SHARED_DIR"])
if os.environ.get("TIKU_DB_PATH"):
    DB_PATH = Path(os.environ["TIKU_DB_PATH"])

# ── 常量 ──
BASE_URL = "https://www.chujuan.cn"
DETAIL_URL = "https://zujuan.xkw.com"

SUBJECTS = {
    "数学": "3", "物理": "6", "化学": "7", "生物": "11",
    "语文": "2", "英语": "4", "历史": "8", "政治": "1015", "地理": "10",
}
SUBJECT_NAME = {v: k for k, v in SUBJECTS.items()}

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36")


# ═══════════════════════════════════════════════════════════════
# 底层函数（Agent 可直接 import）
# ═══════════════════════════════════════════════════════════════

def get_session():
    """创建已认证的 requests.Session"""
    state = SHARED_DIR / "storage-state.json"
    if not state.exists():
        raise FileNotFoundError(f"登录态不存在: {state}\n请先运行 path1_playwright/login.py 扫码登录")

    bridge = PROJECT_DIR / "research_c" / "cookie_bridge.py"
    if bridge.exists():
        sys.path.insert(0, str(bridge.parent))
        from cookie_bridge import playwright_to_requests  # type: ignore
        return playwright_to_requests(state)

    # 降级：直接读 JSON 注入
    session = requests.Session()
    session.headers.update({"User-Agent": UA})
    with open(state) as f:
        data = json.load(f)
    cookies = data.get("cookies", data if isinstance(data, list) else [])
    for c in cookies:
        session.cookies.set(c["name"], c["value"], domain=c.get("domain", ""),
                            path=c.get("path", "/"))
    return session


def discover(subject="数学", zone="exam", page=1, per_page=20):
    """
    发现试卷列表。

    参数:
      subject: 学科名（数学/物理/化学/...）
      zone: 专区（exam=高考, term=备考, sync=同步）
      page: 页码
      per_page: 每页数量

    返回:
      {"total": 2998, "page": 1, "papers": [{paper_id, title, url, subject, zone}]}
    """
    chid = SUBJECTS.get(subject, "3")
    zone_urls = {
        "exam": f"{BASE_URL}/paper/paper-exam-list",
        "term": f"{BASE_URL}/paper/paper-sync-list",
        "sync": f"{BASE_URL}/paper/paper-category-list",
    }
    url = zone_urls.get(zone, zone_urls["exam"])

    session = requests.Session()
    session.headers.update({"User-Agent": UA})
    params = {"xd": "3", "chid": chid, "page": page, "per-page": per_page}
    if zone == "exam":
        params["papertype"] = "0"

    resp = session.get(url, params=params, timeout=30)
    soup = BeautifulSoup(resp.text, "lxml")

    # 总数
    total_el = soup.select_one(".J_count_papers")
    total = int(total_el.text.strip()) if total_el else 0

    papers = []
    for item in soup.select(".item-wrap"):
        links = item.select("a[href*='/paper/view-']")
        title = ""
        href = ""
        for link in links:
            t = link.get("title", "")
            if t:
                title, href = t, link.get("href", "")
                break
        if not title:
            continue
        m = re.search(r'/paper/view-(\d+)', href)
        if m:
            papers.append({
                "paper_id": m.group(1),
                "title": title,
                "url": urljoin(BASE_URL, href),
                "subject": subject,
                "zone": zone,
            })
    return {"total": total, "page": page, "papers": papers}


def extract(paper_id):
    """
    拆解试卷为结构化题目（纯 HTTP，无浏览器）。

    参数:
      paper_id: 试卷 ID（如 6339985）

    返回:
      {paper_id, title, subject, question_count, questions: [{id, index, type, difficulty,
       knowledge_points[], question_text, options{}, answer_text, source}]}
    """
    url = f"{BASE_URL}/paper/view-{paper_id}.shtml"
    resp = requests.get(url, headers={"User-Agent": UA}, timeout=30)
    html = resp.text

    # 提取 paper_detail JSON（大括号配对法）
    idx = html.find("paper_detail:")
    if idx < 0:
        raise ValueError("页面中未找到 paper_detail")
    start = html.find("{", idx)
    depth, end = 0, start
    for i in range(start, len(html)):
        if html[i] == "{": depth += 1
        elif html[i] == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    data = json.loads(html[start:end])
    meta = data["_meta"]
    chid = str(meta.get("chid", "3"))
    paper_year = meta.get("year")  # 试卷年份

    # 子题型数字ID→名称映射
    SUB_TYPE_MAP = {"1": "单选题", "4": "填空题", "5": "解答题/问答题"}

    questions = []
    for section in data.get("content", []):
        for q in section.get("questions", []):
            qid = str(q.get("question_id", ""))

            # 知识点
            kp_dict = q.get("knowledge_info", {})
            kp_list = [v["name"] for v in kp_dict.values()
                       if isinstance(v, dict) and v.get("name")] if isinstance(kp_dict, dict) else []

            # 来源
            ps = q.get("paper_source", {})
            src = ps.get("source_text", "") if isinstance(ps, dict) else ""

            # 题型
            qtype = q.get("channel_type_name", "")
            diff = q.get("difficult_name", "")

            # 展开 list 子题（语文阅读理解、英语阅读、地理综合题等）
            sub_list = q.get("list", [])
            tihao_list = q.get("tihao", []) if isinstance(q.get("tihao"), list) else []

            if sub_list and isinstance(sub_list, list):
                for si, sub in enumerate(sub_list):
                    sqid = str(sub.get("question_id", ""))
                    if not sqid:
                        continue
                    # 子题题型（数字ID映射）
                    sqt = sub.get("question_type", "")
                    stype = SUB_TYPE_MAP.get(str(sqt), qtype) if sqt else qtype
                    # 子题选项
                    sopts = sub.get("options", {})
                    sopts = {k: v for k, v in sopts.items() if v} if isinstance(sopts, dict) else {}
                    # 子题题号（从父题 tihao[i] 取）
                    sidx = str(tihao_list[si]) if si < len(tihao_list) else f"{si+1}"
                    # 子题答案
                    sans = sub.get("answer", "") or ""
                    sans_json = sub.get("answer_json", [])
                    if isinstance(sans_json, list) and not sans:
                        sans = ", ".join(a for a in sans_json if a)
                    questions.append({
                        "id": sqid,
                        "parent_id": qid,
                        "index": sidx,
                        "type": stype,
                        "difficulty": diff or q.get("difficult_name", ""),
                        "knowledge_points": kp_list,
                        "question_text": sub.get("question_text", sub.get("title", "")),
                        "options": sopts,
                        "answer_text": sans,
                        "source": src,
                        "year": paper_year,
                    })
            else:
                # 直题（无 list）
                opts = q.get("options", {})
                opts = {k: v for k, v in opts.items() if v} if isinstance(opts, dict) else {}
                ans = q.get("answer", "") or ""
                ans_json = q.get("answer_json", [])
                if isinstance(ans_json, list) and not ans:
                    ans = ", ".join(a for a in ans_json if a)
                # 索引
                idx = q.get("tihao", "")
                if isinstance(idx, list):
                    idx = ", ".join(str(x) for x in idx)
                questions.append({
                    "id": qid,
                    "index": str(idx),
                    "type": qtype,
                    "difficulty": diff,
                    "knowledge_points": kp_list,
                    "question_text": q.get("title", ""),
                    "options": opts,
                    "answer_text": ans,
                    "source": src,
                    "year": paper_year,
                })

    return {
        "paper_id": paper_id,
        "title": meta.get("title", ""),
        "subject": SUBJECT_NAME.get(chid, chid),
        "question_count": len(questions),
        "questions": questions,
    }


def search(subject=None, knowledge_point=None, question_type=None,
           difficulty=None, has_answer=False, limit=20):
    """
    从本地题库检索题目。

    参数:
      subject: 学科（数学/物理/化学/...），可选
      knowledge_point: 知识点名称（精确匹配），可选
      question_type: 题型（单选题/多选题/填空题/解答题），可选
      difficulty: 难度（容易/较易/普通/较难/困难），可选
      has_answer: 仅返回有答案的题目
      limit: 最大返回数

    返回:
      [{"id", "subject", "type", "difficulty", "knowledge_points[]",
        "question_text", "options", "answer_text", "source", "year"}]
    """
    if not DB_PATH.exists():
        return []

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    sql = "SELECT DISTINCT q.* FROM questions q"
    params = []

    if knowledge_point:
        sql += (" JOIN question_kp qk ON q.id = qk.question_id"
                " JOIN knowledge_points kp ON qk.kp_id = kp.id")

    conds = []
    if subject:
        conds.append("q.subject = ?"); params.append(subject)
    if knowledge_point:
        # 用多种匹配策略：精确匹配 > 词首匹配 > 全字段模糊匹配
        conds.append("(kp.name = ? OR kp.name LIKE ? OR kp.name LIKE ?)")
        params.extend([knowledge_point, f"{knowledge_point}%", f"%{knowledge_point}%"])
    if question_type:
        conds.append("q.question_type = ?"); params.append(question_type)
    if difficulty:
        conds.append("q.difficulty = ?"); params.append(difficulty)
    if has_answer:
        conds.append("q.answer_text != '' AND q.answer_locked = 0")

    if conds:
        sql += " WHERE " + " AND ".join(conds)
    sql += " LIMIT ?"; params.append(limit)

    rows = conn.execute(sql, params).fetchall()
    conn.close()

    return [_row_to_dict(r) for r in rows]


def ingest(paper_id):
    """一键摄入：拆卷 + 入库。返回入库数量。"""
    conn = sqlite3.connect(DB_PATH)
    _ensure_schema(conn)

    paper = extract(paper_id)
    count = _insert_paper(paper, conn)
    conn.commit()
    conn.close()
    return count


def stats():
    """题库统计"""
    if not DB_PATH.exists():
        return {"total": 0, "subjects": {}, "types": {}, "with_answers": 0}

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    total = conn.execute("SELECT COUNT(*) as c FROM questions").fetchone()["c"]
    with_ans = conn.execute(
        "SELECT COUNT(*) as c FROM questions WHERE answer_text != '' AND answer_locked = 0"
    ).fetchone()["c"]

    subjects = {}
    for r in conn.execute("SELECT subject, COUNT(*) as c FROM questions GROUP BY subject"):
        subjects[r["subject"]] = r["c"]

    types = {}
    for r in conn.execute("SELECT question_type, COUNT(*) as c FROM questions GROUP BY question_type"):
        types[r["question_type"]] = r["c"]

    conn.close()
    rate = f"{with_ans / total * 100:.1f}%" if total else "0%"
    return {
        "total": total,
        "with_answers": with_ans,
        "answer_rate": rate,
        "subjects": subjects,
        "types": types,
    }


# ── 内部辅助 ──

def _ensure_schema(conn):
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS questions (
            id TEXT PRIMARY KEY, subject TEXT, grade TEXT, question_type TEXT,
            difficulty TEXT, year INTEGER, question_text TEXT, options TEXT,
            answer_text TEXT, source TEXT, source_url TEXT,
            explanation_url TEXT, answer_locked INTEGER DEFAULT 1,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS knowledge_points (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE
        );
        CREATE TABLE IF NOT EXISTS question_kp (
            question_id TEXT, kp_id INTEGER,
            PRIMARY KEY (question_id, kp_id)
        );
    """)


def _insert_paper(paper, conn):
    count = 0
    for q in paper["questions"]:
        qid = q["id"]
        exist = conn.execute("SELECT 1 FROM questions WHERE id=?", (qid,)).fetchone()
        if exist:
            continue
        conn.execute("""
            INSERT INTO questions (id, subject, grade, question_type, difficulty,
                question_text, options, answer_text, source, answer_locked, year)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            qid, paper["subject"], "高中", q["type"], q["difficulty"],
            q["question_text"],
            json.dumps(q.get("options", {}), ensure_ascii=False),
            q["answer_text"], q["source"],
            0 if q["answer_text"] else 1,
            q.get("year"),
        ))
        for kp in q.get("knowledge_points", []):
            if not kp:
                continue
            conn.execute("INSERT OR IGNORE INTO knowledge_points (name) VALUES (?)", (kp,))
            row = conn.execute("SELECT id FROM knowledge_points WHERE name=?", (kp,)).fetchone()
            if row:
                conn.execute("INSERT OR IGNORE INTO question_kp VALUES (?, ?)", (qid, row[0]))
        count += 1
    return count


def _row_to_dict(r):
    opts = r["options"] or "{}"
    try:
        opts = json.loads(opts)
    except (json.JSONDecodeError, TypeError):
        opts = {}

    # 重建知识点
    kp_list = []
    conn = sqlite3.connect(DB_PATH)
    for kp_row in conn.execute(
        "SELECT kp.name FROM question_kp qk JOIN knowledge_points kp ON qk.kp_id = kp.id WHERE qk.question_id=?",
        (r["id"],)
    ):
        kp_list.append(kp_row[0])
    conn.close()

    return {
        "id": r["id"],
        "subject": r["subject"],
        "type": r["question_type"],
        "difficulty": r["difficulty"],
        "knowledge_points": kp_list,
        "question_text": r["question_text"],
        "options": opts,
        "answer_text": r["answer_text"],
        "source": r["source"],
        "year": r["year"],
    }


def _plain_text(html_str):
    """MathML/HTML → 纯文本摘要"""
    text = re.sub(r'<[^>]+>', '', html_str or "")
    text = text.replace("&nbsp;", " ")
    text = re.sub(r'\s+', ' ', text).strip()
    return text


# ═══════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════

def cmd_discover(args):
    result = discover(args.subject, args.zone, args.page, args.per_page)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"{args.subject} | {args.zone}专区 | 共 {result['total']} 套 | 第{args.page}页")
        print("-" * 55)
        for p in result["papers"]:
            print(f"  {p['paper_id']}  {p['title'][:60]}")


def cmd_extract(args):
    result = extract(args.paper_id)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"试卷: {result['title']}")
        print(f"学科: {result['subject']} | 共 {result['question_count']} 题")
        print("-" * 55)
        for q in result["questions"]:
            kps = ", ".join(q["knowledge_points"][:3])
            opts = " ".join(q["options"].keys()) if q["options"] else ""
            ans = f" [答案:{q['answer_text']}]" if q["answer_text"] else ""
            print(f"  [{q['index']}] {q['type']} | {q['difficulty']} | {kps}{ans}")
            print(f"      {_plain_text(q['question_text'])[:80]}")
            if opts:
                print(f"      选项: {opts}")


def cmd_search(args):
    results = search(
        subject=args.subject,
        knowledge_point=args.knowledge_point,
        question_type=args.type,
        difficulty=args.difficulty,
        has_answer=args.has_answer,
        limit=args.limit,
    )
    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        filters = []
        if args.subject: filters.append(args.subject)
        if args.knowledge_point: filters.append(args.knowledge_point)
        if args.type: filters.append(args.type)
        if args.difficulty: filters.append(args.difficulty)
        if args.has_answer: filters.append("有答案")
        print(f"检索: {', '.join(filters) if filters else '全部'} | {len(results)} 条")
        print("-" * 55)
        for r in results:
            kps = ", ".join(r["knowledge_points"][:3])
            ans = f" [答案:{r['answer_text']}]" if r["answer_text"] else ""
            opts_lbl = " ".join(r["options"].keys()) if r["options"] else ""
            year = f" | {r['year']}" if r.get("year") else ""
            source = f" | {r['source']}" if r["source"] else ""
            print(f"  [{r['type']}] {_plain_text(r['question_text'])[:80]}{ans}")
            if opts_lbl:
                print(f"      选项: {opts_lbl} | 知识点: {kps} | 难度: {r['difficulty']}{year}{source}")
            else:
                print(f"      知识点: {kps} | 难度: {r['difficulty']}{year}{source}")


# ── 答案补全（方向A：webshot 不限配额）──

def fetch_answers(paper_data, session=None, ocr=False, paper_id=None):
    """
    为题目逐题补答案。
    1. 发请求到 /11q{id}.html 提取 explanation URL
    2. 下载 webshot 解析图（不受配额限制）
    3. 可选 Kimi OCR 提取答案文字

    参数:
      paper_data: extract() 返回的 dict
      session: 已认证的 requests.Session
      ocr: 是否调用 Kimi CLI 提取文字答案
      paper_id: 可选，用于解析图命名

    返回:
      更新后的 paper_data，每题增加 explanation_url, explanation_path, answer_text
    """
    if session is None:
        session = get_session()

    pid = paper_id or paper_data.get("paper_id", "unknown")
    img_dir = BASE_DIR / "explanations" / pid
    img_dir.mkdir(parents=True, exist_ok=True)
    fetched = 0

    for i, q in enumerate(paper_data.get("questions", [])):
        qid = q.get("id", "")
        if q.get("answer_text"):
            continue

        # 从 detail 页提取 explanation URL
        try:
            resp = session.get(
                f"{BASE_URL}/question/detail-{qid}.shtml",
                timeout=15,
                headers={"Referer": f"{DETAIL_URL}/"}
            )
            if resp.status_code != 200:
                continue
            html = resp.text
        except Exception:
            continue

        expl_url = ""
        m = re.search(r'"explanation"\s*:\s*"([^"]*webshot[^"]*)"', html)
        if not m:
            m = re.search(r'"(https?://webshot\.zujuan\.com/[^"]+)"', html)
        if m:
            expl_url = m.group(1).replace("\\u0026", "&").replace("\\/", "/")

        if not expl_url:
            continue

        q["explanation_url"] = expl_url
        img_path = img_dir / f"q{qid}.jpg"

        # 下载
        try:
            r = session.get(expl_url, timeout=30,
                           headers={"Referer": f"{DETAIL_URL}/"})
            if r.status_code == 200 and len(r.content) > 1000:
                img_path.write_bytes(r.content)
                q["explanation_path"] = str(img_path)
                fetched += 1

                # OCR 提取答案
                if ocr:
                    ans = _ocr_answer(img_path)
                    if ans:
                        q["answer_text"] = ans
                        q["answer_locked"] = False
        except Exception:
            continue

    paper_data["_answers_fetched"] = fetched
    return paper_data


def _ocr_answer(image_path):
    """Kimi CLI OCR 提取答案文字"""
    import subprocess
    try:
        result = subprocess.run(
            ["kimi", "--quiet", "-p",
             "只输出正确答案的选项字母或数值。不要解释。",
             str(image_path)],
            capture_output=True, text=True, timeout=60
        )
        if result.returncode == 0:
            ans = result.stdout.strip()
            # 清理常见噪声
            ans = re.sub(r'^(答案|正确答案|选|故选)\s*[:：]?\s*', '', ans)
            ans = ans.strip('。. ')
            return ans if len(ans) < 50 else ""
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return ""


def enrich_db(subject=None, limit=50, ocr=False):
    """
    为数据库中无答案的题目补答案。
    从 DB 取题目 → 逐题请求 detail 页 → 下载 webshot → 更新 DB
    """
    if not DB_PATH.exists():
        return {"enriched": 0}

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    sql = "SELECT * FROM questions WHERE (answer_text IS NULL OR answer_text = '') AND answer_locked = 1"
    params = []
    if subject:
        sql += " AND subject = ?"
        params.append(subject)
    sql += " LIMIT ?"
    params.append(limit)

    rows = conn.execute(sql, params).fetchall()
    conn.close()

    if not rows:
        return {"enriched": 0, "message": "没有需要补答案的题目"}

    session = get_session()
    enriched = 0

    for row in rows:
        qid = row["id"]
        try:
            resp = session.get(f"{BASE_URL}/question/detail-{qid}.shtml", timeout=15,
                              headers={"Referer": f"{DETAIL_URL}/"})
            if resp.status_code != 200:
                continue
            html = resp.text
        except Exception:
            continue

        expl_url = ""
        m = re.search(r'"explanation"\s*:\s*"([^"]*webshot[^"]*)"', html)
        if not m:
            m = re.search(r'"(https?://webshot\.zujuan\.com/[^"]+)"', html)
        if m:
            expl_url = m.group(1).replace("\\u0026", "&").replace("\\/", "/")

        if not expl_url:
            continue

        img_dir = BASE_DIR / "explanations" / "db"
        img_dir.mkdir(parents=True, exist_ok=True)
        img_path = img_dir / f"q{qid}.jpg"

        try:
            r = session.get(expl_url, timeout=30,
                           headers={"Referer": f"{DETAIL_URL}/"})
            if r.status_code != 200 or len(r.content) <= 1000:
                continue
            img_path.write_bytes(r.content)

            answer_text = ""
            if ocr:
                answer_text = _ocr_answer(img_path)

            conn = sqlite3.connect(DB_PATH)
            conn.execute(
                "UPDATE questions SET explanation_url=?, answer_text=?, answer_locked=? WHERE id=?",
                (expl_url, answer_text, 0 if answer_text else 1, qid)
            )
            conn.commit()
            conn.close()
            enriched += 1
            time.sleep(0.3)
        except Exception:
            continue

    return {"enriched": enriched, "total_checked": len(rows)}


def cmd_enrich(args):
    result = enrich_db(args.subject, args.limit, args.ocr)
    if args.json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        print(f"补答案完成: 检查 {result.get('total_checked', 0)} 题, "
              f"成功下载 {result['enriched']} 张解析图")


def cmd_ingest(args):
    n = ingest(args.paper_id)

    # 如果需要补答案
    ans_info = ""
    if args.fetch_answers and n > 0:
        paper_data = extract(args.paper_id)
        paper_data = fetch_answers(paper_data, session=get_session(),
                                   ocr=args.ocr, paper_id=args.paper_id)
        # 更新 DB 中的答案
        conn = sqlite3.connect(DB_PATH)
        for q in paper_data.get("questions", []):
            if q.get("answer_text"):
                conn.execute("UPDATE questions SET answer_text=?, answer_locked=0, explanation_url=? WHERE id=?",
                           (q["answer_text"], q.get("explanation_url", ""), q["id"]))
            elif q.get("explanation_url"):
                conn.execute("UPDATE questions SET explanation_url=? WHERE id=?",
                           (q["explanation_url"], q["id"]))
        conn.commit()
        conn.close()
        ans_info = f", 补答案 {paper_data.get('_answers_fetched', 0)} 张"

    if args.json:
        print(json.dumps({
            "paper_id": args.paper_id,
            "ingested": n,
            "status": "ok" if n > 0 else "already_imported",
            "answers_fetched": paper_data.get("_answers_fetched", 0) if args.fetch_answers and n > 0 else 0,
        }, ensure_ascii=False))
    else:
        if n > 0:
            print(f"摄入完成: paper_id={args.paper_id}, 入库 {n} 题{ans_info}")
        else:
            print(f"已导入过: paper_id={args.paper_id}, 无新题")


def cmd_stats(args):
    s = stats()
    if args.json:
        print(json.dumps(s, ensure_ascii=False, indent=2))
    else:
        print(f"题库总量: {s['total']} 题")
        print(f"有答案:   {s['with_answers']} 题 ({s['answer_rate']})")
        print(f"学科分布: {s['subjects']}")
        print(f"题型分布: {s['types']}")


def cmd_batch(args):
    """批量摄入，自动翻页"""
    total_in = 0
    page = 1
    processed = 0
    target = args.count
    while processed < target:
        result = discover(args.subject, args.zone, page=page, per_page=20)
        papers = result["papers"]
        if not papers:
            break
        for p in papers:
            if processed >= target:
                break
            try:
                n = ingest(p["paper_id"])
                total_in += n
                processed += 1
                print(f"  [{processed}/{target}] {p['paper_id']}: {n} 题")
                time.sleep(0.5)
            except Exception as e:
                print(f"  [{processed}] {p['paper_id']}: 失败 ({e})")
        page += 1
        if page > 300:  # 安全上限 300 页 × 10 = 3000 套
            break
        time.sleep(1)
    print(f"\n总计: {processed} 套试卷, {total_in} 新题入库")
    if args.json:
        print(json.dumps({"total_ingested": total_in, "papers_processed": processed}))


def main():
    parser = argparse.ArgumentParser(
        description="题目检索工具 — 人类和 Agent 共用的 CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python3 cli.py discover 数学 --zone exam
  python3 cli.py extract 6339985
  python3 cli.py search 数学 -k 导数 -t 单选题 -n 5
  python3 cli.py search 数学 -k 导数 --has-answer --json
  python3 cli.py ingest 6339985
  python3 cli.py batch 数学 --count 5
  python3 cli.py stats
        """,
    )
    sub = parser.add_subparsers(dest="cmd")

    # discover
    p = sub.add_parser("discover", help="发现试卷")
    p.add_argument("--json", action="store_true", help="JSON 输出（供 Agent 使用）")
    p.add_argument("subject", help="学科（数学/物理/化学/...）")
    p.add_argument("--zone", default="exam", help="专区（exam/term/sync）")
    p.add_argument("--page", type=int, default=1)
    p.add_argument("--per-page", type=int, default=20)

    # extract
    p = sub.add_parser("extract", help="拆解试卷")
    p.add_argument("--json", action="store_true", help="JSON 输出（供 Agent 使用）")
    p.add_argument("paper_id", help="试卷 ID")

    # search
    p = sub.add_parser("search", help="检索题目")
    p.add_argument("--json", action="store_true", help="JSON 输出（供 Agent 使用）")
    p.add_argument("subject", nargs="?", help="学科")
    p.add_argument("-k", "--knowledge-point", help="知识点")
    p.add_argument("-t", "--type", help="题型（单选题/多选题/填空题/解答题）")
    p.add_argument("-d", "--difficulty", help="难度（容易/较易/普通/较难/困难）")
    p.add_argument("-a", "--has-answer", action="store_true", help="仅返回有答案的题目")
    p.add_argument("-n", "--limit", type=int, default=20)

    # ingest
    p = sub.add_parser("ingest", help="一键摄入（拆卷+入库）")
    p.add_argument("--json", action="store_true", help="JSON 输出（供 Agent 使用）")
    p.add_argument("--fetch-answers", "-f", action="store_true", help="补答案（下载webshot解析图）")
    p.add_argument("--ocr", action="store_true", help="Kimi OCR提取答案文字")
    p.add_argument("paper_id", help="试卷 ID")

    # enrich
    p = sub.add_parser("enrich", help="为题库已有题目补答案")
    p.add_argument("--json", action="store_true", help="JSON 输出（供 Agent 使用）")
    p.add_argument("--subject", "-s", help="学科（可选，不指定则全部）")
    p.add_argument("--limit", "-n", type=int, default=50, help="最多处理几题")
    p.add_argument("--ocr", action="store_true", help="Kimi OCR提取答案文字")

    # batch
    p = sub.add_parser("batch", help="批量摄入")
    p.add_argument("--json", action="store_true", help="JSON 输出（供 Agent 使用）")
    p.add_argument("subject", help="学科")
    p.add_argument("--zone", default="exam")
    p.add_argument("--count", type=int, default=10)

    # stats
    p = sub.add_parser("stats", help="题库统计")
    p.add_argument("--json", action="store_true", help="JSON 输出（供 Agent 使用）")

    args = parser.parse_args()

    if args.cmd == "discover":
        cmd_discover(args)
    elif args.cmd == "extract":
        cmd_extract(args)
    elif args.cmd == "search":
        cmd_search(args)
    elif args.cmd == "ingest":
        cmd_ingest(args)
    elif args.cmd == "enrich":
        cmd_enrich(args)
    elif args.cmd == "batch":
        cmd_batch(args)
    elif args.cmd == "stats":
        cmd_stats(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
