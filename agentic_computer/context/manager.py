"""Context window management for the agentic-computer framework.

Tracks conversation entries, enforces token budgets, and provides
automatic eviction and compression to prevent context-window overflow.
Includes anti-context-rot logic that detects stale context and triggers
refresh cycles.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agentic_computer.context.summarizer import ContextSummarizer

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class ContextEntry:
    """A single entry in the context window.

    Attributes:
        role: Speaker role (``"system"``, ``"user"``, ``"assistant"``, etc.).
        content: Raw text content.
        token_count: Estimated token count for this entry.
        timestamp: UTC time when the entry was created.
        priority: Importance weight in ``[0.0, 1.0]``; higher = more important.
        pinned: If ``True`` the entry is never evicted automatically.
    """

    role: str
    content: str
    token_count: int
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    priority: float = 0.5
    pinned: bool = False


@dataclass
class ContextWindow:
    """Container representing the bounded context window.

    Attributes:
        entries: Ordered list of :class:`ContextEntry` objects.
        max_tokens: Hard ceiling on total tokens allowed.
    """

    entries: list[ContextEntry] = field(default_factory=list)
    max_tokens: int = 128_000

    @property
    def current_tokens(self) -> int:
        """Return the sum of estimated tokens across all entries."""
        return sum(entry.token_count for entry in self.entries)


# ---------------------------------------------------------------------------
# Staleness detection constants
# ---------------------------------------------------------------------------

_STALE_SECONDS = 600  # 10 minutes without update -> potentially stale
_STALE_ENTRY_RATIO = 0.6  # more than 60 % of entries older than threshold


# ---------------------------------------------------------------------------
# ContextManager
# ---------------------------------------------------------------------------


class ContextManager:
    """Manages the active context window for an agent session.

    Handles adding entries, enforcing token limits, evicting low-priority
    entries, and compressing older context to reclaim budget.

    Parameters:
        max_tokens: Maximum number of tokens the context window may hold.
    """

    def __init__(self, max_tokens: int = 128_000) -> None:
        self._window = ContextWindow(max_tokens=max_tokens)
        self._summarizer: ContextSummarizer | None = None
        self._last_refresh: float = time.monotonic()

    # -- public properties --------------------------------------------------

    @property
    def window(self) -> ContextWindow:
        """Expose the underlying :class:`ContextWindow`."""
        return self._window

    @property
    def max_tokens(self) -> int:
        """Return the configured maximum token budget."""
        return self._window.max_tokens

    @property
    def current_tokens(self) -> int:
        """Return current total estimated tokens."""
        return self._window.current_tokens

    # -- mutators -----------------------------------------------------------

    def add(
        self,
        role: str,
        content: str,
        priority: float = 0.5,
        pinned: bool = False,
    ) -> ContextEntry:
        """Add a new entry to the context window.

        If adding the entry would exceed the token budget, low-priority
        entries are evicted until there is room.

        Args:
            role: Speaker role.
            content: Text content.
            priority: Importance weight ``[0.0, 1.0]``.
            pinned: Whether the entry should be protected from eviction.

        Returns:
            The newly created :class:`ContextEntry`.
        """
        token_count = self._estimate_tokens(content)
        entry = ContextEntry(
            role=role,
            content=content,
            token_count=token_count,
            priority=priority,
            pinned=pinned,
        )

        # Evict until there is room for the new entry.
        while (
            self._window.current_tokens + token_count > self._window.max_tokens
            and self._window.entries
        ):
            evicted = self._evict_lowest_priority()
            if evicted is None:
                # Only pinned entries remain; cannot free more space.
                logger.warning(
                    "Cannot fit new entry (%d tokens) — only pinned entries remain.",
                    token_count,
                )
                break

        self._window.entries.append(entry)
        self._last_refresh = time.monotonic()
        return entry

    def get_context(self) -> list[ContextEntry]:
        """Return the list of entries that fit within the token budget.

        Entries are returned in insertion order.  If the window is over
        budget (e.g. after external mutation), trailing low-priority
        entries are excluded.

        Returns:
            List of :class:`ContextEntry` instances.
        """
        # Check for staleness and refresh if necessary.
        if self._is_context_stale():
            logger.info("Context appears stale — triggering refresh.")
            self.compress()

        result: list[ContextEntry] = []
        running_tokens = 0
        for entry in self._window.entries:
            if running_tokens + entry.token_count <= self._window.max_tokens:
                result.append(entry)
                running_tokens += entry.token_count
            else:
                break
        return result

    def is_approaching_limit(self, threshold: float = 0.8) -> bool:
        """Check whether the context window is nearing its token ceiling.

        Args:
            threshold: Fraction of ``max_tokens`` (0.0 -- 1.0) at which
                the window is considered "approaching" the limit.

        Returns:
            ``True`` if current usage >= ``threshold * max_tokens``.
        """
        return self._window.current_tokens >= threshold * self._window.max_tokens

    def compress(self) -> int:
        """Summarise older, lower-priority entries to reclaim token budget.

        Non-pinned entries in the first half of the window are replaced with
        a single summary entry.  If no external summarizer is configured the
        method falls back to a simple concatenation-and-truncation strategy.

        Returns:
            Number of tokens freed by the compression.
        """
        tokens_before = self._window.current_tokens

        # Identify candidates: non-pinned entries in the first half.
        midpoint = len(self._window.entries) // 2
        if midpoint == 0:
            return 0

        candidates: list[ContextEntry] = []
        kept: list[ContextEntry] = []
        for idx, entry in enumerate(self._window.entries):
            if idx < midpoint and not entry.pinned:
                candidates.append(entry)
            else:
                kept.append(entry)

        if not candidates:
            return 0

        # Build a summary of the candidates.
        combined_text = "\n".join(
            f"[{c.role}] {c.content}" for c in candidates
        )

        if self._summarizer is not None:
            from agentic_computer.context.summarizer import SummaryLevel

            summary_obj = self._summarizer.summarize(
                combined_text, level=SummaryLevel.BRIEF
            )
            summary_text = summary_obj.content
        else:
            # Fallback: take the first ~25 % of the combined text.
            char_limit = max(len(combined_text) // 4, 200)
            summary_text = combined_text[:char_limit].rstrip() + " [...]"

        summary_entry = ContextEntry(
            role="system",
            content=f"[Context summary] {summary_text}",
            token_count=self._estimate_tokens(summary_text),
            priority=0.6,
            pinned=False,
        )

        self._window.entries = [summary_entry] + kept
        tokens_after = self._window.current_tokens
        freed = tokens_before - tokens_after
        logger.info(
            "Compressed context: %d -> %d tokens (freed %d).",
            tokens_before,
            tokens_after,
            freed,
        )
        self._last_refresh = time.monotonic()
        return freed

    def clear(self) -> None:
        """Remove all entries from the context window."""
        self._window.entries.clear()
        self._last_refresh = time.monotonic()

    def set_summarizer(self, summarizer: ContextSummarizer) -> None:
        """Attach an external summarizer for higher-quality compression.

        Args:
            summarizer: A :class:`ContextSummarizer` instance.
        """
        self._summarizer = summarizer

    # -- private helpers ----------------------------------------------------

    def _estimate_tokens(self, text: str) -> int:
        """Estimate token count for *text* using a simple heuristic.

        Approximation: ~4 characters per token on average for English text.

        Args:
            text: The text to estimate.

        Returns:
            Estimated number of tokens (always >= 1).
        """
        return max(1, len(text) // 4)

    def _evict_lowest_priority(self) -> ContextEntry | None:
        """Remove and return the lowest-priority non-pinned entry.

        Among entries with equal priority the oldest one is evicted first.

        Returns:
            The evicted :class:`ContextEntry`, or ``None`` if only pinned
            entries remain.
        """
        candidates = [
            (idx, entry)
            for idx, entry in enumerate(self._window.entries)
            if not entry.pinned
        ]
        if not candidates:
            return None

        # Sort by priority ascending, then by timestamp ascending (oldest first).
        candidates.sort(key=lambda pair: (pair[1].priority, pair[1].timestamp))
        evict_idx, evicted = candidates[0]
        del self._window.entries[evict_idx]
        logger.debug(
            "Evicted entry (role=%s, tokens=%d, priority=%.2f).",
            evicted.role,
            evicted.token_count,
            evicted.priority,
        )
        return evicted

    # -- anti-context-rot ---------------------------------------------------

    def _is_context_stale(self) -> bool:
        """Detect when context is getting stale and may need refresh.

        Context is considered stale when a significant portion of entries
        are old relative to the most recent entry, and the manager has
        not been refreshed recently.

        Returns:
            ``True`` if context appears stale and should be refreshed.
        """
        entries = self._window.entries
        if len(entries) < 4:
            return False

        # Check wall-clock time since last refresh.
        elapsed = time.monotonic() - self._last_refresh
        if elapsed < _STALE_SECONDS:
            return False

        # Compare entry timestamps: if most are much older than the newest,
        # the context likely contains outdated information.
        newest_ts = max(e.timestamp for e in entries)
        stale_threshold = _STALE_SECONDS  # seconds

        stale_count = sum(
            1
            for e in entries
            if (newest_ts - e.timestamp).total_seconds() > stale_threshold
            and not e.pinned
        )

        ratio = stale_count / len(entries)
        return ratio > _STALE_ENTRY_RATIO
