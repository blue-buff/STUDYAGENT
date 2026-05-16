# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Goal

Building an agent that searches and recommends exam questions for high school students. Data sources include mainstream Chinese exam websites (组卷网/学科网, 菁优网, 百度文库) and public datasets.

## Project Structure

```
get from web/
├── shared/                  # Cross-path shared resources
│   ├── storage-state.json   # Login cookies for chujuan.cn (40 cookies, 14KB)
│   └── chrome_freed         # Empty marker: Path 1 has released Chrome
├── path1_playwright/        # Browser screenshot scraping (Playwright)
├── path2_api/               # HTTP API reverse-engineering (requests)
├── path3_jyeoo/             # 菁优网 scraper (BLOCKED: needs VIP)
├── path4_dataset/           # Public datasets + local search engine
├── path5_search/            # Search engine + LLM extraction (not scalable)
├── path6_xkw/               # SSR paper splitting + answer extraction
├── path7_app/               # App API reverse-engineering (wrong data type)
├── path8_docs/              # Baidu Wenku snippet extraction
├── RESEARCH_BRIEFING.md     # Initial research findings
├── IMPLEMENTATION_PATHS.md  # 8-path analysis
├── PATH_ADJUSTMENTS.md      # Resource constraint supplements
├── RESOURCE_ANALYSIS.md     # Hardware capacity analysis
└── PROMPTS.md               # Original task prompts for each path
```

## Path Viability Summary

| Status | Path | Data Source | What Works |
|--------|------|-------------|------------|
| ✅ Active | Path 1 | 组卷网 screenshots | Login + scrape, 30 answers/day |
| ✅ Active | Path 2 | 组卷网 HTTP API | Anti-bot bypass, answer API, 2389 knowledge nodes |
| ✅ Active | Path 6 | 组卷网 SSR | Paper text at scale, answers via Playwright click |
| ✅ Active | Path 4 | Public datasets | Physics/chem 770 questions, 100% answered |
| ❌ Dead | Path 3 | 菁优网 | Chapter tree built, free quota exhausted, needs VIP |
| ❌ Dead | Path 5 | Search+LLM | 17 questions, not scalable |
| ❌ Dead | Path 7 | App API | Data is Q&A/civil-service, not high school |
| 🟡 Low-prio | Path 8 | Baidu Wenku | Search snippets, 68% accuracy, truncated |

**Core insight**: Paths 1, 2, 6 all target the same site (组卷网/学科网 `chujuan.cn`). They are complementary — Path 6 extracts text at scale, Path 2 fetches answers via HTTP, Path 1 maintains login state.

## Common Commands

### Path 1 — Playwright Screenshot Scraper

```bash
cd "get from web/path1_playwright"

# Login (generates shared/storage-state.json)
python3 login.py

# Search knowledge points
python3 search.py 函数

# Scrape questions by knowledge ID
python3 scrape.py -k zsd27977 -t t1 -d d3 -l 5
python3 scrape.py -k zsd27977 -t t3 -l 5 -y 2025
```

### Path 2 — HTTP API Client

```bash
cd "get from web/path2_api"

# Login
python3 main.py login

# Search questions (no login needed for text)
python3 main.py search zsd27942 -t t1 -d d3 -l 5

# Browse knowledge tree (2389 nodes)
python3 main.py tree 函数

# Get answer image (requires login cookies)
python3 main.py answer 32801513
```

### Path 6 — Paper Splitting + Answer Extraction

```bash
cd "get from web/path6_xkw"

# Extract paper with answers (needs chujuan.cn login cookie)
python3 extract_with_answers.py --paper-id 6339985 --cookie-file cookies.txt
```

### Path 4 — Local Dataset Search

```bash
cd "get from web/path4_dataset"

# Exact filter: subject + knowledge point + difficulty
python3 search_engine.py -s 数学 -k 解析几何 -d medium -a -n 10

# Semantic search
python3 search_engine.py --semantic -w "椭圆离心率取值范围" -a -n 5
```

## Unified Question JSON Schema

All paths should output questions in this format:

```json
{
  "subject": "数学",
  "grade": "高中",
  "knowledge_points": ["导数", "单调性"],
  "question_type": "单选题",
  "difficulty": "中等",
  "year": 2026,
  "question_text": "已知函数 f(x) = ...",
  "question_options": ["A. ...", "B. ...", "C. ...", "D. ..."],
  "answer_text": "C",
  "analysis": "解析文字...",
  "explanation_url": "https://webshot.zujuan.com/...ex.png",
  "source": "2026·广东广州·二模",
  "source_url": "https://www.chujuan.cn/question/detail-xxx.shtml",
  "extraction_confidence": 0.95
}
```

## Key Technical Details

### 组卷网/学科网 (chujuan.cn — primary data source)

- **New domain**: `chujuan.cn` (migrated from `zujuan.xkw.com`, which now has WAF blocks on some subjects)
- **Auth**: WeChat QR scan → cookies: `userId`, `user_token`, `zujuan-core`
- **Anti-bot**: Alibaba Cloud WAF `alicfw` cookie challenge (MurmurHash3-based). Solved in Path 2 via JSDOM execution of challenge JS.
- **Free quota**: 30 answers/day
- **SSR advantage**: Question text, options, knowledge tags, difficulty, and explanation image URLs are embedded in server-rendered HTML. No login needed for these.
- **Answer API**: `POST /zujuan-api/check_ques_parse` → `GET imzujuan.xkw.com/getAnswerAndParse/{qid}/{bankId}/{key}`. Requires `enVqdWFu` param (= base64 of user_token JSON) and `Referer` header pointing to question detail page.
- **Subject coverage**: 18 subjects confirmed (high school: gzsx, gzwl, gzhx, gzsw, gzyw, gzyy, gzdl, gzls, gzzz; middle school: czsx, czwl, czhx, czsw, czyw, czyy, czdl, czls, czzz)
- **Subject differences**: Math answers partially visible in SSR HTML; physics/chemistry answers hidden but explanation image URLs are always present.
- **URL pattern**: `/{grade_prefix}/zsd{knowledge_id}/qt{type_code}d{difficulty}y{year}o{order}/`
- **Knowledge tree**: 2389 nodes in Path 2's `knowledge_tree.py` output (Path 1 has SQLite version, math only)

### 菁优网 (jyeoo.com — blocked, VIP needed)

- 20 subjects across 3 levels, 128 textbook versions, 723 grade/volume entries
- Chapter tree data embedded in hidden HTML `#JYE_BOOK_TREE_HOLDER`
- 2026 changes: login wall + paywall added; free accounts redirected to `/Hints/Recharge` after quota
- Chapter nodes (2163 dynamic nodes) saved in `path3_jyeoo/output/knowledge_trees/`

### Resource Constraints

- MacBook Pro 2016, 8GB RAM, dual-core i7, 233GB SSD (~13GB free)
- Only ONE Chrome/Playwright instance at a time — Path 1 creates `chrome_freed` when done
- Login state in `get from web/shared/storage-state.json` — share across paths

## Implementation Strategy (Current Phase)

1. Merge Path 6 (SSR text at scale) + Path 2 (HTTP answer API) into unified pipeline
2. Use Path 1's `storage-state.json` as shared login credential
3. Path 4 physics/chem data (770 questions) can be directly ingested
4. Path 3 and Path 5 are archived; Path 8 is low-priority supplement
