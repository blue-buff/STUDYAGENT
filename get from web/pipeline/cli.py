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
BASE_DIR = Path(__file__).parent
PROJECT_DIR = BASE_DIR.parent
SHARED_DIR = PROJECT_DIR / "shared"
DB_PATH = BASE_DIR / "questions.db"

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

    questions = []
    for section in data.get("content", []):
        head = section.get("head_title", "")
        for q in section.get("questions", []):
            qid = str(q.get("question_id", ""))
            # 知识点
            kp_dict = q.get("knowledge_info", {})
            kp_list = [v["name"] for v in kp_dict.values()
                       if isinstance(v, dict) and v.get("name")] if isinstance(kp_dict, dict) else []
            # 选项
            opts = q.get("options", {})
            opts = {k: v for k, v in opts.items() if v} if isinstance(opts, dict) else {}
            # 答案
            ans = q.get("answer", "") or ""
            ans_json = q.get("answer_json", [])
            if isinstance(ans_json, list) and not ans:
                ans = ", ".join(a for a in ans_json if a)
            # 来源
            ps = q.get("paper_source", {})
            src = ps.get("source_text", "") if isinstance(ps, dict) else ""

            questions.append({
                "id": qid,
                "index": q.get("tihao", ""),
                "type": q.get("channel_type_name", ""),
                "difficulty": q.get("difficult_name", ""),
                "knowledge_points": kp_list,
                "question_text": q.get("title", ""),
                "options": opts,
                "answer_text": ans,
                "source": src,
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
        conds.append("kp.name = ?"); params.append(knowledge_point)
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
    return {
        "total": total,
        "with_answers": with_ans,
        "answer_rate": f"{with_ans / total * 100:.1f}%" if total else "0%",
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
                question_text, options, answer_text, source, answer_locked)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            qid, paper["subject"], "高中", q["type"], q["difficulty"],
            q["question_text"],
            json.dumps(q.get("options", {}), ensure_ascii=False),
            q["answer_text"], q["source"],
            0 if q["answer_text"] else 1,
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
            source = f" | {r['source']}" if r["source"] else ""
            print(f"  [{r['type']}] {_plain_text(r['question_text'])[:80]}{ans}")
            print(f"      知识点: {kps} | 难度: {r['difficulty']}{source}")


def cmd_ingest(args):
    n = ingest(args.paper_id)
    if args.json:
        print(json.dumps({"paper_id": args.paper_id, "ingested": n, "status": "ok" if n > 0 else "already_imported"}, ensure_ascii=False))
    else:
        if n > 0:
            print(f"摄入完成: paper_id={args.paper_id}, 入库 {n} 题")
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
    """批量摄入"""
    result = discover(args.subject, args.zone, page=1, per_page=args.count)
    total_in = 0
    for p in result["papers"]:
        try:
            n = ingest(p["paper_id"])
            total_in += n
            print(f"  {p['paper_id']}: {n} 题")
            time.sleep(1)
        except Exception as e:
            print(f"  {p['paper_id']}: 失败 ({e})")
    if args.json:
        print(json.dumps({"total_ingested": total_in, "papers_processed": len(result["papers"])}))


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
    p.add_argument("paper_id", help="试卷 ID")

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
    elif args.cmd == "batch":
        cmd_batch(args)
    elif args.cmd == "stats":
        cmd_stats(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
