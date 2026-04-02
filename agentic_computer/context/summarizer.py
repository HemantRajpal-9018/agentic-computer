"""Context summarisation for the agentic-computer framework.

Provides extractive summarisation that works without any external LLM call,
making it suitable for offline / low-latency operation.  An optional LLM
path is also supported for higher-quality abstractive summaries when a
model is available.
"""

from __future__ import annotations

import logging
import math
import re
from collections import Counter
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Enum & data classes
# ---------------------------------------------------------------------------


class SummaryLevel(str, Enum):
    """Controls how aggressively text is compressed.

    BRIEF    - very short; ~10-15 % of original length.
    STANDARD - balanced; ~25-30 % of original length.
    DETAILED - light compression; ~50-60 % of original length.
    """

    BRIEF = "brief"
    STANDARD = "standard"
    DETAILED = "detailed"


# Maps each level to the fraction of sentences to retain.
_LEVEL_RATIOS: dict[SummaryLevel, float] = {
    SummaryLevel.BRIEF: 0.12,
    SummaryLevel.STANDARD: 0.28,
    SummaryLevel.DETAILED: 0.55,
}


@dataclass
class Summary:
    """Result of a summarisation operation.

    Attributes:
        original_tokens: Estimated token count of the source text.
        summary_tokens: Estimated token count of the summary.
        content: The summarised text.
        level: The :class:`SummaryLevel` used.
    """

    original_tokens: int
    summary_tokens: int
    content: str
    level: SummaryLevel


# ---------------------------------------------------------------------------
# Sentence utilities
# ---------------------------------------------------------------------------

# Regex that splits on sentence-ending punctuation followed by whitespace
# or end-of-string, while handling common abbreviations conservatively.
_SENTENCE_RE = re.compile(
    r"(?<=[.!?])\s+(?=[A-Z\"\'\u201c\u2018])"
)


def _split_sentences(text: str) -> list[str]:
    """Split *text* into a list of sentences.

    Uses a regex-based heuristic that splits on sentence-ending
    punctuation (. ! ?) followed by whitespace and an uppercase letter
    or opening quote.

    Args:
        text: Input text.

    Returns:
        List of sentence strings (may be empty for blank input).
    """
    text = text.strip()
    if not text:
        return []
    parts = _SENTENCE_RE.split(text)
    return [s.strip() for s in parts if s.strip()]


def _estimate_tokens(text: str) -> int:
    """Rough token estimate (~4 chars per token)."""
    return max(1, len(text) // 4)


# ---------------------------------------------------------------------------
# ContextSummarizer
# ---------------------------------------------------------------------------


class ContextSummarizer:
    """Extractive text summariser with optional LLM enhancement.

    The default path uses TF-based sentence scoring — no network calls.
    If an ``llm_callable`` is provided it is used instead for a richer
    abstractive summary.

    Parameters:
        llm_callable: Optional async or sync function that accepts a
            prompt string and returns a summary string.  When ``None``
            (the default) only extractive summarisation is used.
    """

    def __init__(
        self,
        llm_callable: Callable[[str], str] | None = None,
    ) -> None:
        self._llm_callable = llm_callable

    # -- public API ---------------------------------------------------------

    def summarize(
        self,
        text: str,
        level: SummaryLevel = SummaryLevel.STANDARD,
    ) -> Summary:
        """Summarise *text* at the requested compression level.

        When an LLM callable is configured it is attempted first; on
        failure the method falls back to extractive summarisation.

        Args:
            text: Source text to summarise.
            level: Desired compression level.

        Returns:
            A :class:`Summary` with the compressed content.
        """
        original_tokens = _estimate_tokens(text)

        # Try LLM path if available.
        if self._llm_callable is not None:
            try:
                summary_text = self._llm_summarize(text, level)
                return Summary(
                    original_tokens=original_tokens,
                    summary_tokens=_estimate_tokens(summary_text),
                    content=summary_text,
                    level=level,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "LLM summarisation failed, falling back to extractive: %s",
                    exc,
                )

        ratio = _LEVEL_RATIOS[level]
        summary_text = self._extractive_summary(text, ratio)
        return Summary(
            original_tokens=original_tokens,
            summary_tokens=_estimate_tokens(summary_text),
            content=summary_text,
            level=level,
        )

    def summarize_conversation(
        self,
        messages: list[dict[str, Any]],
        keep_recent: int = 5,
    ) -> list[dict[str, Any]]:
        """Compress a conversation history while keeping recent messages.

        Older messages (before the last *keep_recent*) are merged into a
        single summary message with role ``"system"``.

        Args:
            messages: List of message dicts with ``"role"`` and ``"content"``
                keys.
            keep_recent: Number of most-recent messages to preserve
                verbatim.

        Returns:
            A new message list with older messages replaced by a summary.
        """
        if len(messages) <= keep_recent:
            return list(messages)

        older = messages[: -keep_recent]
        recent = messages[-keep_recent:]

        combined = "\n".join(
            f"[{m.get('role', 'unknown')}] {m.get('content', '')}"
            for m in older
        )
        summary = self.summarize(combined, level=SummaryLevel.BRIEF)

        summary_message: dict[str, Any] = {
            "role": "system",
            "content": (
                f"[Conversation summary — {summary.original_tokens} tokens "
                f"compressed to {summary.summary_tokens}]\n{summary.content}"
            ),
        }
        return [summary_message] + list(recent)

    # -- extractive summarisation -------------------------------------------

    @staticmethod
    def _extractive_summary(text: str, ratio: float) -> str:
        """Produce an extractive summary by scoring sentences on word frequency.

        Each sentence is scored by the average normalised frequency of its
        words (stop-words are implicitly down-weighted by being common
        across all sentences).  The top-scoring sentences are returned in
        their original order to maintain readability.

        Args:
            text: Source text.
            ratio: Fraction of sentences to keep (0.0 -- 1.0).

        Returns:
            The summarised text.
        """
        sentences = _split_sentences(text)
        if not sentences:
            return text

        num_to_keep = max(1, math.ceil(len(sentences) * ratio))
        if num_to_keep >= len(sentences):
            return text

        # Tokenise into lowercased words.
        word_re = re.compile(r"[a-z0-9]+", re.IGNORECASE)
        word_freq: Counter[str] = Counter()
        sentence_words: list[list[str]] = []

        for sent in sentences:
            words = [w.lower() for w in word_re.findall(sent)]
            sentence_words.append(words)
            word_freq.update(words)

        if not word_freq:
            # Degenerate case — no alphanumeric words found.
            return " ".join(sentences[:num_to_keep])

        # Normalise frequencies by the maximum.
        max_freq = max(word_freq.values())
        normalised: dict[str, float] = {
            w: freq / max_freq for w, freq in word_freq.items()
        }

        # Score each sentence.
        scores: list[tuple[int, float]] = []
        for idx, words in enumerate(sentence_words):
            if not words:
                scores.append((idx, 0.0))
                continue
            score = sum(normalised.get(w, 0.0) for w in words) / len(words)
            # Slight positional boost: first and last sentences are often
            # more important (intro/conclusion heuristic).
            if idx == 0 or idx == len(sentences) - 1:
                score *= 1.25
            scores.append((idx, score))

        # Select top sentences, preserving original order.
        ranked = sorted(scores, key=lambda pair: pair[1], reverse=True)
        selected_indices = sorted(idx for idx, _ in ranked[:num_to_keep])

        return " ".join(sentences[i] for i in selected_indices)

    # -- chunking -----------------------------------------------------------

    @staticmethod
    def _chunk_text(text: str, chunk_size: int = 2000) -> list[str]:
        """Split *text* into chunks of approximately *chunk_size* characters.

        Splits prefer paragraph boundaries (double newlines), then
        sentence boundaries, and finally hard character limits.

        Args:
            text: Source text.
            chunk_size: Target maximum characters per chunk.

        Returns:
            List of text chunks.
        """
        if len(text) <= chunk_size:
            return [text]

        chunks: list[str] = []
        remaining = text

        while remaining:
            if len(remaining) <= chunk_size:
                chunks.append(remaining)
                break

            # Try to break at a paragraph boundary.
            candidate = remaining[:chunk_size]
            para_break = candidate.rfind("\n\n")
            if para_break > chunk_size // 3:
                chunks.append(remaining[:para_break].rstrip())
                remaining = remaining[para_break:].lstrip()
                continue

            # Try sentence boundary.
            for sep in (". ", ".\n", "! ", "? "):
                sent_break = candidate.rfind(sep)
                if sent_break > chunk_size // 3:
                    chunks.append(remaining[: sent_break + 1].rstrip())
                    remaining = remaining[sent_break + 1 :].lstrip()
                    break
            else:
                # Hard break at chunk_size.
                space_break = candidate.rfind(" ")
                if space_break > chunk_size // 3:
                    chunks.append(remaining[:space_break].rstrip())
                    remaining = remaining[space_break:].lstrip()
                else:
                    chunks.append(remaining[:chunk_size])
                    remaining = remaining[chunk_size:]

        return [c for c in chunks if c]

    # -- optional LLM path --------------------------------------------------

    def _llm_summarize(self, text: str, level: SummaryLevel) -> str:
        """Use the configured LLM callable to produce an abstractive summary.

        Args:
            text: Source text to summarise.
            level: Desired compression level (used in the prompt).

        Returns:
            The LLM-generated summary string.

        Raises:
            RuntimeError: If the callable returns empty or fails.
        """
        assert self._llm_callable is not None  # noqa: S101

        level_instruction = {
            SummaryLevel.BRIEF: "very brief (2-3 sentences)",
            SummaryLevel.STANDARD: "concise but complete",
            SummaryLevel.DETAILED: "detailed, preserving key information",
        }[level]

        prompt = (
            f"Summarise the following text. "
            f"Make the summary {level_instruction}.\n\n"
            f"---\n{text}\n---\n\nSummary:"
        )

        result = self._llm_callable(prompt)
        if not result or not result.strip():
            raise RuntimeError("LLM returned an empty summary.")
        return result.strip()
