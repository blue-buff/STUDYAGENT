# 统一题目获取管线

整合 8 条探索路径 + 3 个研究方向成果的端到端题目获取系统。

## 核心发现

1. **题目文本 + 知识点 + 难度** — SSR HTML 免费提取，不限量
2. **解析图** — webshot.zujuan.com 直链下载，不限量（方向A验证：56/56成功）
3. **答案文字** — Kimi OCR 读解析图，准确率 ~90%（方向B验证：11/12正确）
4. **Cookie 桥接** — Playwright ↔ requests 互转（方向C产出）

## 快速开始

```bash
# 1. 确保登录态有效
cd ../path1_playwright && python3 login.py

# 2. 全流程：发现 + 拆卷 + 补答案 + 入库
python3 pipeline.py all --subject math --limit 3

# 3. 检索
python3 pipeline.py query --subject 数学 -k 导数 -t 单选题 -a -n 5
```

## 命令

```bash
# 发现试卷
python3 pipeline.py discover --subject math --zone exam --pages 2

# 拆卷
python3 pipeline.py extract --paper-id 6339985 -o output.json

# 补答案（webshot 下载，可选 Kimi OCR）
python3 pipeline.py answers --input output.json --ocr

# 入库
python3 pipeline.py store --input output_with_answers.json

# 检索
python3 pipeline.py query -s 数学 -k 导数 -t 单选题 -d 中等 -a -n 10

# 导入已有数据（Path 4 + Path 6）
python3 pipeline.py import-existing
```

## 依赖

- Python 3.10+
- requests, beautifulsoup4, lxml
- Kimi CLI（可选，用于 OCR 答案）
- `research_c/cookie_bridge.py`（自动引用）
- `shared/storage-state.json`（登录态）
