"""
LLM-based question extraction from web page content.
Uses Anthropic API (routed through DeepSeek) to parse structured question data.
"""

import json
import time
from typing import Optional
from models import Question, SearchRequest, FetchedPage
import config


EXTRACTION_PROMPT = """你是一个高中题目数据提取专家。你的任务是从给定的网页文本中找出**一道完整的高中题目**，并将其结构化为 JSON。

## 要求

1. **只提取网页中存在的真实题目**，不要编造任何内容。如果找不到完整的题目（至少包含题干），返回 question_found: false。
2. 题干部分即使含有公式（LaTeX）也要保留原始文本。
3. 如果是选择题，提取所有选项并存入 question_options 数组。
4. 答案和解析部分如果在原文中明确出现就提取，否则留空字符串（不要猜测答案）。
5. 根据题目内容推断知识点（knowledge_points）和难度（difficulty）。
6. 给出你对提取质量的置信度（0-1），以及任何值得注意的提取问题。

## 输出格式

请严格按照以下 JSON 格式输出（不要包含其他文字）：

```json
{{
  "question_found": true,
  "subject": "数学/物理/化学/生物/英语/语文",
  "grade": "高中",
  "knowledge_points": ["知识点1", "知识点2"],
  "question_type": "选择题/填空题/解答题/实验题/计算题",
  "difficulty": "基础/中等/较难/压轴",
  "question_text": "完整的题干内容...",
  "question_options": ["A. ...", "B. ...", "C. ...", "D. ..."],
  "answer_text": "答案内容...",
  "analysis": "解析内容...",
  "extraction_confidence": 0.85,
  "extraction_notes": "提取质量说明"
}}
```

如果网页中没有找到完整题目，返回：
```json
{{
  "question_found": false
}}
```

## 目标需求（参考）
用户正在搜索：{subject} - {knowledge_point} - {question_type} - {difficulty}

## 网页内容
来源：{source_url}
标题：{page_title}

{page_text}
"""


class LLMExtractor:
    """Extracts structured question data from web pages using LLM."""

    def __init__(self, provider: Optional[str] = None, model: Optional[str] = None):
        self.provider = provider or config.LLM_PROVIDER
        self.model = model or config.ANTHROPIC_MODEL

    def extract(
        self,
        page: FetchedPage,
        request: Optional[SearchRequest] = None,
    ) -> Optional[Question]:
        """
        Extract a question from a fetched page.

        Args:
            page: The fetched web page content
            request: Optional search request for context

        Returns:
            Question object if found, None otherwise
        """
        if not page.fetch_success or not page.text_content:
            return None

        if self.provider == "claude":
            return self._extract_claude(page, request)
        elif self.provider == "openai":
            return self._extract_openai(page, request)
        else:
            raise ValueError(f"Unknown LLM provider: {self.provider}")

    def extract_batch(
        self,
        pages: list[FetchedPage],
        request: Optional[SearchRequest] = None,
    ) -> list[Question]:
        """Extract questions from multiple pages."""
        questions = []
        for page in pages:
            q = self.extract(page, request)
            if q:
                questions.append(q)
            time.sleep(0.5)  # Rate limiting
        return questions

    def _build_prompt(self, page: FetchedPage, request: Optional[SearchRequest]) -> str:
        """Build the extraction prompt."""
        if request:
            subject = request.subject
            kp = request.knowledge_point
            qt = request.question_type
            diff = request.difficulty
        else:
            subject = "未知"
            kp = "未知"
            qt = "未知"
            diff = "未知"

        return EXTRACTION_PROMPT.format(
            subject=subject,
            knowledge_point=kp,
            question_type=qt,
            difficulty=diff,
            source_url=page.url,
            page_title=page.title,
            page_text=page.text_content,
        )

    def _extract_claude(
        self,
        page: FetchedPage,
        request: Optional[SearchRequest] = None,
    ) -> Optional[Question]:
        """Extract using Claude API (Anthropic SDK routed through DeepSeek)."""
        import anthropic

        client = anthropic.Anthropic(
            base_url=config.ANTHROPIC_BASE_URL,
            auth_token=config.ANTHROPIC_AUTH_TOKEN,
        )

        prompt = self._build_prompt(page, request)

        try:
            message = client.messages.create(
                model=self.model,
                max_tokens=4096,
                messages=[{"role": "user", "content": prompt}],
            )

            # DeepSeek v4 pro returns ThinkingBlock + TextBlock; extract text
            text_blocks = [
                b.text for b in message.content
                if hasattr(b, 'text')
            ]
            if not text_blocks:
                print(f"  [WARN] No text in response for {page.url[:80]}")
                return None
            response_text = "".join(text_blocks)
            return self._parse_response(response_text, page.url)

        except Exception as e:
            print(f"  [ERROR] LLM extraction failed for {page.url[:80]}: {e}")
            return None

    def _extract_openai(
        self,
        page: FetchedPage,
        request: Optional[SearchRequest] = None,
    ) -> Optional[Question]:
        """Extract using OpenAI API."""
        import openai

        client = openai.OpenAI(api_key=config.OPENAI_API_KEY)

        prompt = self._build_prompt(page, request)

        try:
            response = client.chat.completions.create(
                model=config.OPENAI_MODEL,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=4096,
                temperature=0.1,
            )
            response_text = response.choices[0].message.content
            return self._parse_response(response_text, page.url)

        except Exception as e:
            print(f"  [ERROR] OpenAI extraction failed for {page.url[:80]}: {e}")
            return None

    def _parse_response(self, response_text: str, source_url: str) -> Optional[Question]:
        """Parse LLM JSON response into a Question object."""
        # Extract JSON from response (may be wrapped in markdown code blocks)
        json_text = response_text

        # Try to find JSON in code blocks first
        import re
        code_match = re.search(r'```(?:json)?\s*([\s\S]*?)```', response_text)
        if code_match:
            json_text = code_match.group(1)
        else:
            # Try to find JSON object directly
            obj_match = re.search(r'\{[\s\S]*\}', response_text)
            if obj_match:
                json_text = obj_match.group(0)

        try:
            data = json.loads(json_text.strip())
        except json.JSONDecodeError:
            print(f"  [WARN] Failed to parse LLM JSON response")
            return None

        # Check if question was found
        if not data.get("question_found", True):
            return None

        # Build Question object (ensure all string fields are non-None)
        question = Question(
            subject=data.get("subject") or "",
            grade=data.get("grade") or "高中",
            knowledge_points=data.get("knowledge_points") or [],
            question_type=data.get("question_type") or "",
            difficulty=data.get("difficulty") or "",
            question_text=data.get("question_text") or "",
            question_options=data.get("question_options") or [],
            answer_text=data.get("answer_text") or "",
            analysis=data.get("analysis") or "",
            source_url=source_url,
            extraction_confidence=data.get("extraction_confidence", 0.5),
            extraction_notes=data.get("extraction_notes") or "",
        )

        return question
