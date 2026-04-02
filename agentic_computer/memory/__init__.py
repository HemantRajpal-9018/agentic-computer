"""Memory subsystem for the agentic-computer agent.

Provides persistent, searchable memory with vector similarity, automatic
compression of stale entries, and progressive-disclosure retrieval that
respects a token budget.

Public API::

    from agentic_computer.memory import MemoryStore, MemoryCompressor, MemoryRetriever

    async with MemoryStore("./data/agentic.db") as store:
        entry = await store.add("the sky is blue", MemoryType.SEMANTIC)

        compressor = MemoryCompressor()
        if await compressor.should_compress(store):
            await compressor.run_compression(store)

        retriever = MemoryRetriever(store)
        entries = await retriever.retrieve("sky colour", context_budget=2048)
"""

from .compressor import MemoryCompressor
from .retriever import MemoryRetriever
from .schema import MemoryEntry, MemoryQuery, MemorySearchResult, MemoryType
from .store import MemoryStore

__all__ = [
    "MemoryCompressor",
    "MemoryEntry",
    "MemoryQuery",
    "MemoryRetriever",
    "MemorySearchResult",
    "MemoryStore",
    "MemoryType",
]
