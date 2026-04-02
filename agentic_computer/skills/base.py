"""Base skill abstractions for the agentic-computer skill system.

Defines the foundational types that every skill builds on:
``SkillMetadata``, ``SkillContext``, ``SkillResult``, and the abstract
``BaseSkill`` class.  Concrete skills (research, coding, design, etc.)
subclass ``BaseSkill`` and implement the three required hooks.
"""

from __future__ import annotations

import abc
import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class SkillMetadata:
    """Immutable descriptor for a registered skill.

    Attributes:
        name: Short machine-friendly identifier (e.g. ``"research"``).
        description: One-line human-readable summary of the skill.
        version: Semver string (e.g. ``"0.1.0"``).
        author: Author or team name.
        tags: Free-form labels used for filtering and discovery.
    """

    name: str
    description: str
    version: str = "0.1.0"
    author: str = ""
    tags: list[str] = field(default_factory=list)

    def matches_tag(self, tag: str) -> bool:
        """Return ``True`` if *tag* appears (case-insensitive) in this skill's tags."""
        tag_lower = tag.lower()
        return any(t.lower() == tag_lower for t in self.tags)


@dataclass
class SkillContext:
    """Runtime context passed to a skill when it executes.

    ``memory``, ``tools``, and ``config`` are typed as ``Any`` so that
    callers can inject whatever backing implementations are available
    (e.g. a :class:`MemoryStore`, a tool registry dict, or a
    :class:`Settings` instance).

    Attributes:
        task: The natural-language task the skill should carry out.
        memory: Optional memory subsystem handle (read/write memories).
        tools: Optional tool registry or mapping available to the skill.
        config: Optional configuration object / dict.
    """

    task: str
    memory: Any = None
    tools: Any = None
    config: Any = None


@dataclass
class SkillResult:
    """Outcome returned by a skill after execution.

    Attributes:
        success: Whether the skill completed without fatal errors.
        output: Primary textual output (summary, answer, generated code, etc.).
        artifacts: Structured side-outputs such as files, images, or diffs.
            Each artifact is a plain dict with at least a ``"type"`` key.
        metadata: Arbitrary execution metadata (timings, token counts, etc.).
    """

    success: bool
    output: str
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Abstract base skill
# ---------------------------------------------------------------------------

class BaseSkill(abc.ABC):
    """Abstract base class for all skills.

    A *skill* is a focused capability that can decide whether it applies to
    a given task (via :pymeth:`can_handle`) and then carry out that task
    (via :pymeth:`execute`).  The framework uses
    :class:`~agentic_computer.skills.loader.SkillLoader` to discover,
    rank, and invoke skills.

    Subclasses **must** implement:

    * :pymeth:`metadata` (property) -- return a :class:`SkillMetadata`.
    * :pymeth:`execute` -- perform the task described by a :class:`SkillContext`.
    * :pymeth:`can_handle` -- return a ``[0, 1]`` confidence that this
      skill is appropriate for a given task string.
    * :pymeth:`get_required_tools` -- list tool names the skill needs at runtime.
    """

    # ------------------------------------------------------------------
    # Abstract interface
    # ------------------------------------------------------------------

    @property
    @abc.abstractmethod
    def metadata(self) -> SkillMetadata:
        """Return the immutable metadata descriptor for this skill."""

    @abc.abstractmethod
    async def execute(self, context: SkillContext) -> SkillResult:
        """Execute the skill against the provided *context*.

        Args:
            context: A :class:`SkillContext` carrying the task description,
                optional memory handle, tool registry, and configuration.

        Returns:
            A :class:`SkillResult` summarising the outcome.
        """

    @abc.abstractmethod
    def can_handle(self, task: str) -> float:
        """Return a confidence score in ``[0.0, 1.0]`` for *task*.

        A score of ``0.0`` means the skill is completely irrelevant.
        A score of ``1.0`` means it is an ideal match.

        Args:
            task: Natural-language task description.

        Returns:
            A float confidence score between 0 and 1 inclusive.
        """

    @abc.abstractmethod
    def get_required_tools(self) -> list[str]:
        """Return the names of tools this skill requires at runtime.

        The framework checks tool availability before dispatching so
        skills can fail fast when a required tool is missing.

        Returns:
            A list of tool name strings (e.g. ``["web_search", "memory"]``).
        """

    # ------------------------------------------------------------------
    # Convenience helpers
    # ------------------------------------------------------------------

    def _keyword_confidence(self, task: str, keywords: list[str], *, base: float = 0.1) -> float:
        """Calculate confidence from keyword overlap.

        Scans *task* (lowercased) for each keyword and returns a score
        proportional to the number of matches, clamped to ``[0.0, 1.0]``.

        Args:
            task: The task string to inspect.
            keywords: Domain keywords that indicate relevance.
            base: Minimum confidence to return when no keywords match.

        Returns:
            A float in ``[0.0, 1.0]``.
        """
        task_lower = task.lower()
        hits = sum(1 for kw in keywords if kw in task_lower)
        if hits == 0:
            return base
        # Each hit adds 0.2 on top of a 0.3 base; cap at 1.0.
        return min(1.0, 0.3 + hits * 0.2)

    def __repr__(self) -> str:
        meta = self.metadata
        return f"<{self.__class__.__name__} name={meta.name!r} v{meta.version}>"
