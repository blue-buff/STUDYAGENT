# Path 7: 作业帮 / 猿题库 App API 逆向 — 可行性调研报告

**日期**: 2026-05-15
**状态**: 调研完成，等待决策

---

## 1. 核心发现

### 1.1 作业帮 (Zuoyebang)

| 维度 | 评估 |
|------|------|
| **wenda API** (问答平台) | 可行 — 有公开 Python 实现，API 仍在线 |
| **主 App API** (拍照搜题) | 可行但耗时长 — 需完整 APK 逆向 |
| **已知公开项目** | 6 个 GitHub 仓库，其中 1 个 Python 抓取工具可用 |
| **鉴权方式** | 双 MD5 + Token（wenda）；主 App 未知 |
| **HTTPS 证书绑定** | 服务端无；App 端很可能有（需 Frida 绕过） |

#### 已确认在线的 API 端点

```
POST https://wenda.zuoyebang.com/commitui/session/login    → 登录获取 token (HTTP 200 ✓)
POST https://wenda.zuoyebang.com/rui/ask/taskpool          → 获取题目池 (HTTP 200 ✓)
POST https://wenda.zuoyebang.com/commitui/question/getitem → 领取题目
```

**关键限制**：wenda API 是**人工答疑平台**（老师抢题回答），不是主 App 的拍照搜题 API。返回的题目数据可能不如主 API 规范，知识标签/难度分级可能缺失。

#### 鉴权流程

```
登录: userName + md5(md5(password)) → 获取 token
请求: token 作为 form 字段随所有 POST 请求
签名: businessId = md5(timestamp)，其他签名字段为空字符串即可
```

#### 参考源码

- `github.com/binganao/zuoyebang` — Python 抢题脚本（2021 年，v1.12.5）
- `github.com/JoeNJH/zuoyebang` — Selenium 自动化工具
- `github.com/Gerres/crawler-zuoyebang` — Java 爬虫

### 1.2 猿题库 (Yuantiku)

| 维度 | 评估 |
|------|------|
| **API 逆向** | 不可行（需极大量投入）|
| **已知公开项目** | 无 API 客户端；只有 1 个 Android 逆向项目（37 stars，功能有限） |
| **API 文档** | 完全未公开 |
| **同一集团（粉笔）** | 已被逆向，有完整开源客户端（可作为参考） |

**结论**：猿题库本身投入产出比太低，但**同一集团的粉笔 (Fenbi) 平台已有完整逆向实现**，可作为技术参考或替代数据源。

### 1.3 粉笔 (Fenbi) — 惊喜发现

粉笔与猿题库同属一个集团，使用相似的技术架构，且已有活跃的开源生态：

| 维度 | 评估 |
|------|------|
| **API 可获取性** | 高 — 5+ 个活跃项目（2024-2026） |
| **鉴权** | RSA PKCS#1 v1.5 加密密码，Cookie Session |
| **数据质量** | 行测/公考题库，结构化 JSON，带标签分类 |

#### 已确认的粉笔 API 端点

```
POST https://login.fenbi.com/api/users/loginV2   → 登录
GET  https://tiku.fenbi.com/api/xingce/subLabels → 知识点标签
GET  https://tiku.fenbi.com/api/xingce/papers/    → 试卷列表
POST https://tiku.fenbi.com/api/xingce/exercises  → 创建练习
GET  https://urlimg.fenbi.com/api/pdf/tiku/...     → 下载 PDF
```

#### 参考源码

- `github.com/dduutt/fenbi` — Python + Node.js RSA 加密登录
- `github.com/EricPeng1027/fenbi-crawler` — Playwright 爬虫
- `github.com/YSMull/fenbi-helper` — Node.js Docker 工具
- `github.com/maoguy/fenbi-client` — VSCode 扩展

---

## 2. 搜索环境说明

- **中文技术平台（CSDN、知乎）** 对自动化访问返回空白或 403
- **Bing** 对部分逆向相关搜索词返回「应法律法规要求部分结果未予显示」
- **52破解论坛、看雪论坛** 搜索无相关结果（可能被屏蔽或需登录）
- **GitHub** 搜索 `zuoyebang api` 和 `yuantiku api` 返回极少结果

这表明这些平台有法律团队在清理逆向相关内容。

---

## 3. 可行路径对比

| 路径 | 可行性 | 数据质量 | 覆盖范围 | 投入时间 |
|------|--------|---------|---------|---------|
| **A: 作业帮 wenda API** | 高 | 中（Q&A 数据，非题库数据）| 全学科 | 1-3 天 |
| **B: 作业帮主 App 逆向** | 中 | 高（拍照搜题，结构化题库）| 全学科+全学段 | 2-4 周 |
| **C: 猿题库 App 逆向** | 低 | 高 | 全学科+全学段 | 3-6 周 |
| **D: 粉笔 API** | 高 | 高（行测/公考）| 仅公考/事业编 | 1-2 天 |
| **E: 混合方案 (A + D + 参考架构)** | 高 | 中-高 | 多学科 | 1-2 周 |

---

## 4. 风险评估

### 技术风险
- **中等**：主 App 大概率有证书绑定 + 代码混淆 + 签名校验，需 Frida/Xposed 绕过
- **低**：wenda API 和粉笔 API 无证书绑定，直接 curl 可用

### 法律风险
- **中高**：题目数据受版权保护；中国《网络安全法》和《反不正当竞争法》禁止未授权访问和数据爬取
- **所有公开项目均标注「仅供学习交流使用」**
- **Bing 搜索结果审查**表明平台方在主动清理逆向内容

### 稳定性风险
- **中**：API 可能随时变更；wenda API 自 2021 年以来未变（4 年稳定期）

---

## 5. 建议

### 推荐方案：路径 A（作业帮 wenda API）+ 路径 D（粉笔 API）并行

**理由**：
1. 两条路径都已有可运行的开源代码
2. API 端点均已确认在线（2026-05-15）
3. 鉴权机制简单（MD5 / RSA），无需 App 逆向
4. 可在 3-5 天内产出可用数据

### 如果选择继续

下一步：
1. 在 path7_app 下实现作业帮 wenda API 客户端
2. 在 path7_app 下实现粉笔 API 客户端（作为架构参考）
3. 评估返回数据的可用性（题目格式、标签完整性、学科覆盖）
4. 根据结果决定是否深入主 App 逆向

---

## 6. 等待你的决策

请确认以下问题后继续：

1. **是否接受 wenda API 的数据质量**？（Q&A 数据 vs 完整题库）
2. **是否将粉笔纳入采集范围**？（公考数据，非高中题目，但架构可参考）
3. **是否愿意投入 App 逆向**？（2-4 周，需要 Android 模拟器 + Frida）
4. **法律风险是否可接受**？

---

## 附录: 技术参考资料

- Zuoyebang wenda API client: `https://github.com/binganao/zuoyebang/blob/main/source/zyb.py`
- Fenbi API client: `https://github.com/dduutt/fenbi/blob/main/main.py`
- Fenbi RSA encryption JS: `https://github.com/dduutt/fenbi/blob/main/script.js`
- Yuantiku iOS networking lib: `https://github.com/yuantiku/YTKNetwork`
- Fenbi Docker helper (May 2026): `https://github.com/YSMull/fenbi-helper`
