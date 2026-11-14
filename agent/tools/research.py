"""
Web research tool — search + fetch + summarize with source list.
Registered as 'web_research' in the tool registry.
"""

from __future__ import annotations

import logging
from typing import List

from agent.types import RiskLevel, ToolResult
from agent.tools.registry import tool

logger = logging.getLogger(__name__)


@tool(
    "web_research",
    "Internet pe kuch search karke result summarize karna",
    risk_level=RiskLevel.LOW,
    timeout=45,
    category="research",
    param_descriptions={"query": "Search query ya research topic", "max_results": "Kitne results chahiye (default 5)"},
)
def web_research(query: str, max_results: int = 5) -> ToolResult:
    """Search the web and return a summarised answer with sources."""
    try:
        import requests
        from html.parser import HTMLParser

        # DuckDuckGo Lite — no API key needed
        search_url = "https://lite.duckduckgo.com/lite/"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html",
        }
        resp = requests.post(
            search_url,
            data={"q": query},
            headers=headers,
            timeout=10,
        )
        resp.raise_for_status()

        # Parse search results (title + snippet + url)
        results: List[dict] = _parse_ddg_lite(resp.text)
        if not results:
            # Fallback: try fetching first result directly
            return ToolResult.ok(
                message=f"'{query}' ke liye koi result nahi mila.",
                data={"query": query, "results": []},
            )

        top = results[:max_results]
        snippets = "\n".join(
            f"{i+1}. {r['title']}: {r['snippet']}" for i, r in enumerate(top)
        )
        sources = [r.get("url", "") for r in top if r.get("url")]

        summary = f"'{query}' ke baare mein:\n{snippets}"
        return ToolResult.ok(
            message=summary,
            data={"query": query, "results": top, "sources": sources},
        )

    except Exception as exc:
        logger.error("web_research failed: %s", exc)
        return ToolResult.err(f"Web search mein dikkat: {exc}", retryable=True)


def _parse_ddg_lite(html: str) -> List[dict]:
    """Minimal parser for DuckDuckGo Lite HTML results."""
    results: List[dict] = []
    try:
        from html.parser import HTMLParser

        class _P(HTMLParser):
            def __init__(self):
                super().__init__()
                self._results = []
                self._cur: dict = {}
                self._in_a = False
                self._in_snippet = False

            def handle_starttag(self, tag, attrs):
                a = dict(attrs)
                if tag == "a" and "result-link" in a.get("class", ""):
                    self._in_a = True
                    self._cur = {"url": a.get("href", ""), "title": "", "snippet": ""}
                if tag == "td" and "result-snippet" in a.get("class", ""):
                    self._in_snippet = True

            def handle_endtag(self, tag):
                if tag == "a":
                    self._in_a = False
                if tag == "td":
                    if self._in_snippet and self._cur:
                        self._results.append(self._cur)
                        self._cur = {}
                    self._in_snippet = False

            def handle_data(self, data):
                data = data.strip()
                if not data:
                    return
                if self._in_a and self._cur:
                    self._cur["title"] = data
                if self._in_snippet and self._cur:
                    self._cur["snippet"] = (self._cur.get("snippet", "") + " " + data).strip()

        parser = _P()
        parser.feed(html)
        return parser._results
    except Exception:
        return []


@tool(
    "fetch_page",
    "Kisi bhi URL ka content padhna",
    risk_level=RiskLevel.LOW,
    timeout=20,
    category="research",
    param_descriptions={"url": "Page ka URL", "max_chars": "Kitne characters chahiye (default 3000)"},
)
def fetch_page(url: str, max_chars: int = 3000) -> ToolResult:
    """Fetch a URL and return its readable text content."""
    try:
        import requests
        from html.parser import HTMLParser

        resp = requests.get(
            url,
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=10,
        )
        resp.raise_for_status()

        # Strip HTML tags
        class _TextExtractor(HTMLParser):
            def __init__(self):
                super().__init__()
                self.texts: List[str] = []
                self._skip = False

            def handle_starttag(self, tag, attrs):
                if tag in ("script", "style", "nav", "footer", "header"):
                    self._skip = True

            def handle_endtag(self, tag):
                if tag in ("script", "style", "nav", "footer", "header"):
                    self._skip = False

            def handle_data(self, data):
                if not self._skip and data.strip():
                    self.texts.append(data.strip())

        extractor = _TextExtractor()
        extractor.feed(resp.text)
        text = " ".join(extractor.texts)[:max_chars]

        return ToolResult.ok(message=text, data={"url": url, "length": len(text)})
    except Exception as exc:
        return ToolResult.err(f"Page fetch nahi ho paya: {exc}", retryable=True)
