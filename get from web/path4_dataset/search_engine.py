"""
本地题目检索引擎
支持：知识点关键词 + 题型 + 难度 + 科目筛选
可选：text embedding 语义相似推荐
"""

import json
import os
import re
import sys
from pathlib import Path

BASE_DIR = Path(__file__).parent
BANK_FILE = BASE_DIR / "question_bank.json"

# ── 加载题库 ──
def load_bank():
    if not BANK_FILE.exists():
        print(f"错误: 题库文件 {BANK_FILE} 不存在，请先运行 process_data.py")
        sys.exit(1)
    with open(BANK_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)


# ── 知识点关键词列表 ──
ALL_KNOWLEDGE_POINTS = [
    "集合", "函数与导数", "三角函数与解三角形", "数列", "解析几何",
    "立体几何", "概率与统计", "平面向量", "复数", "不等式",
    "排列组合与二项式", "算法", "极坐标与参数方程",
    # 物理
    "力学", "电磁学", "热学", "光学", "原子物理", "振动与波",
    # 化学
    "无机化学", "有机化学", "化学反应原理", "物质结构", "化学实验",
    "综合"
]

QUESTION_TYPES = ["单选题", "多选题", "填空题", "解答题"]
DIFFICULTIES = ["easy", "medium", "hard"]
SUBJECTS = ["数学", "物理", "化学"]


# ── 检索函数 ──
def search(questions, knowledge_points=None, question_type=None, difficulty=None,
           subject=None, keyword=None, limit=50, offset=0, with_answer_only=False):
    """
    多条件筛选题目

    Args:
        knowledge_points: 知识点列表，如 ["函数与导数", "解析几何"]
        question_type: 题型，如 "单选题"
        difficulty: 难度，如 "medium"
        subject: 科目，如 "数学"
        keyword: 题目文本关键词（模糊匹配）
        limit: 返回数量限制
        offset: 偏移量（分页）
        with_answer_only: 只返回有答案的题目

    Returns:
        (results, total_count)
    """
    results = []

    for q in questions:
        # 知识点筛选
        if knowledge_points:
            q_kps = set(q.get("knowledge_points", []))
            if not set(knowledge_points) & q_kps:
                continue

        # 题型筛选
        if question_type and q.get("question_type") != question_type:
            continue

        # 难度筛选
        if difficulty and q.get("difficulty") != difficulty:
            continue

        # 科目筛选
        if subject and q.get("subject") != subject:
            continue

        # 关键词模糊匹配
        if keyword:
            if keyword.lower() not in q.get("question_text", "").lower():
                continue

        # 只含答案
        if with_answer_only and not q.get("answer_text"):
            continue

        results.append(q)

    total = len(results)
    return results[offset:offset + limit], total


# ── 格式化输出 ──
def print_question(q, index=None):
    """打印单道题目"""
    prefix = f"[{index}] " if index is not None else ""
    print(f"{prefix}{'='*60}")
    print(f"科目: {q['subject']} | 题型: {q['question_type']} | 难度: {q['difficulty']}")
    print(f"知识点: {', '.join(q['knowledge_points'])}")
    if q.get('year'):
        print(f"年份: {q['year']} | 来源: {q['source']}")
    print(f"\n{q['question_text'][:500]}")
    if q['answer_text']:
        print(f"\n答案: {q['answer_text']}")
    if q.get('analysis'):
        print(f"解析: {q['analysis'][:300]}")
    print()


# ── 语义搜索 (基于关键词相似度，无需外部模型) ──
def semantic_search(questions, query_text, top_k=10, with_answer_only=False):
    """基于关键词重叠的简单语义搜索（不依赖embedding模型）"""
    # 提取查询中的关键词
    query_keywords = set()
    for kp, keywords in {
        "集合": ["集合", "交集", "并集", "补集", "子集"],
        "函数与导数": ["函数", "导数", "单调", "极值", "切线", "求导", "定义域", "值域", "奇偶", "周期性"],
        "三角函数与解三角形": ["三角", "正弦", "余弦", "正切", "解三角形", "sin", "cos", "tan"],
        "数列": ["数列", "等差", "等比", "通项", "求和", "递推"],
        "解析几何": ["椭圆", "双曲线", "抛物线", "直线", "圆", "距离", "相切", "离心率"],
        "立体几何": ["棱柱", "棱锥", "体积", "表面积", "二面角", "线面"],
        "概率与统计": ["概率", "期望", "方差", "分布", "抽样", "统计"],
        "平面向量": ["向量", "内积", "数量积", "共线"],
        "复数": ["复数", "虚数", "i", "模长", "共轭"],
        "不等式": ["不等式", "线性规划", "≤", "≥", "基本不等式"],
        "排列组合与二项式": ["排列", "组合", "二项式", "计数"],
        # 物理
        "力学": ["力", "运动", "牛顿", "动量", "能量", "功", "摩擦", "重力", "弹力", "加速度", "速度", "位移"],
        "电磁学": ["电场", "磁场", "电流", "电压", "电阻", "电磁", "电荷", "库仑", "安培", "法拉第", "欧姆", "电容"],
        "热学": ["热", "温度", "内能", "熵", "热力学", "分子", "气体", "压强", "体积"],
        "光学": ["光", "反射", "折射", "透镜", "干涉", "衍射", "偏振", "波长", "频率"],
        "原子物理": ["原子", "核", "量子", "光电", "波粒", "能级", "衰变", "放射性", "裂变", "聚变"],
        "振动与波": ["振动", "波", "简谐", "周期", "振幅", "频率", "共振", "声", "机械波"],
        # 化学
        "无机化学": ["元素", "金属", "非金属", "氧化物", "酸", "碱", "盐", "离子", "沉淀", "置换", "化合"],
        "有机化学": ["有机", "烃", "烷", "烯", "炔", "苯", "醇", "醛", "羧酸", "酯", "聚合物", "官能团"],
        "化学反应原理": ["反应", "平衡", "速率", "催化", "焓", "熵", "吉布斯", "氧化还原", "电解", "原电池"],
        "物质结构": ["原子结构", "分子结构", "化学键", "晶体", "轨道", "电子排布", "周期表"],
        "化学实验": ["实验", "滴定", "蒸馏", "萃取", "过滤", "试剂", "指示剂"],
    }.items():
        for kw in keywords:
            if kw.lower() in query_text.lower():
                query_keywords.add(kp)
                break

    # 计算每个题目的相关性分数
    scored = []
    for q in questions:
        if with_answer_only and not q.get("answer_text"):
            continue

        score = 0
        q_text = q["question_text"].lower()

        # 知识点重叠得分
        q_kps = set(q.get("knowledge_points", []))
        kp_overlap = len(query_keywords & q_kps)
        score += kp_overlap * 3

        # 关键词直接命中
        for word in query_text.lower().split():
            if len(word) >= 2 and word in q_text:
                score += 1

        # 完整查询字符串命中
        if query_text.lower() in q_text:
            score += 5

        if score > 0:
            scored.append((score, q))

    scored.sort(key=lambda x: -x[0])
    return [q for _, q in scored[:top_k]], len(scored)


# ── CLI 接口 ──
def interactive():
    """交互式检索"""
    print("加载题库...")
    questions = load_bank()
    print(f"已加载 {len(questions)} 道题目\n")

    while True:
        print("\n" + "=" * 60)
        print("高中数学题库检索 - 输入筛选条件 (回车跳过)")
        print("=" * 60)

        # 科目
        print(f"\n科目: {', '.join(SUBJECTS)}")
        subject = input("> ").strip()
        if subject and subject not in SUBJECTS:
            print(f"无效科目，可选: {SUBJECTS}")
            subject = None

        # 知识点
        print(f"\n知识点 (可多选，用空格分隔):")
        for i, kp in enumerate(ALL_KNOWLEDGE_POINTS):
            print(f"  [{i}] {kp}", end="")
            if (i + 1) % 4 == 0:
                print()
        print()
        kp_input = input("> ").strip()
        knowledge_points = None
        if kp_input:
            # 支持序号或名称输入
            kp_list = []
            for part in kp_input.split():
                try:
                    idx = int(part)
                    if 0 <= idx < len(ALL_KNOWLEDGE_POINTS):
                        kp_list.append(ALL_KNOWLEDGE_POINTS[idx])
                except ValueError:
                    # 按名称匹配
                    for kp in ALL_KNOWLEDGE_POINTS:
                        if part in kp:
                            kp_list.append(kp)
            knowledge_points = list(set(kp_list)) if kp_list else None

        # 题型
        print(f"\n题型: {', '.join(QUESTION_TYPES)}")
        qtype = input("> ").strip()
        if qtype and qtype not in QUESTION_TYPES:
            print(f"无效题型，可选: {QUESTION_TYPES}")
            qtype = None

        # 难度
        print(f"\n难度: {', '.join(DIFFICULTIES)}")
        difficulty = input("> ").strip()
        if difficulty and difficulty not in DIFFICULTIES:
            print(f"无效难度，可选: {DIFFICULTIES}")
            difficulty = None

        # 关键词
        print(f"\n题目关键词 (模糊匹配):")
        keyword = input("> ").strip() or None

        # 只含答案
        print(f"\n只显示有答案的题目? (y/n):")
        answer_only_input = input("> ").strip().lower()
        answer_only = answer_only_input == 'y'

        # 返回数量
        print(f"\n返回数量 (默认20):")
        limit_input = input("> ").strip()
        limit = int(limit_input) if limit_input.isdigit() else 20

        # 检索模式
        print(f"\n检索模式: [1] 精确筛选  [2] 语义搜索 (默认: 1)")
        mode = input("> ").strip()

        print(f"\n检索中...")

        if mode == '2' and keyword:
            query = keyword
            results, total = semantic_search(questions, query, top_k=limit,
                                             with_answer_only=answer_only)
            # 再应用其他筛选条件
            filtered = []
            for q in results:
                if knowledge_points:
                    q_kps = set(q.get("knowledge_points", []))
                    if not set(knowledge_points) & q_kps:
                        continue
                if qtype and q.get("question_type") != qtype:
                    continue
                if difficulty and q.get("difficulty") != difficulty:
                    continue
                if subject and q.get("subject") != subject:
                    continue
                filtered.append(q)
            results = filtered
            total = len(results)
        else:
            results, total = search(questions, knowledge_points=knowledge_points,
                                    question_type=qtype or None,
                                    difficulty=difficulty or None,
                                    subject=subject or None,
                                    keyword=keyword,
                                    limit=limit,
                                    with_answer_only=answer_only)

        print(f"\n找到 {total} 道题目，显示前 {len(results)} 道:\n")
        for i, q in enumerate(results):
            print_question(q, i + 1)

        # 知识统计
        if results:
            from collections import Counter
            kps = Counter()
            for q in results:
                for kp in q.get("knowledge_points", []):
                    kps[kp] += 1
            print(f"结果知识点分布: {dict(kps.most_common(10))}")

        print(f"\n继续检索? (回车继续 / q 退出)")
        if input("> ").strip().lower() == 'q':
            break

    print("再见!")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="高中数学题库本地检索引擎")
    parser.add_argument("--knowledge", "-k", nargs="*", help="知识点关键词")
    parser.add_argument("--type", "-t", choices=QUESTION_TYPES, help="题型")
    parser.add_argument("--difficulty", "-d", choices=DIFFICULTIES, help="难度")
    parser.add_argument("--subject", "-s", choices=SUBJECTS, help="科目")
    parser.add_argument("--keyword", "-w", help="题目文本关键词")
    parser.add_argument("--answer-only", "-a", action="store_true", help="只显示有答案的题目")
    parser.add_argument("--limit", "-n", type=int, default=20, help="返回数量")
    parser.add_argument("--semantic", action="store_true", help="使用语义搜索模式")
    parser.add_argument("--interactive", "-i", action="store_true", help="交互式检索")

    args = parser.parse_args()

    if args.interactive:
        interactive()
        return

    questions = load_bank()

    if args.semantic and args.keyword:
        results, total = semantic_search(questions, args.keyword, top_k=args.limit,
                                         with_answer_only=args.answer_only)
    else:
        results, total = search(questions,
                                knowledge_points=args.knowledge,
                                question_type=args.type,
                                difficulty=args.difficulty,
                                subject=args.subject,
                                keyword=args.keyword,
                                limit=args.limit,
                                with_answer_only=args.answer_only)

    print(f"找到 {total} 道题目，显示前 {len(results)} 道:\n")
    for i, q in enumerate(results):
        print_question(q, i + 1)

    # 导出 JSON
    output_file = BASE_DIR / "search_results.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"结果已保存到 {output_file}")


if __name__ == "__main__":
    main()
