# 公开高中数学题库数据集调研报告

## 概述

为高中数学知识点检索 Agent 搜集公开可用题库数据集，不走爬虫路线，法律风险低、稳定性高。

调研时间：2026-05-15

## 数据源调研结果

### 1. C-Eval (ceval/ceval-exam) ⭐⭐⭐⭐⭐

- **来源**: HuggingFace [`ceval/ceval-exam`](https://huggingface.co/datasets/ceval/ceval-exam)
- **规模**: 13,948 道多选题，覆盖 52 个学科
- **高中相关**:
  - `high_school_mathematics`: 189 题 (test+val+dev)
  - `high_school_physics`: 199 题
  - `high_school_chemistry`: 196 题
- **字段**: id, question, A/B/C/D, answer, explanation
- **优点**: 含答案，题目质量高（来自中国考试/教科书），加载方式支持 HuggingFace streaming 免落盘
- **缺点**: 题量偏少（189 道数学），无知识点标签，无年份/来源，explanation 字段多为空
- **访问方式**: `load_dataset('ceval/ceval-exam', 'high_school_mathematics', split='test', streaming=True)`

### 2. AGIEval (Microsoft 基准数据集) ⭐⭐⭐⭐

- **来源**: GitHub [`ruixiangcui/AGIEval`](https://github.com/ruixiangcui/AGIEval) / HuggingFace `hails/agieval-gaokao-*`
- **规模**:
  - `gaokao-mathqa` (数学选择题): 351 题
  - `gaokao-mathcloze` (数学填空题): 118 题
  - `gaokao-physics` (物理): 200 题
  - `gaokao-chemistry` (化学): 207 题
- **字段**: question, options, label (答案), other (含 source 如"2021年浙江卷—数学")
- **优点**: 含答案 + 年份来源，题型多样（单选+填空），直接可用的 JSONL 格式
- **缺点**: 题量有限（数学共 469 题），无知识点标签
- **文件大小**: ~400KB (JSONL)

### 3. aiguoran/gaokao-math-questions ⭐⭐⭐

- **来源**: GitHub [`aiguoran/gaokao-math-questions`](https://github.com/aiguoran/gaokao-math-questions)
- **规模**: 12,335 道数学题 (data.json, 6.5MB)
- **字段**: content (含 LaTeX), type (单选题/填空题/解答题/多选题), choices, year (2001-2025), source (68个来源), no, tags (13个知识点标签)
- **优点**: 题量最大，年份跨度广 (2001-2025)，含知识点标签（解析几何、函数与导数、立体几何等），含试卷来源
- **缺点**: **无答案**，题目文本含 LaTeX 公式(需渲染)
- **题型分布**: 单选题 5590, 填空题 3443, 解答题 3259, 多选题 43

### 4. 其他发现

| 数据源 | 描述 | 评估 |
|--------|------|------|
| weitianwen/cmath (HuggingFace) | 1.7K 小学数学应用题 | ❌ 小学级别，不适用 |
| Advanced/Discrete/Probability (C-Eval) | 大学级别数学 | ❌ 超出高中范围 |
| middle_school_mathematics (C-Eval) | 177 道初中数学 | ❌ 超出可选用(可作为基础题) |
| malyjacob/zujuan (GitHub) | 组卷网爬虫 | ❌ 走爬虫路线(path3已处理) |

## 质量评估

| 维度 | C-Eval | AGIEval | gaokao-math-questions |
|------|--------|---------|----------------------|
| 题目数量 | ★★☆ (189 数学) | ★★★ (469 数学) | ★★★★★ (12335 数学) |
| 答案完整性 | ★★★★★ (全部有) | ★★★★★ (全部有) | ☆ (无) |
| 知识点标签 | ☆ (无) | ☆ (无) | ★★★★★ (13类标签) |
| 年份来源 | ☆ (无) | ★★★★ (2021为主) | ★★★★★ (2001-2025) |
| 题型多样性 | ★★☆ (仅单选) | ★★★ (单选+填空) | ★★★★★ (4种题型) |
| 时效性 | ★★★ | ★★★ | ★★★★★ (至2025) |
| 结构化程度 | ★★★★★ | ★★★★★ | ★★★★★ |

### 最终选型

组合使用全部 3 个数据源：

- **AGIEval + C-Eval**: 提供有答案的题目作为"黄金标准"（约 1,300 道含答案）
- **gaokao-math-questions**: 提供大规模题库框架 + 知识点标签 + 年份来源元数据
- **互补策略**: 有答案的题目用于答案验证和练习，无答案的题目用于知识点检索和题型训练

## 最终数据集

### 文件清单

```
path4_dataset/
├── question_bank.json          # 统一题库 (5,371题, 3.4MB)
├── knowledge_point_index.json  # 知识点索引 (6MB)
├── dataset_stats.json          # 统计信息
├── process_data.py             # 数据清洗脚本
├── search_engine.py            # 检索引擎
└── gaokao-math-questions/      # 原始数据源 (仅 data.json)
    └── data.json               # 12,335 道原题 (6.5MB)
```

### 统一格式

```json
{
  "subject": "数学",
  "grade": "高三",
  "knowledge_points": ["解析几何", "函数与导数"],
  "question_type": "单选题",
  "difficulty": "medium",
  "question_text": "若椭圆...",
  "answer_text": "C",
  "analysis": "",
  "source": "2021年浙江卷—数学",
  "year": "2021"
}
```

### 统计数据

| 维度 | 数值 |
|------|------|
| 总题目数 | 5,371 |
| 数学 | 4,601 (85.6%) |
| 物理 | 393 (7.3%) |
| 化学 | 377 (7.0%) |
| 含答案 | 1,306 (24.3%) |
| 单选/填空/解答 | 3,166 / 1,138 / 1,067 |
| Easy/Medium/Hard | 1,929 / 3,179 / 263 |
| 年份范围 | 2001 - 2025 |
| 知识点类别 | 25 个 |

### 知识点分布 (Top 10)

1. 解析几何: 1,422 题
2. 函数与导数: 1,198 题
3. 三角函数与解三角形: 872 题
4. 立体几何: 863 题
5. 平面向量: 849 题
6. 数列: 451 题
7. 概率与统计: 397 题
8. 力学: 388 题
9. 排列组合与二项式: 311 题
10. 不等式: 300 题

## 检索引擎

### 使用方式

```bash
# 命令行模式 - 按知识点+题型+难度筛选
python3 search_engine.py -s 数学 -k 解析几何 -t 单选题 -d medium -a -n 10

# 语义搜索模式 - 用自然语言搜索相似题目
python3 search_engine.py --semantic -w "求椭圆的离心率取值范围" -a -n 5

# 交互式模式
python3 search_engine.py -i
```

### 功能

- **精确筛选**: 知识点 + 题型 + 难度 + 科目 + 关键词模糊匹配
- **语义搜索**: 基于关键词重叠的相似度排序
- **答案过滤**: 可只显示有答案的题目
- **结果导出**: 自动保存为 `search_results.json`
- **分页**: 支持 offset/limit

## 局限性与改进方向

| 局限 | 说明 | 改进方向 |
|------|------|---------|
| 答案覆盖率低 | 仅 24.3% 题目含答案 | 用 LLM 批量生成答案 (成本高)；或对接更多含答案数据源 |
| 知识点提取粗糙 | 基于关键词匹配，有误标 | 用分类模型自动标注知识点 |
| 难度评估简单 | 基于规则推断 | 基于题目实际统计数据校准 |
| 物理/化学题量少 | 不到 800 道 | 补充更多物理/化学数据源 |
| 无 real embedding | 语义搜索基于关键词重叠 | 接入 BGE/Text2Vec 中文 embedding 模型 |
| LaTeX 公式 | 题目文本含 LaTeX 需要渲染 | 前端渲染 MathJax/KaTeX |

## 磁盘使用

| 项目 | 大小 |
|------|------|
| question_bank.json | 3.4 MB |
| knowledge_point_index.json | 6.0 MB |
| gaokao-math-questions/data.json | 6.5 MB |
| 脚本文件 | 32 KB |
| **总计** | **~16 MB** |

控制在 100MB 以内，远低于 2GB 限制。
