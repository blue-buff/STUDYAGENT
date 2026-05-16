"""
Data models for the search→extract pipeline.
"""

from dataclasses import dataclass, field, asdict
from typing import Optional
import json


@dataclass
class SearchRequest:
    """User's question search requirements."""
    subject: str              # 数学/物理/化学
    knowledge_point: str      # 导数/牛顿定律/...
    question_type: str        # 选择题/填空题/解答题
    difficulty: str           # 基础/中等/较难/压轴
    grade: str = "高中"
    count: int = 5

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class SearchResult:
    """A single search result item."""
    title: str
    url: str
    snippet: str
    position: int

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class FetchedPage:
    """Content fetched from a search result URL."""
    url: str
    title: str
    text_content: str        # Extracted text (truncated for LLM)
    raw_html_length: int
    fetch_success: bool
    error_message: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Question:
    """Structured question extracted by LLM."""
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
    extraction_confidence: float = 1.0         # LLM self-assessed confidence (0-1)
    extraction_notes: str = ""                 # LLM notes on extraction quality

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)

    def validate(self) -> list[str]:
        """Check required fields. Returns list of missing/problematic fields."""
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


@dataclass
class PipelineResult:
    """Result of running the full pipeline for one search request."""
    request: SearchRequest
    search_results: list[SearchResult] = field(default_factory=list)
    fetched_pages: list[FetchedPage] = field(default_factory=list)
    questions: list[Question] = field(default_factory=list)
    total_time_seconds: float = 0.0
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "request": self.request.to_dict(),
            "search_results": [r.to_dict() for r in self.search_results],
            "fetched_pages": [p.to_dict() for p in self.fetched_pages],
            "questions": [q.to_dict() for q in self.questions],
            "total_time_seconds": self.total_time_seconds,
            "errors": self.errors,
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)

    def valid_questions(self) -> list[Question]:
        return [q for q in self.questions if q.is_valid]
