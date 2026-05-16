# 菁优网 (jyeoo.com) 网站结构分析报告

> 日期: 2026-05-15 | 方法: requests + BeautifulSoup 静态分析 (无浏览器)

## 1. 网站概况

菁优网 (jyeoo.com) 是国内大型教育资源题库网站，自称拥有 2500 万原创全解全析题库。覆盖全学科学段，支持组卷、备课、在线测评等功能。

- **首页**: https://www.jyeoo.com
- **登录页**: https://www.jyeoo.com/account/loginform (重定向自 /account/login)
- **架构**: 传统服务端渲染 + JavaScript 动态内容 (非 SPA)

## 2. 学科覆盖

### 三大学段

| 学段 | URL 后缀 | 示例 |
|------|----------|------|
| 初中 (junior) | `/{subject}/` | `/math/`, `/physics/` |
| 高中 (senior) | `/{subject}2/` | `/math2/`, `/physics2/` |
| 小学 (primary) | `/{subject}3/` | `/math3/`, `/chinese3/` |

### 已确认学科 (20个)

| 学科 | 初中 | 高中 | 小学 |
|------|------|------|------|
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

### 章节树数据 (已提取)

从 HTML 中隐藏的 `#JYE_BOOK_TREE_HOLDER` 元素提取到完整教材版本和年级树:

| 学科 | 教材版本数 | 年级/册数 |
|------|-----------|-----------|
| 初中数学 | 26 | 138 |
| 高中数学 | 14 | 131 |
| 小学数学 | 22 | 197 |
| 初中物理 | 22 | 79 |
| 高中物理 | 12 | 78 |
| 初中化学 | 24 | 51 |
| 高中化学 | 8 | 49 |
| **合计** | **128** | **723** |

数据文件: `output/knowledge_trees/chapter_trees.json`

## 3. URL 规则

### 核心页面

| 功能 | URL 模式 | 说明 |
|------|----------|------|
| 章节挑题 | `/{subject}/ques/search?f=0` | f=0 章节模式 |
| 知识点挑题 | `/{subject}/ques/search?f=1` | f=1 知识点模式 |
| 选择教材 | `/{subject}/ques/search?f=0&bk={GUID}` | bk 为教材 GUID |
| 知识点 TOP30 | `/{subject}/ques/pointtop30?f=1` | 热门知识点 |
| 试卷中心 | `/{subject}/report` | 试卷列表 |
| 试卷推荐 | `/{subject}/paper/recommend` | 推荐试卷 |
| 学科特色 | `/{subject}/ques/topicsearchques` | 特色题型 |
| 收藏挑题 | `/{subject}/favorite/userfavorite` | 需要登录 |

### 教材树数据格式

`#JYE_BOOK_TREE_HOLDER` 中每个 `<li>` 的属性:
- `ek` — 教材版本 ID (整数)
- `nm` — 名称 (如"人教版")
- `bk` — 书本 GUID (如 `f856283e-e8ab-47c9-906a-7705781aa643`)
- `gd` — 年级代码 (如 `8_1` = 八年级上)

### 未确认的 URL

以下 URL 在 JS 中被发现但需要通过浏览器验证:
- `/api/pointcard?a=...&r=...` — 知识点卡片
- `/api/searchsuggest` — 搜索建议 (返回 500)
- `/api/GetPageQuesSearchOcr` — OCR 题目搜索
- `/{subject}/paper/getcart` — 试题篮

## 4. 登录机制

### 登录页面
- URL: `https://www.jyeoo.com/account/loginform?u=%2f`
- 重定向自 `/account/login`

### 登录方式
1. **QQ OAuth 登录** — 第三方跳转
2. **微信/菁优 App 扫码** — 二维码扫码
3. **账号密码登录** — 用户名 + 密码 + 图形验证码
4. **注册** — `/account/setpassword4`

### 安全措施
- 图形验证码: `/api/captcha/{uuid}?w=210&h=36&r={random}`
- JS 加密: 页面加载 `jsencrypt.min.js` (RSA 加密库)
- 登录同意复选框 (服务条款 + 隐私政策)

## 5. 反爬策略分析

### 已知措施
1. **账号风控**: 参考项目报告 API 自动登录会导致账号封禁
2. **假数据投毒**: 后台检测到爬虫时返回不匹配的题目内容 (题目 ID 为假数据)
3. **请求频率限制**: 约 100 次/会话 (参考项目经验)
4. **JS 渲染依赖**: 题目列表和章节树完全由 JavaScript 动态加载

### 静态分析发现
- 无 Cloudflare/WAF 检测到
- robots.txt 未分析
- 静态 HTML 中无题目链接或章节明细
- 教材树数据嵌入 HTML 但章节细节需 JS 渲染

## 6. 阶段 2 待办 (需要 Playwright)

静态分析已到达极限。以下任务需要浏览器 JavaScript 渲染:

1. **登录 + Cookie 保存**: 手动 QQ 扫码 → 保存 Playwright storageState
2. **章节树动态展开**: 选择 bk GUID → JS 加载章节 → 提取完整层级
3. **题目列表抓取**: 按章节浏览 → 获取题目 ID → 翻页
4. **题目详情抓取**: 题干 + 选项 + 答案 + 解析 + 知识点标签
5. **多学科扩展**: 物理、化学

### 阶段 2 入口检查
```
/Users/song/project/STUDYAGENT/get from web/shared/chrome_freed
```
该文件存在时表示 Path 1 已释放 Chrome，可以启动 Playwright。

## 7. 输出文件清单

```
output/
├── site_structure.json              # 全站结构 (24 学科条目)
├── subject_analysis_math.json       # 初中数学页面详细分析
├── subject_analysis_math2.json      # 高中数学页面详细分析
├── subject_analysis_math3.json      # 小学数学页面详细分析
└── knowledge_trees/
    └── chapter_trees.json           # 7学科 128版本 723年级/册
```
