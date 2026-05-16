"""
Main pipeline: Search → Fetch + Snippets → LLM Extract → Structured JSON.
Orchestrates the full question extraction workflow.

Strategy:
1. Generate search queries optimized for finding actual question content
2. Extract from search snippets directly (many contain question+answer)
3. Also fetch pages that allow it (non-JS, non-blocked sites)
4. Send both to LLM for structured extraction
"""

import time
import json
import os
from typing import Optional
from datetime import datetime

from models import SearchRequest, SearchResult, FetchedPage, Question, PipelineResult
from query_templates import QueryTemplates
from search_engine import SearchEngine
from fetcher import PageFetcher
from llm_extractor import LLMExtractor
import config


# Prompt for extracting questions from search snippets (rich text from search results)
SNIPPET_EXTRACTION_PROMPT = """你是一个高中题目数据提取专家。你的任务是从搜索引擎结果摘要（snippets）中找出**高中题目**并将其结构化。

## 搜索上下文
用户需求：{subject} - {knowledge_point} - {question_type} - {difficulty}

## 搜索结果摘要
下面是针对上述需求的搜索结果摘要。每个条目包含标题、URL 和摘要文本。摘要中可能包含部分或完整的题目信息。

{search_snippets}

## 要求

1. 仔细阅读每个搜索结果的摘要，寻找包含完整或部分题目的条目。
2. **如果某个摘要中包含足够完整的题目信息**（题干清晰，至少有题目主体内容），提取它。
3. 如果摘要中包含题干、选项、答案或解析的片段，尽量组合成完整的题目。
4. **只提取搜索结果中实际出现的内容**，不要编造任何内容。
5. 如果摘要中的信息不足以构成一道完整的题目，返回 question_found: false。
6. 在 extraction_notes 中说明信息完整性（如"仅从搜索结果摘要提取，题干完整但缺少选项"）。

## 输出格式

```json
{{
  "question_found": true,
  "subject": "数学/物理/化学",
  "grade": "高中",
  "knowledge_points": ["知识点1"],
  "question_type": "选择题/填空题/解答题",
  "difficulty": "基础/中等/较难",
  "question_text": "题干内容...",
  "question_options": ["A. ...", "B. ..."],
  "answer_text": "答案...",
  "analysis": "解析...",
  "source_url": "来源URL",
  "extraction_confidence": 0.8,
  "extraction_notes": "信息完整性说明"
}}
```

如果所有摘要中都找不到足够完整的题目信息，返回：
```json
{{
  "question_found": false
}}
```
"""


class ExtractionPipeline:
    """End-to-end pipeline for extracting questions from web search."""

    def __init__(
        self,
        search_backend: Optional[str] = None,
        llm_provider: Optional[str] = None,
    ):
        self.search_engine = SearchEngine(backend=search_backend)
        self.fetcher = PageFetcher()
        self.extractor = LLMExtractor(provider=llm_provider)

    def run(self, request: SearchRequest) -> PipelineResult:
        """
        Execute the full pipeline for one search request.

        Steps:
        1. Generate search queries (focusing on content, not site restrictions)
        2. Execute search
        3. Try to extract from search snippets (fast path)
        4. Fetch top non-JS result pages
        5. Extract questions from fetched pages with LLM
        6. Validate and return results
        """
        start_time = time.time()
        result = PipelineResult(request=request)
        print(f"\n{'='*60}")
        print(f"Pipeline: {request.subject} - {request.knowledge_point}")
        print(f"  Type: {request.question_type} | Difficulty: {request.difficulty}")
        print(f"{'='*60}")

        # Step 1: Generate search queries
        print("\n[1/5] Generating search queries...")
        queries = QueryTemplates.generate_queries(request, strategy="all")
        for i, q in enumerate(queries):
            print(f"  Q{i+1}: {q}")
        print(f"  Generated {len(queries)} queries")

        # Step 2: Search
        print("\n[2/5] Executing search...")
        search_results = self.search_engine.search_multi(queries, max_results_per_query=8)
        result.search_results = search_results
        print(f"  Found {len(search_results)} unique results")

        if not search_results:
            result.errors.append("No search results found")
            result.total_time_seconds = time.time() - start_time
            return result

        # Show top results
        for r in search_results[:5]:
            snippet_preview = r.snippet[:80].replace("\n", " ")
            print(f"  [{r.position}] {r.title[:60]}...")
            print(f"      {snippet_preview}...")

        # Step 3: Extract from search snippets (fast path)
        print("\n[3/5] Extracting from search snippets...")
        snippet_questions = self._extract_from_snippets(search_results, request)
        if snippet_questions:
            print(f"  Extracted {len(snippet_questions)} questions from snippets")
            result.questions.extend(snippet_questions)

        # Step 4: Fetch pages
        print("\n[4/5] Fetching result pages...")
        top_urls = []
        for r in search_results:
            from config import JS_ONLY_SITES
            if any(js_site in r.url for js_site in JS_ONLY_SITES):
                continue
            top_urls.append(r.url)
            if len(top_urls) >= 6:
                break

        if top_urls:
            fetched_pages = self.fetcher.fetch_multi(top_urls)
            result.fetched_pages = [p for p in fetched_pages if p.fetch_success]
            success_count = len(result.fetched_pages)
            fail_count = len(fetched_pages) - success_count
            print(f"  Fetched {success_count} pages successfully ({fail_count} failed)")
        else:
            print("  No fetchable URLs (all JS-only sites)")
            result.fetched_pages = []

        # Step 5: Extract questions from fetched pages with LLM
        if result.fetched_pages:
            print("\n[5/5] Extracting questions from fetched pages...")
            page_questions = self.extractor.extract_batch(result.fetched_pages, request)
            # Merge with snippet questions, avoid duplicates by URL
            existing_urls = {q.source_url for q in result.questions}
            for q in page_questions:
                if q.source_url not in existing_urls:
                    result.questions.append(q)
                    existing_urls.add(q.source_url)
            print(f"  Extracted {len(page_questions)} questions from pages")
        else:
            print("\n[5/5] Skipping page extraction (no successful fetches)")

        # Show results
        valid_count = len([q for q in result.questions if q.is_valid])
        print(f"\n  Total: {len(result.questions)} questions ({valid_count} valid)")

        for q in result.questions:
            status = "✓" if q.is_valid else "✗"
            issues = "; ".join(q.validate()) if not q.is_valid else ""
            print(f"  {status} [{q.question_type}] {q.question_text[:80]}...")
            if issues:
                print(f"     Issues: {issues}")

        result.total_time_seconds = round(time.time() - start_time, 1)
        print(f"\nDone in {result.total_time_seconds}s")
        return result

    def _extract_from_snippets(
        self,
        search_results: list[SearchResult],
        request: SearchRequest,
    ) -> list[Question]:
        """Try to extract questions directly from search result snippets."""
        # Build a compact representation of search results with snippets
        snippets_text_parts = []
        for r in search_results[:15]:  # Top 15 results
            snippets_text_parts.append(
                f"[结果 {r.position}]\n标题: {r.title}\nURL: {r.url}\n摘要: {r.snippet}\n"
            )

        snippets_text = "\n---\n".join(snippets_text_parts)

        # Truncate if too long
        if len(snippets_text) > 6000:
            snippets_text = snippets_text[:6000] + "\n\n[... 截断 ...]"

        prompt = SNIPPET_EXTRACTION_PROMPT.format(
            subject=request.subject,
            knowledge_point=request.knowledge_point,
            question_type=request.question_type,
            difficulty=request.difficulty,
            search_snippets=snippets_text,
        )

        try:
            import anthropic
            client = anthropic.Anthropic(
                base_url=config.ANTHROPIC_BASE_URL,
                auth_token=config.ANTHROPIC_AUTH_TOKEN,
            )

            message = client.messages.create(
                model=config.ANTHROPIC_MODEL,
                max_tokens=4096,
                messages=[{"role": "user", "content": prompt}],
            )

            # Extract text from TextBlocks (DeepSeek v4 pro returns ThinkingBlock + TextBlock)
            text_blocks = [
                b.text for b in message.content
                if hasattr(b, 'text')
            ]
            if not text_blocks:
                return []

            response_text = "".join(text_blocks)

            # Parse multiple questions from the response
            return self._parse_snippet_response(response_text)

        except Exception as e:
            print(f"  [WARN] Snippet extraction failed: {e}")
            return []

    def _parse_snippet_response(self, response_text: str) -> list[Question]:
        """Parse LLM response that may contain multiple questions."""
        import re

        # Try to find all JSON objects in the response
        questions = []

        # The LLM might return a single JSON object or an array
        # First try to parse as JSON array
        json_text = response_text.strip()

        # Try array format
        array_match = re.search(r'\[\s*\{[\s\S]*\}\s*\]', json_text)
        if array_match:
            try:
                items = json.loads(array_match.group(0))
                for item in items:
                    q = self._json_to_question(item)
                    if q and q.is_valid:
                        questions.append(q)
                return questions
            except json.JSONDecodeError:
                pass

        # Try single object format
        obj_match = re.search(r'```(?:json)?\s*([\s\S]*?)```', response_text)
        if obj_match:
            json_text = obj_match.group(1)
        else:
            obj_match = re.search(r'\{[\s\S]*\}', response_text)
            if obj_match:
                json_text = obj_match.group(0)

        try:
            data = json.loads(json_text.strip())
            if isinstance(data, dict):
                q = self._json_to_question(data)
                if q and q.is_valid:
                    questions.append(q)
        except json.JSONDecodeError:
            pass

        return questions

    def _json_to_question(self, data: dict) -> Optional[Question]:
        """Convert parsed JSON dict to Question object."""
        if not data.get("question_found", True):
            return None

        return Question(
            subject=data.get("subject") or "",
            grade=data.get("grade") or "高中",
            knowledge_points=data.get("knowledge_points") or [],
            question_type=data.get("question_type") or "",
            difficulty=data.get("difficulty") or "",
            question_text=data.get("question_text") or "",
            question_options=data.get("question_options") or [],
            answer_text=data.get("answer_text") or "",
            analysis=data.get("analysis") or "",
            source_url=data.get("source_url") or "",
            extraction_confidence=data.get("extraction_confidence", 0.5),
            extraction_notes=data.get("extraction_notes") or "",
        )

    def save_result(self, result: PipelineResult, filename: Optional[str] = None):
        """Save pipeline result to JSON file."""
        if filename is None:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            kp = result.request.knowledge_point.replace("/", "_")
            filename = f"{result.request.subject}_{kp}_{ts}.json"

        filepath = os.path.join(config.OUTPUT_DIR, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(result.to_json())
        print(f"Saved result to {filepath}")
        return filepath

    def save_questions(self, result: PipelineResult, filename: Optional[str] = None):
        """Save only valid questions as a JSON array."""
        if filename is None:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            kp = result.request.knowledge_point.replace("/", "_")
            filename = f"questions_{result.request.subject}_{kp}_{ts}.json"

        filepath = os.path.join(config.OUTPUT_DIR, filename)
        valid_questions = [q.to_dict() for q in result.valid_questions()]
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(valid_questions, f, ensure_ascii=False, indent=2)
        print(f"Saved {len(valid_questions)} questions to {filepath}")
        return filepath


def run_batch(requests: list[SearchRequest]) -> list[PipelineResult]:
    """Run the pipeline for multiple search requests."""
    pipeline = ExtractionPipeline()
    results = []

    for i, req in enumerate(requests):
        print(f"\n{'#'*60}")
        print(f"# Batch {i+1}/{len(requests)}")
        print(f"{'#'*60}")
        try:
            result = pipeline.run(req)
            results.append(result)
            pipeline.save_result(result)
            pipeline.save_questions(result)
            time.sleep(3)  # Delay between requests
        except Exception as e:
            print(f"  [FATAL] Pipeline failed: {e}")
            import traceback
            traceback.print_exc()
            results.append(PipelineResult(
                request=req,
                errors=[f"Pipeline failed: {str(e)}"],
            ))

    return results
