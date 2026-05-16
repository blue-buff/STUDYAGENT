#!/usr/bin/env python3
"""
整卷提取 + 拆分为单题
从 chujuan.cn 抓取整张试卷，解析为独立题目，输出 Path 1 兼容 JSON。

Usage:
  python3 extract_paper.py --paper-id 6339985
  python3 extract_paper.py --discover --xd 3 --chid 3
  python3 extract_paper.py --discover --xd 3 --chid 6 --zone exam
"""
import re
import json
import time
import os
import argparse
from datetime import datetime, timezone

import requests

BASE_URL = "https://www.chujuan.cn"
SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
})

QUESTION_TYPE_MAP = {
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

PAPER_ZONES = {
    "category": "/paper/paper-category-list",
    "sync": "/paper/paper-sync-list",
    "exam": "/paper/paper-exam-list",
}


def fetch(url, label=""):
    for attempt in range(3):
        try:
            r = SESSION.get(url, timeout=20, allow_redirects=True)
            r.encoding = r.apparent_encoding or "utf-8"
            if r.status_code == 200:
                return r.text
        except Exception as e:
            print(f"  [{label}] Error: {e}, retry {attempt+1}")
        time.sleep(1 + attempt)
    return None


def extract_json_after(html, pattern, max_forward=200000):
    """Extract balanced JSON after a pattern match."""
    m = re.search(pattern, html)
    if not m:
        return None
    return _extract_balanced(html, m.end(), max_forward)


def _extract_balanced(html, start_pos, max_forward=200000):
    """Extract balanced JSON from start_pos, finding first { or [."""
    remaining = html[start_pos:]
    first_brace = remaining.find("{")
    first_bracket = remaining.find("[")

    if first_brace == -1 and first_bracket == -1:
        return None

    if first_bracket != -1 and (first_brace == -1 or first_bracket < first_brace):
        open_c, close_c = "[", "]"
        real_start = start_pos + first_bracket
    else:
        open_c, close_c = "{", "}"
        real_start = start_pos + first_brace

    depth = 0
    i = real_start
    end_limit = min(len(html), real_start + max_forward)
    while i < end_limit:
        ch = html[i]
        if ch == open_c:
            depth += 1
        elif ch == close_c:
            depth -= 1
            if depth == 0:
                return html[real_start : i + 1]
        i += 1
    return None


def extract_json_around(html, pos, max_back=10000, max_forward=20000):
    """Extract balanced JSON object surrounding a position."""
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
    return _extract_balanced(html, start, max_forward)


def _re_find(html, pattern, default=""):
    """Find a regex pattern and return group(1) or default."""
    m = re.search(pattern, html)
    return m.group(1) if m else default


# ── Paper Discovery ──────────────────────────────────────
def discover_papers(xd=3, chid=3, zone="exam", page=1, papertype=0):
    zone_path = PAPER_ZONES.get(zone, PAPER_ZONES["exam"])
    url = f"{BASE_URL}{zone_path}?xd={xd}&chid={chid}&page={page}&papertype={papertype}"
    print(f"Discovering: {url}")

    html = fetch(url, f"discover-{zone}-p{page}")
    if not html:
        return []

    json_str = extract_json_after(html, r"result_data\s*:\s*")
    if not json_str:
        return []

    try:
        data = json.loads(json_str)
    except json.JSONDecodeError:
        return []

    return data.get("data", {}).get("list", [])


# ── Paper Metadata (regex-based, avoids malformed JSON in HTML) ─
def extract_paper_meta(paper_id):
    """Extract paper metadata from paper view page using regex."""
    url = f"{BASE_URL}/paper/view-{paper_id}.shtml"
    html = fetch(url, f"paper-{paper_id}")
    if not html:
        return None

    # Extract using the paper_detail JSON - but only the _meta part which is flat
    # The _meta fields are simple values, no nested HTML
    meta = {}
    meta["xd"] = _re_find(html, r'"xd"\s*:\s*(\d+)')
    meta["chid"] = _re_find(html, r'"chid"\s*:\s*(\d+)')
    meta["title"] = _re_find(html, r'"title"\s*:\s*"((?:[^"\\]|\\.)*)"', "").replace('\\"', '"')
    meta["paper_type"] = _re_find(html, r'"paper_type"\s*:\s*"([^"]*)"')
    meta["paper_type_id"] = _re_find(html, r'"paper_type_id"\s*:\s*(\d+)')
    meta["year"] = _re_find(html, r'"year"\s*:\s*(\d+)')
    meta["question_num"] = _re_find(html, r'"question_num"\s*:\s*(\d+)')
    meta["xdName"] = _re_find(html, r'"xdName"\s*:\s*"([^"]*)"')
    meta["xkName"] = _re_find(html, r'"xkName"\s*:\s*"([^"]*)"')
    meta["show_all_content"] = _re_find(html, r'"show_all_content"\s*:\s*(\d+)')

    # Extract provinces array
    prov_json = extract_json_after(html, r'"provinces"\s*:\s*')
    if prov_json:
        try:
            meta["provinces"] = json.loads(prov_json)
        except json.JSONDecodeError:
            meta["provinces"] = []

    # Extract tizu_sort (section titles)
    tizu_json = extract_json_after(html, r'"tizu_sort"\s*:\s*')
    if tizu_json:
        try:
            meta["tizu_sort"] = json.loads(tizu_json)
        except json.JSONDecodeError:
            meta["tizu_sort"] = []

    # Question IDs from detail links
    question_ids = list(dict.fromkeys(
        re.findall(r"/question/detail-(\d+)\.shtml", html)
    ))

    return {"paper_id": paper_id, "meta": meta, "question_ids": question_ids}


# ── Question Extraction ──────────────────────────────────
def extract_questions_from_paper_html(html):
    """Extract ALL question data from paper page HTML."""
    questions = []
    covered = set()

    for m in re.finditer(r'"question_id"\s*:\s*(\d{7,})', html):
        qid = m.group(1)
        pos = m.start()
        if any(abs(pos - p) < 200 for p in covered):
            continue

        json_str = extract_json_around(html, pos)
        if not json_str:
            # Fallback: individual page
            q = extract_question_individual(qid)
            if q:
                questions.append(q)
            continue

        covered.add(pos)
        try:
            obj = json.loads(json_str)
            if "question_id" in obj:
                questions.append(obj)
        except json.JSONDecodeError:
            q = extract_question_individual(qid)
            if q:
                questions.append(q)

    return questions


def extract_question_individual(question_id):
    """Fallback: extract from individual question detail page."""
    url = f"{BASE_URL}/question/detail-{question_id}.shtml"
    html = fetch(url, f"q-{question_id}")
    if not html:
        return None

    json_str = extract_json_after(html, r'"question_id"\s*:\s*\d{7,}')
    if not json_str:
        return None

    # Find the surrounding object
    for m in re.finditer(r'"question_id"\s*:\s*(\d{7,})', html):
        qid = m.group(1)
        obj_str = extract_json_around(html, m.start())
        if obj_str:
            try:
                return json.loads(obj_str)
            except json.JSONDecodeError:
                pass

    return None


# ── Format Conversion ────────────────────────────────────
def html_to_text(html_str):
    if not html_str:
        return ""
    text = re.sub(r"<[^>]+>", "", html_str)
    text = text.replace("&nbsp;", " ").replace("&amp;", "&")
    text = text.replace("&lt;", "<").replace("&gt;", ">")
    text = text.replace("&quot;", '"').replace("&#39;", "'")
    text = text.replace("&emsp;", "  ")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def question_to_path1_format(q, index, paper_meta, batch_ts):
    qtype = str(q.get("question_type", ""))
    type_name = QUESTION_TYPE_MAP.get(qtype, qtype)

    question_text = html_to_text(q.get("question_text") or q.get("title", ""))

    options = q.get("options")
    if options and isinstance(options, dict):
        opt_texts = []
        for label in sorted(options.keys()):
            opt_texts.append(f"{label}. {html_to_text(options[label])}")
        if opt_texts:
            question_text += "\n" + "\n".join(opt_texts)

    answer = q.get("answer", "")
    explanation = q.get("explanation", "")

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
    # Also check t_knowledge for tree-structured knowledge
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
    if not knowledge:
        klist = q.get("knowledge", [])
        if isinstance(klist, list):
            knowledge = [k for k in klist if isinstance(k, str)]

    source = q.get("question_source") or q.get("paper_title") or paper_meta.get("title", "")
    difficulty = q.get("difficult_name", "")

    return {
        "id": f"q_{batch_ts}_{index}",
        "index": str(index).zfill(3),
        "questionPath": "",
        "answerPath": "",
        "images": [],
        "source": source,
        "questionType": type_name,
        "difficulty": difficulty,
        "scoreRate": None,
        "knowledgeKeywords": knowledge,
        "questionText": question_text,
        "answerText": html_to_text(answer) if answer else "",
        "explanationUrl": explanation if explanation else "",
        "answerLocked": not bool(answer),
        "questionId": str(q.get("question_id", "")),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def paper_to_path1_output(paper_data, questions):
    meta = paper_data["meta"]
    batch_ts = str(int(time.time() * 1000))
    grade_code = str(meta.get("xd", "3"))
    chid_code = str(meta.get("chid", "3"))

    # Separate main questions from sub-questions
    main_questions = [q for q in questions if not q.get("parent_id")]
    if not main_questions:
        main_questions = questions

    options = {
        "timestamp": batch_ts,
        "knowledgeId": "",
        "knowledgePoint": "",
        "grade": XD_MAP.get(grade_code, grade_code),
        "subject": CHID_MAP.get(chid_code, chid_code),
        "type": "整卷",
        "paperType": meta.get("paper_type", ""),
        "paperId": str(paper_data["paper_id"]),
        "paperTitle": meta.get("title", ""),
        "year": int(meta.get("year", 0)) if meta.get("year") else None,
        "order": "最新",
        "source": "paper",
        "provinces": [p.get("name", "") for p in meta.get("provinces", [])],
    }

    results = [question_to_path1_format(q, i, meta, batch_ts)
               for i, q in enumerate(main_questions, 1)]

    return {"options": options, "results": results}


# ── Main ─────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="整卷提取 + 拆分为单题")
    parser.add_argument("--paper-id", help="试卷ID")
    parser.add_argument("--discover", action="store_true")
    parser.add_argument("--xd", type=int, default=3)
    parser.add_argument("--chid", type=int, default=3)
    parser.add_argument("--zone", default="exam", choices=["category", "sync", "exam"])
    parser.add_argument("--page", type=int, default=1)
    parser.add_argument("--papertype", type=int, default=0)
    parser.add_argument("--output")
    parser.add_argument("--output-dir",
                        default=os.path.dirname(os.path.abspath(__file__)))
    args = parser.parse_args()

    if args.discover:
        papers = discover_papers(
            xd=args.xd, chid=args.chid, zone=args.zone,
            page=args.page, papertype=args.papertype,
        )
        if not papers:
            print("No papers found!")
            return

        xd_name = XD_MAP.get(str(args.xd), str(args.xd))
        ch_name = CHID_MAP.get(str(args.chid), str(args.chid))
        out_path = args.output or os.path.join(
            args.output_dir,
            f"papers_{xd_name}_{ch_name}_{args.zone}.json"
        )
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(papers, f, ensure_ascii=False, indent=2)
        print(f"Saved to {out_path}")

        for p in papers[:10]:
            print(f"  [{p['id']}] {p['title'][:80]} | {p.get('type_text','')} | "
                  f"y={p.get('year','')} | q={p.get('question_num','')} | "
                  f"lock={p.get('is_lock','?')}")

    elif args.paper_id:
        print(f"Paper {args.paper_id}")
        paper_data = extract_paper_meta(args.paper_id)
        if not paper_data:
            print("Failed to extract paper metadata!")
            return

        meta = paper_data["meta"]
        print(f"  Title: {meta.get('title', 'N/A')}")
        print(f"  Subject: {meta.get('xkName','')} | "
              f"Grade: {meta.get('xdName','')} | "
              f"Type: {meta.get('paper_type','')}")

        url = f"{BASE_URL}/paper/view-{args.paper_id}.shtml"
        paper_html = fetch(url, f"paper-html-{args.paper_id}")
        if not paper_html:
            print("Failed to fetch paper page!")
            return

        questions = extract_questions_from_paper_html(paper_html)
        print(f"  Extracted {len(questions)} questions from paper page")

        output = paper_to_path1_output(paper_data, questions)
        out_path = args.output or os.path.join(
            args.output_dir, f"paper_{args.paper_id}_questions.json"
        )
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        print(f"Saved {len(output['results'])} questions to {out_path}")

        types = {}
        for r in output["results"]:
            t = r["questionType"]
            types[t] = types.get(t, 0) + 1
        print(f"  Types: {json.dumps(types, ensure_ascii=False)}")
        locked = sum(1 for r in output["results"] if r["answerLocked"])
        print(f"  Answers locked: {locked}/{len(output['results'])}")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
