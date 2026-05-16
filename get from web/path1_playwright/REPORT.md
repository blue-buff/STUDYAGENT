# 组卷网题目抓取 Agent — 工作报告

> 路径：`/Users/song/project/STUDYAGENT/get from web/path1_playwright/`
> 日期：2026-05-16

## 一、项目目标

为高中生构建按知识点检索题目的抓取 Agent，基于 [malyjacob/zujuan](https://github.com/malyjacob/zujuan) (MIT 许可证) 的 TypeScript 项目进行改造和封装，输出可直接调用的 Python 脚本。

## 二、zujuan 原项目调研

### 2.1 项目概况

- 语言：TypeScript + Playwright，CLI 工具
- 目标站点：zujuan.xkw.com（学科网组卷网）
- 已验证功能：知识点树搜索、SQLite 数据库构建
- 未验证功能：扫码登录（我们补完了这一步）

### 2.2 核心抓取流程

```
连接浏览器 → 访问 URL → 检查登录态 → 滚动加载题目 →
逐题截图(div.exam-item__cnt) → 点击展开答案(div.wrapper.quesdiv) →
收集答案URL → 并行下载答案图片 → 保存 JSON + 截图
```

### 2.3 URL 规则

```
https://zujuan.xkw.com/{学科前缀}/zsd{知识点ID}/qt{题型码}d{难度}y{年份}o{排序}p{页码}/
```

题型码（高中数学）：单选=2701, 多选=2704, 填空=2702, 解答=2703
排序：o2=最新, o1=最热, o0=综合

## 三、登录方案

### 3.1 原方案（zujuan start）

- 启动持久化 Chrome 进程（CDP 9222），展示微信扫码二维码
- **不可用原因**：headless 模式下 Chrome 冷启动超过 30s CDP 超时；终端环境无法扫码

### 3.2 我们的方案

独立 Python 登录脚本 `login.py`：

1. Playwright 启动 headless Chromium
2. 导航到 zujuan.xkw.com → 触发 `logindiv()` → 等待 `#qrcode canvas`
3. 截图保存为 `shared/login-qr.png`
4. 终端 ASCII 展示二维码
5. 每 2s 新建页面检查 `a.login-btn` 是否消失
6. 登录成功 → 保存 `storage-state.json`（40 个 cookie）
7. 浏览器自动关闭

### 3.3 遇到的问题和解决

| 问题 | 原因 | 解决 |
|------|------|------|
| CDP 连接超时 | Chrome 冷启动慢 | 改用 Playwright 直接管理浏览器，不依赖持久化 CDP 进程 |
| 终端无法扫码 | headless 环境无 GUI | ASCII 艺术展示二维码 + 文件保存供外部打开 |
| 关注公众号后无反应 | 公众号关注是前置步骤 | 关注后再次扫码即可完成登录 |

## 四、抓取验证结果

### 4.1 测试用例

```bash
python scrape.py -k zsd27977 -t t1 -l 3
# 知识点: 交集的概念及运算
# 题型: 单选题
# 数量: 3道
```

### 4.2 输出样例

```json
{
  "metadata": {
    "knowledgeId": "zsd27977",
    "grade": "high",
    "type": "单选题",
    "order": "最新",
    "url": "https://zujuan.xkw.com/gzsx/zsd27977/qt2701o2/"
  },
  "results": [
    {
      "index": "001",
      "questionPath": "001/question.png",
      "answerPath": "001/answer.png",
      "questionType": "单选题",
      "difficulty": "容易",
      "source": "2026·广西贵港·三模",
      "knowledgeKeywords": ["交集的概念及运算", "数学运算能力"]
    }
  ]
}
```

### 4.3 截图统计

| 项目 | 数值 |
|------|------|
| 题目截图 | 7-9 KB/张 |
| 答案截图 | 32-36 KB/张 |
| 3 道题合计 | ~125 KB |
| 累计输出 | 720 KB（远低于 200MB 上限） |

## 五、交付物清单

### 5.1 path1_playwright/ 工作目录

| 文件 | 功能 |
|------|------|
| `scrape.py` | 核心抓取脚本，支持函数式调用和 CLI 两种方式 |
| `login.py` | 独立登录脚本，保存 storage-state.json |
| `search.py` | 知识点搜索（查询 SQLite 数据库） |
| `scrape.sh` | Shell 封装，一键抓取 |
| `SUBJECT_EXTENSION.md` | 学科扩展可行性分析 |
| `output/` | 抓取结果输出目录 |

### 5.2 shared/ 共享目录

| 文件 | 用途 |
|------|------|
| `storage-state.json` | 登录态（40 cookies，供其他 Path 读取） |
| `chrome_freed` | Chrome 已释放标记 |

### 5.3 函数式接口

```python
from scrape import scrape, search_knowledge

# 搜索知识点
results = search_knowledge("函数", grade="high")
# → [("zsd27927", "函数与导数", 0, None), ...]

# 抓取题目
output = await scrape(
    knowledge_id="zsd27977",
    qtype="t1",         # 单选题
    difficulty="d3",    # 适中
    grade="high",
    limit=10,
)
# → {"metadata": {...}, "results": [...]}
```

## 六、学科扩展分析

### 6.1 已验证

组卷网使用统一 URL 结构和 HTML 模板，**18 个学科全部可达**：

高中：数学(gzsx)、物理(gzwl)、化学(gzhx)、生物(gzsw)、语文(gzyw)、英语(gzyy)、地理(gzdl)、历史(gzls)、政治(gzzz)

初中：数学(czsx)、物理(czwl)、化学(czhx)、生物(czsw)、语文(czyw)、英语(czyy)、地理(czdl)、历史(czls)、政治(czzz)

### 6.2 扩展步骤

1. 获取目标学科的知识点树（爬取或手动整理）
2. 验证该学科的题型码和排序参数
3. 修改 `GRADE_PREFIX` 映射表
4. 运行抓取测试

### 6.3 物理学科初步验证

- URL: `https://zujuan.xkw.com/gzwl/zsd41934/x4o2/`
- 题目数: 10 道，结构一致
- 排序参数: `x4` (新题)，不同于数学的 `o2`
- 知识点 ID: 同一 zsd 格式，不同 ID 段

## 七、已知限制

1. **答案配额**：免费用户每日 30 道答案，超限后只能截图题目
2. **知识点树**：目前仅高中数学有预生成文本，其他学科需自行获取
3. **题型码差异**：不同学科的 qt 编码可能不同，需逐学科验证
4. **登录态有效期**：storage-state.json 过期后需重新扫码
