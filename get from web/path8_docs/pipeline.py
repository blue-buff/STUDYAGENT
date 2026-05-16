"""
End-to-end pipeline: Search Baidu Wenku → Extract Snippets → Split → Structured JSON.
"""

import argparse
import json
import os
import time
from dataclasses import dataclass, field

import config
from search_papers import search_papers, PaperSnippet
from split_questions import split_and_extract, Question


@dataclass
class PipelineResult:
    subject: str
    knowledge_point: str
    snippets_found: list[dict] = field(default_factory=list)
    questions: list[dict] = field(default_factory=list)
    total_time_seconds: float = 0.0
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "subject": self.subject,
            "knowledge_point": self.knowledge_point,
            "snippets_found": self.snippets_found,
            "questions": self.questions,
            "total_time_seconds": self.total_time_seconds,
            "errors": self.errors,
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)


def _compile_paper_text(snippets: list[PaperSnippet]) -> str:
    """Combine multiple search snippets into a single paper-like text for LLM splitting."""
    parts = []
    for i, s in enumerate(snippets):
        parts.append(f"--- 文档片段 {i+1}: {s.title} ---")
        parts.append(s.snippet_text)
        parts.append("")
    return "\n".join(parts)


def run_pipeline(
    subject: str,
    knowledge_point: str,
    max_snippets: int = None,
    dry_run: bool = False,
) -> PipelineResult:
    """
    Run the full extraction pipeline.

    Args:
        subject: Subject to search (e.g., "数学")
        knowledge_point: Knowledge point (e.g., "导数")
        max_snippets: Max snippets to process (default from config)
        dry_run: If True, only search without LLM processing
    """
    max_snippets = max_snippets or config.MAX_SEARCH_RESULTS
    max_snippets = min(max_snippets, 15)

    result = PipelineResult(
        subject=subject,
        knowledge_point=knowledge_point,
    )
    start = time.time()

    print(f"\n{'='*60}")
    print(f"Path 8: Document Platform Exam Paper Pipeline")
    print(f"Subject: {subject} | Knowledge Point: {knowledge_point}")
    print(f"Max Snippets: {max_snippets} | Dry Run: {dry_run}")
    print(f"{'='*60}\n")

    # ── Step 1: Search & Extract ───────────────────────────────────────
    print("[Step 1/2] Searching Baidu Wenku and extracting snippets...")
    snippets = search_papers(subject, knowledge_point, max_results=max_snippets)
    result.snippets_found = [s.to_dict() for s in snippets]

    if not snippets:
        msg = "No content found on Baidu Wenku"
        result.errors.append(msg)
        print(f"  {msg}")
        result.total_time_seconds = time.time() - start
        return result

    total_chars = sum(s.text_length for s in snippets)
    print(f"  Found {len(snippets)} snippets, {total_chars} total chars")

    if dry_run:
        print("\n  [DRY RUN] Skipping LLM splitting. Snippets found:")
        for s in snippets[:5]:
            print(f"    [{s.platform}] {s.title} ({s.text_length} chars)")
            print(f"      {s.snippet_text[:120]}...")
        result.total_time_seconds = time.time() - start
        return result

    # ── Step 2: Compile & Split into Questions ─────────────────────────
    print(f"\n[Step 2/2] Compiling snippets & splitting into questions...")
    paper_text = _compile_paper_text(snippets)

    # Group snippets by their URLs for source tracking
    source_url = snippets[0].url if snippets else ""

    all_questions = split_and_extract(
        paper_text=paper_text,
        subject=subject,
        source_url=source_url,
        source_platform="wenku",
    )

    result.questions = [q.to_dict() for q in all_questions]

    # ── Save Results ───────────────────────────────────────────────────
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    safe_kp = knowledge_point.replace("/", "_")
    output_path = os.path.join(
        config.OUTPUT_DIR,
        f"{subject}_{safe_kp}_{timestamp}.json",
    )

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(result.to_json())

    result.total_time_seconds = time.time() - start

    # ── Summary ────────────────────────────────────────────────────────
    valid = len([q for q in all_questions if q.is_valid])
    print(f"\n{'='*60}")
    print(f"Pipeline Complete")
    print(f"  Snippets found:   {len(snippets)}")
    print(f"  Total chars:      {total_chars}")
    print(f"  Questions found:  {len(all_questions)}")
    print(f"  Valid questions:  {valid}")
    print(f"  Total time:       {result.total_time_seconds:.1f}s")
    print(f"  Output:           {output_path}")
    print(f"{'='*60}\n")

    return result


def main():
    parser = argparse.ArgumentParser(
        description="Path 8: Document Platform Exam Paper → Structured Questions",
    )
    parser.add_argument(
        "--subject", "-s",
        default="数学",
        help="Subject to search (default: 数学)",
    )
    parser.add_argument(
        "--knowledge-point", "-k",
        required=True,
        help="Knowledge point to search (e.g., 导数, 三角函数)",
    )
    parser.add_argument(
        "--max-snippets", "-n",
        type=int,
        default=None,
        help="Max snippets to process (default: 10)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Search only, skip LLM processing",
    )
    parser.add_argument(
        "--search-only",
        action="store_true",
        help="Search and print results, then exit",
    )

    args = parser.parse_args()

    if args.search_only:
        snippets = search_papers(args.subject, args.knowledge_point)
        print(f"\nFound {len(snippets)} snippets:")
        for s in snippets:
            print(f"\n  [{s.platform}] {s.title} ({s.text_length} chars)")
            print(f"  URL: {s.url}")
            print(f"  {s.snippet_text[:300]}...")
        return

    return run_pipeline(
        subject=args.subject,
        knowledge_point=args.knowledge_point,
        max_snippets=args.max_snippets,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
