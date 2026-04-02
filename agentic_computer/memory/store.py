"""SQLite-backed memory store with vector similarity search.

Provides persistent storage for MemoryEntry objects using aiosqlite for async
I/O and numpy for cosine-similarity computation over dense embeddings.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiosqlite
import numpy as np

from .schema import MemoryEntry, MemoryQuery, MemorySearchResult, MemoryType

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS memories (
    id          TEXT PRIMARY KEY,
    content     TEXT NOT NULL,
    type        TEXT NOT NULL,
    embedding_json TEXT,
    metadata_json  TEXT NOT NULL DEFAULT '{}',
    created_at  TEXT NOT NULL,
    accessed_at TEXT NOT NULL,
    access_count INTEGER NOT NULL DEFAULT 0,
    importance  REAL NOT NULL DEFAULT 0.5
);
"""

_CREATE_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_memories_type ON memories(type);
CREATE INDEX IF NOT EXISTS idx_memories_importance ON memories(importance DESC);
CREATE INDEX IF NOT EXISTS idx_memories_accessed_at ON memories(accessed_at DESC);
"""


def _iso(dt: datetime) -> str:
    """Format a datetime as ISO-8601 string in UTC."""
    return dt.astimezone(timezone.utc).isoformat()


def _parse_iso(s: str) -> datetime:
    """Parse an ISO-8601 string back into a timezone-aware datetime."""
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _row_to_entry(row: aiosqlite.Row) -> MemoryEntry:
    """Convert a raw SQLite row into a MemoryEntry dataclass."""
    embedding_raw = row[3]  # embedding_json
    embedding: list[float] | None = json.loads(embedding_raw) if embedding_raw else None
    metadata: dict[str, Any] = json.loads(row[4])  # metadata_json
    return MemoryEntry(
        id=row[0],
        content=row[1],
        memory_type=MemoryType(row[2]),
        embedding=embedding,
        metadata=metadata,
        created_at=_parse_iso(row[5]),
        accessed_at=_parse_iso(row[6]),
        access_count=row[7],
        importance_score=row[8],
    )


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors using numpy.

    Returns a float in [-1, 1].  When either vector has zero magnitude the
    result is 0.0 (undefined case treated as no similarity).
    """
    va = np.asarray(a, dtype=np.float64)
    vb = np.asarray(b, dtype=np.float64)
    dot = float(np.dot(va, vb))
    norm_a = float(np.linalg.norm(va))
    norm_b = float(np.linalg.norm(vb))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


class MemoryStore:
    """Async SQLite memory store with optional vector similarity search.

    Usage::

        store = MemoryStore("/path/to/db.sqlite")
        await store.init_db()
        entry = await store.add("hello world", MemoryType.SEMANTIC)
        results = await store.search(MemoryQuery(query="hello", limit=5))
        await store.close()

    The store keeps the database connection open for the lifetime of the
    instance.  Call :meth:`close` when done, or use as an async context
    manager::

        async with MemoryStore(path) as store:
            ...
    """

    def __init__(self, db_path: str | Path = ":memory:") -> None:
        self._db_path = str(db_path)
        self._db: aiosqlite.Connection | None = None

    # -- lifecycle -----------------------------------------------------------

    async def init_db(self) -> None:
        """Open the database connection and create tables if they don't exist."""
        if self._db_path != ":memory:":
            Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(self._db_path)
        await self._db.execute(_CREATE_TABLE_SQL)
        await self._db.executescript(_CREATE_INDEX_SQL)
        await self._db.commit()

    async def close(self) -> None:
        """Close the underlying database connection."""
        if self._db is not None:
            await self._db.close()
            self._db = None

    async def __aenter__(self) -> MemoryStore:
        await self.init_db()
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()

    @property
    def _conn(self) -> aiosqlite.Connection:
        if self._db is None:
            raise RuntimeError("MemoryStore is not initialised — call init_db() first")
        return self._db

    # -- CRUD ----------------------------------------------------------------

    async def add(
        self,
        content: str,
        memory_type: MemoryType = MemoryType.WORKING,
        metadata: dict[str, Any] | None = None,
        embedding: list[float] | None = None,
        importance: float = 0.5,
    ) -> MemoryEntry:
        """Persist a new memory and return the created MemoryEntry.

        Args:
            content: Textual content of the memory.
            memory_type: Classification of the memory.
            metadata: Optional metadata dictionary.
            embedding: Optional dense vector for similarity search.
            importance: Importance score in [0, 1].

        Returns:
            The newly created MemoryEntry.
        """
        now = datetime.now(timezone.utc)
        entry = MemoryEntry(
            content=content,
            memory_type=memory_type,
            embedding=embedding,
            metadata=metadata or {},
            created_at=now,
            accessed_at=now,
            access_count=0,
            importance_score=max(0.0, min(1.0, importance)),
        )
        embedding_json = json.dumps(entry.embedding) if entry.embedding is not None else None
        await self._conn.execute(
            """
            INSERT INTO memories
                (id, content, type, embedding_json, metadata_json,
                 created_at, accessed_at, access_count, importance)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                entry.id,
                entry.content,
                entry.memory_type.value,
                embedding_json,
                json.dumps(entry.metadata),
                _iso(entry.created_at),
                _iso(entry.accessed_at),
                entry.access_count,
                entry.importance_score,
            ),
        )
        await self._conn.commit()
        return entry

    async def get(self, memory_id: str) -> MemoryEntry | None:
        """Retrieve a single memory by its ID, or *None* if not found."""
        cursor = await self._conn.execute(
            "SELECT id, content, type, embedding_json, metadata_json, "
            "created_at, accessed_at, access_count, importance "
            "FROM memories WHERE id = ?",
            (memory_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return _row_to_entry(row)

    async def delete(self, memory_id: str) -> bool:
        """Delete a memory by ID.  Returns True if a row was actually removed."""
        cursor = await self._conn.execute(
            "DELETE FROM memories WHERE id = ?", (memory_id,)
        )
        await self._conn.commit()
        return cursor.rowcount > 0

    async def get_recent(self, limit: int = 20) -> list[MemoryEntry]:
        """Return the *limit* most-recently accessed memories."""
        cursor = await self._conn.execute(
            "SELECT id, content, type, embedding_json, metadata_json, "
            "created_at, accessed_at, access_count, importance "
            "FROM memories ORDER BY accessed_at DESC LIMIT ?",
            (limit,),
        )
        rows = await cursor.fetchall()
        return [_row_to_entry(r) for r in rows]

    async def update_access(self, memory_id: str) -> None:
        """Bump access_count and set accessed_at to now for a memory."""
        now = _iso(datetime.now(timezone.utc))
        await self._conn.execute(
            "UPDATE memories SET access_count = access_count + 1, accessed_at = ? WHERE id = ?",
            (now, memory_id),
        )
        await self._conn.commit()

    async def count(self, memory_type: MemoryType | None = None) -> int:
        """Return the total number of stored memories, optionally filtered by type."""
        if memory_type is None:
            cursor = await self._conn.execute("SELECT COUNT(*) FROM memories")
        else:
            cursor = await self._conn.execute(
                "SELECT COUNT(*) FROM memories WHERE type = ?", (memory_type.value,)
            )
        row = await cursor.fetchone()
        return row[0] if row else 0

    # -- search --------------------------------------------------------------

    async def search(self, query: MemoryQuery) -> list[MemorySearchResult]:
        """Search memories using cosine similarity on embeddings.

        If the query has no embedding information (i.e. ``query.query`` is set
        but no embedding is supplied), a text-based ``LIKE`` fallback is used
        instead and similarity scores are set to 1.0 for matches.

        When embeddings are available on stored entries, cosine similarity is
        computed in-process using numpy.  Entries below
        ``query.min_similarity`` are filtered out.  Results are sorted by
        descending similarity and capped at ``query.limit``.
        """
        # Build the base SQL with optional type filter
        sql = (
            "SELECT id, content, type, embedding_json, metadata_json, "
            "created_at, accessed_at, access_count, importance FROM memories"
        )
        params: list[Any] = []
        where_clauses: list[str] = []
        if query.memory_type is not None:
            where_clauses.append("type = ?")
            params.append(query.memory_type.value)

        if where_clauses:
            sql += " WHERE " + " AND ".join(where_clauses)

        cursor = await self._conn.execute(sql, params)
        rows = await cursor.fetchall()
        entries = [_row_to_entry(r) for r in rows]

        # If caller didn't supply an embedding we fall back to text matching
        # and sort by importance.
        if not entries:
            return []

        # Check whether we can do vector search: need at least one entry
        # with an embedding.  The caller should ideally pass an embedding
        # on the MemoryQuery via a separate field, but to keep the public API
        # simple we detect "has embeddings in the store" and, when available,
        # do a brute-force scan.
        #
        # For the query vector we look for a ``_query_embedding`` key stuffed
        # into the query object (set by the retriever).  When missing we
        # fall back to text search.
        query_embedding: list[float] | None = getattr(query, "_query_embedding", None)

        results: list[MemorySearchResult] = []

        if query_embedding is not None:
            # Vector similarity search
            for entry in entries:
                if entry.embedding is None:
                    continue
                sim = cosine_similarity(query_embedding, entry.embedding)
                if sim >= query.min_similarity:
                    results.append(MemorySearchResult(entry=entry, similarity_score=sim))
            results.sort(key=lambda r: r.similarity_score, reverse=True)
        else:
            # Text fallback: case-insensitive substring match, ranked by importance
            q_lower = query.query.lower()
            for entry in entries:
                if q_lower and q_lower in entry.content.lower():
                    results.append(MemorySearchResult(entry=entry, similarity_score=1.0))
            results.sort(key=lambda r: r.entry.importance_score, reverse=True)

        return results[: query.limit]

    async def search_by_embedding(
        self,
        embedding: list[float],
        memory_type: MemoryType | None = None,
        limit: int = 10,
        min_similarity: float = 0.0,
    ) -> list[MemorySearchResult]:
        """Convenience wrapper: search using a raw embedding vector.

        This avoids the need to construct a MemoryQuery and attach the
        embedding manually.

        Args:
            embedding: Dense query vector.
            memory_type: Optional type filter.
            limit: Max results.
            min_similarity: Minimum cosine similarity threshold.

        Returns:
            Sorted list of MemorySearchResult.
        """
        q = MemoryQuery(memory_type=memory_type, limit=limit, min_similarity=min_similarity)
        # Attach embedding to the query object for the search method
        object.__setattr__(q, "_query_embedding", embedding)
        return await self.search(q)
