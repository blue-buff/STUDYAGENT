"""
Web page fetcher and text extraction module.
Fetches search result pages and extracts clean text for LLM processing.
"""

import re
import time
from typing import Optional
import requests
from bs4 import BeautifulSoup
from models import FetchedPage
import config


class PageFetcher:
    """Fetches web pages and extracts readable text content."""

    # Max characters to send to LLM (controls cost and context window)
    MAX_TEXT_LENGTH = 8000

    # Common non-content elements to remove
    REMOVE_TAGS = [
        "script", "style", "nav", "footer", "header",
        "aside", "noscript", "iframe", "form", "button",
    ]
    REMOVE_CLASS_IDS = [
        "sidebar", "comment", "advertisement", "ad", "banner",
        "menu", "navigation", "footer", "header", "popup",
        "recommend", "related", "share", "login", "register",
    ]

    def __init__(self, timeout: int = None, max_text_length: int = None):
        self.timeout = timeout or config.HTTP_TIMEOUT
        self.max_text_length = max_text_length or self.MAX_TEXT_LENGTH
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        })

    def _is_js_only_site(self, url: str) -> bool:
        """Check if URL belongs to a known JS-only site."""
        from config import JS_ONLY_SITES
        for site in JS_ONLY_SITES:
            if site in url:
                return True
        return False

    def fetch(self, url: str) -> FetchedPage:
        """Fetch a single page and extract text."""
        if self._is_js_only_site(url):
            return FetchedPage(
                url=url,
                title="",
                text_content="",
                raw_html_length=0,
                fetch_success=False,
                error_message="JS-only site (requires Playwright), skipped",
            )

        try:
            resp = self.session.get(url, timeout=self.timeout, allow_redirects=True)
            resp.raise_for_status()

            # Detect encoding
            resp.encoding = resp.apparent_encoding or "utf-8"

            text = self._extract_text(resp.text)

            # Mark as failed if we got no real content
            if not text or len(text) < 100:
                return FetchedPage(
                    url=url,
                    title=self._extract_title(resp.text),
                    text_content=text,
                    raw_html_length=len(resp.text),
                    fetch_success=False,
                    error_message="Page has no extractable text content (likely JS-rendered)",
                )

            return FetchedPage(
                url=url,
                title=self._extract_title(resp.text),
                text_content=text,
                raw_html_length=len(resp.text),
                fetch_success=True,
            )
        except Exception as e:
            return FetchedPage(
                url=url,
                title="",
                text_content="",
                raw_html_length=0,
                fetch_success=False,
                error_message=str(e),
            )

    def fetch_multi(self, urls: list[str], delay: float = 0.5) -> list[FetchedPage]:
        """Fetch multiple pages sequentially with delay for politeness."""
        pages = []
        for url in urls:
            page = self.fetch(url)
            pages.append(page)
            if page.fetch_success:
                time.sleep(delay)  # Politeness delay
        return pages

    def _extract_text(self, html: str) -> str:
        """Extract readable text from HTML, removing boilerplate."""
        soup = BeautifulSoup(html, "html.parser")

        # Remove non-content elements
        for tag in self.REMOVE_TAGS:
            for el in soup.find_all(tag):
                el.decompose()

        # Remove elements by class/id patterns
        for pattern in self.REMOVE_CLASS_IDS:
            for el in soup.find_all(class_=re.compile(pattern, re.I)):
                el.decompose()
            for el in soup.find_all(id=re.compile(pattern, re.I)):
                el.decompose()

        # Get text
        text = soup.get_text(separator="\n", strip=True)

        # Clean up whitespace
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = re.sub(r"[ \t]{2,}", " ", text)

        # Truncate to max length for LLM
        if len(text) > self.max_text_length:
            text = text[:self.max_text_length] + "\n\n[... content truncated ...]"

        return text

    def _extract_title(self, html: str) -> str:
        """Extract page title from HTML."""
        soup = BeautifulSoup(html, "html.parser")
        title_tag = soup.find("title")
        if title_tag:
            return title_tag.get_text(strip=True)
        return ""
