"""Research skill for the agentic-computer skill system.

Implements a multi-phase research workflow: **search** -> **analyze** ->
**synthesize**.  The skill leverages a ``web_search`` tool (when available)
and the memory subsystem to persist findings across sessions.
"""

from __future__ import annotations

import logging
from typing import Any

from agentic_computer.skills.base import (
    BaseSkill,
    SkillContext,
    SkillMetadata,
    SkillResult,
)

logger = logging.getLogger(__name__)

# Keywords that indicate a research-oriented task.
_RESEARCH_KEYWORDS: list[str] = [
    "research",
    "search",
    "find",
    "investigate",
    "look up",
    "lookup",
    "summarize",
    "summarise",
    "analyze",
    "analyse",
    "explore",
    "discover",
    "what is",
    "who is",
    "how does",
    "compare",
    "review",
    "report",
    "study",
    "gather information",
]


class ResearchSkill(BaseSkill):
    """Skill that performs multi-step research on a given topic.

    The execution pipeline has three phases:

    1. **Search** -- query the web (or local memory) for relevant sources.
    2. **Analyze** -- extract key facts, claims, and relationships from
       the raw search results.
    3. **Synthesize** -- combine the analysis into a coherent summary
       that directly addresses the user's task.
    """

    # ------------------------------------------------------------------
    # BaseSkill interface
    # ------------------------------------------------------------------

    @property
    def metadata(self) -> SkillMetadata:
        return SkillMetadata(
            name="research",
            description="Multi-step research: search, analyze, and synthesize information.",
            version="0.1.0",
            author="agentic-computer",
            tags=["research", "search", "analysis", "information-retrieval"],
        )

    def can_handle(self, task: str) -> float:
        """Return high confidence for research / search / investigation tasks."""
        return self._keyword_confidence(task, _RESEARCH_KEYWORDS)

    def get_required_tools(self) -> list[str]:
        return ["web_search"]

    async def execute(self, context: SkillContext) -> SkillResult:
        """Run the full research pipeline: search -> analyze -> synthesize.

        If any phase fails the skill returns a partial result with
        ``success=False`` and whatever output was gathered up to that point.

        Args:
            context: Execution context carrying the task, memory handle,
                tool registry, and configuration.

        Returns:
            A :class:`SkillResult` with a synthesised answer as ``output``
            and intermediate artifacts (search hits, analysis notes).
        """
        task = context.task
        artifacts: list[dict[str, Any]] = []
        logger.info("ResearchSkill starting for task: %s", task)

        # Phase 1 -- Search
        try:
            search_results = await self._search_phase(task, context)
            artifacts.append({
                "type": "search_results",
                "phase": "search",
                "data": search_results,
            })
        except Exception as exc:
            logger.error("Search phase failed: %s", exc)
            return SkillResult(
                success=False,
                output=f"Research failed during search phase: {exc}",
                artifacts=artifacts,
                metadata={"phase_reached": "search", "error": str(exc)},
            )

        # Phase 2 -- Analyze
        try:
            analysis = await self._analyze_phase(search_results, context)
            artifacts.append({
                "type": "analysis",
                "phase": "analyze",
                "data": analysis,
            })
        except Exception as exc:
            logger.error("Analysis phase failed: %s", exc)
            return SkillResult(
                success=False,
                output=f"Research failed during analysis phase: {exc}",
                artifacts=artifacts,
                metadata={"phase_reached": "analyze", "error": str(exc)},
            )

        # Phase 3 -- Synthesize
        try:
            summary = await self._synthesize_phase(analysis, task, context)
        except Exception as exc:
            logger.error("Synthesis phase failed: %s", exc)
            return SkillResult(
                success=False,
                output=f"Research failed during synthesis phase: {exc}",
                artifacts=artifacts,
                metadata={"phase_reached": "synthesize", "error": str(exc)},
            )

        # Persist the final summary in memory if available.
        if context.memory is not None:
            try:
                await self._store_in_memory(context.memory, task, summary)
            except Exception as exc:
                logger.warning("Failed to persist research to memory: %s", exc)

        logger.info("ResearchSkill completed successfully.")
        return SkillResult(
            success=True,
            output=summary,
            artifacts=artifacts,
            metadata={"phase_reached": "synthesize", "sources": len(search_results)},
        )

    # ------------------------------------------------------------------
    # Internal phases
    # ------------------------------------------------------------------

    async def _search_phase(
        self,
        query: str,
        context: SkillContext,
    ) -> list[dict[str, Any]]:
        """Execute web searches and return a list of result dicts.

        Each result dict has at least ``"title"``, ``"url"``, and ``"snippet"``
        keys.  If no ``web_search`` tool is registered the method falls back
        to returning any relevant memories.

        Args:
            query: The search query derived from the task.
            context: Skill execution context.

        Returns:
            A list of search-hit dicts.
        """
        results: list[dict[str, Any]] = []

        # Try the web_search tool first.
        web_search = self._get_tool(context, "web_search")
        if web_search is not None:
            # Build multiple query variants to improve coverage.
            queries = self._expand_queries(query)
            for q in queries:
                try:
                    raw = await web_search(q)
                    if isinstance(raw, list):
                        results.extend(raw)
                    elif isinstance(raw, dict) and "results" in raw:
                        results.extend(raw["results"])
                    else:
                        results.append({
                            "title": q,
                            "url": "",
                            "snippet": str(raw),
                        })
                except Exception as exc:
                    logger.warning("web_search failed for query %r: %s", q, exc)

        # Supplement with memory recall when available.
        if context.memory is not None:
            try:
                memories = await self._recall_from_memory(context.memory, query)
                for mem in memories:
                    results.append({
                        "title": "Memory recall",
                        "url": "",
                        "snippet": mem,
                    })
            except Exception as exc:
                logger.warning("Memory recall failed: %s", exc)

        # Deduplicate by URL (keep first occurrence).
        seen_urls: set[str] = set()
        unique: list[dict[str, Any]] = []
        for r in results:
            url = r.get("url", "")
            if url and url in seen_urls:
                continue
            if url:
                seen_urls.add(url)
            unique.append(r)

        logger.info("Search phase returned %d unique results.", len(unique))
        return unique

    async def _analyze_phase(
        self,
        results: list[dict[str, Any]],
        context: SkillContext,
    ) -> dict[str, Any]:
        """Analyze raw search results and extract structured insights.

        Returns a dict with:

        * ``"key_facts"`` -- list of concise factual statements.
        * ``"sources"`` -- list of source URLs that contributed.
        * ``"themes"`` -- high-level themes or categories identified.
        * ``"contradictions"`` -- conflicting claims (if any).

        Args:
            results: Search results from the search phase.
            context: Skill execution context.

        Returns:
            A structured analysis dict.
        """
        key_facts: list[str] = []
        sources: list[str] = []
        themes: set[str] = set()

        for result in results:
            snippet = result.get("snippet", "")
            url = result.get("url", "")
            title = result.get("title", "")

            if snippet:
                # Extract individual sentences as candidate facts.
                sentences = [
                    s.strip() for s in snippet.replace("\n", " ").split(".")
                    if len(s.strip()) > 20
                ]
                key_facts.extend(sentences)

            if url:
                sources.append(url)

            if title:
                themes.update(self._extract_themes(title))

        # Deduplicate facts while preserving order.
        seen: set[str] = set()
        unique_facts: list[str] = []
        for fact in key_facts:
            normalized = fact.lower().strip()
            if normalized not in seen:
                seen.add(normalized)
                unique_facts.append(fact)

        analysis: dict[str, Any] = {
            "key_facts": unique_facts,
            "sources": list(dict.fromkeys(sources)),  # deduplicate, keep order
            "themes": sorted(themes),
            "contradictions": self._find_contradictions(unique_facts),
            "result_count": len(results),
        }

        logger.info(
            "Analysis phase extracted %d facts, %d sources, %d themes.",
            len(unique_facts),
            len(analysis["sources"]),
            len(analysis["themes"]),
        )
        return analysis

    async def _synthesize_phase(
        self,
        analysis: dict[str, Any],
        original_task: str,
        context: SkillContext,
    ) -> str:
        """Synthesize the analysis into a coherent natural-language summary.

        The summary is structured as:

        1. A direct answer to the original task.
        2. Supporting evidence from key facts.
        3. Source attribution.

        Args:
            analysis: Structured analysis from the analyze phase.
            original_task: The user's original task string.
            context: Skill execution context.

        Returns:
            A formatted summary string.
        """
        key_facts = analysis.get("key_facts", [])
        sources = analysis.get("sources", [])
        themes = analysis.get("themes", [])

        sections: list[str] = []

        # Header
        sections.append(f"## Research Summary\n\n**Task:** {original_task}\n")

        # Themes overview
        if themes:
            theme_list = ", ".join(themes)
            sections.append(f"**Key themes:** {theme_list}\n")

        # Key findings
        if key_facts:
            sections.append("### Key Findings\n")
            # Group into a readable list, capping at 15 to avoid walls of text.
            for i, fact in enumerate(key_facts[:15], start=1):
                sections.append(f"{i}. {fact}.")
            if len(key_facts) > 15:
                sections.append(f"\n*... and {len(key_facts) - 15} more findings.*")
            sections.append("")  # blank line
        else:
            sections.append(
                "No concrete findings were extracted.  The search may need "
                "more specific queries.\n"
            )

        # Sources
        if sources:
            sections.append("### Sources\n")
            for url in sources[:10]:
                sections.append(f"- {url}")
            sections.append("")

        return "\n".join(sections)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _get_tool(context: SkillContext, name: str) -> Any:
        """Retrieve a tool callable from the context's tool registry.

        Supports both dict-like and attribute-based tool registries.

        Args:
            context: Skill execution context.
            name: Tool name to look up.

        Returns:
            The tool callable, or ``None`` if unavailable.
        """
        if context.tools is None:
            return None
        if isinstance(context.tools, dict):
            return context.tools.get(name)
        return getattr(context.tools, name, None)

    @staticmethod
    def _expand_queries(query: str) -> list[str]:
        """Generate query variants for broader search coverage.

        Returns the original query plus up to two reformulations.

        Args:
            query: Original search query.

        Returns:
            A list of 1-3 query strings.
        """
        queries = [query]
        # Add a more specific variant.
        words = query.split()
        if len(words) > 4:
            queries.append(" ".join(words[:5]) + " detailed explanation")
        # Add a broader variant.
        if len(words) > 2:
            queries.append(" ".join(words[:3]) + " overview")
        return queries

    @staticmethod
    def _extract_themes(title: str) -> list[str]:
        """Extract rough thematic labels from a result title.

        Splits on common delimiters and filters short tokens.

        Args:
            title: A search result title.

        Returns:
            A list of candidate theme strings.
        """
        separators = [" - ", " | ", ": ", " -- "]
        parts = [title]
        for sep in separators:
            expanded: list[str] = []
            for part in parts:
                expanded.extend(part.split(sep))
            parts = expanded
        return [p.strip() for p in parts if len(p.strip()) > 3]

    @staticmethod
    def _find_contradictions(facts: list[str]) -> list[dict[str, str]]:
        """Heuristically detect contradictions among extracted facts.

        Uses simple negation pattern matching.  A production implementation
        would use NLI or an LLM, but this gives a useful first pass.

        Args:
            facts: List of factual statements.

        Returns:
            A list of dicts with ``"fact_a"`` and ``"fact_b"`` keys.
        """
        negation_pairs = [
            ("is not", "is"),
            ("does not", "does"),
            ("cannot", "can"),
            ("no longer", "still"),
            ("never", "always"),
        ]
        contradictions: list[dict[str, str]] = []
        for i, fact_a in enumerate(facts):
            for fact_b in facts[i + 1:]:
                a_lower = fact_a.lower()
                b_lower = fact_b.lower()
                for neg, pos in negation_pairs:
                    if (neg in a_lower and pos in b_lower) or (
                        neg in b_lower and pos in a_lower
                    ):
                        # Check that the facts share at least one significant word.
                        words_a = {w for w in a_lower.split() if len(w) > 4}
                        words_b = {w for w in b_lower.split() if len(w) > 4}
                        if words_a & words_b:
                            contradictions.append({"fact_a": fact_a, "fact_b": fact_b})
                            break
        return contradictions

    @staticmethod
    async def _recall_from_memory(memory: Any, query: str) -> list[str]:
        """Retrieve relevant memories as plain-text snippets.

        Supports memory objects with an async ``search`` or ``recall``
        method that returns objects with a ``content`` attribute or plain
        strings.

        Args:
            memory: The memory subsystem handle.
            query: Search query.

        Returns:
            A list of memory content strings.
        """
        recall_fn = getattr(memory, "search", None) or getattr(memory, "recall", None)
        if recall_fn is None:
            return []

        raw_results = await recall_fn(query)
        if not isinstance(raw_results, (list, tuple)):
            raw_results = [raw_results]

        snippets: list[str] = []
        for item in raw_results:
            if isinstance(item, str):
                snippets.append(item)
            elif hasattr(item, "content"):
                snippets.append(str(item.content))
            elif hasattr(item, "entry") and hasattr(item.entry, "content"):
                snippets.append(str(item.entry.content))
        return snippets

    @staticmethod
    async def _store_in_memory(memory: Any, task: str, summary: str) -> None:
        """Persist the research summary into the memory subsystem.

        Supports memory objects with an async ``store`` or ``add`` method.

        Args:
            memory: The memory subsystem handle.
            task: Original task (used as metadata).
            summary: The synthesised summary to persist.
        """
        store_fn = getattr(memory, "store", None) or getattr(memory, "add", None)
        if store_fn is None:
            return
        await store_fn(
            content=summary,
            metadata={"source": "research_skill", "task": task},
        )
