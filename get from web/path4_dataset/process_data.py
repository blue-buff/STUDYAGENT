"""
数据清洗与转换脚本
将多个数据源统一转换为标准 JSON 格式：
{ subject, grade, knowledge_points, question_type, difficulty, question_text, answer_text, analysis, source, year }

数据源：
1. AGIEval gaokao-mathqa / mathcloze / physics / chemistry (JSONL, 含答案)
2. C-Eval high_school_mathematics / physics / chemistry (HuggingFace streaming, 含答案)
3. gaokao-math-questions data.json (12K+ 题，含知识点标签，不含答案)

输出：统一格式的题库 JSON，按知识点+题型+难度可筛选
"""

import json
import os
import re
from pathlib import Path

BASE_DIR = Path(__file__).parent
OUTPUT_FILE = BASE_DIR / "question_bank.json"

# ── 知识点映射：将各数据源的标签映射到统一的知识点 ──
KNOWLEDGE_MAP = {
    # C-Eval / AGIEval 常见题目关键词 → 知识点
    "集合": ["集合", "交集", "并集", "补集", "子集"],
    "函数与导数": ["函数", "导数", "单调", "极值", "切线", "求导", "定义域", "值域", "奇偶", "周期性", "指数函数", "对数函数", "幂函数", "反函数", "复合函数"],
    "三角函数与解三角形": ["三角", "正弦", "余弦", "正切", "解三角形", "△ABC", "sin", "cos", "tan", "cot", "弧度", "诱导公式", "和差化积", "倍角", "半角"],
    "数列": ["数列", "等差", "等比", "通项", "求和", "递推", "a_n", "a_{n}"],
    "解析几何": ["椭圆", "双曲线", "抛物线", "直线", "圆", "距离", "相切", "渐近线", "离心率", "准线", "焦点", "弦", "切线", "截距"],
    "立体几何": ["棱柱", "棱锥", "圆柱", "圆锥", "球", "体积", "表面积", "二面角", "线面", "面面", "平行", "垂直", "异面", "三视图"],
    "概率与统计": ["概率", "期望", "方差", "分布", "抽样", "统计", "回归", "独立", "互斥", "二项式"],
    "平面向量": ["向量", "dot", "内积", "数量积", "共线", "基底", "坐标"],
    "复数": ["复数", "虚数", "i", "复平面", "模长", "共轭"],
    "不等式": ["不等式", "不等式组", "线性规划", "可行域", "约束条件", "≤", "≥", "基本不等式", "柯西", "排序不等式", "绝对值不等式"],
    "排列组合与二项式": ["排列", "组合", "二项式", "计数", "C(", "P(", "A("],
    "算法": ["程序框图", "流程图", "算法", "循环", "条件语句"],
    "极坐标与参数方程": ["极坐标", "参数方程", "极径", "极角", "ρ", "θ"],
    # 物理
    "力学": ["力", "运动", "牛顿", "动量", "能量", "功", "摩擦", "重力", "弹力", "加速度", "速度", "位移", "匀速", "匀加速", "自由落体", "抛体", "圆周运动", "万有引力", "机械能", "动能", "势能"],
    "电磁学": ["电场", "磁场", "电流", "电压", "电阻", "电磁", "电荷", "库仑", "安培", "法拉第", "欧姆", "电容", "电感", "洛伦兹", "左手定则", "右手定则"],
    "热学": ["热", "温度", "内能", "熵", "热力学", "分子", "气体", "压强", "体积", "理想气体", "等温", "等压"],
    "光学": ["光", "反射", "折射", "透镜", "干涉", "衍射", "偏振", "波长", "频率", "折射率", "临界角"],
    "原子物理": ["原子", "核", "量子", "光电", "波粒", "能级", "衰变", "放射性", "裂变", "聚变", "氢原子", "光子", "电子"],
    "振动与波": ["振动", "波", "简谐", "周期", "振幅", "频率", "共振", "声", "机械波", "横波", "纵波", "波长"],
    # 化学
    "无机化学": ["元素", "金属", "非金属", "氧化物", "酸", "碱", "盐", "离子", "沉淀", "置换", "化合", "分解", "复分解"],
    "有机化学": ["有机", "烃", "烷", "烯", "炔", "苯", "醇", "醛", "羧酸", "酯", "聚合物", "官能团", "同分异构", "加成", "取代", "消去"],
    "化学反应原理": ["反应", "平衡", "速率", "催化", "焓", "熵", "吉布斯", "氧化还原", "电解", "原电池", "化学平衡", "勒夏特列"],
    "物质结构": ["原子结构", "分子结构", "化学键", "晶体", "轨道", "电子排布", "周期表", "共价键", "离子键", "金属键"],
    "化学实验": ["实验", "滴定", "蒸馏", "萃取", "过滤", "试剂", "指示剂", "容量瓶", "量筒", "pH试纸", "检验"],
}

# ── 难度推断规则 ──
def infer_difficulty(question_text, question_type, year_str="", tags=None):
    """根据题目类型、年份、关键词推断难度"""
    # 高考真题默认 medium
    difficulty = "medium"

    # 选择题前几题通常是 easy
    if question_type == "单选题":
        # 集合、复数类题目通常是 easy
        if tags and any(t in ["集合", "复数", "算法"] for t in tags):
            difficulty = "easy"
        elif tags and any(t in ["函数与导数", "解析几何", "数列"] for t in tags):
            # 后面的大题通常 hard
            if "压轴" in question_text or "求证" in question_text:
                difficulty = "hard"
            else:
                difficulty = "medium"
    elif question_type == "填空题":
        difficulty = "medium"
    elif question_type in ["解答题", "多选题"]:
        # 解答题通常 medium-hard
        if "证明" in question_text or "求范围" in question_text:
            difficulty = "hard"
        else:
            difficulty = "medium"

    return difficulty


def extract_knowledge_points(question_text, tags=None):
    """从题目文本和标签中提取知识点"""
    points = set()
    text_lower = question_text.lower()

    for knowledge, keywords in KNOWLEDGE_MAP.items():
        for kw in keywords:
            if kw.lower() in text_lower:
                points.add(knowledge)
                break

    # 如果有外部标签，优先使用
    if tags:
        for tag in tags:
            tag_clean = tag.strip()
            if tag_clean in KNOWLEDGE_MAP:
                points.add(tag_clean)
            # 模糊匹配
            for knowledge in KNOWLEDGE_MAP:
                if knowledge in tag_clean or tag_clean in knowledge:
                    points.add(knowledge)

    return sorted(list(points)) if points else ["综合"]


# ── 数据源处理 ──

def process_agieval(filepath, subject, question_type_default, grade="高三"):
    """处理 AGIEval JSONL 文件"""
    questions = []
    if not os.path.exists(filepath):
        print(f"  [SKIP] {filepath} not found")
        return questions

    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            item = json.loads(line)

            # 提取选项和答案
            options = item.get('options', [])
            question_text = item.get('question', '')
            label = item.get('label', '')
            passage = item.get('passage', '')
            source_info = item.get('other', {})

            # 构建完整题目文本
            full_question = question_text
            if passage:
                full_question = passage + "\n" + question_text

            # 构建选项文本
            options_text = ""
            if options:
                options_text = "\n".join(options)
                full_question += "\n" + options_text

            # 确定题目类型
            qtype = question_type_default

            # 构建答案
            answer = label if label else ""

            # 确定难度和知识点
            knowledge_points = extract_knowledge_points(question_text + " " + options_text)
            difficulty = infer_difficulty(question_text, qtype, tags=knowledge_points)

            # 提取年份和来源
            year = ""
            source = ""
            if isinstance(source_info, dict):
                src_str = source_info.get('source', '')
                year_match = re.search(r'(\d{4})', str(src_str))
                if year_match:
                    year = year_match.group(1)
                source = src_str

            questions.append({
                "subject": subject,
                "grade": grade,
                "knowledge_points": knowledge_points,
                "question_type": qtype,
                "difficulty": difficulty,
                "question_text": full_question.strip(),
                "answer_text": answer,
                "analysis": "",
                "source": source or f"AGIEval-{subject}",
                "year": year,
            })

    return questions


def process_ceval(json_filepath, subject, grade="高三"):
    """处理已保存的 C-Eval JSON 文件"""
    questions = []
    if not os.path.exists(json_filepath):
        print(f"  [SKIP] {json_filepath} not found")
        return questions

    with open(json_filepath, 'r', encoding='utf-8') as f:
        items = json.load(f)

    for item in items:
        question_text = item.get('question', '')
        options = []
        for key in ['A', 'B', 'C', 'D']:
            if key in item and item[key]:
                options.append(f"({key}) {item[key]}")

        options_text = "\n".join(options)
        full_question = question_text + "\n" + options_text if options_text else question_text

        answer = item.get('answer', '')
        explanation = item.get('explanation', '') or ''

        knowledge_points = extract_knowledge_points(question_text + " " + options_text)
        difficulty = infer_difficulty(question_text, "单选题", tags=knowledge_points)

        questions.append({
            "subject": subject,
            "grade": grade,
            "knowledge_points": knowledge_points,
            "question_type": "单选题",
            "difficulty": difficulty,
            "question_text": full_question.strip(),
            "answer_text": answer,
            "analysis": explanation,
            "source": f"C-Eval-{subject}",
            "year": "",
        })

    return questions


def process_gaokao_math(json_filepath):
    """处理 gaokao-math-questions data.json (无答案，含知识点标签)"""
    questions = []
    if not os.path.exists(json_filepath):
        print(f"  [SKIP] {json_filepath} not found")
        return questions

    with open(json_filepath, 'r', encoding='utf-8') as f:
        items = json.load(f)

    # 限制数量避免过大
    max_questions = 5000
    for item in items[:max_questions]:
        content = item.get('content', '')
        qtype = item.get('type', '单选题')
        choices = item.get('choices', {})
        year = item.get('year', '')
        source = item.get('source', '')
        tags = item.get('tags', [])

        # 构建完整题目
        full_question = content
        if choices:
            choice_lines = []
            for key, val in choices.items():
                choice_lines.append(f"{key}. {val}")
            full_question += "\n" + "\n".join(choice_lines)

        knowledge_points = extract_knowledge_points(content, tags=tags)
        difficulty = infer_difficulty(content, qtype, year, tags=knowledge_points)

        questions.append({
            "subject": "数学",
            "grade": "高三",
            "knowledge_points": knowledge_points,
            "question_type": qtype,
            "difficulty": difficulty,
            "question_text": full_question.strip(),
            "answer_text": "",  # 该数据源无答案
            "analysis": "",
            "source": source,
            "year": year,
        })

    return questions


# ── 主流程 ──

def main():
    all_questions = []
    stats = {}

    # 1. AGIEval 数据 (含答案)
    print("=" * 60)
    print("处理 AGIEval 数据...")
    agieval_sources = [
        ("agieval_mathqa.jsonl", "数学", "单选题"),
        ("agieval_gaokao-mathcloze.jsonl", "数学", "填空题"),
        ("agieval_gaokao-physics.jsonl", "物理", "单选题"),
        ("agieval_gaokao-chemistry.jsonl", "化学", "单选题"),
    ]
    for filename, subject, qtype in agieval_sources:
        filepath = BASE_DIR / filename
        qs = process_agieval(str(filepath), subject, qtype)
        print(f"  {filename}: {len(qs)} questions")
        stats[f"AGIEval-{filename}"] = len(qs)
        all_questions.extend(qs)

    # 2. C-Eval 数据 (含答案)
    print("\n处理 C-Eval 数据...")
    ceval_sources = [
        ("ceval_math_raw.json", "数学"),
        ("ceval_physics_raw.json", "物理"),
        ("ceval_chemistry_raw.json", "化学"),
    ]
    for filename, subject in ceval_sources:
        filepath = BASE_DIR / filename
        qs = process_ceval(str(filepath), subject)
        print(f"  {filename}: {len(qs)} questions")
        stats[f"C-Eval-{filename}"] = len(qs)
        all_questions.extend(qs)

    # 3. gaokao-math-questions (无答案，含标签)
    print("\n处理 gaokao-math-questions...")
    gmq_path = BASE_DIR / "gaokao-math-questions" / "data.json"
    qs = process_gaokao_math(str(gmq_path))
    print(f"  data.json: {len(qs)} questions (sampled from 12335)")
    stats["gaokao-math-questions"] = len(qs)
    all_questions.extend(qs)

    # ── 去重 ──
    print(f"\n去重前: {len(all_questions)} questions")
    seen = set()
    deduped = []
    for q in all_questions:
        # 用题目文本的前 100 字符作为去重 key
        key = q["question_text"][:100].strip()
        if key not in seen:
            seen.add(key)
            deduped.append(q)
        else:
            # 合并知识点
            for existing in deduped:
                if existing["question_text"][:100].strip() == key:
                    existing_kp = set(existing["knowledge_points"])
                    new_kp = set(q["knowledge_points"])
                    existing["knowledge_points"] = sorted(list(existing_kp | new_kp))
                    # 保留有答案的版本
                    if not existing["answer_text"] and q["answer_text"]:
                        existing["answer_text"] = q["answer_text"]
                    break

    print(f"去重后: {len(deduped)} questions")

    # ── 统计 ──
    from collections import Counter
    subjects = Counter(q["subject"] for q in deduped)
    types = Counter(q["question_type"] for q in deduped)
    difficulties = Counter(q["difficulty"] for q in deduped)
    has_answer = sum(1 for q in deduped if q["answer_text"])

    print(f"\n统计:")
    print(f"  科目分布: {dict(subjects)}")
    print(f"  题型分布: {dict(types)}")
    print(f"  难度分布: {dict(difficulties)}")
    print(f"  含答案: {has_answer}/{len(deduped)} ({100*has_answer/len(deduped):.1f}%)")

    # ── 输出 ──
    print(f"\n写入 {OUTPUT_FILE}...")
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(deduped, f, ensure_ascii=False, indent=2)

    file_size = os.path.getsize(OUTPUT_FILE) / 1024 / 1024
    print(f"完成! 文件大小: {file_size:.1f} MB")

    # ── 保存统计 ──
    stats["total_before_dedup"] = len(all_questions)
    stats["total_after_dedup"] = len(deduped)
    stats["with_answer"] = has_answer
    stats["subjects"] = dict(subjects)
    stats["types"] = dict(types)
    stats["difficulties"] = dict(difficulties)

    with open(BASE_DIR / "dataset_stats.json", 'w', encoding='utf-8') as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)

    print(f"统计已保存到 dataset_stats.json")

    # ── 生成按知识点的子索引 ──
    kp_index = {}
    for q in deduped:
        for kp in q["knowledge_points"]:
            if kp not in kp_index:
                kp_index[kp] = []
            kp_index[kp].append({
                "subject": q["subject"],
                "question_type": q["question_type"],
                "difficulty": q["difficulty"],
                "question_text": q["question_text"][:200],
                "answer_text": q["answer_text"],
            })

    with open(BASE_DIR / "knowledge_point_index.json", 'w', encoding='utf-8') as f:
        json.dump(kp_index, f, ensure_ascii=False, indent=2)

    for kp, items in sorted(kp_index.items(), key=lambda x: -len(x[1])):
        print(f"  {kp}: {len(items)} 题")


if __name__ == "__main__":
    main()
