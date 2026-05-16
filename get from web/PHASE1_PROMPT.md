```
## 任务：阶段一 — 合并组卷网三条路径，输出统一题库

### 背景

项目目标是为高中生构建一个按需求检索题目的 Agent。经过 8 条路径的并行探索，已经确认组卷网/学科网（chujuan.cn）是唯一完全打通的主数据源，三条路径（Path 1/2/6）分别打通了不同环节。你的任务是把它们合并成一条完整的端到端流水线。

### 你必须先阅读以下文件（按顺序）

1. `/Users/song/project/STUDYAGENT/CLAUDE.md` — 项目全局上下文
2. `/Users/song/project/STUDYAGENT/get from web/path6_xkw/ANALYSIS.md` — 学科网试卷结构、URL 规则、SSR 数据模型
3. `/Users/song/project/STUDYAGENT/get from web/path6_xkw/FREE_RESOURCE_REPORT.md` — 免费可用范围、与 Path 1 的互补关系
4. `/Users/song/project/STUDYAGENT/get from web/path2_api/API_DOCS.md` — 反爬绕过、登录流程、答案 API 逆向文档
5. `/Users/song/project/STUDYAGENT/get from web/path1_playwright/REPORT.md` — 登录方案、学科扩展分析
6. `/Users/song/project/STUDYAGENT/get from web/path1_playwright/SUBJECT_EXTENSION.md` — 18 学科 URL 前缀

### 你拥有的资产

**登录态（可直接使用）：**
- `/Users/song/project/STUDYAGENT/get from web/shared/storage-state.json` — Path 1 产出的 40 个 cookie，Playwright 格式
- `/Users/song/project/STUDYAGENT/get from web/path6_xkw/chujuan_storage_state.json` — Path 6 产出的 chujuan.cn 登录态
- `/Users/song/project/STUDYAGENT/get from web/path2_api/config/cookies.pkl` — Path 2 的 requests cookie（如果存在）

**参考代码（可以直接 import 或改造）：**
- `/Users/song/project/STUDYAGENT/get from web/path6_xkw/extract_with_answers.py` — SSR 拆卷 + Playwright 点答案的完整脚本
- `/Users/song/project/STUDYAGENT/get from web/path2_api/client.py` — HTTP 搜索 + 题目解析
- `/Users/song/project/STUDYAGENT/get from web/path2_api/challenge.py` — alicfw 反爬绕过
- `/Users/song/project/STUDYAGENT/get from web/path2_api/knowledge_tree.py` — 2389 知识点节点
- `/Users/song/project/STUDYAGENT/get from web/path1_playwright/scrape.py` — Playwright 截图抓取

**已有数据（可直接入库）：**
- `/Users/song/project/STUDYAGENT/get from web/path6_xkw/paper_6339985_with_answers.json` — 数学 17 题，12 道有文字答案
- `/Users/song/project/STUDYAGENT/get from web/path6_xkw/paper_6395321_questions.json` — 物理 21 题
- `/Users/song/project/STUDYAGENT/get from web/path6_xkw/paper_6229652_questions.json` — 化学 18 题
- `/Users/song/project/STUDYAGENT/get from web/path6_xkw/papers_高中_数学_exam.json` — 数学试卷列表（10 套，高考专区首页）
- `/Users/song/project/STUDYAGENT/get from web/path6_xkw/papers_高中_物理_exam.json` — 物理试卷列表（10 套）
- `/Users/song/project/STUDYAGENT/get from web/path6_xkw/papers_高中_化学_exam.json` — 化学试卷列表（10 套）
- `/Users/song/project/STUDYAGENT/get from web/path4_dataset/question_bank.json` — 理化 770 道（100% 有答案），数学 4601 道（9% 有答案）

### 目标

在 `/Users/song/project/STUDYAGENT/get from web/pipeline/` 下构建一个统一的题目获取流水线：

```
试卷发现 → SSR 拆题 → 补答案 → 统一入库
```

**具体要求：**

**模块 A — 试卷发现（`discover.py`）**
- 输入：学科（chid）、专区类型（exam/sync/备考）、年份范围、数量
- 调用 chujuan.cn 的试卷列表 API（参考 Path 6 的 URL 规则）
- 输出：试卷列表 JSON（paper_id, title, year, subject, question_count, url）

**模块 B — 拆题（`extract.py`）**
- 输入：paper_id 或试卷 URL
- 用 requests 抓取 SSR HTML，提取嵌入的 paper_detail JSON（参考 Path 6 ANALYSIS.md 第 3 节）
- 对每道题提取：question_id, question_type, difficulty, knowledge_keywords, question_text（HTML+纯文本）, options（如有）, source, explanation_url
- 输出：符合统一 Schema 的题目列表 JSON（见 CLAUDE.md）
- 不能依赖 Playwright——这个模块必须纯 HTTP

**模块 C — 补答案（`fetch_answers.py`）**
- 输入：模块 B 输出的题目列表 JSON
- 对没有 answer_text 的题目，调 Path 2 逆向出的答案 API：
  1. GET `{question_detail_page}` → 提取 `__RequestVerificationToken`
  2. POST `/zujuan-api/check_ques_parse` → 获取 key
  3. GET `imzujuan.xkw.com/getAnswerAndParse/{qid}/{bankId}/{key}?enVqdWFu=...`
- 需要处理登录态（读取 storage-state.json 或 cookies.pkl，注入 requests.Session）
- 配额感知：免费账号每日 30 次，超出后标记 pending 而非报错
- 对选择题/填空题，如果 SSR HTML 里已有答案文本则跳过 API 调用

**模块 D — 统一入库（`store.py`）**
- 输入：任意模块输出的题目 JSON
- 存入 SQLite 数据库 `pipeline/questions.db`
- 表结构：subjects, knowledge_points, questions, question_kp（多对多）
- 支持去重（同一 question_id 不重复插入）
- 支持按学科+知识点+题型+难度+年份查询

**模块 E — 已有数据导入（`import_existing.py`）**
- 把 Path 4 的理化 770 道、Path 6 已有的 56 道题导入 SQLite
- 字段映射到统一 Schema

### 关键线索

1. **域名**：组卷网已从 zujuan.xkw.com 迁移到 chujuan.cn。旧域名对部分学科有 WAF 拦截，一律用新域名。
2. **SSR 数据位置**：试卷页 HTML 的 `<script>` 标签中有 `paper_detail` 和 `FilterParams.data` 两个 JSON 对象，包含完整的题目结构。不需要浏览器就能拿到。
3. **答案 API 的 Referer 防盗链**：调 imzujuan.xkw.com 的答案接口必须带 `Referer: https://zujuan.xkw.com/11q{questionId}.html`（注意是旧域名），否则返回 403。
4. **enVqdWFu 参数**：= base64("zujuan") 的 key，value 是 user_token cookie 的值（base64 JSON: `{"userId":"...","user_token":"..."}`）。
5. **学科差异**：数学的 SSR HTML 里部分答案文本已暴露（选择题 ABCD、填空题数字），物理/化学没有。所以补答案时数学题可以少调 API。
6. **答案配额**：免费账号 30 次/天。checkQuesParse 返回 `{"key": "", "first": false}` 表示配额用完。不要在这种情况下重试。
7. **反爬 alicfw**：首次访问 zujuan.xkw.com 会触发阿里云 WAF challenge，Path 2 的 `challenge.py` 用 JSDOM 执行 challenge JS 来获取 alicfw cookie。
8. **统一 Schema**：见 CLAUDE.md 中定义的格式。所有模块的输出必须对齐。

### 测试要求（必须全部通过才能交付）

编写 `pipeline/test_pipeline.py`，包含以下测试用例：

```
test_discover_math_exam_papers    — 发现数学高考专区试卷，返回 ≥5 套
test_discover_physics_papers      — 发现物理试卷
test_extract_math_paper           — 拆解一份数学试卷，≥10 题，每题有 question_text + knowledge_keywords
test_extract_physics_paper        — 拆解一份物理试卷，验证字段完整
test_extract_output_schema         — 验证输出 JSON 符合统一 Schema（必填字段检查）
test_answer_api_with_login         — 用登录态获取一道题的答案，返回非空
test_answer_quota_exceeded_graceful — 模拟配额用完场景，验证不崩溃且标记 pending
test_store_insert                  — 插入题目到 SQLite，验证去重
test_store_query                   — 按学科+知识点+题型+难度查询，返回正确结果
test_import_path4_physics         — 导入 Path 4 理化数据，≥700 题
test_import_path6_existing        — 导入 Path 6 现有 56 题
test_end_to_end                   — 端到端：发现试卷 → 拆题 → 补答案 → 入库，全流程无异常
```

所有测试用 `pytest` 运行，数据库测试用临时文件（测试后清理）。CI 命令：`cd pipeline && python3 -m pytest test_pipeline.py -v`

### 资源约束

- 本机 8GB 内存，双核。不要同时启动多个 Playwright/Chrome 实例。
- 模块 B 纯 HTTP，不消耗额外资源。模块 C 的答案 API 是 HTTP 调用，也不需要浏览器（但如果 storage-state.json 过期需要重新扫码，调用 Path 1 的 login.py）。
- 磁盘剩余 ~13GB，SQLite 数据库预计 <100MB，无风险。
- 不要安装大型新依赖。用已有的库（requests, bs4, playwright, sqlite3）。

### 交付物检查清单

- [ ] `pipeline/discover.py` 可运行
- [ ] `pipeline/extract.py` 可运行（纯 HTTP）
- [ ] `pipeline/fetch_answers.py` 可运行
- [ ] `pipeline/store.py` 可运行
- [ ] `pipeline/import_existing.py` 可运行
- [ ] `pipeline/test_pipeline.py` 全部 12 个测试通过
- [ ] `pipeline/README.md` 记录使用方法
- [ ] `pipeline/questions.db` 至少包含 500 道题（含已有数据导入）

TIPS：STUDYAGENT 目录下之前有别的 AI 在工作（path1-path8），它们的代码在各自子目录下不要改动。你只在 `pipeline/` 下工作。有需要帮助的地方停下来喊我。
```
