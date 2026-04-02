"""Tests for the memory module."""

from __future__ import annotations

import asyncio
import os
import tempfile
from pathlib import Path

import pytest

from agentic_computer.memory.schema import (
    MemoryEntry,
    MemoryQuery,
    MemorySearchResult,
    MemoryType,
)
from agentic_computer.memory.store import MemoryStore
from agentic_computer.memory.compressor import MemoryCompressor
from agentic_computer.memory.retriever import MemoryRetriever


class TestMemorySchema:
    """Tests for memory data models."""

    def test_memory_type_enum(self) -> None:
        assert MemoryType.EPISODIC.value == "episodic"
        assert MemoryType.SEMANTIC.value == "semantic"
        assert MemoryType.PROCEDURAL.value == "procedural"
        assert MemoryType.WORKING.value == "working"

    def test_create_memory_entry(self) -> None:
        entry = MemoryEntry(
            content="The user prefers Python over JavaScript",
            memory_type=MemoryType.SEMANTIC,
        )
        assert entry.content == "The user prefers Python over JavaScript"
        assert entry.memory_type == MemoryType.SEMANTIC
        assert isinstance(entry.id, str)
        assert entry.access_count == 0
        assert entry.importance_score == 0.5

    def test_memory_entry_with_embedding(self) -> None:
        embedding = [0.1, 0.2, 0.3, 0.4, 0.5]
        entry = MemoryEntry(
            content="Test memory",
            memory_type=MemoryType.EPISODIC,
            embedding=embedding,
        )
        assert entry.embedding == embedding
        assert len(entry.embedding) == 5

    def test_memory_query(self) -> None:
        query = MemoryQuery(
            query="Python preferences",
            memory_type=MemoryType.SEMANTIC,
            limit=5,
            min_similarity=0.7,
        )
        assert query.query == "Python preferences"
        assert query.limit == 5
        assert query.min_similarity == 0.7

    def test_memory_search_result(self) -> None:
        entry = MemoryEntry(content="test", memory_type=MemoryType.WORKING)
        result = MemorySearchResult(entry=entry, similarity_score=0.95)
        assert result.similarity_score == 0.95
        assert result.entry.content == "test"


class TestMemoryStore:
    """Tests for the SQLite memory store."""

    @pytest.fixture
    async def store(self, tmp_path: Path) -> MemoryStore:
        """Create a temporary memory store."""
        db_path = tmp_path / "test_memory.db"
        store = MemoryStore(db_path=db_path)
        await store.init_db()
        return store

    @pytest.mark.asyncio
    async def test_init_db(self, tmp_path: Path) -> None:
        db_path = tmp_path / "init_test.db"
        store = MemoryStore(db_path=db_path)
        await store.init_db()
        assert db_path.exists()

    @pytest.mark.asyncio
    async def test_add_memory(self, store: MemoryStore) -> None:
        entry = await store.add(
            content="Test memory entry",
            memory_type=MemoryType.EPISODIC,
            metadata={"source": "test"},
        )
        assert entry.content == "Test memory entry"
        assert entry.memory_type == MemoryType.EPISODIC
        assert entry.metadata["source"] == "test"

    @pytest.mark.asyncio
    async def test_get_memory(self, store: MemoryStore) -> None:
        added = await store.add(
            content="Retrievable memory",
            memory_type=MemoryType.SEMANTIC,
        )
        retrieved = await store.get(added.id)
        assert retrieved is not None
        assert retrieved.content == "Retrievable memory"
        assert retrieved.id == added.id

    @pytest.mark.asyncio
    async def test_get_nonexistent(self, store: MemoryStore) -> None:
        result = await store.get("nonexistent-id")
        assert result is None

    @pytest.mark.asyncio
    async def test_delete_memory(self, store: MemoryStore) -> None:
        added = await store.add(content="To delete", memory_type=MemoryType.WORKING)
        deleted = await store.delete(added.id)
        assert deleted is True
        result = await store.get(added.id)
        assert result is None

    @pytest.mark.asyncio
    async def test_get_recent(self, store: MemoryStore) -> None:
        for i in range(5):
            await store.add(
                content=f"Memory {i}",
                memory_type=MemoryType.EPISODIC,
            )
        recent = await store.get_recent(limit=3)
        assert len(recent) == 3

    @pytest.mark.asyncio
    async def test_update_access(self, store: MemoryStore) -> None:
        added = await store.add(content="Access me", memory_type=MemoryType.SEMANTIC)
        assert added.access_count == 0
        await store.update_access(added.id)
        updated = await store.get(added.id)
        assert updated is not None
        assert updated.access_count == 1


class TestMemoryCompressor:
    """Tests for memory compression."""

    def test_calculate_importance(self) -> None:
        compressor = MemoryCompressor()
        entry = MemoryEntry(
            content="Important memory",
            memory_type=MemoryType.SEMANTIC,
            access_count=10,
            importance_score=0.8,
        )
        score = compressor._calculate_importance(entry)
        assert 0.0 <= score <= 1.0

    def test_importance_increases_with_access(self) -> None:
        compressor = MemoryCompressor()
        low_access = MemoryEntry(
            content="Rarely accessed", memory_type=MemoryType.EPISODIC, access_count=1
        )
        high_access = MemoryEntry(
            content="Often accessed", memory_type=MemoryType.EPISODIC, access_count=50
        )
        assert compressor._calculate_importance(high_access) > compressor._calculate_importance(low_access)


class TestMemoryRetriever:
    """Tests for memory retrieval."""

    def test_estimate_tokens(self) -> None:
        # _estimate_tokens is a static method
        text = "Hello world this is a test"  # 26 chars -> ~6-7 tokens
        tokens = MemoryRetriever._estimate_tokens(text)
        assert 5 <= tokens <= 10

    def test_empty_text_tokens(self) -> None:
        assert MemoryRetriever._estimate_tokens("") == 0
