#!/usr/bin/env python3
"""
统一题目获取管线 — 整合 Path 1/2/6 + 方向A/B/C 研究成果

用法：
  python3 pipeline.py discover --subject math --zone exam    # 发现试卷
  python3 pipeline.py extract --paper-id 6339985              # 拆卷
  python3 pipeline.py answers --input paper_6339985.json     # 补答案
  python3 pipeline.py import-existing                         # 导入已有数据
  python3 pipeline.py all --subject math --limit 5           # 全流程
"""

import argparse
import json
import os
import re
import sys
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

# ── 路径 ──
BASE_DIR = Path(__file__).parent
PROJECT_DIR = BASE_DIR.parent
SHARED_DIR = PROJECT_DIR / "shared"
DB_PATH = BASE_DIR / "questions.db"

# ── 学科/学段映射 ──
CHID_MAP = {
    "math": "3", "physics": "6", "chemistry": "7", "biology": "11",
    "chinese": "2", "english": "4", "history": "8", "politics": "1015",
    "geography": "10",
}
XD_MAP = {"primary": "1", "junior": "2", "senior": "3"}
SUBJECT_NAMES = {v: k for k, v in {
    "数学": "3", "物理": "6", "化学": "7", "生物": "11",
    "语文": "2", "英语": "4", "历史": "8", "政治": "1015", "地理": "10",
}.items()}

BASE_URL = "https://www.chujuan.cn"
DETAIL_URL = "https://zujuan.xkw.com"

COOKIE_BRIDGE_PATH = PROJECT_DIR / "research_c" / "cookie_bridge.py"
if COOKIE_BRIDGE_PATH.exists():
    sys.path.insert(0, str(COOKIE_BRIDGE_PATH.parent))
    from cookie_bridge import playwright_to_requests


def get_session():
    """从 storage-state.json 创建已认证的 requests.Session"""
    state_path = SHARED_DIR / "storage-state.json"
    if not state_path.exists():
        print("错误: storage-state.json 不存在，请先运行 path1_playwright/login.py")
        sys.exit(1)
    return playwright_to_requests(state_path)


# ═══════════════════════════════════════════════════════════════
# 模块 A: 试卷发现
# ═══════════════════════════════════════════════════════════════

def discover_papers(subject="math", zone="exam", pages=1, per_page=20):
    """
    发现试卷列表。
    zone: exam(高考专区) | sync(同步专区) | term(备考专区)
    """
    chid = CHID_MAP.get(subject, "3")
    zone_urls = {
        "exam": f"{BASE_URL}/paper/paper-exam-list",
        "sync": f"{BASE_URL}/paper/paper-category-list",
        "term": f"{BASE_URL}/paper/paper-sync-list",
    }
    url = zone_urls.get(zone, zone_urls["exam"])
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    })

    papers = []
    for page in range(1, pages + 1):
        params = {"xd": "3", "chid": chid, "page": page, "per-page": per_page}
        if zone == "exam":
            params["papertype"] = "0"
        resp = session.get(url, params=params, timeout=30)
        if resp.status_code != 200:
            print(f"  页面 {page} 请求失败: {resp.status_code}")
            continue

        soup = BeautifulSoup(resp.text, "lxml")
        # 试卷列表在 ul > li > .item-wrap 中，标题在第二个 a 标签的 title 属性
        for item in soup.select(".item-wrap"):
            links = item.select("a[href*='/paper/view-']")
            if not links:
                continue
            # 取第一个有 title 的链接
            title = ""
            href = ""
            for link in links:
                t = link.get("title", "")
                if t:
                    title = t
                    href = link.get("href", "")
                    break
            if not title:
                continue
            paper_id = re.search(r'/paper/view-(\d+)', href)
            if paper_id and title:
                papers.append({
                    "paper_id": paper_id.group(1),
                    "title": title,
                    "url": urljoin(BASE_URL, href),
                    "subject": subject,
                    "zone": zone,
                })

    print(f"发现 {len(papers)} 套试卷")
    return papers


# ═══════════════════════════════════════════════════════════════
# 模块 B: SSR 拆题
# ═══════════════════════════════════════════════════════════════

def extract_paper(paper_id):
    """从试卷页 SSR HTML 提取所有题目"""
    url = f"{BASE_URL}/paper/view-{paper_id}.shtml"
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    })

    resp = session.get(url, timeout=30)
    if resp.status_code != 200:
        print(f"请求失败: {resp.status_code}")
        return None

    html = resp.text

    # 提取 paper_detail JSON（格式: paper_detail: {...}）
    paper_detail = None
    idx = html.find("paper_detail:")
    if idx < 0:
        idx = html.find("paper_detail =")
    if idx >= 0:
        start = html.find("{", idx)
        if start >= 0:
            depth, end = 0, start
            for i in range(start, len(html)):
                if html[i] == "{":
                    depth += 1
                elif html[i] == "}":
                    depth -= 1
                    if depth == 0:
                        end = i + 1
                        break
            try:
                paper_detail = json.loads(html[start:end])
            except json.JSONDecodeError:
                pass

    if not paper_detail:
        print("无法提取 paper_detail")
        return None

    # 提取题目 ID 列表
    question_ids = []
    # 优先从 _meta.question_ids
    meta = paper_detail.get("_meta", {})
    raw_ids = meta.get("question_ids", [])
    if raw_ids:
        question_ids = [str(qid) for qid in raw_ids]

    # 补充: 从 structure 中提取
    if not question_ids:
        structure = paper_detail.get("structure", [])
        for section in structure if isinstance(structure, list) else [structure]:
            for q in section.get("questions", []):
                qid = q.get("question_id") or q.get("questionId")
                if qid:
                    question_ids.append(str(qid))

    # 从 content 中直接提取所有题目（完整数据在 paper_detail JSON 里）
    questions = []
    meta = paper_detail.get("_meta", {})
    chid = str(meta.get("chid", "3"))

    for section in paper_detail.get("content", []):
        for q in section.get("questions", []):
            qid = str(q.get("question_id", ""))
            if not qid:
                continue

            # 知识点（knowledge_info 格式: {id: {name, ...}}）
            kp_dict = q.get("knowledge_info", {})
            if isinstance(kp_dict, dict):
                kp_list = [v["name"] for v in kp_dict.values() if isinstance(v, dict) and v.get("name")]
            else:
                kp_list = []

            # 选项
            options = q.get("options", {})
            if isinstance(options, dict):
                options = {k: v for k, v in options.items() if v}

            # 答案（SSR 中通常为空，需后续从 detail 页补）
            answer = q.get("answer", "") or ""
            answer_json = q.get("answer_json", [])
            if isinstance(answer_json, list) and not answer:
                answer = ", ".join([a for a in answer_json if a])

            # 来源
            ps = q.get("paper_source", {})
            source_text = ps.get("source_text", "") if isinstance(ps, dict) else str(ps)

            questions.append({
                "id": qid,
                "questionId": qid,
                "index": str(q.get("tihao", "")),
                "questionType": q.get("channel_type_name", ""),
                "difficulty": q.get("difficult_name", ""),
                "scoreRate": q.get("difficult_index"),
                "knowledgeKeywords": kp_list,
                "questionText": q.get("title", ""),
                "questionHtml": q.get("question_text", ""),
                "options": options,
                "answerText": answer,
                "explanationUrl": "",   # 需从 detail 页补
                "source": source_text,
                "answerLocked": not bool(answer),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })

    if not questions:
        print("无法提取题目")
        return None

    chid = str(meta.get("chid", "3"))
    output = {
        "options": {
            "paperId": paper_id,
            "paperTitle": meta.get("title", ""),
            "subject": SUBJECT_NAMES.get(chid, chid),
            "grade": "高中",
            "year": meta.get("year"),
            "source": "paper",
        },
        "results": questions,
    }
    return output


def fetch_question_detail(qid, session=None):
    """从题目详情页提取结构化数据 + explanation URL"""
    if session is None:
        session = requests.Session()

    url = f"{DETAIL_URL}/11q{qid}.html"
    try:
        resp = session.get(url, timeout=15)
        if resp.status_code != 200:
            return None
        html = resp.text
    except Exception:
        return None

    # 提取 question 数据
    qdata = _extract_json(html, r'"question"\s*:\s*')
    if not qdata:
        qdata = _extract_json(html, "question")

    title = qdata.get("title", "") if qdata else ""
    qtype = qdata.get("channel_type_name", "") if qdata else ""
    if not qtype and qdata:
        qt = qdata.get("question_type", "")
        qtype = {"1": "单选题", "2": "多选题", "4": "填空题", "6": "解答题"}.get(str(qt), qt)

    difficulty = ""
    score_rate = None
    knowledge_keywords = []
    source = ""
    explanation_url = ""
    options = {}

    if qdata:
        # 知识点
        knowledge_keywords = [k.get("title", k) if isinstance(k, dict) else k
                              for k in qdata.get("knowledge", [])]
        source = qdata.get("question_source", "")

    # 题型/难度从 HTML 补充
    soup = BeautifulSoup(html, "lxml")
    info_spans = soup.select(".addi-info .info-cnt")
    for span in info_spans:
        text = span.get_text(strip=True)
        if "(" in text and any(d in text for d in ["容易", "较易", "适中", "较难", "困难"]):
            difficulty = text.split("(")[0]
        elif not qtype and any(t in text for t in ["单选题", "多选题", "填空题", "解答题"]):
            qtype = text

    # explanation URL（核心：不受配额限制）
    expl_match = re.search(r'"explanation"\s*:\s*"([^"]*webshot[^"]*)"', html)
    if not expl_match:
        expl_match = re.search(r'"(https?://webshot\.zujuan\.com/[^"]+)"', html)
    if expl_match:
        explanation_url = expl_match.group(1).replace("\\u0026", "&").replace("\\/", "/")

    # 选项
    if qdata:
        raw_opts = qdata.get("options", {})
        if isinstance(raw_opts, dict):
            options = {k: v for k, v in raw_opts.items() if v}

    # 答案文本（SSR 中可能暴露）
    answer_text = ""
    at_match = re.search(r'"answer_text"\s*:\s*"([^"]*)"', html)
    if at_match and at_match.group(1).strip():
        answer_text = at_match.group(1)

    return {
        "id": qid,
        "questionId": qid,
        "index": "",
        "questionType": qtype,
        "difficulty": difficulty,
        "scoreRate": score_rate,
        "knowledgeKeywords": knowledge_keywords,
        "questionText": title,
        "options": options,
        "answerText": answer_text,
        "explanationUrl": explanation_url,
        "source": source,
        "answerLocked": not bool(answer_text),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def _extract_json(html, pattern):
    """从 HTML 中提取 JSON 对象"""
    if isinstance(pattern, str) and not pattern.startswith(r'"'):
        # 匹配 = {...} 或 : {...}
        for prefix in [f'{pattern}\\s*=\\s*', f'{pattern}\\s*:\\s*', f'"{pattern}"\\s*:\\s*']:
            m = re.search(f'{prefix}({{.*?}});', html, re.DOTALL)
            if m:
                try:
                    return json.loads(m.group(1))
                except json.JSONDecodeError:
                    continue
        return None

    m = re.search(f'{pattern}({{.*?}})', html, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    return None


# ═══════════════════════════════════════════════════════════════
# 模块 C: 补答案（webshot 下载 + Kimi OCR）
# ═══════════════════════════════════════════════════════════════

def fetch_answers(input_data, use_ocr=False):
    """
    为题目补答案。
    流程（基于方向A发现：detail页 HTML 有 explanation URL，不限配额）：
    1. 有 answerText → 跳过
    2. 发请求到 /11q{id}.html → 从 HTML 提取 explanation URL
    3. 下载解析图（webshot CDN，不限量）
    4. 可选 Kimi OCR 提取答案文字
    """
    if isinstance(input_data, str):
        with open(input_data) as f:
            data = json.load(f)
    else:
        data = input_data

    results = data.get("results", data if isinstance(data, list) else [])
    session = get_session()

    for i, q in enumerate(results):
        qid = q.get("questionId", q.get("id", ""))
        print(f"  [{i+1}/{len(results)}] {qid} ...", end=" ")

        if q.get("answerText"):
            print("已有答案，跳过")
            continue

        # 从 detail 页提取 explanation URL
        try:
            resp = session.get(
                f"{DETAIL_URL}/11q{qid}.html",
                timeout=15,
                headers={"Referer": f"{DETAIL_URL}/"}
            )
            if resp.status_code != 200:
                print(f"detail 页失败 ({resp.status_code})")
                continue
            detail_html = resp.text
        except Exception as e:
            print(f"请求失败: {e}")
            continue

        # 提取 explanation URL
        expl_url = ""
        expl_match = re.search(r'"explanation"\s*:\s*"([^"]*webshot[^"]*)"', detail_html)
        if not expl_match:
            expl_match = re.search(r'"(https?://webshot\.zujuan\.com/[^"]+)"', detail_html)
        if expl_match:
            expl_url = expl_match.group(1).replace("\\u0026", "&").replace("\\/", "/")

        if expl_url:
            q["explanationUrl"] = expl_url
            img_path = BASE_DIR / "explanations" / f"q{qid}.jpg"
            img_path.parent.mkdir(exist_ok=True)
            if _download_image(expl_url, img_path, session):
                q["explanationPath"] = str(img_path)
                print(f"图已下载 ({img_path.stat().st_size} bytes)", end="")

                if use_ocr:
                    answer = ocr_answer(img_path)
                    if answer:
                        q["answerText"] = answer
                        q["answerLocked"] = False
                        print(f" OCR: {answer}", end="")
                print()
            else:
                print("下载失败")
        else:
            print("无 explanation URL")

    return data


def _fetch_detail_html(qid, session):
    try:
        resp = session.get(f"{DETAIL_URL}/11q{qid}.html", timeout=15,
                          headers={"Referer": f"{DETAIL_URL}/"})
        return resp.text if resp.status_code == 200 else ""
    except Exception:
        return ""


def _download_image(url, path, session):
    try:
        resp = session.get(url, timeout=30,
                          headers={"Referer": f"{DETAIL_URL}/"})
        if resp.status_code == 200 and len(resp.content) > 1000:
            path.write_bytes(resp.content)
            return True
    except Exception:
        pass
    return False


def ocr_answer(image_path):
    """用 Kimi CLI OCR 提取答案"""
    import subprocess
    try:
        result = subprocess.run(
            ["kimi", "--quiet", "-p",
             "只输出正确答案（选项字母或数值），不要任何解释。",
             str(image_path)],
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return ""


# ═══════════════════════════════════════════════════════════════
# 模块 D: SQLite 存储
# ═══════════════════════════════════════════════════════════════

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS subjects (
            id INTEGER PRIMARY KEY, name TEXT UNIQUE
        );
        CREATE TABLE IF NOT EXISTS knowledge_points (
            id INTEGER PRIMARY KEY, name TEXT UNIQUE
        );
        CREATE TABLE IF NOT EXISTS questions (
            id TEXT PRIMARY KEY,
            subject TEXT,
            grade TEXT,
            question_type TEXT,
            difficulty TEXT,
            year INTEGER,
            question_text TEXT,
            options TEXT,
            answer_text TEXT,
            analysis_text TEXT,
            source TEXT,
            source_url TEXT,
            explanation_url TEXT,
            explanation_path TEXT,
            answer_locked INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS question_kp (
            question_id TEXT, kp_id INTEGER,
            PRIMARY KEY (question_id, kp_id),
            FOREIGN KEY (question_id) REFERENCES questions(id),
            FOREIGN KEY (kp_id) REFERENCES knowledge_points(id)
        );
    """)
    conn.commit()
    return conn


def store_questions(data, conn=None):
    """题目入库，自动去重"""
    close_conn = False
    if conn is None:
        conn = init_db()
        close_conn = True

    results = data.get("results", data if isinstance(data, list) else [])
    opts = data.get("options", {})
    inserted = 0

    for q in results:
        qid = str(q.get("questionId") or q.get("id", ""))
        if not qid:
            continue

        # 去重
        existing = conn.execute("SELECT 1 FROM questions WHERE id=?", (qid,)).fetchone()
        if existing:
            continue

        subject = opts.get("subject", q.get("subject", ""))
        grade = opts.get("grade", q.get("grade", "高中"))

        conn.execute("""
            INSERT OR IGNORE INTO questions
            (id, subject, grade, question_type, difficulty, year,
             question_text, options, answer_text,
             source, source_url, explanation_url, explanation_path,
             answer_locked)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            qid, subject, grade,
            q.get("questionType", ""),
            q.get("difficulty", ""),
            opts.get("year") or q.get("year"),
            q.get("questionText", ""),
            json.dumps(q.get("options", {}), ensure_ascii=False),
            q.get("answerText", ""),
            q.get("source", ""),
            q.get("sourceUrl", ""),
            q.get("explanationUrl", ""),
            q.get("explanationPath", ""),
            1 if q.get("answerLocked") else 0,
        ))

        # 知识点关联
        for kp_name in q.get("knowledgeKeywords", []):
            if not kp_name:
                continue
            conn.execute("INSERT OR IGNORE INTO knowledge_points (name) VALUES (?)", (kp_name,))
            row = conn.execute("SELECT id FROM knowledge_points WHERE name=?", (kp_name,)).fetchone()
            if row:
                conn.execute("INSERT OR IGNORE INTO question_kp (question_id, kp_id) VALUES (?, ?)",
                             (qid, row[0]))

        inserted += 1

    conn.commit()
    if close_conn:
        conn.close()
    return inserted


def query_questions(subject=None, knowledge_point=None, question_type=None,
                    difficulty=None, has_answer=False, limit=20):
    """精确检索题目"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    sql = "SELECT DISTINCT q.* FROM questions q"
    params = []

    if knowledge_point:
        sql += " JOIN question_kp qk ON q.id = qk.question_id JOIN knowledge_points kp ON qk.kp_id = kp.id"

    conditions = []
    if subject:
        conditions.append("q.subject = ?")
        params.append(subject)
    if knowledge_point:
        conditions.append("kp.name = ?")
        params.append(knowledge_point)
    if question_type:
        conditions.append("q.question_type = ?")
        params.append(question_type)
    if difficulty:
        conditions.append("q.difficulty = ?")
        params.append(difficulty)
    if has_answer:
        conditions.append("q.answer_text != '' AND q.answer_locked = 0")

    if conditions:
        sql += " WHERE " + " AND ".join(conditions)
    sql += " LIMIT ?"
    params.append(limit)

    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ═══════════════════════════════════════════════════════════════
# 模块 E: 已有数据导入
# ═══════════════════════════════════════════════════════════════

def import_existing():
    """导入 Path 4 + Path 6 已有数据"""
    conn = init_db()
    total = 0

    # Path 4 数据集
    path4 = PROJECT_DIR / "path4_dataset" / "question_bank.json"
    if path4.exists():
        with open(path4) as f:
            bank = json.load(f)
        for q in bank:
            qid = q.get("id") or q.get("question_id", "")
            if not qid:
                qid = f"p4_{hash(q.get('question_text', ''))}"
            existing = conn.execute("SELECT 1 FROM questions WHERE id=?", (str(qid),)).fetchone()
            if existing:
                continue
            conn.execute("""
                INSERT OR IGNORE INTO questions
                (id, subject, grade, question_type, difficulty, year,
                 question_text, options, answer_text, analysis_text,
                 source, answer_locked)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                str(qid),
                q.get("subject", ""),
                q.get("grade", "高中"),
                q.get("question_type", ""),
                q.get("difficulty", ""),
                q.get("year"),
                q.get("question_text", ""),
                json.dumps(q.get("question_options", []), ensure_ascii=False),
                q.get("answer_text", ""),
                q.get("analysis", ""),
                q.get("source_url", ""),
                0 if q.get("answer_text") else 1,
            ))
            total += 1
        conn.commit()
        print(f"Path 4: 导入 {total} 道题")

    # Path 6 数据
    path6_dir = PROJECT_DIR / "path6_xkw"
    for pattern in ["*_with_answers.json", "*_questions.json"]:
        for fpath in sorted(path6_dir.glob(pattern)):
            with open(fpath) as f:
                data = json.load(f)
            n = store_questions(data, conn)
            total += n
            print(f"Path 6 ({fpath.name}): 导入 {n} 道题")

    conn.close()
    print(f"总计导入 {total} 道题")
    return total


# ═══════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="统一题目获取管线")
    sub = parser.add_subparsers(dest="cmd")

    # discover
    p = sub.add_parser("discover", help="发现试卷")
    p.add_argument("--subject", default="math")
    p.add_argument("--zone", default="exam")
    p.add_argument("--pages", type=int, default=1)

    # extract
    p = sub.add_parser("extract", help="拆卷")
    p.add_argument("--paper-id", required=True)
    p.add_argument("-o", "--output")

    # answers
    p = sub.add_parser("answers", help="补答案")
    p.add_argument("--input", required=True)
    p.add_argument("--ocr", action="store_true")

    # store
    p = sub.add_parser("store", help="入库")
    p.add_argument("--input", required=True)

    # query
    p = sub.add_parser("query", help="检索")
    p.add_argument("--subject")
    p.add_argument("--knowledge-point", "-k")
    p.add_argument("--question-type", "-t")
    p.add_argument("--difficulty", "-d")
    p.add_argument("--has-answer", "-a", action="store_true")
    p.add_argument("--limit", "-n", type=int, default=10)

    # import-existing
    sub.add_parser("import-existing", help="导入已有数据")

    # all (全流程)
    p = sub.add_parser("all", help="全流程")
    p.add_argument("--subject", default="math")
    p.add_argument("--limit", type=int, default=3)
    p.add_argument("--ocr", action="store_true")

    args = parser.parse_args()

    if args.cmd == "discover":
        papers = discover_papers(args.subject, args.zone, args.pages)
        print(json.dumps(papers, ensure_ascii=False, indent=2))

    elif args.cmd == "extract":
        output = extract_paper(args.paper_id)
        if output:
            out_path = args.output or f"paper_{args.paper_id}_questions.json"
            with open(out_path, "w") as f:
                json.dump(output, f, ensure_ascii=False, indent=2)
            print(f"已保存到 {out_path} ({len(output['results'])} 题)")

    elif args.cmd == "answers":
        data = fetch_answers(args.input, args.ocr)
        out_path = args.input.replace(".json", "_with_answers.json")
        with open(out_path, "w") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        answered = sum(1 for q in data.get("results", []) if q.get("answerText"))
        print(f"已保存到 {out_path} ({answered}/{len(data['results'])} 有答案)")

    elif args.cmd == "store":
        with open(args.input) as f:
            data = json.load(f)
        n = store_questions(data)
        print(f"入库 {n} 道题")

    elif args.cmd == "query":
        rows = query_questions(
            subject=args.subject,
            knowledge_point=args.knowledge_point,
            question_type=args.question_type,
            difficulty=args.difficulty,
            has_answer=args.has_answer,
            limit=args.limit,
        )
        for r in rows:
            print(f"[{r['question_type']}] {r['question_text'][:80]}...")
            if r.get("answer_text"):
                print(f"  答案: {r['answer_text']}")
        print(f"---\n共 {len(rows)} 条结果")

    elif args.cmd == "import-existing":
        import_existing()

    elif args.cmd == "all":
        print(f"=== 1. 发现试卷 ({args.subject}) ===")
        papers = discover_papers(args.subject, limit=args.limit)
        if not papers:
            print("未发现试卷")
            return
        total = 0
        for p in papers[:args.limit]:
            print(f"\n=== 2. 拆卷 {p['paper_id']} ===")
            output = extract_paper(p["paper_id"])
            if not output:
                continue
            print(f"  提取 {len(output['results'])} 题")
            print(f"=== 3. 补答案 ===")
            output = fetch_answers(output, use_ocr=args.ocr)
            print(f"=== 4. 入库 ===")
            n = store_questions(output)
            total += n
            print(f"  入库 {n} 题")
        print(f"\n总计入库 {total} 道题")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
