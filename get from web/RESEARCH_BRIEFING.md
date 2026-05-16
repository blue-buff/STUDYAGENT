# 题目检索 Agent — 开源社区调查简报

> 调查日期：2026-05-15 | 目标：为高中生学习按需求推荐题目

---

## 一、开源项目调研

### 🔥 最活跃 / 最相关

| 项目 | ⭐ | 更新 | 技术栈 | 说明 |
|------|----|------|--------|------|
| **[bzyzh/xkw-zujuan-script](https://github.com/bzyzh/xkw-zujuan-script)** | 34 | 2026-05-13 | JS (Tampermonkey) | 油猴脚本，在组卷网页面一键导出/打印试卷，需 PLUS 会员 |
| **[kaibush/tk-exam-paper](https://github.com/kaibush/tk-exam-paper)** | 22 | 2026-05-04 | Python (requests+BS4+Flask+PyQt5) | 爬取组卷网自动生成试卷，含 GUI 界面 |
| **[pansoul1/zujuan-export](https://github.com/pansoul1/zujuan-export)** | 12 | 2026-05-14 | JS (Tampermonkey) | 组卷网试卷一键导出 Word（图片转 Base64、LaTeX 转 Unicode） |
| **[malyjacob/zujuan](https://github.com/malyjacob/zujuan)** | 6 | 2026-05-08 | TypeScript (Playwright+SQLite) | **🏆 最完整的命令行爬虫**：截图+OCR+导出 HTML/Markdown，知识点树浏览 |
| **[pengwow/jyeoo-crawler-gui](https://github.com/pengwow/jyeoo-crawler-gui)** | 30 | 2026-01-21 | Python (PyQt5+Selenium) | 菁优网图形化爬虫（已归档，2019年停更） |

### 其他相关项目（活跃度低）
- **pengwow/web-crawler** ⭐14 — 菁优网 Python 爬虫（2022年最后更新）
- **CodeZhangBorui/Jyeoo-Userscripts** ⭐5 — 菁优网打印处理脚本
- **wolkard/PythonReptile** ⭐4 — 组卷网试题爬虫 (Jupyter Notebook)
- **id94264/zujuan** ⭐4 — 组卷网隐藏无关元素+打印（2026-05-07 更新）
- **Frank-678/zxxk-zujuan-paper-downloader** ⭐6 — 学科网试卷下载油猴脚本

---

## 二、主流题目网站分析

| 网站 | 学科覆盖 | 技术难度 | API 公开 | 备注 |
|------|---------|---------|---------|------|
| **组卷网 (zujuan.xkw.com)** | 数学（初高中） | 中 | ❌ | 学科网旗下，微信扫码登录，JS 动态渲染 |
| **菁优网 (jyeoo.com)** | 多学科（数理化英等） | 高 | ❌ | 题库量大，反爬严格，QQ 登录 |
| **学科网 (xkw.com)** | 全学科全学段 | 中 | ❌ | 与组卷网同体系，资源最全 |
| **21世纪教育网 (21cnjy.com)** | 全学科 | 未知 | ❌ | 未发现开源爬虫 |

**共同特点**：
- 全部需要登录（微信/QQ 扫码为主）
- 全部使用 JS 动态渲染（必须用浏览器自动化或逆向 API）
- 均无公开 API
- 反爬机制以登录态检测 + 频率限制为主

---

## 三、技术方案对比

### 方案 A：浏览器自动化（Playwright/CDP）
- **代表项目**：malyjacob/zujuan
- **优点**：能处理任意 JS 渲染、截图精确、绕过大部分反爬
- **缺点**：资源消耗大、速度慢（每题需滚动+等待渲染）、需维护浏览器实例
- **适用**：对数据质量要求高、需要截图或复杂交互

### 方案 B：HTTP 请求模拟（requests + BS4）
- **代表项目**：tk-exam-paper
- **优点**：轻量快速、资源消耗低
- **缺点**：需要逆向工程 API（token 加密、签名等）、容易因网站改版失效
- **适用**：对速度要求高、网站反爬较弱

### 方案 C：用户脚本（Tampermonkey）
- **代表项目**：xkw-zujuan-script、zujuan-export
- **优点**：开发简单、利用用户已有的登录态和会员权限
- **缺点**：依赖用户手动操作浏览器、无法自动化、仍需要付费会员
- **适用**：个人使用、半自动化场景

---

## 四、本地验证结果

已 clone 并成功运行 `malyjacob/zujuan`：

```bash
# ✅ 依赖安装成功 (183 packages)
# ✅ TypeScript 编译成功
# ✅ 知识点搜索功能正常
$ node dist/index.js list --search "函数"
找到 2 个匹配结果:
  • 函数与导数 (zsd27927)
  • 三角函数与解三角形 (zsd27928)

# ✅ 知识点树浏览正常（18个高中数学顶级知识领域）
```

**已验证可用的功能**：
- SQLite 知识点数据库查询
- 知识点树层级浏览（3 级深度，涵盖全部高中数学考点）
- URL 构建逻辑（题型/难度/年份/排序参数组合）
- 配置文件管理

**尚未测试**（需要微信扫码登录 + 浏览器）：
- 浏览器启动与扫码登录
- 实际题目抓取（scrape）
- 视觉 OCR 识别
- HTML/Markdown 导出

---

## 五、推荐实施方案

### 推荐以 `malyjacob/zujuan` 为基础构建

**理由**：
1. 最新更新（2026-05-08），代码质量高，架构清晰
2. 完整的 CLI 工具链（启动→搜索→抓取→导出→浏览）
3. TypeScript 编写，类型安全，易于扩展
4. MIT 许可证，无法律风险
5. 已验证可本地编译运行

**核心数据流**：
```
用户需求（自然语言）
    → LLM 解析（科目/年级/知识点/题型/难度/数量）
    → 知识点匹配（SQLite 模糊搜索）
    → URL 构造 + Playwright 抓取
    → 题目截图/OCR → 结构化数据
    → 返回推荐结果
```

**需要扩展的方向**：
1. 支持更多学科（当前仅数学，需要扩展到物理、化学等）
2. 支持菁优网等其他题目源
3. 封装为 API/工具接口供 Agent 调用
4. 添加题目缓存/去重机制

---

## 六、关键风险

1. **登录态稳定性**：微信扫码登录可能数天到数周过期，需定期维护
2. **网站改版**：zujuan.xkw.com 页面结构变化会导致抓取失效
3. **法律合规**：需遵守目标网站的 ToS，仅用于学习交流
4. **扩展学科的成本**：不同学科的题型码、知识点树、URL 规则都不同，需要逐学科适配

---

> **下一步**：请审阅以上调查结果，我将根据您的指示进入具体实现阶段。
