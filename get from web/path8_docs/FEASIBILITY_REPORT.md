# Path 8: Document Platform Feasibility Report

Date: 2026-05-15 | Researcher: AI Agent

## 1. Platform Accessibility Summary

| Platform | Search Results | Document Viewer | Free Content | Verdict |
|----------|---------------|-----------------|-------------|---------|
| **Baidu Wenku** | Works (Playwright) | Blocked (CAPTCHA) | Rich snippets in search | **PARTIALLY FEASIBLE** |
| **Doc88** | Not working (JS-rendered) | Not tested | Unknown | **NOT FEASIBLE** |
| **Docin** | Not working (JS-rendered) | Not tested | Unknown | **NOT FEASIBLE** |

### Baidu Wenku Details

**Search page (wenku.baidu.com/search):**
- Accessible via Playwright headless browser (Chromium)
- Search results contain rich text snippets with complete question content
- Each snippet includes: question text, options (A/B/C/D), answers (答案：), analysis (解析：)
- ~150-350 chars per snippet, 18+ unique results per 4-query batch
- URL pattern: `wenku.baidu.com/view/{id}.html?fr=income{d}-doc-search`

**Document viewer page (wenku.baidu.com/view/...):**
- Blocked by CAPTCHA (百度安全验证 - slider puzzle)
- CAPTCHA appears even in headful browser mode
- Direct document access NOT feasible without manual intervention
- Download requires VIP membership anyway

### Doc88 (doc88.com)
- Search page is fully JS-rendered, no results load in headless browser
- Document viewer not tested (no URLs obtained)
- Likely requires login + credits for full access

### Docin (docin.com)
- Search page returns "这个网页真没有……" (page doesn't exist) in headless
- Fully JS-dependent search
- Not feasible for automated access

## 2. Extraction Strategy

### Working Approach: Search Snippet Extraction

Since the document viewer is CAPTCHA-blocked but search results are rich:

1. **Search** with 4 query variations per knowledge point on Baidu Wenku
2. **Extract** rich text from search result snippets (title + body text)
3. **Compile** multiple snippets into a combined "paper text"
4. **Split** with LLM into individual questions
5. **Structure** each question with LLM (knowledge points, difficulty, etc.)

### Quality of Snippet Content

Sample snippet analysis:
- **Best case**: Full question text + options + answer + analysis, 300+ chars
- **Average case**: Multiple questions with answers, 150-200 chars
- **Worst case**: Summarized/truncated content, 50-100 chars (marked with "全部...")

Approximately 70% of snippets contain usable question data.

## 3. Technical Findings

### CAPTCHA Bypass
- Baidu uses slider CAPTCHA on document viewer pages
- Headful browser does NOT bypass it
- Potential future solutions: cookie injection from logged-in browser, manual CAPTCHA solving service

### PDF/DOCX Download
- Not tested — document viewer blocked
- VIP required for download anyway
- Snippet extraction makes this unnecessary

### Math Formula Handling
- Formulas appear as plain text in snippets (e.g., f(x)=x³-3x²+2, f&#39;(x) = 3x² - 6x)
- LaTeX-like notation preserved in some snippets
- LLM can interpret and structure these

### Resource Usage
- No PDF/DOCX downloads needed → zero disk impact
- No OCR needed → zero model storage
- Playwright browser: ~300MB (already installed)
- Total pipeline: ~5MB code + snippets

## 4. Go/No-Go Decision

### VERDICT: PARTIALLY FEASIBLE — PROCEED WITH MVP

**Reasons:**
1. Baidu Wenku search snippets provide rich, usable question data
2. 18+ snippets per search batch, ~70% contain complete questions
3. No file downloads, OCR, or VIP needed
4. Works with headless Playwright (automated)

**Limitations:**
1. Cannot access full document content (CAPTCHA on viewer)
2. Only Baidu Wenku works (Doc88/Docin are JS-blocked)
3. Snippet content is truncated (~300 chars max per result)
4. Some papers are summarized rather than shown in full

**Recommendation**: The snippet-based approach is viable for a proof-of-concept MVP. For production, investigate Baidu Wenku API reverse-engineering or logged-in cookie injection.
