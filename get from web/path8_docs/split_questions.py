"""
LLM-based exam paper question splitter.
Two-pass approach:
  Pass 1: Split full paper text into individual question blocks
  Pass 2: Extract structured fields from each question block
"""

import json
import re
import time
from dataclasses import dataclass, field
from typing import Optional


# Reuse the Question schema from path5 to maintain consistency
@dataclass
class Question:
    subject: str
    grade: str
    knowledge_points: list[str]
    question_type: str
    difficulty: str
    question_text: str
    question_options: list[str] = field(default_factory=list)
    answer_text: str = ""
    analysis: str = ""
    source_url: str = ""
    source_platform: str = ""
    extraction_confidence: float = 1.0
    extraction_notes: str = ""

    def to_dict(self) -> dict:
        return {
            "subject": self.subject,
            "grade": self.grade,
            "knowledge_points": self.knowledge_points,
            "question_type": self.question_type,
            "difficulty": self.difficulty,
            "question_text": self.question_text,
            "question_options": self.question_options,
            "answer_text": self.answer_text,
            "analysis": self.analysis,
            "source_url": self.source_url,
            "source_platform": self.source_platform,
            "extraction_confidence": self.extraction_confidence,
            "extraction_notes": self.extraction_notes,
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)

    def validate(self) -> list[str]:
        issues = []
        if not self.question_text or len(self.question_text) < 10:
            issues.append("question_text is too short or empty")
        if not self.knowledge_points:
            issues.append("knowledge_points is empty")
        if not self.subject:
            issues.append("subject is empty")
        if self.extraction_confidence < 0.3:
            issues.append(f"low confidence: {self.extraction_confidence}")
        return issues

    @property
    def is_valid(self) -> bool:
        return len(self.validate()) == 0


# ── LLM Prompts ────────────────────────────────────────────────────────────

SPLIT_PROMPT = """你是一个高中试卷题目拆分专家。你的任务是将一份完整的试卷文本拆分为独立的题目。

## 试卷内容
{paper_text}

## 拆分规则
1. 识别每道题的起始位置（题号，如 "1."、"1．"、"一、"、"（1）"等）
2. 识别题型标签（一、选择题 / 二、填空题 / 三、解答题 等）
3. 每道题应包含完整的题干内容，选择题要包含所有选项
4. 答案和解析如果在题目附近就包含进来，如果在试卷末尾的统一答案区则单独标注
5. 题目中的数学公式保留原始文本格式
6. 不要漏掉任何题目

## 输出格式
请严格按照以下 JSON 格式输出，只输出 JSON，不要包含其他文字：

```json
{{
  "paper_info": {{
    "title": "试卷标题（如果可从内容推断）",
    "subject": "数学/物理/化学/...",
    "total_questions": 20,
    "sections": ["一、选择题（共X题）", "二、填空题（共X题）", "三、解答题（共X题）"]
  }},
  "questions": [
    {{
      "question_number": 1,
      "section": "一、选择题",
      "question_type": "选择题",
      "question_text": "完整的题干文本，包含所有选项...",
      "answer_text": "如果有随题答案就提取，否则留空",
      "analysis": "如果有随题解析就提取，否则留空"
    }}
  ]
}}
```

注意：
- question_text 必须包含该题的完整内容，不要截断
- 如果试卷末尾有统一的"参考答案"区域，先不要急于提取答案，在 paper_info 中标注"答案在末尾统一区域"
- 对于解答题，如果题目中有 "解：" 开头的部分但不是答案，不要误判为答案"""


EXTRACT_DETAIL_PROMPT = """你是一个高中题目结构化专家。请从以下题目中提取详细的结构化信息。

## 题目内容
试卷来源：{source_url}
题型标签：{section}
题号：{question_number}
题干：
{question_text}

已有答案（如有）：{answer_text}
已有解析（如有）：{analysis}

## 你的任务
1. 判断题目所属的知识点（knowledge_points），从高中数学常见知识点中选择
2. 判断难度（基础/中等/较难/压轴）
3. 如果是选择题且有选项，提取完整选项列表
4. 确认或补充答案和解析
5. 评估提取质量置信度（0-1）

## 输出格式
```json
{{
  "knowledge_points": ["知识点1", "知识点2"],
  "difficulty": "基础/中等/较难/压轴",
  "question_options": ["A. ...", "B. ...", "C. ...", "D. ..."],
  "answer_text": "确认或补充的答案",
  "analysis": "确认或补充的解析",
  "extraction_confidence": 0.85,
  "extraction_notes": "提取说明（如有问题请注明）"
}}
```"""


# ── LLM Client ─────────────────────────────────────────────────────────────

def _call_llm(prompt: str, max_tokens: int = 8192) -> Optional[str]:
    """Call the LLM API (Anthropic-compatible, routed through DeepSeek)."""
    import config as cfg

    if not cfg.ANTHROPIC_AUTH_TOKEN:
        print("  [ERROR] ANTHROPIC_AUTH_TOKEN not set")
        return None

    try:
        import anthropic
        client = anthropic.Anthropic(
            base_url=cfg.ANTHROPIC_BASE_URL,
            auth_token=cfg.ANTHROPIC_AUTH_TOKEN,
        )
        message = client.messages.create(
            model=cfg.ANTHROPIC_MODEL,
            max_tokens=max_tokens,
            thinking={"type": "enabled", "budget_tokens": 1024},
            messages=[{"role": "user", "content": prompt}],
        )
        # Handle multiple content blocks (TextBlock, ThinkingBlock, etc.)
        texts = []
        for block in message.content:
            if hasattr(block, "text") and block.text:
                texts.append(block.text)
        return "\n".join(texts) if texts else None
    except Exception as e:
        print(f"  [ERROR] LLM call failed: {e}")
        return None


def _parse_json_response(response_text: str) -> Optional[dict]:
    """Extract JSON from LLM response (handles markdown code blocks)."""
    json_text = response_text
    code_match = re.search(r'```(?:json)?\s*([\s\S]*?)```', response_text)
    if code_match:
        json_text = code_match.group(1)
    else:
        obj_match = re.search(r'\{[\s\S]*\}', response_text)
        if obj_match:
            json_text = obj_match.group(0)

    try:
        return json.loads(json_text.strip())
    except json.JSONDecodeError as e:
        print(f"  [WARN] Failed to parse JSON: {e}")
        return None


# ── Pass 1: Split Paper into Question Blocks ───────────────────────────────

def split_paper(
    paper_text: str,
    subject: str = "数学",
) -> Optional[dict]:
    """
    Split a full exam paper text into individual question blocks.

    Returns the parsed JSON dict with paper_info and questions list,
    or None if splitting failed.
    """
    # Truncate paper text if too long for context
    max_chars = 30_000
    if len(paper_text) > max_chars:
        print(f"  [WARN] Paper text too long ({len(paper_text)} chars), truncating to {max_chars}")
        paper_text = paper_text[:max_chars] + "\n\n[... 内容过长，已截断 ...]"

    prompt = SPLIT_PROMPT.format(paper_text=paper_text)
    response = _call_llm(prompt, max_tokens=8192)

    if not response:
        return None

    result = _parse_json_response(response)
    return result


# ── Pass 2: Extract Details per Question ───────────────────────────────────

def extract_question_details(
    question_block: dict,
    source_url: str = "",
) -> Optional[Question]:
    """Extract structured fields from a single question block."""
    prompt = EXTRACT_DETAIL_PROMPT.format(
        source_url=source_url,
        section=question_block.get("section", ""),
        question_number=question_block.get("question_number", "?"),
        question_text=question_block.get("question_text", ""),
        answer_text=question_block.get("answer_text", ""),
        analysis=question_block.get("analysis", ""),
    )

    response = _call_llm(prompt, max_tokens=2048)
    if not response:
        return None

    detail = _parse_json_response(response)
    if not detail:
        return None

    return Question(
        subject=question_block.get("subject", ""),
        grade="高中",
        knowledge_points=detail.get("knowledge_points", []),
        question_type=question_block.get("question_type", ""),
        difficulty=detail.get("difficulty", ""),
        question_text=question_block.get("question_text", ""),
        question_options=detail.get("question_options", []),
        answer_text=detail.get("answer_text", ""),
        analysis=detail.get("analysis", ""),
        source_url=source_url,
        extraction_confidence=detail.get("extraction_confidence", 0.5),
        extraction_notes=detail.get("extraction_notes", ""),
    )


# ── Full Pipeline ──────────────────────────────────────────────────────────

def split_and_extract(
    paper_text: str,
    subject: str,
    source_url: str = "",
    source_platform: str = "",
) -> list[Question]:
    """
    Full two-pass pipeline: split paper → extract details for each question.

    Returns list of structured Question objects.
    """
    print(f"  Pass 1: Splitting paper into questions...")
    split_result = split_paper(paper_text, subject)

    if not split_result:
        print("  [ERROR] Paper splitting failed")
        return []

    questions_raw = split_result.get("questions", [])
    paper_info = split_result.get("paper_info", {})
    print(f"  Found {len(questions_raw)} questions in paper: {paper_info.get('title', 'Unknown')}")

    # Check if answers are in a separate section at the end
    # If so, extract answer mapping first
    print(f"  Pass 2: Extracting details for each question...")
    questions = []
    for i, qblock in enumerate(questions_raw):
        qnum = qblock.get("question_number", i + 1)
        print(f"    Processing question {qnum}/{len(questions_raw)}...")

        detail = extract_question_details(qblock, source_url)
        if detail:
            detail.subject = subject
            detail.source_platform = source_platform
            detail.source_url = source_url
            questions.append(detail)
        else:
            # Fallback: create basic question from the split block
            questions.append(Question(
                subject=subject,
                grade="高中",
                knowledge_points=[],
                question_type=qblock.get("question_type", ""),
                difficulty="",
                question_text=qblock.get("question_text", ""),
                answer_text=qblock.get("answer_text", ""),
                analysis=qblock.get("analysis", ""),
                source_url=source_url,
                source_platform=source_platform,
                extraction_confidence=0.3,
                extraction_notes="Pass 2 extraction failed, using Pass 1 data only",
            ))

        time.sleep(0.3)

    print(f"  Extracted {len(questions)} questions total")
    return questions
