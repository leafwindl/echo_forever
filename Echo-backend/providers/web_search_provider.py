from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Protocol

import httpx

from shared.config import settings


@dataclass(frozen=True)
class WebSearchRequest:
    query: str
    locale: str = "zh-CN"
    maximum_results: int = 5
    recency_days: int | None = None


@dataclass(frozen=True)
class WebSearchItem:
    title: str
    canonical_url: str
    snippet: str
    published_at: str | None = None
    source_domain: str = ""


@dataclass(frozen=True)
class WebSearchResult:
    results: tuple[WebSearchItem, ...] = field(default_factory=tuple)
    retrieved_at: str = ""


class WebSearchProvider(Protocol):
    async def search(self, request: WebSearchRequest) -> WebSearchResult: ...


class TavilyWebSearchProvider:
    async def search(self, request: WebSearchRequest) -> WebSearchResult:
        if not settings.web_search_enabled or not settings.web_search_api_key:
            return WebSearchResult(retrieved_at=datetime.now(timezone.utc).isoformat())
        payload: dict[str, object] = {
            "api_key": settings.web_search_api_key,
            "query": request.query,
            "max_results": min(request.maximum_results, settings.web_search_max_results),
            "search_depth": "basic",
            "include_answer": False,
            "include_raw_content": False,
        }
        if request.recency_days:
            payload["days"] = request.recency_days
        async with httpx.AsyncClient(timeout=settings.web_search_timeout_seconds) as client:
            response = await client.post(settings.web_search_base_url, json=payload)
            response.raise_for_status()
            data = response.json()
        items = []
        for item in data.get("results", []):
            url = str(item.get("url", ""))
            if not url.startswith(("https://", "http://")):
                continue
            domain = httpx.URL(url).host or ""
            items.append(
                WebSearchItem(
                    title=str(item.get("title", ""))[:300],
                    canonical_url=url,
                    snippet=str(item.get("content", ""))[:1200],
                    published_at=item.get("published_date"),
                    source_domain=domain,
                )
            )
        return WebSearchResult(
            results=tuple(items),
            retrieved_at=datetime.now(timezone.utc).isoformat(),
        )

