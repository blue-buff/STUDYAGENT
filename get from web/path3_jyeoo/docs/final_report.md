# 菁优网 (jyeoo.com) 爬虫实现报告

> 日期: 2026-05-16 | 路径: path3_jyeoo

## 一、项目概览

成功打通菁优网数据源的技术链路：完成网站结构分析、登录认证、章节树提取、题目列表定位。因免费账号每日配额限制，题目详情抓取在等待配额重置或 VIP 账号。

### 项目结构

```
path3_jyeoo/
├── config.json                     # 学科映射、URL 模板、请求参数
├── requirements.txt                # requests, bs4, lxml, playwright
├── jyeoo/                          # 核心模块包
│   ├── config.py                   # 配置加载
│   ├── session_mgr.py              # requests.Session 管理 + UA 伪装
│   ├── subject_analyzer.py         # HTML 解析 + 页面结构分析
│   ├── url_parser.py               # URL 规则提取和构建
│   ├── knowledge_tree.py           # 知识点树提取（静态+动态）
│   ├── models.py                   # 数据模型 (Subject, Question, KnowledgePoint)
│   └── utils.py                    # 日志、延迟、重试工具
├── scripts/
│   ├── 01_analyze_structure.py     # 阶段1: 静态分析全站结构
│   ├── 02_extract_knowledge_tree.py # 阶段1: 静态提取知识点树
│   ├── 03_fetch_questions.py       # 阶段1: 静态抓取题目（已确认需JS）
│   ├── 04_login.py                 # 阶段2: Playwright 登录脚本
│   ├── 05_dynamic_chapter_tree.py  # 阶段2: 动态章节树提取
│   ├── 06_scrape_questions.py      # 阶段2: 题目抓取（初版）
│   ├── 07_auth_scrape.py           # 阶段2: 认证后章节树+题目
│   ├── 08_scrape_questions.py      # 阶段2: 修正版题目抓取
│   └── parse_chapter_trees.py      # 阶段1: JYE_BOOK_TREE_HOLDER 解析
├── output/
│   ├── site_structure.json         # 全站 24 学科条目
│   ├── subject_analysis_math*.json # 数学学科页面详细分析
│   ├── knowledge_trees/
│   │   ├── chapter_trees.json      # 7学科 128版本 723年级/册
│   │   └── dynamic_chapters.json   # 4学科 2163 动态章节节点
│   ├── sample_questions/           # 题目 JSON 输出目录
│   └── auth/state.json             # Playwright 登录状态
└── docs/
    ├── site_analysis.md            # 阶段1 网站分析文档
    └── final_report.md             # 本报告
```

---

## 二、阶段 1：静态分析（requests + BeautifulSoup）

### 2.1 学科覆盖

从首页 HTML 提取到 20 个学科入口，确认为三学段结构：

| 学科 | 初中 URL | 高中 URL | 小学 URL |
|------|----------|----------|----------|
| 数学 | `/math/` | `/math2/` | `/math3/` |
| 物理 | `/physics/` | `/physics2/` | — |
| 化学 | `/chemistry/` | `/chemistry2/` | — |
| 生物 | `/bio/` | `/bio2/` | — |
| 语文 | `/chinese/` | `/chinese2/` | `/chinese3/` |
| 英语 | `/english/` | `/english2/` | `/english3/` |
| 地理 | `/geo/` | `/geo2/` | — |
| 历史 | `/history/` | `/history2/` | — |
| 政治 | `/politics/` | `/politics2/` | — |
| 科学 | `/science/` | — | — |

### 2.2 URL 规则

```
章节挑题: /{subject}/ques/search?f=0
知识点挑题: /{subject}/ques/search?f=1
选择教材:   /{subject}/ques/search?f=0&bk={GUID}
题目详情:   /{subject}/ques/detail/{question_id}
登录页:     /account/loginform
```

### 2.3 关键发现：隐藏的教材树

HTML 中存在 `<ul id="JYE_BOOK_TREE_HOLDER" style="display:none;">` 元素，包含完整的教材版本和年级树数据：

```html
<li ek="14" nm="人教版">
  <ul>
    <li bk="f856283e-..." gd="8_1" nm="八年级上"></li>
  </ul>
</li>
```

从该元素提取到 **7 学科 / 128 教材版本 / 723 年级册** 的完整索引，数据存储在 `output/knowledge_trees/chapter_trees.json`。

### 2.4 登录机制

- 登录页: `/account/loginform`（重定向自 `/account/login`）
- 三种方式: QQ OAuth / 微信扫码 / 账号密码 + 图形验证码
- 安全措施: `jsencrypt.min.js` RSA 加密 + CAPTCHA (`/api/captcha/{uuid}`)
- 题目搜索页强制登录（2026年已收紧）

---

## 三、阶段 2：动态抓取（Playwright）

### 3.1 登录认证

用户手动登录后导出 cookie，关键认证 cookie 为：
- `jy` — 加密的 session token（674 字符）
- `jyean` — 辅助认证 token
- `LF_Email` — 登录账号标识

保存为 Playwright `storage_state` 格式：`output/auth/state.json`。验证可成功访问题目搜索页。

### 3.2 动态章节树提取

使用 Playwright 访问搜索页后，`#divTree` 中 JS 渲染出完整章节树。提取结果：

| 学科 | 节点数 | 教材版本示例 |
|------|--------|-------------|
| 初中数学 | 214 | 人教版、北师大版、苏科版、浙教版等 26 种 |
| 高中数学 | 588 | 人教A版、北师大版、苏教版、湘教版等 14 种 |
| 初中物理 | 900 | 人教版、教科版、沪科版、鲁科版等 22 种 |
| 初中化学 | 461 | 人教版、鲁教版、沪教版、科粤版等 24 种 |
| **合计** | **2163** | |

数据存储在 `output/knowledge_trees/dynamic_chapters.json`。

### 3.3 题目列表定位

点击章节节点 → URL 更新为 `q={bk_GUID}~{chapter_GUID}~` → 页面加载 10 道题目链接。

```
https://www.jyeoo.com/math/ques/search?f=0&isMutiple=0
  &q=75a08844-6562-4bf5-a182-034cf7929588~4e1c9a08-d989-45c8-b89f-097da57cbd75~
  &lbs=&pd=1&mindg=0.1&maxdg=0.9
```

参数含义：

| 参数 | 含义 | 示例 |
|------|------|------|
| `q` | `{bk_GUID}~{chapter_GUID}~` | 教材~章节 |
| `pd` | 页码 | 1-100 |
| `mindg`/`maxdg` | 难度范围 | 0.1-0.9 |
| `isMutiple` | 是否为交集模式 | 0/1 |

### 3.4 题目详情格式（推断）

题目详情 URL 格式：`/{subject}/ques/detail/{question_id}`

question_id 为 base64 风格编码字符串，如 `830SXcOW7IasJlqEo11DmAfZ`。

预期页面结构（基于 HTML 选择器搜索）：

| 内容 | 预期选择器 |
|------|-----------|
| 题干 | `.fieldtip-question` / `.question-content` / `.ques-content` |
| 答案 | `.fieldtip-answer` / `.answer-content` |
| 解析 | `.fieldtip-analysis` / `.analysis-content` |
| 知识点 | `a[href*="point"]` / `.tag span` |
| 题型/难度/年份 | `span[class*="type"]` / `span[class*="diff"]` |

---

## 四、反爬分析

### 4.1 已确认措施

| 措施 | 说明 |
|------|------|
| 登录墙 | 题目搜索页强制登录（2026年新增） |
| 付费墙 | 免费账号访问题目内容被重定向到 `/Hints/Recharge` |
| 每日配额 | 免费账号约 30-100 次请求/天 |
| JS 渲染 | 章节树、题目列表完全由 JS 动态生成 |
| 假数据投毒 | 参考项目报告：后台检测后返回不匹配的题目内容 |

### 4.2 对抗策略（已实现）

- `--disable-blink-features=AutomationControlled` 隐藏自动化标识
- `navigator.webdriver` 覆盖为 `undefined`
- 真实 User-Agent + 中文 locale
- 请求间隔 2-5 秒随机延迟
- `requests.Session` 保持 cookie 一致性

---

## 五、当前阻塞与下一步

### 阻塞

**免费账号每日配额用尽**。点击章节后重定向到付费页面 `/Hints/Recharge`。题目详情页同样需要 VIP 权限。

这与参考项目（pengwow/jyeoo-crawler-gui, 2019）声称"详情页不需要登录"不同——菁优网在 2026 年已大幅收紧访问控制。

### 下一步

1. **配额重置后继续** — 等待次日配额重置，运行 `scripts/08_scrape_questions.py` 抓取题目详情
2. **VIP 账号** — 付费后可突破配额限制
3. **验证详情页选择器** — 需在配额恢复后实际打开详情页验证 CSS 选择器

### 验证命令

```bash
# 确认登录状态
python3 scripts/04_login.py

# 提取章节树（已完成）
python3 scripts/07_auth_scrape.py

# 抓取题目详情（配额恢复后）
python3 scripts/08_scrape_questions.py
```

---

## 六、统一输出格式

抓取到的题目将输出为：

```json
{
  "subject": "初中数学",
  "grade": "",
  "knowledge_points": ["有理数", "绝对值"],
  "question_type": "选择题",
  "difficulty": "中档",
  "year": "2025",
  "question_text": "已知 |a| = 3，|b| = 2...",
  "answer_text": "故选 C",
  "analysis": "本题考查绝对值的概念...",
  "options": ["A. 1", "B. -1", "C. 5", "D. ±1"],
  "source_url": "https://www.jyeoo.com/math/ques/detail/...",
  "source_id": "830SXcOW7IasJlqEo11DmAfZ",
  "chapter": "第1章 有理数"
}
```

---

## 七、产出文件清单

| 文件 | 大小 | 说明 |
|------|------|------|
| `output/knowledge_trees/chapter_trees.json` | 117 KB | 7学科 723 册静态教材树 |
| `output/knowledge_trees/dynamic_chapters.json` | — | 4学科 2163 动态章节节点 |
| `output/site_structure.json` | 7 KB | 全站学科 URL 映射 |
| `output/auth/state.json` | — | Playwright 登录状态 |
| `docs/site_analysis.md` | — | 阶段 1 分析文档 |
| `docs/final_report.md` | — | 本报告 |
