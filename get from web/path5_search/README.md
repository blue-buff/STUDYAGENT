# Path 5: 搜索引擎聚合 + LLM 题目提取 Pipeline

> 不依赖特定题库网站，通过搜索引擎搜索题目，用 LLM 从搜索结果中提取和结构化题目内容。
> 覆盖面最广，适合作为兜底方案。

---

## 快速开始

```bash
# 安装依赖
pip install ddgs anthropic requests beautifulsoup4

# 快速测试（2个案例，约6分钟）
python3 run_example.py --test

# 运行全部12个案例
python3 run_example.py

# 自定义搜索
python3 run_example.py --query "高中数学 导数单调性 选择题 解析 答案"

# 仅搜索不提取（调试用）
python3 run_example.py --search-only

# 搜索+抓取但跳过LLM提取
python3 run_example.py --dry-run
```

## 文件说明

| 文件 | 用途 |
|------|------|
| `config.py` | API密钥、模型、目标站点等所有配置 |
| `models.py` | 数据模型：SearchRequest, Question, PipelineResult 等 |
| `query_templates.py` | 根据学科/知识点/题型/难度生成搜索词 |
| `search_engine.py` | 搜索后端抽象层（DuckDuckGo/Brave/Bing） |
| `fetcher.py` | 抓取网页并提取纯文本（跳过JS渲染站点） |
| `llm_extractor.py` | 调用 LLM 从文本中提取结构化题目 |
| `pipeline.py` | 总控 Pipeline：搜索→摘要提取→抓取→LLM提取 |
| `run_example.py` | 命令行入口 |
| `SEARCH_API_COMPARISON.md` | 搜索 API 选型对比 |
| `ACCURACY_REPORT.md` | 准确率评估和已知问题列表 |
| `output/` | 输出目录（JSON结果） |

## 配置

所有配置通过环境变量控制，无需修改代码：

```bash
# 搜索后端（默认 duckduckgo，可选 brave / bing）
export SEARCH_BACKEND=duckduckgo

# Brave Search API（免费 2000次/月）https://brave.com/search/api/
export BRAVE_API_KEY=BSA...

# Bing Web Search API（Azure 免费 1000次/月）
export BING_API_KEY=...

# LLM 切换（默认 claude，可选 openai）
export LLM_PROVIDER=claude

# 搜索结果数量
export SEARCH_MAX_RESULTS=10
```

## 数据流

```
用户需求 "数学 导数单调性 选择题 中等"
  │
  ├─ 1. query_templates.py 生成搜索词
  │     "已知函数f(x)" 导数单调性 选择题 中等
  │
  ├─ 2. search_engine.py 调用 DuckDuckGo 搜索
  │     返回 20-30 条结果（标题+URL+摘要）
  │
  ├─ 3. pipeline.py 从搜索摘要直接提取题目
  │     摘要中常包含完整题目内容
  │
  ├─ 4. fetcher.py 抓取可访问的页面
  │     自动跳过 JS 渲染站点（zujuan, jyeoo）
  │
  └─ 5. llm_extractor.py DeepSeek V4 Pro 提取结构化 JSON
       {
         "subject": "数学",
         "question_text": "已知函数f(x)=...",
         "question_options": ["A. ...", "B. ..."],
         "answer_text": "...",
         "analysis": "...",
         "source_url": "https://..."
       }
```

## 关键设计决策

### 为什么用题目文本模式搜索，而不是主题描述？

测试发现，搜索 `"已知函数f(x)" 导数单调性 选择题` 比搜索 `高中数学 导数单调性 题目` 效果好得多。前者直接匹配题目中出现的文字，返回的结果摘要中往往包含完整的题干。

### 为什么从搜索摘要提取题目？

中国主流教育文档站点（道客巴巴、豆丁网、百度文库）都需要登录才能查看完整内容。但搜索引擎的摘要（snippet）中常常已经包含了题目的关键信息——题干、选项、甚至答案。Pipeline 优先从摘要提取，再尝试抓取页面。

### 搜索 API 选型

| 后端 | 免费额度 | 中文质量 | 推荐场景 |
|------|---------|---------|---------|
| DuckDuckGo | 无限制 | ★★★ | 开发/测试 |
| Brave Search | 2000次/月 | ★★★★ | 小规模生产 |
| Bing Web Search | 1000次/月 | ★★★★★ | 生产环境 |

当前默认使用 DuckDuckGo（零成本零配置）。

## 输出格式

统一 JSON Schema（与其它 Path 一致）：

```json
{
  "subject": "数学",
  "grade": "高中",
  "knowledge_points": ["导数", "函数单调性"],
  "question_type": "选择题",
  "difficulty": "中等",
  "question_text": "已知函数f(x)的定义域为[0,2]，则函数f(2x-1)的定义域为（ ）",
  "question_options": ["A. [0,2]", "B. [1/2, 3/2]", "C. [-1,3]", "D. [0,3]"],
  "answer_text": "B",
  "analysis": "",
  "source_url": "https://gist.github.com/...",
  "extraction_confidence": 0.99,
  "extraction_notes": "题目、选项和答案均直接从网页提取"
}
```

## 已知限制

1. **53% 的题目缺答案/解析**：源网站不展示，需付费或登录
2. **JS 站点无法抓取**：zujuan.xkw.com、jyeoo.com 需 Playwright（已自动跳过）
3. **DuckDuckGo 结果不稳定**：中文搜索质量波动，升级到 Bing API 可改善
4. **题型匹配不完美**：30% 的题目题型与用户请求不完全一致（搜选择题得解答题）

详细分析见 `ACCURACY_REPORT.md`。
