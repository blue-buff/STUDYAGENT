#!/usr/bin/env python3
"""
Path 5: Search Engine + LLM Question Extraction Pipeline
Main execution script.

Usage:
    python3 run_example.py                    # Run all 12 test cases
    python3 run_example.py --test             # Run first 2 cases as a quick test
    python3 run_example.py --case 3           # Run a specific test case
    python3 run_example.py --dry-run          # Only search, no LLM extraction
"""

import sys
import os
import argparse

# Ensure we can import from this directory
sys.path.insert(0, os.path.dirname(__file__))

from pipeline import ExtractionPipeline, run_batch
from query_templates import TEST_CASES, QueryTemplates, SearchRequest
from search_engine import SearchEngine
from fetcher import PageFetcher
import config


def main():
    parser = argparse.ArgumentParser(
        description="Path 5: Search + LLM Question Extraction Pipeline"
    )
    parser.add_argument(
        "--test", action="store_true",
        help="Quick test: only run first 2 test cases"
    )
    parser.add_argument(
        "--case", type=int, default=None,
        help="Run a specific test case (1-12)"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Only search and fetch, skip LLM extraction"
    )
    parser.add_argument(
        "--max", type=int, default=12,
        help="Max number of test cases to run"
    )
    parser.add_argument(
        "--search-only", action="store_true",
        help="Only test search, don't fetch pages or extract"
    )
    parser.add_argument(
        "--query", type=str, default=None,
        help="Run a custom search query directly"
    )
    args = parser.parse_args()

    # Custom query mode
    if args.query:
        print(f"Search query: {args.query}")
        engine = SearchEngine()
        results = engine.search(args.query, max_results=10)
        for r in results:
            print(f"  [{r.position}] {r.title}")
            print(f"      {r.url}")
            print(f"      {r.snippet[:100]}...")
            print()
        return

    # Search-only mode
    if args.search_only:
        req = TEST_CASES[0] if not args.case else TEST_CASES[args.case - 1]
        print(f"Testing search for: {req.subject} - {req.knowledge_point}")
        queries = QueryTemplates.generate_queries(req, strategy="all")
        engine = SearchEngine()
        results = engine.search_multi(queries, max_results_per_query=5)
        for r in results:
            print(f"  [{r.position}] {r.title}")
            print(f"      {r.url}")
            print(f"      {r.snippet[:120]}...")
            print()
        return

    # Select test cases
    if args.case:
        cases = [TEST_CASES[args.case - 1]]
    elif args.test:
        cases = TEST_CASES[:2]
    else:
        cases = TEST_CASES[:args.max]

    print(f"Running pipeline for {len(cases)} test case(s)")
    print(f"Search backend: {config.SEARCH_BACKEND}")
    print(f"LLM provider: {config.LLM_PROVIDER} ({config.ANTHROPIC_MODEL})")
    print(f"Output dir: {config.OUTPUT_DIR}")

    if args.dry_run:
        # Dry run: search + fetch only
        for i, req in enumerate(cases):
            print(f"\n{'#'*60}")
            print(f"# DRY RUN {i+1}/{len(cases)}: {req.subject} - {req.knowledge_point}")
            print(f"{'#'*60}")
            queries = QueryTemplates.generate_queries(req)
            engine = SearchEngine()
            results = engine.search_multi(queries, max_results_per_query=3)
            print(f"  Search: {len(results)} results")
            fetcher = PageFetcher()
            urls = [r.url for r in results[:3]]
            pages = fetcher.fetch_multi(urls)
            for p in pages:
                if p.fetch_success:
                    print(f"  ✓ {p.url[:80]} ({len(p.text_content)} chars)")
                else:
                    print(f"  ✗ {p.url[:80]} ({p.error_message})")
    else:
        # Full pipeline
        results = run_batch(cases)

        # Final summary
        print(f"\n{'='*60}")
        print("FINAL SUMMARY")
        print(f"{'='*60}")
        total_valid = 0
        total_questions = 0
        for r in results:
            valid = len(r.valid_questions())
            total = len(r.questions)
            total_valid += valid
            total_questions += total
            status = "✓" if valid > 0 else "✗"
            print(f"  {status} {r.request.subject}-{r.request.knowledge_point}: "
                  f"{valid}/{total} valid questions")
        print(f"\n  Total: {total_valid}/{total_questions} valid questions across {len(results)} searches")
        print(f"  Output files: {config.OUTPUT_DIR}/")


if __name__ == "__main__":
    main()
