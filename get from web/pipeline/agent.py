#!/usr/bin/env python3
"""
Agent 自然语言接口
将用户口语化请求解析为结构化查询参数，调用 CLI 工具执行并格式化输出。

用法:
    from agent import ask
    print(ask("我导数比较弱，找5道中等难度选择题"))

测试:
    python3 agent.py
"""

import json
import re
import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "questions.db"

from cli import search, discover, stats

# ═══════════════════════════════════════════════════════════════
# 映射表
# ═══════════════════════════════════════════════════════════════

SUBJECT_KEYWORDS = {
    "数学": ["数学", "数学题"],
    "物理": ["物理", "物理题", "理科"],
    "化学": ["化学", "化学题"],
    "生物": ["生物", "生物题"],
    "语文": ["语文", "语文题"],
    "英语": ["英语", "英文", "英语题", "英文题"],
    "历史": ["历史", "历史题"],
    "政治": ["政治", "政治题"],
    "地理": ["地理", "地理题"],
}

# 口语化难度词 → CLI 标准难度名
DIFFICULTY_MAP = {
    "容易": ["简单", "容易", "基础", "入门", "最简单", "很容易", "不难",
             "简单的", "容易的", "基础题", "送分"],
    "较易": ["较易", "比较简单", "偏简单", "稍微简单", "不太难", "比较基础"],
    "普通": ["中等", "普通", "一般", "适中", "中等难度", "正常", "中档",
             "中等的", "普通的", "一般般"],
    "较难": ["较难", "比较难", "偏难", "难一点", "有点难", "难一些", "稍难"],
    "困难": ["困难", "很难", "非常难", "最难", "特别难", "超难", "压轴",
             "高难度", "极难"],
}

TYPE_MAP = {
    "单选题": ["选择题", "单选", "单选题", "选择"],
    "多选题": ["多选题", "多选", "不定项"],
    "填空题": ["填空题", "填空"],
    "解答题": ["解答题", "大题", "解答", "计算题", "简答题", "应用题", "证明题"],
}

ACTION_KEYWORDS = {
    "discover": ["卷子", "试卷", "模拟卷", "真题卷", "套卷", "模拟题",
                 "有什么卷", "有哪些卷", "找卷", "发现卷子"],
    "stats": ["统计", "多少题", "题库", "数量", "有多少", "总共", "一共",
              "总计", "概况", "概况"],
}

# 弱项描述关键词 —— 找到这些词的位置后，取其前面 2-4 个汉字作为知识点候选
WEAKNESS_MARKERS = [
    "比较弱", "比较差", "不太好", "不太会", "不太行",
    "薄弱", "不会", "不行", "很差", "不好",
    "需要多练", "想练一下", "想做一下", "想练练",
    "要多练", "要加强", "比较薄弱",
]

# ═══════════════════════════════════════════════════════════════
# 辅助函数
# ═══════════════════════════════════════════════════════════════

def _fuzzy_match_kp(keyword: str, subject: str | None = None) -> str | None:
    """
    在 knowledge_points 表中模糊匹配知识点。
    先用 subject 限定的范围搜，找不到则跨学科搜。
    返回最佳匹配的名称，找不到返回 None。
    """
    if not DB_PATH.exists():
        return None

    conn = sqlite3.connect(DB_PATH)

    # 精确匹配
    exact = conn.execute(
        "SELECT name FROM knowledge_points WHERE name = ?", (keyword,)
    ).fetchone()
    if exact:
        conn.close()
        return exact[0]

    # 模糊匹配（先按学科限定，再全局）
    if subject:
        rows = conn.execute("""
            SELECT DISTINCT kp.name FROM knowledge_points kp
            JOIN question_kp qk ON kp.id = qk.kp_id
            JOIN questions q ON q.id = qk.question_id
            WHERE kp.name LIKE ? AND q.subject = ?
        """, (f"%{keyword}%", subject)).fetchall()
    else:
        rows = conn.execute(
            "SELECT name FROM knowledge_points WHERE name LIKE ?",
            (f"%{keyword}%",)
        ).fetchall()

    conn.close()

    if rows:
        # 返回最短的匹配名（通常最精确）—— 如 "导数" 匹配到
        # "导数的几何意义"(7字) 和 "利用导数研究函数的单调性"(12字)，
        # 选最短的更贴近用户意图
        return min(rows, key=lambda r: len(r[0]))[0]
    return None


def _infer_subject_by_kp(keyword: str) -> str | None:
    """通过知识点关键词反推学科（按该学科下匹配题目数量降序取第一）"""
    if not DB_PATH.exists():
        return None

    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("""
        SELECT q.subject, COUNT(*) AS cnt
        FROM questions q
        JOIN question_kp qk ON q.id = qk.question_id
        JOIN knowledge_points kp ON qk.kp_id = kp.id
        WHERE kp.name LIKE ?
        GROUP BY q.subject
        ORDER BY cnt DESC
    """, (f"%{keyword}%",)).fetchall()
    conn.close()

    if rows:
        return rows[0][0]
    return None


def _extract_number(text: str) -> int | None:
    """从口语文本中提取题目数量（如 '5道' '找10题' '3个'）"""
    m = re.search(r'(\d+)\s*[道题个条]', text)
    if m:
        return int(m.group(1))
    m = re.search(r'[找要前](\d+)', text)
    if m:
        return int(m.group(1))
    return None


def _find_subject(text: str) -> str | None:
    """扫描用户输入，匹配已知学科关键词"""
    # 按关键词长度降序排列，优先匹配长词（如 "政治生活" 优于 "政治"）
    all_kw = []
    for subj, keywords in SUBJECT_KEYWORDS.items():
        for kw in keywords:
            all_kw.append((kw, subj))
    all_kw.sort(key=lambda x: -len(x[0]))

    for kw, subj in all_kw:
        if kw in text:
            return subj
    return None


def _find_difficulty(text: str) -> str | None:
    for diff, keywords in DIFFICULTY_MAP.items():
        for kw in keywords:
            if kw in text:
                return diff
    return None


def _find_question_type(text: str) -> str | None:
    for qtype, keywords in TYPE_MAP.items():
        for kw in keywords:
            if kw in text:
                return qtype
    return None


def _detect_action(text: str) -> str:
    """检测用户意图：search / discover / stats"""
    for action, keywords in ACTION_KEYWORDS.items():
        for kw in keywords:
            if kw in text:
                return action
    return "search"


def _extract_knowledge_candidate(text: str) -> str | None:
    """
    从用户输入中提取可能是知识点的词语。
    策略：找到弱项描述标记（如 '比较弱'），取其前面紧邻的若干个
    中文字符作为知识点候选。
    """
    # 常见的前导词（人称/指示代词）——需要从候选开头剥离
    LEADING_WORDS = {"我", "你", "他", "她", "它", "俺", "咱",
                     "我们", "你们", "他们", "她们", "它们",
                     "这个", "那个", "这些", "那些", "这种", "那种"}

    # 第一步：弱项描述标记
    for marker in WEAKNESS_MARKERS:
        idx = text.find(marker)
        if idx > 0:
            # 取 marker 之前的文本
            prefix = text[:idx]
            # 提取末尾连续的中文字符（含标点），最多 6 个
            m = re.search(r'[一-鿿㐀-䶿]{2,6}$', prefix)
            if m:
                candidate = m.group()
                # 剥离前导的人称代词
                for lw in sorted(LEADING_WORDS, key=len, reverse=True):
                    if candidate.startswith(lw):
                        candidate = candidate[len(lw):]
                        break
                # 过滤非知识点词
                stop_words = {"帮我", "给我", "我想", "我要", "一下",
                              "比较", "非常", "特别", "有点", "一些",
                              "几个", "那种", "有没有", "能不能"}
                if candidate not in stop_words and len(candidate) >= 2:
                    return candidate
            break  # 只处理第一个匹配的标记

    # 第二步：题型词前的名词（如 "找5道函数选择题" → 函数）
    m = re.search(r'[道个]\s*([一-鿿㐀-䶿]{2,5})\s*(?:的)?\s*(?:选择|填空|解答|多选|大题)', text)
    if m:
        candidate = m.group(1)
        if len(candidate) >= 2:
            return candidate

    # 第三步："关于XX的题" 模式
    m = re.search(r'关于([一-鿿㐀-䶿]{2,5})的题', text)
    if m:
        return m.group(1)

    # 第四步："找N道XX题" / "XX题" 模式（如 "找5道导数题"）
    m = re.search(r'[道个]\s*([一-鿿㐀-䶿]{2,5})题', text)
    if m:
        return m.group(1)

    return None


# ═══════════════════════════════════════════════════════════════
# 核心函数
# ═══════════════════════════════════════════════════════════════

def parse_intent(user_input: str) -> dict:
    """
    解析用户自然语言输入为结构化查询参数。

    示例:
        "我导数比较弱，找5道中等难度的选择题练练"
        → {"subject": "数学", "knowledge_point": "利用导数研究函数的单调性",
           "question_type": "单选题", "difficulty": "普通",
           "limit": 5, "has_answer": False}

        "物理有什么卷子"
        → {"action": "discover", "subject": "物理", "zone": "exam"}

        "题库里有多少化学题"
        → {"action": "stats", "subject": "化学"}
    """
    params: dict = {
        "action": "search",
        "has_answer": False,
        "limit": 20,
    }

    # ── 1. 动作（discover / stats / search）──
    params["action"] = _detect_action(user_input)

    # ── 2. 学科 ──
    subject = _find_subject(user_input)
    if subject:
        params["subject"] = subject

    # ── 3. 知识点 ──
    kp_candidate = _extract_knowledge_candidate(user_input)

    # 排除掉已知的学科词、难度词、题型词
    if kp_candidate:
        known_words = set()
        for kw_list in SUBJECT_KEYWORDS.values():
            known_words.update(kw_list)
        for kw_list in DIFFICULTY_MAP.values():
            known_words.update(kw_list)
        for kw_list in TYPE_MAP.values():
            known_words.update(kw_list)
        if kp_candidate in known_words:
            kp_candidate = None

    if kp_candidate:
        # 去数据库做模糊匹配（仅用于验证知识点存在 & 显示名称）
        matched = _fuzzy_match_kp(kp_candidate, subject=subject)
        if matched:
            params["knowledge_point"] = kp_candidate  # 用户原词，用于 LIKE 搜索
            params["_kp_display"] = matched            # DB 全名，用于展示
            # 如果还没确定学科，通过知识点反推
            if not subject:
                inferred = _infer_subject_by_kp(kp_candidate)
                if inferred:
                    params["subject"] = inferred

    # ── 4. 难度 ──
    diff = _find_difficulty(user_input)
    if diff:
        params["difficulty"] = diff

    # ── 5. 题型 ──
    qtype = _find_question_type(user_input)
    if qtype:
        params["question_type"] = qtype

    # ── 6. 数量 ──
    n = _extract_number(user_input)
    if n is not None:
        params["limit"] = n

    # ── 7. 是否需要答案 ──
    if any(w in user_input for w in ["带答案", "有答案", "要答案", "含答案", "附答案"]):
        params["has_answer"] = True
    elif any(w in user_input for w in ["不带答案", "不要答案", "无答案", "没答案", "不看答案"]):
        params["has_answer"] = False

    # ── 8. discover 专区 ──
    if params["action"] == "discover":
        if any(w in user_input for w in ["同步", "单元", "同步练习", "随堂"]):
            params["zone"] = "sync"
        elif any(w in user_input for w in ["备考", "复习", "期末", "期中"]):
            params["zone"] = "term"
        else:
            params["zone"] = "exam"

    # ── 9. 特殊处理：如果用户只说找题没给知识点也没给学科，给点提示 ──
    if params["action"] == "search" and "knowledge_point" not in params and "subject" not in params:
        params["_hint"] = "请指定学科或知识点，例如：'找5道数学导数题' 或 '物理有什么题'"

    return params


def execute(params: dict) -> dict:
    """
    根据结构化参数调用 CLI 函数执行实际查询。

    返回统一格式:
        {"action": "search|discover|stats", "result": ..., "params": ...}
    """
    action = params.get("action", "search")

    if action == "stats":
        # 如果用户指定了学科，做一次额外查询给出该学科的数量
        result = stats()
        extra = {}
        if params.get("subject"):
            conn = sqlite3.connect(DB_PATH)
            cnt = conn.execute(
                "SELECT COUNT(*) FROM questions WHERE subject = ?",
                (params["subject"],)
            ).fetchone()[0]
            conn.close()
            extra["subject_count"] = cnt
            extra["requested_subject"] = params["subject"]
        return {"action": "stats", "result": result, "params": params, "extra": extra}

    elif action == "discover":
        result = discover(
            subject=params.get("subject", "数学"),
            zone=params.get("zone", "exam"),
        )
        return {"action": "discover", "result": result, "params": params}

    else:  # search
        # 知识点使用 LIKE 模糊匹配（用户说"导数"应匹配"利用导数研究..."等）
        kp = params.get("knowledge_point")
        if kp:
            questions = _search_by_kp(
                subject=params.get("subject"),
                knowledge_keyword=kp,
                question_type=params.get("question_type"),
                difficulty=params.get("difficulty"),
                has_answer=params.get("has_answer", False),
                limit=params.get("limit", 20),
            )
        else:
            questions = search(
                subject=params.get("subject"),
                knowledge_point=None,
                question_type=params.get("question_type"),
                difficulty=params.get("difficulty"),
                has_answer=params.get("has_answer", False),
                limit=params.get("limit", 20),
            )
        return {"action": "search", "result": questions, "params": params}


def _search_by_kp(subject=None, knowledge_keyword=None, question_type=None,
                  difficulty=None, has_answer=False, limit=20):
    """
    通过知识点关键词（LIKE 模糊匹配）搜索题目。
    与 cli.search 区别：kp.name LIKE '%keyword%' 而非 kp.name = 'exact'。
    """
    if not DB_PATH.exists():
        return []

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    sql = ("SELECT DISTINCT q.* FROM questions q"
           " JOIN question_kp qk ON q.id = qk.question_id"
           " JOIN knowledge_points kp ON qk.kp_id = kp.id")
    conds = []
    params = []

    if subject:
        conds.append("q.subject = ?"); params.append(subject)
    if knowledge_keyword:
        conds.append("kp.name LIKE ?"); params.append(f"%{knowledge_keyword}%")
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

    # Rebuild each row with knowledge_points populated (same as _row_to_dict)
    results = []
    for r in rows:
        opts_raw = r["options"] or "{}"
        try:
            opts = json.loads(opts_raw)
        except (json.JSONDecodeError, TypeError):
            opts = {}

        kp_rows = conn.execute(
            "SELECT kp.name FROM question_kp qk"
            " JOIN knowledge_points kp ON qk.kp_id = kp.id"
            " WHERE qk.question_id=?", (r["id"],)
        ).fetchall()
        kp_list = [kr[0] for kr in kp_rows]

        results.append({
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
        })

    conn.close()
    return results


def _strip_html(text: str) -> str:
    """移除 HTML/MathML 标签，返回纯文本"""
    text = re.sub(r'<[^>]+>', '', text or "")
    text = text.replace("&nbsp;", " ")
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def format_response(result: dict, user_input: str = "") -> str:
    """
    将执行结果格式化为用户友好的自然语言回复。
    """
    action = result.get("action", "search")
    params = result.get("params", {})

    # ── 提示（没给足够信息时）──
    if params.get("_hint"):
        hint = params["_hint"]
        lines = [hint]
        # 列出可用的学科
        if DB_PATH.exists():
            conn = sqlite3.connect(DB_PATH)
            subjects = conn.execute(
                "SELECT DISTINCT subject FROM questions ORDER BY subject"
            ).fetchall()
            conn.close()
            if subjects:
                lines.append("当前题库包含学科：" + "、".join(r[0] for r in subjects))
        return "\n".join(lines)

    # ── stats ──
    if action == "stats":
        s = result["result"]
        extra = result.get("extra", {})
        lines = [f"题库概况（共 {s['total']} 题）："]
        lines.append(f"  有答案：{s['with_answers']} 题（{s.get('answer_rate', 'N/A')}）")

        if extra.get("subject_count") is not None:
            lines.append(
                f"  其中 {extra['requested_subject']}：{extra['subject_count']} 题"
            )

        if s.get("subjects"):
            items = [f"{k}({v})" for k, v in s["subjects"].items()]
            lines.append(f"  学科分布：{', '.join(items)}")
        if s.get("types"):
            items = [f"{k}({v})" for k, v in s["types"].items()]
            lines.append(f"  题型分布：{', '.join(items)}")
        return "\n".join(lines)

    # ── discover ──
    if action == "discover":
        d = result["result"]
        papers = d.get("papers", [])
        subject = params.get("subject", "")
        zone_name = {"exam": "高考", "term": "备考", "sync": "同步"}
        zone_label = zone_name.get(params.get("zone", "exam"), "高考")

        if not papers:
            return f"未找到 {subject}{zone_label} 专区的试卷。"

        lines = [
            f"{subject} {zone_label}专区共 {d['total']} 套试卷，以下是前 {len(papers)} 套："
        ]
        for i, p in enumerate(papers, 1):
            lines.append(f"  {i}. [{p['paper_id']}] {p['title'][:70]}")
        return "\n".join(lines)

    # ── search ──
    questions = result["result"]

    # 构建筛选条件描述
    desc_parts = []
    if params.get("subject"):
        desc_parts.append(params["subject"])
    if params.get("knowledge_point"):
        desc_parts.append(params.get("_kp_display", params["knowledge_point"]))
    if params.get("question_type"):
        desc_parts.append(params["question_type"])
    if params.get("difficulty"):
        desc_parts.append(params["difficulty"])
    if params.get("has_answer"):
        desc_parts.append("有答案")

    desc = "、".join(desc_parts) if desc_parts else "全部"

    if not questions:
        lines = [f"未找到符合条件的题目（{desc}）。"]
        lines.append("")
        lines.append("建议：")
        lines.append("  - 检查知识点名称是否准确")
        lines.append("  - 尝试放宽筛选条件（如去掉难度/题型限制）")
        lines.append("  - 使用 '题库概况' 查看当前有哪些题目可用")
        return "\n".join(lines)

    lines = [f"已为你找到 {len(questions)} 道 {desc} 题目：", "-" * 50]

    for i, q in enumerate(questions, 1):
        kps = ", ".join(q.get("knowledge_points", [])[:3])
        diff = q.get("difficulty", "?")
        qtype = q.get("type", "")

        text = _strip_html(q.get("question_text", ""))[:120]

        lines.append(f"【第{i}题】{qtype} | 难度：{diff} | {kps}")
        lines.append(f"  {text}")

        opts = q.get("options", {})
        if opts:
            opt_parts = []
            for k, v in list(opts.items())[:4]:
                opt_parts.append(f"{k}. {_strip_html(v)[:40]}")
            lines.append(f"  选项：{'  '.join(opt_parts)}")

        ans = q.get("answer_text", "")
        if ans:
            lines.append(f"  答案：{ans}")

        src = q.get("source", "")
        if src:
            lines.append(f"  来源：{src}")

        lines.append("")

    return "\n".join(lines)


def ask(user_input: str) -> str:
    """
    一站式接口：解析意图 → 执行查询 → 格式化输出。

    用法:
        >>> from agent import ask
        >>> print(ask("我导数比较弱，找5道中等难度选择题"))
    """
    try:
        params = parse_intent(user_input)
        result = execute(params)
        return format_response(result, user_input)
    except Exception as e:
        # 开发阶段暴露完整错误方便调试
        return f"处理请求时出错：{type(e).__name__}: {e}"


# ═══════════════════════════════════════════════════════════════
# 自测
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    test_cases = [
        "我导数比较弱，找5道中等难度的选择题练练",
        "物理有什么卷子",
        "题库里有多少化学题",
        "找10道生物题，要简单的，带答案",
        "帮我找10道理科题，要简单的",
        "找5道导数题",
        "题库统计",
    ]

    for tc in test_cases:
        print("=" * 60)
        print(f"用户输入: {tc}")
        print("-" * 40)
        params = parse_intent(tc)
        print(f"解析结果: {params}")
        print("-" * 40)
        response = ask(tc)
        print(f"Agent 回复:")
        print(response)
        print()
