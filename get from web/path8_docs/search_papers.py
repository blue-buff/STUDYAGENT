"""
Search Baidu Wenku via Playwright and extract rich paper content from search results.
DuckDuckGo is broken; Doc88/Docin search pages are JS-rendered and return no results.
Baidu Wenku search pages return rich snippets with full question text.
"""

import asyncio
import re
import time
from dataclasses import dataclass, field

from playwright.async_api import async_playwright

import config


@dataclass
class PaperSnippet:
    """Content extracted from a Baidu Wenku search result snippet."""
    title: str
    url: str
    platform: str
    snippet_text: str    # The full text content from the snippet
    position: int

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "url": self.url,
            "platform": self.platform,
            "snippet_text": self.snippet_text,
            "position": self.position,
        }

    @property
    def text_length(self) -> int:
        return len(self.snippet_text)


async def _search_wenku(page, query: str, max_results: int = 10) -> list[PaperSnippet]:
    """Search Baidu Wenku and extract rich snippets from results."""
    search_url = f"https://wenku.baidu.com/search?word={query}"
    await page.goto(search_url, wait_until="load", timeout=config.PLAYWRIGHT_TIMEOUT)
    await asyncio.sleep(5)  # Wait for JS to render results

    html = await page.content()

    # Extract document URLs with titles from the HTML
    # Baidu Wenku embeds doc URLs in JavaScript/HTML
    doc_urls = list(set(re.findall(
        r'https?://wenku\.baidu\.com/view/[a-f0-9]+\.html[^"\']*',
        html
    )))

    if not doc_urls:
        print("    No document URLs found in page")
        return []

    # Get all visible text
    body_text = await page.inner_text("body")
    lines = [l.strip() for l in body_text.split('\n') if l.strip()]

    # Extract paper snippets: look for title lines followed by content
    # Title patterns: ends with 试卷, 试题, 及答案, 真题, 练习题 etc.
    title_pattern = re.compile(
        r'.*(?:试卷|试题|及答案|真题|练习题|测试题|复习|专题|单元).*'
    )

    snippets = []
    current_title = None
    current_content_lines = []

    for line in lines:
        is_title = bool(title_pattern.match(line)) and len(line) < 100

        if is_title:
            # Save previous snippet
            if current_title and current_content_lines:
                content = '\n'.join(current_content_lines)
                if len(content) > 50:  # Minimum meaningful content
                    # Find matching URL
                    matched_url = ""
                    for u in doc_urls:
                        # Try to match by position or content
                        if len(snippets) < len(doc_urls):
                            matched_url = doc_urls[len(snippets)]
                            break

                    snippets.append(PaperSnippet(
                        title=current_title,
                        url=matched_url or f"https://wenku.baidu.com/search?word={query}",
                        platform="wenku",
                        snippet_text=content,
                        position=len(snippets) + 1,
                    ))

            current_title = line
            current_content_lines = []
        elif current_title:
            # Skip navigation/UI lines
            if len(line) < 10 or line in ("新建", "上传", "收藏", "下载", "搜索文档"):
                continue
            if re.match(r'^\d+\.?\d*$', line):  # Just a number
                continue
            if line.startswith("共") and "页" in line:  # "共9页"
                continue
            if line.endswith("阅读"):
                continue
            current_content_lines.append(line)

    # Save last snippet
    if current_title and current_content_lines:
        content = '\n'.join(current_content_lines)
        if len(content) > 50:
            matched_url = ""
            if len(snippets) < len(doc_urls):
                matched_url = doc_urls[len(snippets)]
            snippets.append(PaperSnippet(
                title=current_title,
                url=matched_url or f"https://wenku.baidu.com/search?word={query}",
                platform="wenku",
                snippet_text=content,
                position=len(snippets) + 1,
            ))

    return snippets[:max_results]


async def _search_all(
    subject: str,
    knowledge_point: str,
    max_results: int = 10,
) -> list[PaperSnippet]:
    """Search across multiple queries to maximize content."""
    all_snippets = []

    queries = [
        f"高中{subject} {knowledge_point} 试卷 答案",
        f"{subject} {knowledge_point} 高考真题",
        f"{subject} {knowledge_point} 试题及答案",
        f"高中{subject} {knowledge_point} 练习题",
    ]

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=not config.PLAYWRIGHT_HEADLESS,
        )
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
            locale="zh-CN",
        )
        page = await context.new_page()

        for query in queries:
            print(f"  Searching Baidu Wenku: {query}")
            try:
                snippets = await _search_wenku(page, query, max_results // len(queries) + 3)
                print(f"    Found {len(snippets)} snippets")
                all_snippets.extend(snippets)
                await asyncio.sleep(2)  # Politeness delay between queries
            except Exception as e:
                print(f"    [WARN] Search failed: {e}")

        await browser.close()

    # Deduplicate by title similarity
    seen_titles = set()
    unique = []
    for s in all_snippets:
        # Simple dedup: first 30 chars of title
        title_key = s.title[:30]
        if title_key not in seen_titles:
            seen_titles.add(title_key)
            unique.append(s)

    # Sort by content richness (prefer snippets with answers)
    def score(s: PaperSnippet) -> int:
        s_score = 0
        if "答案" in s.snippet_text:
            s_score += 10
        if "解析" in s.snippet_text:
            s_score += 5
        if "A" in s.snippet_text and "B" in s.snippet_text:
            s_score += 3  # Has multiple choice options
        if len(s.snippet_text) > 200:
            s_score += 3  # Rich content
        return s_score

    unique.sort(key=score, reverse=True)
    return unique


def search_papers(
    subject: str,
    knowledge_point: str,
    max_results: int = None,
) -> list[PaperSnippet]:
    """
    Search Baidu Wenku and extract rich snippet content.

    Args:
        subject: Subject to search (e.g., "数学")
        knowledge_point: Knowledge point (e.g., "导数")
        max_results: Max results to return

    Returns:
        List of PaperSnippet objects with rich text content
    """
    max_results = max_results or config.MAX_SEARCH_RESULTS
    print(f"  Searching Baidu Wenku for: {subject} {knowledge_point}")
    snippets = asyncio.run(_search_all(subject, knowledge_point, max_results))
    print(f"  Total unique snippets: {len(snippets)}")
    return snippets


if __name__ == "__main__":
    # Quick test
    results = search_papers("数学", "导数", max_results=5)
    for r in results:
        print(f"\n{'='*60}")
        print(f"[{r.platform}] {r.title}")
        print(f"URL: {r.url}")
        print(f"Text length: {r.text_length}")
        print(f"---\n{r.snippet_text[:500]}...")
