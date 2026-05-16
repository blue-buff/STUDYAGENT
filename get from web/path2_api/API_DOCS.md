# ZuJuan API Reverse Engineering Documentation

## Overview

组卷网 (zujuan.xkw.com) uses a hybrid architecture:
- **Question lists**: Server-side rendered HTML (no separate API)
- **Answer images**: `imzujuan.xkw.com/getAnswerAndParse` (requires login)
- **Formula images**: `staticzujuan.xkw.com/quesimg/Upload/formula/`
- **Anti-bot**: Alibaba Cloud WAF (alicfw cookie challenge)

## 1. Anti-Bot Challenge

### Detection
The first request to `zujuan.xkw.com` returns a challenge page with:
- `<input name="parm_0" value="...">` 
- `<input name="parm_1" value="...">`
- Obfuscated `hash32()` JavaScript function (MurmurHash3-based)
- `alicfw` cookie name in obfuscated code

### Solution
The JS computes a hash from:
- `parm_0`, `parm_1` values
- `window.location.host`, `window.location.protocol`
- `document.documentElement.clientWidth`, `clientHeight`

We execute the exact challenge JS in JSDOM to extract cookies:
- `alicfw`: `{hash}|{parm_0}|{parm_1}|{parm_1}` (URL-encoded)
- `alicfw_gfver`: `v1.200309.1`

These cookies must be sent with all subsequent requests to `zujuan.xkw.com`.

**Note**: The login domain (`passport.zujuan.com`) does NOT have this challenge.

## 2. Login Flow (WeChat QR Code)

### Endpoints
| URL | Purpose |
|-----|---------|
| `https://passport.zujuan.com/login` | Login page (session init) |
| `https://passport.zujuan.com/connect/weixin-qrcode?iframe=1&width=220&height=220` | Get QR code |
| `https://passport.zujuan.com/connect/issubscribe?ticket={tkt}&jump_url={url}&r={rand}` | Poll scan status |
| `https://passport.zujuan.com/connect/wxlogin?ticket={tkt}&jump_url={url}` | Complete login |

### Flow
1. GET `/login` — obtain initial session cookies
2. GET `/connect/weixin-qrcode` — extract QR code `<img src>` and `ticket` param
3. Display QR code image to user
4. Poll `/connect/issubscribe` — `{"code": 0}` = waiting, `{"code": 1}` = scanned
5. GET `/connect/wxlogin` — sets login cookies
6. Verify: GET `https://www.zujuan.com/u/index` — check for `#J_realname`

### After Login
Cookies are saved to `config/cookies.pkl` for reuse.

## 3. Question Search

### URL Pattern
```
https://zujuan.xkw.com/{grade}/zsd{knowledge_id}/{filters}/
```

### Parameters
| Parameter | Format | Example |
|-----------|--------|---------|
| grade | `gzsx` (high) / `czsx` (middle) | `gzsx` |
| knowledge_id | `zsd` + digits | `zsd27942` |
| question type | `qt` + type code | `qt2701` (单选) |
| difficulty | `d{1-5}` | `d3` (适中) |
| year | `y{YYYY}` | `y2025` |
| order | `o2` (latest) / `o1` (hot) / `o0` (comprehensive) | `o2` |
| page | `p{n}` (suffix to order) | `o2p2` (page 2) |

### Type Codes (High School)
| Type | Code | Sub-types |
|------|------|-----------|
| 单选 (t1) | 2701 | — |
| 多选 (t2) | 2704 | +01 (2答案), +02 (3答案), +03 (4+答案) |
| 填空 (t3) | 2702 | +01 (单空), +02 (双空), +03 (多空) |
| 解答 (t4) | 2703 | — |

### Type Codes (Middle School)
| Type | Code |
|------|------|
| 单选 | 1101 |
| 多选 | 1104 |
| 填空 | 1102 |
| 解答 | 1103 |

### Example URLs
```
# 集合 + 单选题 + 适中 + 最新
https://zujuan.xkw.com/gzsx/zsd27942/qt2701d3o2/

# 函数 + 解答题 + 困难 + 2025年 + 第2页
https://zujuan.xkw.com/gzsx/zsd27927/qt2703d5y2025o2p2/
```

## 4. Page Structure (Question Data)

### HTML Structure
```html
<div class="tk-quest-item quesroot" questionid="32801513" bankid="11">
  <div class="ques-additional">
    <div class="top-msg">
      <span class="addi-msg">
        <a class="addi-msg ques-src" title="原始出处：...">2026·陕西咸阳·三模</a>
      </span>
    </div>
    <div class="msg-box">
      <div class="left-msg">
        <span class="addi-info"><span class="info-cnt">单选题</span></span>
        <span class="addi-info"><span class="info-cnt">适中(0.74)</span></span>
        <div class="knowledge-list">
          <a class="knowledge-item" title="交集的概念及运算">
          <a class="knowledge-item" title="由对数函数的单调性解不等式">
        </div>
      </div>
    </div>
  </div>
  <div class="wrapper quesdiv">
    <div class="exam-item__cnt">
      <!-- Question text with formula images -->
      1. 已知集合<img src="https://staticzujuan.xkw.com/quesimg/Upload/formula/...">...
    </div>
    <div hidden class="exam-item__opt">
      <div class="item answer"></div>  <!-- Answer image loaded here -->
      <div class=""></div>              <!-- Parse/analysis here -->
    </div>
  </div>
</div>
```

### Extracted Fields
- `id`: Question ID (from `questionid` attribute)
- `source`: Exam source (e.g., "2026·陕西咸阳·三模")
- `question_type`: 单选题/多选题/填空题/解答题
- `difficulty`: 容易/较易/适中/较难/困难
- `score_rate`: Score rate (0-1)
- `knowledge_keywords`: Array of knowledge point names
- `tags`: Labels like "名校"
- `content_html`: Full question HTML
- `content_text`: Plain text of question
- `formula_images`: List of LaTeX formula image URLs

## 5. Answer Images API

### Endpoints
| Endpoint | URL | Description |
|----------|-----|-------------|
| checkQuesParse | `POST /zujuan-api/check_ques_parse` | Get one-time key for answer access |
| getAnswerAndParse | `GET https://imzujuan.xkw.com/getAnswerAndParse/{qid}/{bankId}/{key}` | Combined answer + analysis JPEG |
| Answer (only) | `GET https://imzujuan.xkw.com/Answer/{qid}/{bankId}/{width}/14/28/{key}` | Answer-only image |
| Parse (only) | `GET https://imzujuan.xkw.com/Parse/{qid}/{bankId}/{width}/14/28/{key}` | Analysis-only image |

### Flow
1. **Get CSRF token**: Fetch `https://zujuan.xkw.com/11q{questionId}.html`, extract `__RequestVerificationToken` from hidden `<input>`
2. **Get answer key**: POST `/zujuan-api/check_ques_parse` with form data `{quesId, bankId}`, plus headers:
   - `Content-Type: application/x-www-form-urlencoded`
   - `RequestVerification: {csrf_token}`
   - `Referer: https://zujuan.xkw.com/11q{questionId}.html`
   - `Origin: https://zujuan.xkw.com`
   - Response: `{"key": "...", "first": false}`
3. **Download answer**: GET `https://imzujuan.xkw.com/getAnswerAndParse/{qid}/{bankId}/{key}?enVqdWFu={user_token}&width=766` with headers:
   - `Referer: https://zujuan.xkw.com/11q{questionId}.html`
   - `Origin: https://zujuan.xkw.com`
   - Returns JPEG image (typically 40-80KB)

### Critical: Referer Anti-Leech
Without the `Referer` header pointing to the question detail page, imzujuan.xkw.com returns a 403x19 PNG error image: "您没有权限查看组卷网答案解析，请直接访问站点查看！"

### enVqdWFu Parameter
- `enVqdWFu` = base64("zujuan") — literally the parameter name
- Value: the `user_token` cookie (base64-encoded JSON: `{"userId":"...","user_token":"..."}`)

### Required Cookies
- `userId`: Numeric user ID
- `user_token`: Base64-encoded auth token
- `zujuan-core`: ASP.NET Core session cookie
- `UT1`, `xkw-device-id`, `xkw-fs-id`: Cross-domain tracking cookies

### Daily Limits
- Free users: 30 answers/day
- When limit reached, `checkQuesParse` returns `{"key": "", "first": false}`

## 6. Configuration API (`/zujuan-api/base`)
Returns 654KB JS file with platform configuration:
- `edu[]`: All education levels and subjects
- `diffs[]`: Difficulty levels `[{ID:1,Name:"容易"},...]`
- `answerimg`: `https://imzujuan.xkw.com/Answer`
- `jiexiimg`: `https://imzujuan.xkw.com/Parse`
- `answerAndParse`: `https://imzujuan.xkw.com/getAnswerAndParse`
- `sso_url`: `https://sso.zxxk.com`
- `questypeorder`: Question type order for display

## 7. Limitations

1. **Answer images require login cookies** (userId, user_token, zujuan-core)
2. **Free users limited to 30 answers/day**
3. **Anti-leech protection**: Answer images require correct `Referer` header (question detail page URL)
4. **Question content uses formula images** (PNG) for LaTeX math — text extraction would need OCR
5. **Question list is server-rendered HTML** — no separate JSON API, must be parsed with BeautifulSoup
6. **Cookies expire** — `zujuan-core` and `user_token` have limited lifetime, need browser re-login
