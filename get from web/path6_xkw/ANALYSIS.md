# 组卷网/学科网试卷结构分析文档

> Path 6 - 整卷拆分 | 2026-05-15

## 1. 网站体系概述

组卷网（zujuan.xkw.com）已迁移至新域名 **chujuan.cn**，与学科网（xkw.com）共用账号体系。

| 组件 | 旧域名 | 新域名（当前） |
|------|--------|----------------|
| 主站 | zujuan.xkw.com | www.chujuan.cn |
| 登录 | passport.zujuan.com | pass.chujuan.cn |
| 静态资源 | static.zujuanyi.com | static.zujuanyi.com（不变） |
| 数学公式渲染 | math.21cnjy.com | math.21cnjy.com |

**技术栈**: Backbone.js + Vue.js SPA，首屏 SSR（服务端渲染），后续交互 AJAX。

**学段与学科编码**:
- xd（学段）: 1=小学, 2=初中, 3=高中
- chid（学科）: 2=语文, 3=数学, 4=英语, 6=物理, 7=化学, 8=历史, 9=政治, 10=地理, 11=生物, 14=信息技术, 15=通用技术, 1015=思想政治

## 2. URL 规则

### 2.1 试卷列表页

| 专区 | URL 模式 | 说明 |
|------|----------|------|
| 同步专区 | `/paper/paper-category-list?xd=3&chid=3` | 按章节的单元测试、同步练习 |
| 备考专区 | `/paper/paper-sync-list?xd=3&chid=3` | 期中期末、月考等阶段性考试 |
| 高考专区 | `/paper/paper-exam-list?xd=3&chid=3` | 高考真题、模拟题 |

**筛选参数**:
- `page` - 页码（从1开始）
- `per-page` - 每页数量（默认10）
- `papertype` - 试卷类型（0=全部，各专区不同）
- `paperyear` - 年份（2026~2016，-1=更早）
- `province_id` - 省份（1-34，-1=不限）
- `termid` - 学期（23-28，备考专区）

**备考专区 papertype**:
| 值 | 类型 |
|----|------|
| 0 | 全部 |
| 4 | 期中考试 |
| 3 | 月考试卷 |
| 5 | 期末考试 |
| 6 | 单元测试 |
| 17 | 专题复习 |
| 12 | 开学考试 |

**高考专区 papertype**:
| 值 | 类型 |
|----|------|
| 0 | 全部 |
| 18 | 高考真题 |
| 19 | 高考复习 |
| 20 | 高考压轴 |
| 9 | 高考模拟 |
| 10 | 学业考试 |

### 2.2 试卷详情页

```
/paper/view-{paper_id}.shtml
```

试卷页 SSR 嵌入两个关键数据：
1. `paper_detail` JSON - 试卷元数据（标题、学科、题型结构、题号列表）
2. `FilterParams.data` JSON - 题型/难度/知识点等筛选配置

### 2.3 单题详情页

```
/question/detail-{question_id}.shtml
```

单题页 SSR 嵌入完整题目数据（`Application.QuestionDetailView` 的 `question` 参数），包含：
- 题目文字（MathML + HTML 格式）
- 选项（选择题）
- 答案（需登录/VIP 才能查看，否则为空）
- 解析图片 URL（存储在 webshot.zujuan.com）

### 2.4 按知识点搜题（Path 1 路线）

```
/gzsx/zsd{知识点ID}/qt{题型码}d{难度}y{年份}o{排序}/
```

详见 Path 1 文档，本路径不重复。

## 3. 试卷数据模型

### 3.1 试卷元数据（paper_detail._meta）

```json
{
  "xd": 3,                    // 学段
  "chid": 3,                  // 学科ID
  "title": "试卷标题",
  "paper_type": "高考模拟",    // 试卷类型文字
  "paper_type_id": 9,         // 试卷类型码
  "paper_type_group": 3,      // 试卷类型分组
  "year": 2026,               // 年份
  "question_num": 19,         // 题目总数
  "term": "高考阶段",          // 学期/阶段
  "xdName": "高中",           // 学段名称
  "xkName": "数学",           // 学科名称
  "style": [0,0,0,...],       // 题型分隔标记
  "tizu_sort": ["一、选择题...", "二、填空题..."],  // 题型标题
  "show_all_content": 1,      // 是否可查看全部内容
  "is_lock": 0,              // 是否锁定（VIP）
  "download_num": 2,          // 下载次数
  "look_num": 10,             // 浏览次数
  "provinces": [{"id":"19","name":"广东省"}],
  "categories": [{"category_id":2940,"category_name":"高中数学"},...]
}
```

### 3.2 试卷中的题目结构（从列表页获取）

```json
{
  "structure": [
    {
      "head_title": "一、选择题：本题共8小题，每小题5分，共40分...",
      "questions": [
        {"question_id": 68956362, "score": {"score": 0, "scoreList": null, "subScore": null}},
        ...
      ]
    },
    ...
  ],
  "question_ids": [68956362, 68956363, ...]
}
```

### 3.3 单题数据模型（从题目详情页提取）

```json
{
  "question_id": "68956362",
  "question_type": "1",              // 1=单选, 2=多选, 4=填空, 6=解答
  "question_channel_type": 1,
  "channel_type_name": "单选题",
  "district_question_name": [],      // 地区题型名称
  "title": "已知集合A={-1,0,1}，B={x|x²<1}，则A∩B=（       ）",  // 纯文本标题
  "question_text": "已知集合<img class=\"mathml\" src=\"...\"/>，则...</img>（       ）",  // HTML格式
  "options": {
    "A": "<img class=\"mathml\" src=\"...\"/>...",
    "B": "...",
    "C": "...",
    "D": "..."
  },
  "answer": "",                      // 答案（通常为空，需登录查看）
  "answer_json": ["", "", "", ""],
  "explanation": "https://webshot.zujuan.com/q/.../68956362ex.png?hash=...&sign=...",  // 解析图片URL
  "explain_sort_need": "0",
  "sub_explanation": [],
  "question_source": "广东广州市天河区2026届普通高中毕业班适应性训练（二模）数学试卷",
  "isVip": "",                       // VIP 标记
  "access": "",                      // 访问权限
  "status": "2",
  "knowledge": ["集合", "交集"]       // 知识点（部分题目有）
}
```

## 4. 页面 DOM 结构（供 Playwright 方案参考）

### 4.1 试卷查看页（PaperShowView）

关键 CSS 选择器（来自 xkw-zujuan-script userscript）:
- `.sec-title` - 题型分区标题
- `.tk-quest-item.quesroot` - 题目项
- `.wrapper.quesdiv` - 题目内容包装
- `.exam-item__cnt` - 题目题干
- `.exam-item__opt` - 题目选项/答案区域
- `.knowledge-box` - 知识点标签
- `#isshowAnswer` - 显示答案复选框
- `.ques-additional` - 题目附加信息（来源、题型、难度、得分率、知识点关键词）

### 4.2 试卷编辑页（PaperEditView）

来自 zujuan-export userscript:
- `.paper-title .main-title` - 试卷标题
- `.ques-type` - 题型分区
- `.ques-item` - 题目项
- `.exam-item__cnt` - 题目内容
- `table[name="optionsTable"]` - 选择题选项表
- `.questypename` - 题型名称
- `.quesindex` - 题号

## 5. 跨学科差异分析

### 已验证可访问的学科（高中）
| 学科 | chid | 状态 |
|------|------|------|
| 数学 | 3 | 完全可访问 |
| 物理 | 6 | 可访问（SSR有数据） |
| 化学 | 7 | 可访问（SSR有数据） |

### 被 WAF 拦截的学科
语文(2)、英语(4)、生物(11)、地理(10)、历史(8)、政治(1015) 在 zujuan.xkw.com 子域名触发 405 阻断页面，但 chujuan.cn 主域名下均正常。

### 学科间差异
- **数学**: 大量 MathML 公式，通过 `<img class="mathml" src="math.21cnjy.com/math2svg/...">` 渲染
- **物理/化学**: 可能包含实验图、装置图、化学式图片
- **语文/英语**: 阅读理解题型，文本较长，包含阅读材料
- 所有学科的题目文本均为 HTML 片段，公式统一用 math.21cnjy.com 的 MathML→SVG 服务

## 6. 提取策略对比

| 方案 | 方法 | 优点 | 缺点 |
|------|------|------|------|
| A. SSR 静态解析 | requests 抓取 SSR HTML，正则提取嵌入 JSON | 无需浏览器，速度快 | 答案被锁，无法获取 answer 内容 |
| B. Playwright 自动化 | 浏览器渲染 + 注入 userscript | 可点击"显示答案"获取全部内容 | 需要登录，每日限30次答案查看 |
| C. 混合方案 | requests 提取题目文本 + Playwright 补充答案 | 兼顾效率和完整性 | 复杂度高 |

**当前推荐**: 方案 A（SSR 静态解析）用于题目文本提取；当 chrome_freed 信号出现且 storage-state.json 可用时，补充方案 B 获取答案。
