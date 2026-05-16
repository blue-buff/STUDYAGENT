# 六个路径的 Claude Code 提示词

---

## Path 1：组卷网 Playwright 浏览器自动化

```
## 背景
目标是为高中生构建一个按需求检索题目的 Agent。我们在 /Users/song/project/STUDYAGENT/get from web/zujuan/ 下已经 clone 并编译通过了 malyjacob/zujuan 项目（TypeScript + Playwright，MIT 许可证）。它是一个组卷网（zujuan.xkw.com）数学题目抓取 CLI 工具，知识点树搜索已验证可用。

## 已知
- 项目路径：/Users/song/project/STUDYAGENT/get from web/zujuan/
- 已验证：依赖安装、TypeScript 编译、`list --search` 知识点搜索均正常
- 未验证：扫码登录、实际题目抓取、OCR、导出
- 当前仅支持高中数学（18个知识领域，3级深度知识点树）

## 目标
1. 阅读 zujuan 项目的 CLAUDE.md 和核心源码（src/lib/scraper.ts, src/commands/scrape.ts, src/lib/browser.ts），理解抓取流程
2. 尝试启动浏览器扫码登录（zujuan start），如果无法扫码则分析原因并写替代方案
3. 至少成功抓取一个知识点的题目（zujuan scrape -k <id> -l 3）
4. 将 CLI 功能封装为一个可直接调用的函数/脚本：输入知识点ID+筛选条件→输出 JSON 题目列表
5. 分析如何扩展到物理、化学等学科（URL 规则、知识点树获取方式）
6. 在 /Users/song/project/STUDYAGENT/get from web/path1_playwright/ 下完成所有工作代码

## 交付物
- 可运行的题目抓取脚本（Python 或 Node.js）
- 抓取成功的验证截图或 JSON 输出
- 扩展到其他学科的可行性分析

TIPS：STUDYAGENT目录下还有别的ai在工作，不要干扰他们。有需要帮忙的地方停下来喊我。
```

---

## Path 2：组卷网 HTTP API 逆向

```
## 背景
目标是为高中生构建一个按需求检索题目的 Agent。组卷网（zujuan.xkw.com）是学科网旗下的在线组卷平台，高中数学题库完整。我们已有一条 Playwright 浏览器自动化路径在并行推进，本路径尝试更轻量的 HTTP API 逆向方案。

## 已知
- 参考项目：/Users/song/project/STUDYAGENT/get from web/tk-exam-paper/ （Python + requests，22⭐）
- 组卷网 URL 规则：https://zujuan.xkw.com/gzsx/zsd{知识点ID}/qt{题型码}d{难度}y{年份}o{排序}/
- 登录方式：微信扫码，tk-exam-paper 中有 QR 码登录流程代码
- 题型码：高中 单选=2701, 多选=2704, 填空=2702, 解答=2703
- 知识点树文本文件位于 /Users/song/project/STUDYAGENT/get from web/zujuan/KNOWLEDGE_TREE_HIGH.txt
- 网站需要 JS 动态渲染，但底层可能有 XHR/Fetch API

## 目标
1. 使用浏览器开发者工具或抓包工具分析组卷网的 XHR/Fetch 请求，找到题目列表和题目详情的 API 端点
2. 逆向分析请求参数中的 token/sign/加密字段生成逻辑
3. 用 Python 实现：扫码登录 → Cookie 持久化 → API 请求 → 解析结构化题目数据（非截图，而是文字内容）
4. 将 zujuan 项目的知识点树移植为 Python dict/JSON 格式
5. 实现筛选逻辑：知识点 + 题型 + 难度 + 年份 → 题目列表 JSON
6. 在 /Users/song/project/STUDYAGENT/get from web/path2_api/ 下完成所有工作代码

## 交付物
- API 逆向分析文档（端点、参数、加密方式）
- Python 可运行脚本：登录 + 搜索 + 获取题目详情
- 成功获取题目的 JSON 输出样例
- 知识点树 JSON 文件

TIPS：STUDYAGENT目录下还有别的ai在工作，不要干扰他们。有需要帮忙的地方停下来喊我。
```

---

## Path 3：菁优网 (jyeoo.com) 多学科爬虫

```
## 背景
目标是为高中生构建一个按需求检索题目的 Agent。菁优网（jyeoo.com）是国内大型教育资源题库网站，覆盖数学、物理、化学、英语等多学科，题库量可能比组卷网更大。已有组卷网路径在并行推进，本路径负责打通菁优网数据源，实现多学科覆盖。

## 已知
- 参考项目（GitHub）：pengwow/jyeoo-crawler-gui（30⭐，PyQt5+Selenium+MySQL，已归档）和 pengwow/web-crawler（14⭐，Python）
- 菁优网使用 QQ 登录，有图形验证码/反爬
- 网站有章节/知识点分类体系
- 原项目使用 PhantomJS（已废弃），需迁移到 Playwright 或 Selenium 新版
- 目标输出格式统一为：JSON { subject, grade, knowledge_points, question_type, difficulty, question_text, answer_text, analysis, source_url }

## 目标
1. 访问 jyeoo.com，手动浏览了解当前（2026年）的学科分类、章节结构、题型体系
2. 分析网站的登录机制和反爬策略（是否需要验证码、token 等）
3. 用 Playwright（推荐）或 requests 实现：登录 → 按章节/知识点浏览题目列表 → 获取题目详情（题干+答案+解析）
4. 优先打通数学学科，然后尝试物理、化学
5. 构建各学科的知识点索引
6. 输出统一 JSON 格式的题目数据
7. 在 /Users/song/project/STUDYAGENT/get from web/path3_jyeoo/ 下完成所有工作代码

## 交付物
- 菁优网网站结构分析文档（学科、章节、URL 规则）
- Python 可运行脚本：登录 + 搜索题目 + 获取详情
- 成功获取的题目 JSON 样例（尽量覆盖多个学科）
- 知识点索引文件

TIPS：STUDYAGENT目录下还有别的ai在工作，不要干扰他们。有需要帮忙的地方停下来喊我。
```

---

## Path 4：公开题库数据集 + 本地检索

```
## 背景
目标是为高中生构建一个按需求检索题目的 Agent。本路径不依赖任何特定网站爬取，而是搜集已有的公开题库数据集，构建本地检索引擎。这是法律风险最低、稳定性最高的方案，作为其他路径的兜底。

## 已知
- 已有项目都走爬虫路线，未发现有人整理过公开高中题库数据集
- 可能的数据来源：HuggingFace 数据集、GitHub 题库仓库、历年高考真题公开文本、教育开放数据平台
- 目标科目：数学、物理、化学（优先数学）
- 目标输出格式统一为：JSON { subject, grade, knowledge_points, question_type, difficulty, question_text, answer_text, analysis }

## 目标
1. 广泛搜索公开可用的中文高中数学题库数据集：
   - HuggingFace datasets（搜索 "math exam chinese" "gaokao" 等）
   - GitHub 仓库（搜索 "题库" "高中数学" "gaokao math" 等）
   - 开放数据平台（Kaggle、天池等）
   - 历年高考真题 PDF/文本
2. 对找到的数据集进行质量评估（题目数量、覆盖范围、结构化程度、时效性）
3. 选择质量最好的 1-2 个数据源，清洗并转换为统一 JSON 格式
4. 实现本地检索：按知识点关键词 + 题型 + 难度筛选题目
5. 可选：用 text embedding 实现语义相似题目推荐
6. 在 /Users/song/project/STUDYAGENT/get from web/path4_dataset/ 下完成所有工作代码

## 交付物
- 数据源调研报告（找到哪些数据集，质量如何）
- 数据清洗脚本 + 最终题库 JSON 文件（至少 100+ 道题）
- 检索脚本：输入筛选条件 → 输出匹配题目列表
- 数据集质量评估

TIPS：STUDYAGENT目录下还有别的ai在工作，不要干扰他们。有需要帮忙的地方停下来喊我。
```

---

## Path 5：搜索引擎聚合 + LLM 解析

```
## 背景
目标是为高中生构建一个按需求检索题目的 Agent。本路径不绑定任何特定题库网站，而是通过搜索引擎（Bing/Google）搜索题目，再用 LLM 从搜索结果中提取和结构化题目内容。覆盖面最广，适合作为不依赖特定网站的兜底方案。

## 已知
- 搜索 query 示例："高中数学 导数单调性 选择题 中等难度 site:zujuan.xkw.com"
- 可以用 Bing Search API、SerpAPI、或者直接 WebFetch
- LLM 需要从 HTML/文本中提取：题干、选项、答案、解析，并判断知识点和难度
- 目标输出格式统一为：JSON { subject, grade, knowledge_points, question_type, difficulty, question_text, answer_text, analysis, source_url }

## 目标
1. 调研可用的搜索 API（Bing Web Search API、SerpAPI、Brave Search API 等），对比免费额度、质量和价格
2. 设计搜索 query 模板：根据用户需求（学科+知识点+题型+难度）生成高效搜索词
3. 实现搜索 → 抓取搜索结果页面 → LLM 提取题目信息的 Pipeline
4. 测试不同 LLM（Claude、GPT-4、DeepSeek 等）在题目提取中的准确率
5. 处理常见问题：搜索结果不包含完整题目、题目格式多样、LLM 幻觉等
6. 至少成功获取 10 道不同知识点/题型的题目作为验证
7. 在 /Users/song/project/STUDYAGENT/get from web/path5_search/ 下完成所有工作代码

## 交付物
- 搜索 API 选型对比
- 可运行的 Python Pipeline：需求 → 搜索 → LLM 提取 → 结构化 JSON
- 10+ 道成功提取的题目 JSON 样例
- 准确率评估和已知问题列表

TIPS：STUDYAGENT目录下还有别的ai在工作，不要干扰他们。有需要帮忙的地方停下来喊我。
```


---

## Path 6：学科网 (xkw.com) 试卷资源 + 自动拆分

```
## 背景
目标是为高中生构建一个按需求检索题目的 Agent。学科网（xkw.com/zujuan.xkw.com）是国内最大的教育资源平台之一，覆盖全学科全学段。已有多个油猴脚本项目可以导出/打印试卷。本路径探索从试卷级资源中自动拆分为独立题目。

## 已知
- 参考项目已 clone 到本地：
  - /Users/song/project/STUDYAGENT/get from web/xkw-zujuan-script/ （34⭐，油猴脚本，2026-05-13更新）
  - /Users/song/project/STUDYAGENT/get from web/zujuan-export/ （12⭐，导出Word）
- xkw-zujuan-script 可以在试卷编辑页一键导出/打印，但优质试卷需要 PLUS 会员
- 学科网与组卷网同体系，URL 规则类似
- 目标输出格式统一为：JSON { subject, grade, knowledge_points, question_type, difficulty, question_text, answer_text, analysis, source_url }

## 目标
1. 阅读 xkw-zujuan-script 的 user.js 源码，理解其工作原理（如何与页面交互、如何提取内容）
2. 分析学科网/组卷网的试卷结构：试卷页面 URL 规则、试卷包含哪些元数据（标题、学科、年份等）
3. 探索免费可用的资源范围（哪些试卷/题目不需要 PLUS 会员）
4. 实现试卷自动拆分：将整张试卷 HTML/Word 解析为独立题目
5. 用 Playwright 自动化油猴脚本的执行流程（启动浏览器 → 注入脚本 → 导出试卷 → 拆分）
6. 尝试扩展学科覆盖（物理、化学等），分析不同学科的页面结构差异
7. 在 /Users/song/project/STUDYAGENT/get from web/path6_xkw/ 下完成所有工作代码

## 交付物
- 学科网/组卷网试卷结构分析文档
- 免费可用资源范围报告
- 试卷自动下载 + 拆分为单题的 Python 脚本
- 拆分后的题目 JSON 样例（尽量覆盖多学科）

TIPS：STUDYAGENT目录下还有别的ai在工作，不要干扰他们。有需要帮忙的地方停下来喊我。
```
