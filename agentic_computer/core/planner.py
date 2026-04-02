"""Task planning and dependency resolution for agentic-computer.

The :class:`Planner` uses an LLM to decompose a high-level task into a
:class:`TaskPlan` of ordered :class:`SubTask` items, then builds a dependency
graph and produces a topologically-sorted execution order so the downstream
:class:`~agentic_computer.core.executor.Executor` can schedule work correctly.
"""

from __future__ import annotations

import json
import logging
import uuid
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from agentic_computer.config import LLMConfig, get_settings
from agentic_computer.core.agent import (
    AgentRole,
    AgentState,
    BaseAgent,
    Plan,
    Result,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


class SubTaskStatus(str, Enum):
    """Lifecycle of an individual subtask."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class SubTask:
    """A single unit of work inside a :class:`TaskPlan`.

    Attributes:
        id: Unique identifier for this subtask.
        description: What needs to be done.
        agent_role: Which :class:`AgentRole` should handle this subtask.
        dependencies: IDs of subtasks that must complete first.
        status: Current lifecycle status.
        result: Populated once execution finishes.
        metadata: Arbitrary extra context.
    """

    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    description: str = ""
    agent_role: AgentRole = AgentRole.EXECUTOR
    dependencies: list[str] = field(default_factory=list)
    status: SubTaskStatus = SubTaskStatus.PENDING
    result: Any = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class TaskPlan:
    """A decomposed plan for a high-level task.

    Attributes:
        id: Unique plan identifier.
        description: The original task description.
        subtasks: Ordered list of :class:`SubTask` items.
        dependencies: Adjacency list mapping subtask ID -> list of dependency IDs.
        metadata: Arbitrary extra context.
    """

    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    description: str = ""
    subtasks: list[SubTask] = field(default_factory=list)
    dependencies: dict[str, list[str]] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    # ----- convenience helpers ----------------------------------------

    def get_subtask(self, subtask_id: str) -> SubTask | None:
        """Return the subtask with *subtask_id*, or ``None``."""
        for st in self.subtasks:
            if st.id == subtask_id:
                return st
        return None

    def ready_subtasks(self) -> list[SubTask]:
        """Return subtasks whose dependencies are all completed."""
        completed_ids = {
            st.id for st in self.subtasks if st.status == SubTaskStatus.COMPLETED
        }
        return [
            st
            for st in self.subtasks
            if st.status == SubTaskStatus.PENDING
            and all(dep in completed_ids for dep in st.dependencies)
        ]

    @property
    def is_complete(self) -> bool:
        """``True`` when every subtask has finished (completed, failed, or skipped)."""
        terminal = {SubTaskStatus.COMPLETED, SubTaskStatus.FAILED, SubTaskStatus.SKIPPED}
        return all(st.status in terminal for st in self.subtasks)


# ---------------------------------------------------------------------------
# Dependency graph helpers
# ---------------------------------------------------------------------------


def build_dependency_graph(subtasks: list[SubTask]) -> dict[str, list[str]]:
    """Build an adjacency-list dependency graph from a list of subtasks.

    Returns:
        Dict mapping each subtask ID to the list of subtask IDs it depends on.
    """
    return {st.id: list(st.dependencies) for st in subtasks}


def topological_sort(graph: dict[str, list[str]]) -> list[str]:
    """Return a topologically sorted list of node IDs (Kahn's algorithm).

    Args:
        graph: Adjacency list where ``graph[node]`` lists the nodes it
            depends on (i.e. edges point *from* dependency *to* dependent).

    Returns:
        Node IDs in an order where every node appears after all of its
        dependencies.

    Raises:
        ValueError: If the graph contains a cycle.
    """
    # Build in-degree map and reverse adjacency for traversal.
    in_degree: dict[str, int] = {node: 0 for node in graph}
    reverse: dict[str, list[str]] = {node: [] for node in graph}
    for node, deps in graph.items():
        in_degree[node] = len(deps)
        for dep in deps:
            if dep not in reverse:
                reverse[dep] = []
            reverse[dep].append(node)

    queue: deque[str] = deque(
        node for node, degree in in_degree.items() if degree == 0
    )
    ordered: list[str] = []

    while queue:
        node = queue.popleft()
        ordered.append(node)
        for dependent in reverse.get(node, []):
            in_degree[dependent] -= 1
            if in_degree[dependent] == 0:
                queue.append(dependent)

    if len(ordered) != len(graph):
        raise ValueError(
            "Dependency graph contains a cycle — cannot produce a valid execution order."
        )
    return ordered


# ---------------------------------------------------------------------------
# Planner agent
# ---------------------------------------------------------------------------

_PLAN_SYSTEM_PROMPT = """\
You are a task planning assistant.  Given a high-level task, decompose it into
concrete subtasks that can be executed independently where possible.

Return a JSON array of objects with exactly these keys:
  - "description" (string): what the subtask should accomplish.
  - "agent_role" (string): one of "planner", "executor", "verifier", "researcher", "coder".
  - "dependencies" (array of ints): zero-indexed positions of subtasks this one depends on.

Return ONLY valid JSON — no markdown fences, no commentary.
"""


class Planner(BaseAgent):
    """Agent that decomposes a high-level task into an executable plan.

    The planner sends the task to the configured LLM with a structured prompt,
    parses the JSON response into :class:`SubTask` objects, builds a dependency
    graph, and returns a :class:`TaskPlan` with a topologically valid ordering.

    Parameters:
        llm_config: Optional LLM configuration override.
    """

    def __init__(self, llm_config: LLMConfig | None = None) -> None:
        super().__init__(name="Planner", role=AgentRole.PLANNER, llm_config=llm_config)

    async def plan(self, task: str) -> TaskPlan:
        """Decompose *task* into a full :class:`TaskPlan`.

        This is the primary public API.  It calls :pymeth:`think` internally
        and enriches the result with dependency resolution.

        Args:
            task: Natural-language description of the work to be done.

        Returns:
            A :class:`TaskPlan` with subtasks ordered by dependency.
        """
        self.state = AgentState.THINKING
        self.add_message("user", task)

        try:
            subtasks = await self._decompose_task(task)
            if not subtasks:
                # Fallback: single subtask mirroring the whole task.
                subtasks = [
                    SubTask(description=task, agent_role=AgentRole.EXECUTOR)
                ]

            dep_graph = build_dependency_graph(subtasks)
            sorted_ids = topological_sort(dep_graph)

            # Reorder subtasks to match the topological ordering.
            id_to_subtask = {st.id: st for st in subtasks}
            ordered = [id_to_subtask[sid] for sid in sorted_ids if sid in id_to_subtask]

            plan = TaskPlan(
                description=task,
                subtasks=ordered,
                dependencies=dep_graph,
            )
            self.state = AgentState.DONE
            logger.info(
                "Planner created plan %s with %d subtasks for: %s",
                plan.id,
                len(plan.subtasks),
                task[:80],
            )
            return plan

        except Exception as exc:
            self.state = AgentState.ERROR
            logger.error("Planning failed: %s", exc)
            # Return a minimal single-step plan so the system can still proceed.
            fallback = TaskPlan(
                description=task,
                subtasks=[SubTask(description=task, agent_role=AgentRole.EXECUTOR)],
            )
            fallback.dependencies = build_dependency_graph(fallback.subtasks)
            return fallback

    # ------------------------------------------------------------------
    # BaseAgent interface
    # ------------------------------------------------------------------

    async def think(self, task: str) -> Plan:
        """Return a lightweight :class:`Plan` for compatibility with BaseAgent."""
        task_plan = await self.plan(task)
        return Plan(
            description=task_plan.description,
            steps=[st.description for st in task_plan.subtasks],
            metadata={"plan_id": task_plan.id},
        )

    async def execute(self, plan: Plan) -> Result:
        """Planners do not execute — they return the plan as a result."""
        return Result(
            success=True,
            output=plan,
            metadata={"note": "Planner does not execute; returning plan as output."},
        )

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _decompose_task(self, task: str) -> list[SubTask]:
        """Ask the LLM to break *task* into subtasks and parse the response."""
        messages = [
            {"role": "system", "content": _PLAN_SYSTEM_PROMPT},
            {"role": "user", "content": task},
        ]
        raw = await self.llm_call(messages)
        return self._parse_subtasks(raw)

    @staticmethod
    def _parse_subtasks(raw_json: str) -> list[SubTask]:
        """Parse LLM JSON output into a list of :class:`SubTask` objects.

        Handles common LLM output quirks (markdown fences, trailing commas).
        """
        text = raw_json.strip()
        # Strip markdown code fences if present.
        if text.startswith("```"):
            lines = text.splitlines()
            text = "\n".join(
                line for line in lines if not line.strip().startswith("```")
            )

        try:
            items = json.loads(text)
        except json.JSONDecodeError:
            logger.warning("Failed to parse planner JSON; returning empty list.")
            return []

        if not isinstance(items, list):
            items = [items]

        role_map = {r.value: r for r in AgentRole}
        subtasks: list[SubTask] = []
        id_list: list[str] = []

        # First pass: create subtasks with temporary IDs.
        for item in items:
            st = SubTask(
                description=item.get("description", ""),
                agent_role=role_map.get(item.get("agent_role", "executor"), AgentRole.EXECUTOR),
            )
            subtasks.append(st)
            id_list.append(st.id)

        # Second pass: resolve integer-index dependencies to actual IDs.
        for idx, item in enumerate(items):
            raw_deps = item.get("dependencies", [])
            resolved: list[str] = []
            for dep in raw_deps:
                if isinstance(dep, int) and 0 <= dep < len(id_list):
                    resolved.append(id_list[dep])
                elif isinstance(dep, str) and dep in id_list:
                    resolved.append(dep)
            subtasks[idx].dependencies = resolved

        return subtasks
