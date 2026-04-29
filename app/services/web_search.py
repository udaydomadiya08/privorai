from __future__ import annotations

import httpx

from app.config import Settings
from app.models import SearchResult


class SecureWebSearchClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @property
    def enabled(self) -> bool:
        return self.settings.enable_web_search and bool(self.settings.tavily_api_key)

    async def search(self, query: str) -> SearchResult:
        if not self.enabled:
            return SearchResult(query=query, provider="disabled", results=[])

        payload = {
            "api_key": self.settings.tavily_api_key,
            "query": query,
            "search_depth": "basic",
            "max_results": 5,
        }
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post("https://api.tavily.com/search", json=payload)
            response.raise_for_status()
            data = response.json()
        results = [
            {"title": item.get("title", ""), "url": item.get("url", ""), "content": item.get("content", "")}
            for item in data.get("results", [])
        ]
        return SearchResult(query=query, provider="tavily", results=results)
