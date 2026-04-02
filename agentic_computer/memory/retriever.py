"""Progressive-disclosure memory retriever.

Retrieves memories from the store in order of relevance, progressively
adding entries until a configurable token budget is exhausted.  This
ensures the calling agent receives the most useful context without
blowing up its prompt window.
"""

from __future__ import annotations

from .schema import MemoryEntry, MemoryQuery, MemorySearchResult, MemoryType
from .store import MemoryStore

# Rough average characters-per-token for English text (GPT-family models).
_CHARS_PER_TOKEN = 4


class MemoryRetriever:
    """Retrieves and ranks memories from a MemoryStore with budget control.

    The retriever supports two modes:

    * **Budget-bounded** (:meth:`retrieve`): returns the most relevant
      memories whose combined token estimate does not exceed
      ``context_budget``.
    * **Simple top-k** (:meth:`retrieve_relevant`): returns up to
      ``limit`` results sorted by relevance.

    Usage::

        retriever = MemoryRetriever(store)
        entries = await retriever.retrieve("deployment steps", context_budget=2000)
    """

    def __init__(self, store: MemoryStore) -> None:
        self._store = store

    # -- public API ----------------------------------------------------------

    async def retrieve(
        self,
        query: str,
        context_budget: int = 4096,
        memory_type: MemoryType | None = None,
        min_similarity: float = 0.0,
    ) -> list[MemoryEntry]:
        """Progressively retrieve memories within a token budget.

        The algorithm:
        1. Fetch a large candidate set sorted by relevance.
        2. Walk down the ranked list, accumulating token cost.
        3. Stop adding once the next entry would exceed the budget.
        4. Update access timestamps for every returned entry.

        Args:
            query: Free-text query string.
            context_budget: Maximum estimated tokens for all returned content.
            memory_type: Optional filter to restrict results by type.
            min_similarity: Minimum similarity threshold for candidates.

        Returns:
            A list of MemoryEntry objects fitting within the budget,
            ordered from most to least relevant.
        """
        # Fetch more candidates than we'll likely need so we have room to fill
        candidates = await self.retrieve_relevant(
            query,
            limit=200,
            memory_type=memory_type,
            min_similarity=min_similarity,
        )

        selected: list[MemoryEntry] = []
        tokens_used = 0

        for result in candidates:
            entry_tokens = self._estimate_tokens(result.entry.content)
            if tokens_used + entry_tokens > context_budget:
                # If we haven't added anything yet, still include the top result
                # even if it exceeds the budget (better than returning nothing).
                if not selected:
                    selected.append(result.entry)
                    await self._store.update_access(result.entry.id)
                break
            selected.append(result.entry)
            tokens_used += entry_tokens
            await self._store.update_access(result.entry.id)

        return selected

    async def retrieve_relevant(
        self,
        query: str,
        limit: int = 10,
        memory_type: MemoryType | None = None,
        min_similarity: float = 0.0,
    ) -> list[MemorySearchResult]:
        """Return the top-*limit* search results ranked by relevance.

        This is a thin wrapper over :pymethod:`MemoryStore.search` that
        applies additional re-ranking based on a composite score of
        similarity, importance, and recency.

        Args:
            query: Free-text query string.
            limit: Maximum results to return.
            memory_type: Optional type filter.
            min_similarity: Minimum cosine-similarity threshold.

        Returns:
            Sorted list of MemorySearchResult.
        """
        # Pull a larger set so we can re-rank effectively
        search_query = MemoryQuery(
            query=query,
            memory_type=memory_type,
            limit=max(limit * 3, 50),
            min_similarity=min_similarity,
        )
        raw_results = await self._store.search(search_query)

        ranked = self._rank_by_relevance(raw_results, query)
        return ranked[:limit]

    # -- internals -----------------------------------------------------------

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        """Estimate the number of tokens in *text*.

        Uses a simple heuristic: ``len(text) / 4``.  This approximates
        the average token length observed across GPT-family tokenisers
        for English prose.  The estimate is deliberately conservative
        (slightly over-counting) so we don't accidentally exceed the
        budget.

        Args:
            text: The input string.

        Returns:
            Estimated token count (always >= 1 for non-empty text).
        """
        if not text:
            return 0
        return max(1, len(text) // _CHARS_PER_TOKEN)

    @staticmethod
    def _rank_by_relevance(
        results: list[MemorySearchResult],
        query: str,
    ) -> list[MemorySearchResult]:
        """Re-rank search results using a composite relevance score.

        The composite score blends:
        * **Similarity** (weight 0.50): raw cosine similarity from the store.
        * **Importance** (weight 0.30): the entry's stored importance score.
        * **Keyword overlap** (weight 0.20): fraction of query words found in
          the entry content (case-insensitive).

        Args:
            results: Unranked (or pre-ranked) search results.
            query: The original query text for keyword overlap.

        Returns:
            A new list sorted by composite score descending.
        """
        if not results:
            return []

        query_words = set(query.lower().split())

        def _composite(result: MemorySearchResult) -> float:
            sim = result.similarity_score
            importance = result.entry.importance_score

            # Keyword overlap ratio
            if query_words:
                content_lower = result.entry.content.lower()
                hits = sum(1 for w in query_words if w in content_lower)
                keyword_score = hits / len(query_words)
            else:
                keyword_score = 0.0

            return 0.50 * sim + 0.30 * importance + 0.20 * keyword_score

        scored = sorted(results, key=_composite, reverse=True)
        return scored
