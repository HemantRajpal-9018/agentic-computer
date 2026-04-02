"""Web search tool with pluggable provider backends.

Supports Serper (Google Search API) and Tavily as search providers.
The active provider is determined by :mod:`agentic_computer.config`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import httpx

from agentic_computer.config import get_settings
from agentic_computer.tools.registry import BaseTool, ToolResult, ToolSpec

logger = logging.getLogger(__name__)

# Default number of search results to request.
_DEFAULT_NUM_RESULTS: int = 5


@dataclass(frozen=True)
class SearchResult:
    """A single search result returned by a provider.

    Attributes:
        title: Page title.
        url: Page URL.
        snippet: Short text excerpt from the page.
    """

    title: str
    url: str
    snippet: str


# ---------------------------------------------------------------------------
# Provider base and implementations
# ---------------------------------------------------------------------------


class _SearchProvider:
    """Base class for search provider backends."""

    async def search(self, query: str, num_results: int) -> list[SearchResult]:
        """Execute a search and return parsed results."""
        raise NotImplementedError


class _SerperProvider(_SearchProvider):
    """Serper.dev Google Search JSON API backend.

    Expects the ``SERPER_API_KEY`` to be set via config.
    """

    API_URL = "https://google.serper.dev/search"

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    async def search(self, query: str, num_results: int) -> list[SearchResult]:
        """Call the Serper API and return structured results.

        Args:
            query: Search query string.
            num_results: Maximum number of results to return.
        """
        headers = {"X-API-KEY": self._api_key, "Content-Type": "application/json"}
        payload: dict[str, Any] = {"q": query, "num": num_results}

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(self.API_URL, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()

        results: list[SearchResult] = []
        for item in data.get("organic", [])[:num_results]:
            results.append(
                SearchResult(
                    title=item.get("title", ""),
                    url=item.get("link", ""),
                    snippet=item.get("snippet", ""),
                )
            )
        return results


class _TavilyProvider(_SearchProvider):
    """Tavily Search API backend.

    Expects the ``TAVILY_API_KEY`` to be set via config.
    """

    API_URL = "https://api.tavily.com/search"

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    async def search(self, query: str, num_results: int) -> list[SearchResult]:
        """Call the Tavily API and return structured results.

        Args:
            query: Search query string.
            num_results: Maximum number of results to return.
        """
        payload: dict[str, Any] = {
            "api_key": self._api_key,
            "query": query,
            "max_results": num_results,
            "search_depth": "basic",
        }

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(self.API_URL, json=payload)
            resp.raise_for_status()
            data = resp.json()

        results: list[SearchResult] = []
        for item in data.get("results", [])[:num_results]:
            results.append(
                SearchResult(
                    title=item.get("title", ""),
                    url=item.get("url", ""),
                    snippet=item.get("content", ""),
                )
            )
        return results


# ---------------------------------------------------------------------------
# WebSearchTool
# ---------------------------------------------------------------------------


def _build_provider(provider_name: str, api_key: str) -> _SearchProvider:
    """Instantiate the appropriate search provider.

    Args:
        provider_name: ``"serper"`` or ``"tavily"``.
        api_key: API key for the selected provider.

    Raises:
        ValueError: If *provider_name* is not recognised.
    """
    if provider_name == "serper":
        return _SerperProvider(api_key)
    if provider_name == "tavily":
        return _TavilyProvider(api_key)
    raise ValueError(f"Unknown search provider: '{provider_name}'. Use 'serper' or 'tavily'.")


class WebSearchTool(BaseTool):
    """Web search tool backed by Serper or Tavily.

    The provider is selected from :func:`agentic_computer.config.get_settings`.
    """

    def __init__(self) -> None:
        settings = get_settings()
        self._provider: _SearchProvider = _build_provider(
            settings.search.provider,
            settings.search.api_key,
        )

    # ------------------------------------------------------------------
    # BaseTool interface
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        return "web_search"

    @property
    def description(self) -> str:
        return "Search the web using Serper or Tavily and return structured results."

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name,
            description=self.description,
            parameters={
                "query": {"type": "string", "description": "Search query."},
                "num_results": {
                    "type": "integer",
                    "description": f"Number of results (default {_DEFAULT_NUM_RESULTS}).",
                },
            },
            required_params=["query"],
        )

    async def execute(self, **kwargs: Any) -> ToolResult:
        """Run a web search and return results."""
        query = kwargs.get("query", "")
        num_results = int(kwargs.get("num_results", _DEFAULT_NUM_RESULTS))
        return await self.search(query, num_results)

    # ------------------------------------------------------------------
    # Public method
    # ------------------------------------------------------------------

    async def search(self, query: str, num_results: int = _DEFAULT_NUM_RESULTS) -> ToolResult:
        """Execute a web search and return a list of :class:`SearchResult`.

        Args:
            query: The search query.
            num_results: Maximum number of results to retrieve.

        Returns:
            ToolResult whose ``output`` is a list of serialised SearchResult dicts.
        """
        if not query.strip():
            return ToolResult(success=False, error="Search query must not be empty")

        try:
            results = await self._provider.search(query, num_results)
            serialised = [
                {"title": r.title, "url": r.url, "snippet": r.snippet} for r in results
            ]
            return ToolResult(success=True, output=serialised)
        except httpx.HTTPStatusError as exc:
            return ToolResult(
                success=False,
                error=f"Search API returned HTTP {exc.response.status_code}: {exc.response.text}",
            )
        except Exception as exc:
            logger.exception("Web search failed")
            return ToolResult(success=False, error=f"Search failed: {exc}")
