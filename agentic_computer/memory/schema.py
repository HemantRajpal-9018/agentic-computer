"""Memory data models for the agentic-computer memory subsystem.

Defines the core types used across the memory store, compressor, and retriever:
MemoryType enum, MemoryEntry/MemoryQuery/MemorySearchResult dataclasses.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class MemoryType(str, Enum):
    """Classification of memory by cognitive analogy.

    EPISODIC  - specific events / experiences (what happened)
    SEMANTIC  - general knowledge / facts (what is true)
    PROCEDURAL - how-to knowledge / skills (how to do something)
    WORKING   - short-lived scratch-pad items (current context)
    """

    EPISODIC = "episodic"
    SEMANTIC = "semantic"
    PROCEDURAL = "procedural"
    WORKING = "working"


@dataclass
class MemoryEntry:
    """A single memory record stored in the memory system.

    Attributes:
        id: Unique identifier (UUID4).
        content: The textual content of the memory.
        memory_type: Classification of the memory.
        embedding: Optional dense vector for similarity search.
        metadata: Arbitrary key-value metadata (e.g. source, tags).
        created_at: Timestamp when the memory was first stored.
        accessed_at: Timestamp of the most recent access.
        access_count: Number of times this memory has been accessed.
        importance_score: Numeric importance in [0, 1]; higher = more important.
    """

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    content: str = ""
    memory_type: MemoryType = MemoryType.WORKING
    embedding: list[float] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    accessed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    access_count: int = 0
    importance_score: float = 0.5


@dataclass
class MemoryQuery:
    """Parameters for searching the memory store.

    Attributes:
        query: Free-text search string (also used for embedding lookup).
        memory_type: Optional filter — only return memories of this type.
        limit: Maximum number of results to return.
        min_similarity: Minimum cosine-similarity threshold (0-1).
    """

    query: str = ""
    memory_type: MemoryType | None = None
    limit: int = 10
    min_similarity: float = 0.0


@dataclass
class MemorySearchResult:
    """A single search hit pairing a MemoryEntry with its similarity score.

    Attributes:
        entry: The matched memory entry.
        similarity_score: Cosine similarity between the query and entry embeddings (0-1).
    """

    entry: MemoryEntry
    similarity_score: float = 0.0
