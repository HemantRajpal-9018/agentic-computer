"""Memory compressor — merges and summarises old / low-importance memories.

The compressor runs periodically to keep the memory store lean.  It identifies
clusters of related memories, merges them into single summary entries, and
deletes the originals.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

from .schema import MemoryEntry, MemoryType
from .store import MemoryStore

# Tunables ----------------------------------------------------------------

# Compress when total count exceeds this threshold.
_COMPRESS_COUNT_THRESHOLD = 500

# Memories older than this many days are candidates for compression.
_STALE_DAYS = 7

# Importance score below which a memory is a compression candidate.
_LOW_IMPORTANCE_CUTOFF = 0.35

# Minimum group size before we bother merging.
_MIN_GROUP_SIZE = 2

# Maximum group size per compression pass to keep summaries coherent.
_MAX_GROUP_SIZE = 20


class MemoryCompressor:
    """Compresses old and low-importance memories in a MemoryStore.

    The compressor scores each memory for importance, selects candidates that
    are old or unimportant, groups them by memory type, merges each group into
    a single summary entry, and removes the originals.
    """

    # -- public API ----------------------------------------------------------

    async def compress(self, entries: list[MemoryEntry]) -> MemoryEntry:
        """Merge a list of related MemoryEntry objects into a single summary.

        The summary content is a newline-joined digest of each entry's content
        prefixed by a bullet.  The resulting entry inherits the most common
        memory type, the highest importance among the group, and an averaged
        embedding (when available).

        Args:
            entries: Two or more entries to merge.

        Returns:
            A new MemoryEntry representing the compressed summary.

        Raises:
            ValueError: If fewer than two entries are supplied.
        """
        if len(entries) < _MIN_GROUP_SIZE:
            raise ValueError(
                f"Need at least {_MIN_GROUP_SIZE} entries to compress, got {len(entries)}"
            )

        # Build a bullet-point summary of the merged content
        summary_lines: list[str] = []
        for entry in entries:
            # Truncate very long individual memories to keep the summary bounded
            snippet = entry.content[:300].strip()
            if len(entry.content) > 300:
                snippet += "..."
            summary_lines.append(f"- {snippet}")
        summary_text = "Compressed memory summary:\n" + "\n".join(summary_lines)

        # Determine the dominant memory type (most frequent)
        type_counts: dict[MemoryType, int] = {}
        for entry in entries:
            type_counts[entry.memory_type] = type_counts.get(entry.memory_type, 0) + 1
        dominant_type = max(type_counts, key=lambda t: type_counts[t])

        # Compute averaged embedding if any entries have one
        merged_embedding = self._average_embeddings(entries)

        # Aggregate metadata keys (keep unique values for each key)
        merged_metadata: dict[str, object] = {"compressed_from": [e.id for e in entries]}
        for entry in entries:
            for key, value in entry.metadata.items():
                if key not in merged_metadata:
                    merged_metadata[key] = value

        # Importance = max in group (compressed memories are at least as important)
        best_importance = max(e.importance_score for e in entries)

        now = datetime.now(timezone.utc)
        return MemoryEntry(
            content=summary_text,
            memory_type=dominant_type,
            embedding=merged_embedding,
            metadata=merged_metadata,  # type: ignore[arg-type]
            created_at=now,
            accessed_at=now,
            access_count=0,
            importance_score=best_importance,
        )

    async def should_compress(self, store: MemoryStore) -> bool:
        """Return True when the store has grown large enough to justify compression.

        The heuristic checks total count and the proportion of stale entries.
        """
        total = await store.count()
        if total < _COMPRESS_COUNT_THRESHOLD:
            return False

        # Also check whether there are enough stale, low-importance candidates
        candidates = await self._get_candidates(store)
        return len(candidates) >= _MIN_GROUP_SIZE

    async def run_compression(self, store: MemoryStore) -> int:
        """Execute one compression pass and return the number of memories compressed.

        Steps:
        1. Identify candidate memories (old or low-importance).
        2. Group them by memory type.
        3. For each group of sufficient size, merge into a summary entry.
        4. Insert the summary and delete the originals.

        Returns:
            The total number of original memories that were replaced.
        """
        candidates = await self._get_candidates(store)
        if len(candidates) < _MIN_GROUP_SIZE:
            return 0

        # Group by memory type
        groups: dict[MemoryType, list[MemoryEntry]] = {}
        for entry in candidates:
            groups.setdefault(entry.memory_type, []).append(entry)

        total_compressed = 0

        for _mem_type, group in groups.items():
            if len(group) < _MIN_GROUP_SIZE:
                continue

            # Process in chunks of _MAX_GROUP_SIZE
            for start in range(0, len(group), _MAX_GROUP_SIZE):
                chunk = group[start : start + _MAX_GROUP_SIZE]
                if len(chunk) < _MIN_GROUP_SIZE:
                    continue

                summary_entry = await self.compress(chunk)
                await store.add(
                    content=summary_entry.content,
                    memory_type=summary_entry.memory_type,
                    metadata=summary_entry.metadata,
                    embedding=summary_entry.embedding,
                    importance=summary_entry.importance_score,
                )

                # Remove the originals
                for entry in chunk:
                    await store.delete(entry.id)

                total_compressed += len(chunk)

        return total_compressed

    # -- internals -----------------------------------------------------------

    @staticmethod
    def _calculate_importance(entry: MemoryEntry) -> float:
        """Score a memory's importance on a [0, 1] scale.

        Factors:
        * **Recency** — more recently accessed memories score higher.
        * **Access count** — frequently accessed memories score higher.
        * **Type bonus** — procedural and semantic memories get a small boost
          because they tend to represent durable knowledge.

        The final score is a weighted blend clamped to [0, 1].
        """
        now = datetime.now(timezone.utc)

        # Recency score: decays with a half-life of ~3 days
        age_hours = max((now - entry.accessed_at).total_seconds() / 3600.0, 0.0)
        recency = math.exp(-0.01 * age_hours)  # ~0.49 after 3 days

        # Access frequency score: logarithmic saturation
        frequency = min(math.log1p(entry.access_count) / math.log1p(50), 1.0)

        # Type bonus
        type_bonus: dict[MemoryType, float] = {
            MemoryType.PROCEDURAL: 0.15,
            MemoryType.SEMANTIC: 0.10,
            MemoryType.EPISODIC: 0.05,
            MemoryType.WORKING: 0.0,
        }
        bonus = type_bonus.get(entry.memory_type, 0.0)

        # Weighted blend
        score = 0.45 * recency + 0.35 * frequency + 0.20 * bonus / 0.15
        # Normalise bonus term: max bonus is 0.15 so divide by 0.15 to get [0,1]

        return max(0.0, min(1.0, score))

    async def _get_candidates(self, store: MemoryStore) -> list[MemoryEntry]:
        """Return memories eligible for compression (stale + low importance)."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=_STALE_DAYS)
        all_recent = await store.get_recent(limit=10_000)  # fetch everything ordered by access

        candidates: list[MemoryEntry] = []
        for entry in all_recent:
            importance = self._calculate_importance(entry)
            if entry.accessed_at < cutoff or importance < _LOW_IMPORTANCE_CUTOFF:
                candidates.append(entry)

        # Sort candidates by importance ascending so the least important come first
        candidates.sort(key=lambda e: self._calculate_importance(e))
        return candidates

    @staticmethod
    def _average_embeddings(entries: list[MemoryEntry]) -> list[float] | None:
        """Compute the element-wise mean of all non-None embeddings.

        Returns None if no entry has an embedding.
        """
        vectors = [e.embedding for e in entries if e.embedding is not None]
        if not vectors:
            return None

        import numpy as np

        arr = np.array(vectors, dtype=np.float64)
        mean_vec = arr.mean(axis=0)
        # Re-normalise to unit length so cosine similarity stays well-behaved
        norm = float(np.linalg.norm(mean_vec))
        if norm > 0:
            mean_vec = mean_vec / norm
        return mean_vec.tolist()
