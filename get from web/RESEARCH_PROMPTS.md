# 阶段二：三个并行研究方向

---

## 方向 A：验证 Playwright 点击路径是否限配额

```
## 任务

验证一个关键假设：组卷网的答案 API 限 30 次/天，但 Path 6 用 Playwright 模拟点击"显示答案解析"按钮从 DOM 提取答案，这条浏览器交互路径是否受同一配额限制？

## 背景

- 组卷网(chujuan.cn)免费账号每日可通过 API 查看 30 道题目的答案
- Path 6 发现另一条路径：Playwright 打开试卷页 → 点击"显示答案解析"按钮 → DOM 渲染出答案文字 → 直接从 DOM 提取文本
- 这条浏览器路径可能不受 30 次限制（因为走的是页面交互而非 API 调用）
- 也可能受限制（后端同一个配额计数器）

## 已有资产

- 登录态：`/Users/song/project/STUDYAGENT/get from web/shared/storage-state.json`（Playwright 格式，5月15日生成，需验证是否仍有效）
- 参考代码：`/Users/song/project/STUDYAGENT/get from web/path6_xkw/extract_with_answers.py`（第 212-238 行是点击逻辑）
- 参考代码：`/Users/song/project/STUDYAGENT/get from web/path1_playwright/scrape.py`（Playwright 截图抓取）
- 关键文档：`/Users/song/project/STUDYAGENT/get from web/path2_api/API_DOCS.md`（答案 API 逆向文档）

## 实验设计

### 实验 1：API 路径基线
1. 用 Path 2 的 checkQuesParse API 连续调 35 次，记录第几次开始返回 `{"key":""}`
2. 确认 30 次限制的准确性

### 实验 2：Playwright 点击路径
1. 用 Playwright 登录（复用 storage-state.json）
2. 连续打开 40 道不同的题目详情页，每道点击"显示答案解析"
3. 记录每道题是否能从 DOM 提取到 answer_text
4. 如果 40 次全部成功 → Playwright 路径不限配额 ✅
5. 如果第 N 次开始失败 → 受限，记录 N 的值

### 实验 3（如果实验 2 也受限）：多账号方案
- 注册第二个免费账号，确认不同账号的配额独立
- 如果独立，测试账号切换的自动化可行性

## 产出

- 实验数据（几次后受限，受限于哪个环节）
- 结论：Playwright 路径是否可绕过配额限制
- 如果可绕过：修改 `fetch_answers.py` 的方案建议
- 在 `/Users/song/project/STUDYAGENT/get from web/research_a/` 下工作

TIPS：STUDYAGENT 目录下还有别的 AI 在工作，不要干扰他们。如果 storage-state.json 过期，告诉我就行。
```

---

## 方向 B：解析图 OCR 提取答案（使用 Kimi CLI 图像理解）

```
## 任务

验证：所有题目都有免费的解析图 URL（webshot.zujuan.com/...ex.png），用 Kimi 的视觉能力读图提取答案文字。如果准确率高，直接绕过答案 API 的配额限制。

## 背景

- Path 6 发现所有题目（数理化 56 道）都有 `explanation_url`，指向 webshot.zujuan.com 的解析图 JPEG
- 这些图片通常包含：答案 + 详细解析过程 + 公式推导
- URL 示例：`https://webshot.zujuan.com/q/.../68956362ex.png?hash=...&sign=...`
- 图片是免费的，不限量
- 关键问题：用 LLM Vision 读图提取的答案准确率能否达到可用水平？

## Kimi CLI 非交互模式

```bash
# 基本用法
kimi --print -p "你的提示词"

# 图片理解（Kimi 支持直接传图片）
kimi --print -p "提取这张解析图中的答案和关键步骤" image.png

# 极简输出（只输出最终文本，适合脚本）
kimi --quiet -p "提取答案" image.png

# 管道输入
echo "解析图中展示了什么？" | kimi --print image.png
```

## 实验设计

### 步骤 1：获取测试样本
从 Path 6 已有的数据中提取解析图 URL：
```bash
python3 -c "
import json
d = json.load(open('/Users/song/project/STUDYAGENT/get from web/path6_xkw/paper_6339985_with_answers.json'))
for q in d['results'][:10]:
    url = q.get('explanationUrl', '')
    if url:
        print(f\"{q['questionId']}: {url}\")
"
```

### 步骤 2：下载 5-10 张解析图
```bash
curl -o test_images/q{id}.jpg "{url}"
```
注意：解析图可能需要 Referer 头（参考 Path 2 API_DOCS.md 的防盗链说明）

### 步骤 3：逐张提取答案
对每张图用 Kimi CLI 提取：
```bash
kimi --quiet -p "提取这张数学解析图中标注的正确答案（选项字母或数值），只输出答案，不要解释。" test_images/q1.jpg
```

### 步骤 4：对比准确率
- 将 Path 6 已有答案的 12 道数学题作为 ground truth
- 统计 Kimi 提取的答案与 ground truth 的匹配率
- 记录哪些题型准确率高（选择题选项 vs 填空题数值 vs 解答题步骤）

### 步骤 5（如果可行）：成本估算
- 单张图的 token 消耗
- 1000 道题的总成本

## 产出

- 10 张解析图样本
- 每张图的 Kimi 提取结果 vs 正确结果对比表
- 准确率报告（按题型拆分）
- 成本估算
- 结论：OCR 路径是否可行
- 在 `/Users/song/project/STUDYAGENT/get from web/research_b/` 下工作

TIPS：图片下载时注意 Referer 防盗链。如果 Kimi CLI 不直接支持图片路径，尝试 base64 编码或先确认 Kimi 的图片输入方式。
```

---

## 方向 C：登录态保鲜 + Cookie 桥接

```
## 任务

解决两个实际问题：
1. storage-state.json 过期后怎么续命（能不能自动化）
2. Path 1 的 Playwright cookie 和 Path 2 的 requests cookie 怎么互转

## 背景

### 问题 1：登录态保鲜
- storage-state.json 是 5 月 15 日扫码生成的
- 组卷网的登录态一般是数天到数周过期
- 当前过期后需要人工重新扫码
- 如果流水线因登录态过期中断，自动化程度大打折扣

### 问题 2：Cookie 跨路径共享
- Path 1 产出 storage-state.json（Playwright 格式，JSON 数组）
- Path 2 需要 requests.Session cookie（Python http.cookiejar 或 dict 格式）
- 当前两条路径的 cookie 不能直接互通
- 需要搞清楚哪些 cookie 是关键鉴权字段

## 已有资产

- Playwright cookie：`/Users/song/project/STUDYAGENT/get from web/shared/storage-state.json`
- Path 2 config cookie：`/Users/song/project/STUDYAGENT/get from web/path2_api/config/cookies.pkl`（如果存在）
- Path 6 cookie：`/Users/song/project/STUDYAGENT/get from web/path6_xkw/chujuan_storage_state.json`
- Path 1 登录脚本：`/Users/song/project/STUDYAGENT/get from web/path1_playwright/login.py`
- Path 2 登录脚本：`/Users/song/project/STUDYAGENT/get from web/path2_api/login.py`
- 关键文档：`/Users/song/project/STUDYAGENT/get from web/path2_api/API_DOCS.md`（第 5 节列出了所需 cookie 列表）

## 实验设计

### 实验 1：识别关键鉴权 cookie
1. 读取 storage-state.json，列出所有 cookie 的 name + domain
2. 逐个剔除 cookie，发请求验证哪个 cookie 是真正决定认证的
3. 确认 Path 2 API_DOCS 中列的 `userId`, `user_token`, `zujuan-core`, `UT1` 是否都在

### 实验 2：Cookie 格式转换
1. 写转换函数：Playwright cookie JSON → requests.Session cookies
2. 用转换后的 Session 发请求，验证是否能通过认证
3. 如果成功，产出 `cookie_bridge.py`

### 实验 3：登录态保鲜测试
1. 用 requests.Session 带 cookie 每 30 分钟发一次请求到 chujuan.cn 首页
2. 检测响应是否包含重定向到登录页（说明过期了）
3. 如果长期活跃能延长有效期，记录最长的保鲜时间

### 实验 4：自动化重登可行性
1. 研究 Path 1 的 login.py 是否有可自动化的环节
2. 扫码二维码后，微信回调是否需要人工确认
3. 评估全自动重登的可行性（结论可能是"不可行，必须人工"）

## 产出

- 关键鉴权 cookie 清单
- `cookie_bridge.py`（Playwright ↔ requests 互转）
- 登录态保鲜方案（定期心跳 or 过期通知）
- 自动化重登可行性评估
- 在 `/Users/song/project/STUDYAGENT/get from web/research_c/` 下工作

TIPS：STUDYAGENT 目录下还有别的 AI 在工作，不要干扰他们。不要反复调 API 导致被封号。如果 storage-state.json 已经过期，直接告诉我结论（"需要重新扫码"），然后基于新的扫码做续命测试。
```

---

## 启动命令

三个会话并行启动，各自在独立目录下工作：

```bash
# 会话 A
mkdir -p "/Users/song/project/STUDYAGENT/get from web/research_a"

# 会话 B
mkdir -p "/Users/song/project/STUDYAGENT/get from web/research_b"
mkdir -p "/Users/song/project/STUDYAGENT/get from web/research_b/test_images"

# 会话 C
mkdir -p "/Users/song/project/STUDYAGENT/get from web/research_c"
```
