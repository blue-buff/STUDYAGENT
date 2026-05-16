"""
Search engine abstraction layer.
Supports DuckDuckGo (free), Brave Search API, and Bing Web Search API.
"""

import time
from typing import Optional
from models import SearchResult
import config


class SearchEngine:
    """Multi-backend search engine for Chinese high school questions."""

    def __init__(self, backend: Optional[str] = None):
        self.backend = backend or config.SEARCH_BACKEND

    def search(self, query: str, max_results: int = None) -> list[SearchResult]:
        """
        Execute a search query.

        Args:
            query: The search query string
            max_results: Max number of results to return (default from config)

        Returns:
            List of SearchResult objects
        """
        max_results = max_results or config.SEARCH_MAX_RESULTS

        if self.backend == "duckduckgo":
            return self._search_duckduckgo(query, max_results)
        elif self.backend == "brave":
            return self._search_brave(query, max_results)
        elif self.backend == "bing":
            return self._search_bing(query, max_results)
        else:
            raise ValueError(f"Unknown search backend: {self.backend}")

    def _search_duckduckgo(self, query: str, max_results: int) -> list[SearchResult]:
        """Search using DuckDuckGo (free, no API key). Uses ddgs (v9+) library."""
        try:
            from ddgs import DDGS
        except ImportError:
            raise ImportError(
                "ddgs not installed. Run: pip install ddgs"
            )

        results = []
        try:
            with DDGS() as ddgs:
                for i, r in enumerate(ddgs.text(query, max_results=max_results)):
                    results.append(SearchResult(
                        title=r.get("title", ""),
                        url=r.get("href", ""),
                        snippet=r.get("body", ""),
                        position=i + 1,
                    ))
        except Exception as e:
            time.sleep(3)
            try:
                with DDGS() as ddgs:
                    for i, r in enumerate(ddgs.text(query, max_results=max_results)):
                        results.append(SearchResult(
                            title=r.get("title", ""),
                            url=r.get("href", ""),
                            snippet=r.get("body", ""),
                            position=i + 1,
                        ))
            except Exception as e2:
                raise RuntimeError(
                    f"DuckDuckGo search failed after retry: {e2}"
                ) from e

        return results

    def _search_brave(self, query: str, max_results: int) -> list[SearchResult]:
        """Search using Brave Search API (free tier: 2,000 queries/month)."""
        if not config.BRAVE_API_KEY:
            raise ValueError("BRAVE_API_KEY not set. Get one at https://brave.com/search/api/")

        import requests

        url = "https://api.search.brave.com/res/v1/web/search"
        headers = {
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
            "X-Subscription-Token": config.BRAVE_API_KEY,
        }
        params = {
            "q": query,
            "count": min(max_results, 20),
            "country": "CN",
            "search_lang": "zh",
        }

        resp = requests.get(url, headers=headers, params=params, timeout=config.HTTP_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()

        results = []
        web_results = data.get("web", {}).get("results", [])
        for i, r in enumerate(web_results[:max_results]):
            results.append(SearchResult(
                title=r.get("title", ""),
                url=r.get("url", ""),
                snippet=r.get("description", ""),
                position=i + 1,
            ))
        return results

    def _search_bing(self, query: str, max_results: int) -> list[SearchResult]:
        """Search using Bing Web Search API (free tier: 1,000 queries/month on Azure)."""
        if not config.BING_API_KEY:
            raise ValueError("BING_API_KEY not set. Get one at Azure Marketplace.")

        import requests

        url = "https://api.bing.microsoft.com/v7.0/search"
        headers = {"Ocp-Apim-Subscription-Key": config.BING_API_KEY}
        params = {
            "q": query,
            "count": min(max_results, 50),
            "mkt": "zh-CN",
            "setLang": "zh-Hans",
        }

        resp = requests.get(url, headers=headers, params=params, timeout=config.HTTP_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()

        results = []
        for i, r in enumerate(data.get("webPages", {}).get("value", [])[:max_results]):
            results.append(SearchResult(
                title=r.get("name", ""),
                url=r.get("url", ""),
                snippet=r.get("snippet", ""),
                position=i + 1,
            ))
        return results

    def search_multi(self, queries: list[str], max_results_per_query: int = 5) -> list[SearchResult]:
        """Search across multiple queries, deduplicating results by URL."""
        seen_urls = set()
        all_results = []

        for query in queries:
            try:
                results = self.search(query, max_results=max_results_per_query)
                for r in results:
                    if r.url not in seen_urls:
                        seen_urls.add(r.url)
                        all_results.append(r)
                time.sleep(1)  # Rate limiting
            except Exception as e:
                # Log and continue with other queries
                print(f"  [WARN] Search failed for '{query[:60]}...': {e}")
                continue

        # Re-number positions
        for i, r in enumerate(all_results):
            r.position = i + 1

        return all_results
