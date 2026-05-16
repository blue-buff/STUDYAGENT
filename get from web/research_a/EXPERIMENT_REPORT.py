#!/usr/bin/env python3
"""
配额验证实验 — 最终报告生成脚本
打印完整实验结论，不做任何网络请求。
Usage: python3 EXPERIMENT_REPORT.py
"""

REPORT = """
======================================================================
配额验证实验 — 最终报告
======================================================================
日期: 2026-05-16
存储态: shared/storage-state.json (2026-05-15 23:48 生成)
账号: userId=86599050 (免费账号)

======================================================================
1. 问题定义
======================================================================

组卷网的 checkQuesParse API 限免费用户 30 次/天查看答案。
Path 6 发现另一条路径：Playwright 模拟点击"显示答案解析"按钮，
从 DOM 提取 webshot 答案图片 URL。本实验验证这条浏览器交互路径
是否受同一配额限制。

======================================================================
2. 实验方法
======================================================================

实验 A (experiment_quota.py):
  - 用 Playwright 打开 3 张试卷页 (chujuan.cn)
  - 每页点击"显示答案解析"按钮
  - 监控所有网络请求 (检测 checkQuesParse 调用)
  - 提取 DOM 中的 webshot 答案图片 URL

实验 B (experiment_webshot.py):
  - 用 Playwright 访问 56 道题目的 Detail 页
  - 从页面 HTML 中提取 explanation webshot URL
  - 用 requests 逐一下载所有 webshot 图片
  - 统计成功/失败数

======================================================================
3. 实验结果
======================================================================

3.1 网络监控 (实验 A)
  - 处理 3 张试卷，共 555 个网络请求
  - checkQuesParse API 调用数: 0
  - 结论：试卷页的"显示答案解析"按钮不触发 checkQuesParse

3.2 网页图片提取 (实验 A)
  - 试卷页点击按钮后，DOM 中 webshot 图片数: 0
  - 试卷页 HTML 中 answer_text 字段: 全部为空
  - 结论：试卷页不再通过 webshot 图片展示答案 (机制可能已变更)

3.3 题目Detail页提取 (实验 B)
  - 访问 56 道题 Detail 页：56/56 成功
  - 每页都有 explanation webshot URL (100% 覆盖率)
  - answer_text 字段: 0/56 非空 (可能今日配额已耗尽或机制不同)

3.4 webshot 图片下载 (实验 B)
  ┌─────────────────────────────────────────┐
  │  尝试下载: 56 张                          │
  │  下载成功: 56 张  (100%)                  │
  │  下载失败: 0 张                            │
  │  单张大小: 8KB ~ 166KB (有效答案解析图片)   │
  └─────────────────────────────────────────┘

3.5 补充分析
  Path 6 昨日数据 (paper_6339985_with_answers.json):
    - 单选题 (6道): 全部有 answer_text ("A", "C", "B", ...)
    - 多选题 (3道): 全部有 answer_text ("A,C", "A,B,D", ...)
    - 填空题 (3道): 全部有 answer_text
    - 解答题 (5道): 全部无 answer_text (答案仅图片形式)

  今日数据 (本实验):
    - answer_text: 全部为空 (56/56)
    - explanation URL: 全部存在 (56/56)
    - 推断: answer_text 依赖 30次/天 配额（昨日已用尽），
           但 explanation webshot URL 不依赖配额

======================================================================
4. 结论
======================================================================

核心结论:
  >>> webshot 答案解析图片路径不受 30 次/天 配额限制 <<<

详细说明:

  1. explanation webshot 图片 (题目Detail页)
     - URL 嵌入在 /question/detail-{qid}.shtml 的页面 JSON 中
     - 下载 servers 为 webshot.zujuan.com (CDN)
     - 不需要 checkQuesParse API 密钥
     - 已验证：连续下载 56 张全部成功 (> 30 次限制)
     - 需要正确的 Referer header (题目Detail页 URL)
     - 需要有效的登录 cookie (userId, user_token)

  2. answer_text (文字答案)
     - 嵌入在试卷页或题目Detail页的 JSON 数据中
     - 单选题/多选题/填空题通常有文字答案 (如 "A", "C", "21")
     - 解答题无文字答案 (仅图片形式)
     - 可能受 30次/天 配额影响 (昨日 12/12 有效，今日 0/56)
     - 注意：即使 answer_text 为空，explanation 图片仍可下载

  3. checkQuesParse API (答案图片密钥)
     - 30次/天 限制：当配额用尽返回 {"key": "", "first": false}
     - 用于获取 imzujuan.xkw.com 上的动态答案图片
     - webshot 路径完全绕过了这个 API

======================================================================
5. 实际应用建议
======================================================================

获取答案的最佳路径 (绕过配额):

  步骤 1: 用 requests/Playwright 访问题目 Detail 页
          GET https://www.chujuan.cn/question/detail-{qid}.shtml
          (需要 userId + user_token cookies)

  步骤 2: 从页面 HTML 中正则提取 explanation URL
          pattern: "explanation"\s*:\s*"(https://webshot[^"]+)"

  步骤 3: 用 requests 下载图片
          GET {explanation_url}
          Header: Referer: https://www.chujuan.cn/question/detail-{qid}.shtml
          (需要 login cookies)

  注意:
  - 需要间隔 0.2-0.5s 防止触发反爬
  - explanation 图片是「答案 + 解析」合并图，非纯答案
  - answer_text (文字答案) 可能受限，但可从图片 OCR 提取
  - cookies 有效期有限 (zujuan-core ~12h, user_token ~24h)

======================================================================
6. 实验产出文件
======================================================================

  research_a/
  ├── EXPERIMENT_REPORT.py      (本报告)
  ├── experiment_quota.py       (实验 A: 试卷页 + 网络监控)
  ├── experiment_webshot.py     (实验 B: Detail页提取 + 图片下载)
  ├── experiment_results.json   (实验 A 详细结果)
  └── experiment_webshot_results.json (实验 B 详细结果)

======================================================================
"""

if __name__ == "__main__":
    print(REPORT)
