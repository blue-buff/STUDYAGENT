"""
Extract exam paper text from document platform viewers using Playwright.
Handles JS-rendered pages, text layer extraction, and pagination.
"""

import asyncio
import re
import sys
from dataclasses import dataclass

from playwright.async_api import async_playwright, Page

import config


@dataclass
class ExtractedPaper:
    """Full text content extracted from a document platform paper."""
    url: str
    platform: str
    title: str
    full_text: str
    page_count: int
    pages_text: list[str]  # per-page text
    extract_success: bool
    error_message: str = ""


async def _wait_for_content(page: Page, timeout_ms: int = 15_000) -> bool:
    """Wait for document content to load on the viewer page."""
    try:
        # Wait for any common text container
        await page.wait_for_selector(
            "body", timeout=timeout_ms
        )
        # Additional wait for JS to render the viewer
        await asyncio.sleep(config.PLAYWRIGHT_WAIT_AFTER_LOAD / 1000)
        return True
    except Exception:
        return False


async def _extract_text_from_page(page: Page, platform: str) -> str:
    """Extract text from the current viewer page using platform-specific selectors."""
    info = config.PLATFORMS.get(platform, {})

    # Try platform-specific text layer selectors first
    selectors_to_try = [
        info.get("text_layer_selector", ""),
        ".reader-txt", ".txt", ".txt-layer", "[class*=reader-txt]",
        ".page-txt", "[class*=txt-content]", ".text-content",
        ".reader-word-layer", ".word-layer",
        # Fallback: any element with text-looking class
        "[class*=text]", "[class*=txt]",
    ]

    # Remove empty selectors
    selectors_to_try = [s for s in selectors_to_try if s]

    texts = []
    for selector in selectors_to_try:
        try:
            elements = await page.query_selector_all(selector)
            if elements:
                for el in elements:
                    text = await el.inner_text()
                    if text and len(text.strip()) > 5:
                        texts.append(text.strip())
                if texts:
                    break
        except Exception:
            continue

    if not texts:
        # Last resort: get all visible text from body
        try:
            body_text = await page.inner_text("body")
            if body_text:
                texts.append(body_text)
        except Exception:
            pass

    return "\n".join(texts)


async def _get_page_count(page: Page, platform: str) -> int:
    """Try to detect the total number of pages in the document."""
    # Look for page indicators like "1/10" or "共10页"
    try:
        page_text = await page.inner_text("body")
        patterns = [
            r"(\d+)\s*/\s*(\d+)",     # "1/10"
            r"共\s*(\d+)\s*页",         # "共10页"
            r"第\s*\d+\s*页.*?共\s*(\d+)\s*页",  # "第1页 共10页"
        ]
        for pat in patterns:
            m = re.search(pat, page_text)
            if m:
                # Return the total count (second group for 1/10, first for others)
                count = int(m.group(2) if m.lastindex >= 2 else m.group(1))
                if 1 <= count <= 50:
                    return count
    except Exception:
        pass
    return 1  # Default: assume at least 1 page


async def _click_next_page(page: Page, platform: str) -> bool:
    """Try to navigate to the next page. Returns True if successful."""
    info = config.PLATFORMS.get(platform, {})
    selectors = [
        info.get("next_page_btn", ""),
        ".next-page", ".page-next", "[class*=next]",
        ".next", ".arrow-right", ".page-down",
        "button[title*=下一页]", "a[title*=下一页]",
    ]
    selectors = [s for s in selectors if s]

    for selector in selectors:
        try:
            btn = await page.query_selector(selector)
            if btn:
                is_disabled = await btn.get_attribute("disabled")
                classes = await btn.get_attribute("class") or ""
                if is_disabled or "disabled" in classes:
                    continue
                await btn.click()
                await asyncio.sleep(1.5)  # Wait for next page to render
                return True
        except Exception:
            continue

    # Fallback: try PageDown key
    try:
        await page.keyboard.press("PageDown")
        await asyncio.sleep(1.5)
        return True
    except Exception:
        pass

    return False


async def _scroll_page(page: Page) -> None:
    """Scroll the viewer to trigger lazy loading."""
    try:
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await asyncio.sleep(0.5)
        await page.evaluate("window.scrollTo(0, 0)")
        await asyncio.sleep(0.5)
    except Exception:
        pass


async def extract_paper(
    url: str,
    platform: str,
    max_pages: int = None,
) -> ExtractedPaper:
    """
    Load a document platform page with Playwright and extract its full text.

    Args:
        url: The document viewer URL
        platform: Platform key ("wenku", "doc88", "docin")
        max_pages: Max pages to scroll through (default from config)

    Returns:
        ExtractedPaper with full text content
    """
    max_pages = max_pages or config.MAX_PAGES_PER_PAPER
    platform_name = config.PLATFORMS.get(platform, {}).get("name", platform)

    print(f"  Extracting from {platform_name}: {url[:80]}...")

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=config.PLAYWRIGHT_HEADLESS,
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
        page.set_default_timeout(config.PLAYWRIGHT_TIMEOUT)

        try:
            await page.goto(url, wait_until="domcontentloaded")
            content_loaded = await _wait_for_content(page)

            if not content_loaded:
                return ExtractedPaper(
                    url=url, platform=platform, title="",
                    full_text="", page_count=0, pages_text=[],
                    extract_success=False,
                    error_message="Content did not load within timeout",
                )

            await _scroll_page(page)

            # Get document title
            title = await page.title()
            page_count = await _get_page_count(page, platform)
            actual_pages = min(page_count, max_pages)

            # Extract text page by page
            pages_text = []
            for i in range(actual_pages):
                print(f"    Extracting page {i+1}/{actual_pages}...")
                page_text = await _extract_text_from_page(page, platform)
                if page_text:
                    pages_text.append(page_text)

                if i < actual_pages - 1:
                    moved = await _click_next_page(page, platform)
                    if not moved:
                        print(f"    Could not navigate past page {i+1}, stopping")
                        break

            full_text = "\n\n--- PAGE BREAK ---\n\n".join(pages_text)

            # Cleanup: remove excessive whitespace
            full_text = re.sub(r"\n{4,}", "\n\n\n", full_text)
            full_text = re.sub(r"[ \t]{3,}", "  ", full_text)

            success = len(full_text) > 100
            return ExtractedPaper(
                url=url,
                platform=platform,
                title=title,
                full_text=full_text,
                page_count=len(pages_text),
                pages_text=pages_text,
                extract_success=success,
                error_message="" if success else f"Extracted only {len(full_text)} chars of text",
            )

        except Exception as e:
            return ExtractedPaper(
                url=url, platform=platform, title="",
                full_text="", page_count=0, pages_text=[],
                extract_success=False, error_message=str(e),
            )
        finally:
            await browser.close()


async def extract_papers(
    paper_urls: list[tuple[str, str]],
    max_pages: int = None,
) -> list[ExtractedPaper]:
    """Extract multiple papers sequentially."""
    results = []
    for url, platform in paper_urls:
        paper = await extract_paper(url, platform, max_pages=max_pages)
        results.append(paper)
    return results


if __name__ == "__main__":
    # Quick test with a provided URL
    if len(sys.argv) > 1:
        url = sys.argv[1]
        platform = sys.argv[2] if len(sys.argv) > 2 else "wenku"
        result = asyncio.run(extract_paper(url, platform))
        print(f"\nTitle: {result.title}")
        print(f"Pages: {result.page_count}")
        print(f"Success: {result.extract_success}")
        if result.error_message:
            print(f"Error: {result.error_message}")
        print(f"\n--- Full Text (first 1000 chars) ---\n{result.full_text[:1000]}")
