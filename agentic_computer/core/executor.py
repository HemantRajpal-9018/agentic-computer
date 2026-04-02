"""Task executor with parallel scheduling, retry logic, and progress tracking.

The :class:`Executor` takes a :class:`~agentic_computer.core.planner.TaskPlan`
and drives its subtasks through to completion, respecting the dependency graph,
running independent subtasks in parallel via ``asyncio.gather``, and retrying
transient failures with exponential back-off.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable

from agentic_computer.config import LLMConfig, get_settings
from agentic_computer.core.agent import (
    AgentRole,
    AgentState,
    BaseAgent,
    Plan,
    Result,
)
from agentic_computer.core.planner import SubTask, SubTaskStatus, TaskPlan

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Supporting data classes
# ---------------------------------------------------------------------------


@dataclass
class ExecutionContext:
    """Runtime context passed to every subtask execution.

    Attributes:
        plan: The full :class:`TaskPlan` being executed.
        results: Mapping of subtask ID -> :class:`Result` for completed subtasks.
        start_time: Epoch timestamp when execution began.
        metadata: Arbitrary extra context (e.g. environment info).
    """

    plan: TaskPlan
    results: dict[str, Result] = field(default_factory=dict)
    start_time: float = field(default_factory=time.monotonic)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def elapsed_seconds(self) -> float:
        """Seconds elapsed since execution started."""
        return time.monotonic() - self.start_time

    @property
    def completed_count(self) -> int:
        """Number of subtasks that have finished (success or failure)."""
        return len(self.results)

    @property
    def total_count(self) -> int:
        """Total number of subtasks in the plan."""
        return len(self.plan.subtasks)

    @property
    def progress_pct(self) -> float:
        """Completion percentage (0.0 -- 100.0)."""
        if self.total_count == 0:
            return 100.0
        return (self.completed_count / self.total_count) * 100.0


@dataclass
class ProgressEvent:
    """A snapshot of execution progress, emitted after each subtask finishes.

    Attributes:
        subtask_id: The subtask that just completed.
        status: Terminal status of the subtask.
        completed: Number of subtasks finished so far.
        total: Total subtask count.
        elapsed: Seconds since execution began.
    """

    subtask_id: str
    status: SubTaskStatus
    completed: int
    total: int
    elapsed: float


# Type alias for an optional progress callback.
ProgressCallback = Callable[[ProgressEvent], Awaitable[None] | None]


# ---------------------------------------------------------------------------
# Executor agent
# ---------------------------------------------------------------------------

_EXECUTE_SYSTEM_PROMPT = """\
You are a task execution assistant.  You will be given a specific subtask
description along with context from previously completed subtasks.

Execute the subtask to the best of your ability and return a clear, concise
result.  If the subtask asks you to produce code, return only the code.
If it asks for analysis, return the analysis.  Be precise and thorough.
"""


class Executor(BaseAgent):
    """Agent that drives a :class:`TaskPlan` through to completion.

    Execution proceeds in *waves*: at each wave the executor identifies all
    subtasks whose dependencies are satisfied, runs them concurrently with
    ``asyncio.gather``, records results, and repeats until every subtask has
    a terminal status.

    Parameters:
        llm_config: Optional LLM configuration override.
        max_retries: Maximum number of retry attempts per subtask.
        base_delay: Initial back-off delay in seconds (doubled on each retry).
        on_progress: Optional async/sync callback invoked after each subtask.
    """

    def __init__(
        self,
        llm_config: LLMConfig | None = None,
        max_retries: int = 3,
        base_delay: float = 1.0,
        on_progress: ProgressCallback | None = None,
    ) -> None:
        super().__init__(name="Executor", role=AgentRole.EXECUTOR, llm_config=llm_config)
        self.max_retries: int = max_retries
        self.base_delay: float = base_delay
        self._on_progress: ProgressCallback | None = on_progress

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def execute_plan(self, plan: TaskPlan) -> ExecutionContext:
        """Execute all subtasks in *plan*, respecting dependencies.

        Args:
            plan: The plan produced by the :class:`Planner`.

        Returns:
            An :class:`ExecutionContext` containing every subtask result.
        """
        self.state = AgentState.EXECUTING
        ctx = ExecutionContext(plan=plan)
        logger.info(
            "Executor starting plan %s (%d subtasks).", plan.id, len(plan.subtasks)
        )

        try:
            while not plan.is_complete:
                ready = plan.ready_subtasks()
                if not ready:
                    # All remaining subtasks have unmet dependencies that
                    # themselves failed — mark them as skipped.
                    for st in plan.subtasks:
                        if st.status == SubTaskStatus.PENDING:
                            st.status = SubTaskStatus.SKIPPED
                            ctx.results[st.id] = Result(
                                success=False,
                                error="Skipped due to failed dependency.",
                            )
                            await self._emit_progress(ctx, st.id, SubTaskStatus.SKIPPED)
                    break

                # Run all ready subtasks concurrently.
                coros = [self._run_subtask(st, ctx) for st in ready]
                await asyncio.gather(*coros)

            self.state = AgentState.DONE
            logger.info(
                "Executor finished plan %s in %.1fs (%.0f%% success).",
                plan.id,
                ctx.elapsed_seconds,
                self._success_rate(ctx),
            )
        except Exception as exc:
            self.state = AgentState.ERROR
            logger.error("Executor encountered fatal error: %s", exc)
            raise

        return ctx

    # ------------------------------------------------------------------
    # BaseAgent interface
    # ------------------------------------------------------------------

    async def think(self, task: str) -> Plan:
        """Executors do not plan; returns a trivial single-step plan."""
        return Plan(description=task, steps=[task])

    async def execute(self, plan: Plan) -> Result:
        """Execute a lightweight :class:`Plan` by running its steps sequentially."""
        self.state = AgentState.EXECUTING
        outputs: list[str] = []
        for step in plan.steps:
            try:
                output = await self._execute_single_step(step, {})
                outputs.append(output)
            except Exception as exc:
                self.state = AgentState.ERROR
                return Result(success=False, error=str(exc))
        self.state = AgentState.DONE
        return Result(success=True, output="\n\n".join(outputs))

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _run_subtask(self, subtask: SubTask, ctx: ExecutionContext) -> None:
        """Execute a single subtask with retry logic and record the result."""
        subtask.status = SubTaskStatus.IN_PROGRESS
        last_error: str | None = None

        for attempt in range(1, self.max_retries + 1):
            try:
                dep_context = self._gather_dependency_context(subtask, ctx)
                output = await self._execute_single_step(subtask.description, dep_context)
                subtask.status = SubTaskStatus.COMPLETED
                subtask.result = output
                result = Result(
                    success=True,
                    output=output,
                    metadata={"attempts": attempt},
                )
                ctx.results[subtask.id] = result
                await self._emit_progress(ctx, subtask.id, SubTaskStatus.COMPLETED)
                logger.debug(
                    "Subtask %s completed on attempt %d.", subtask.id, attempt
                )
                return
            except Exception as exc:
                last_error = str(exc)
                logger.warning(
                    "Subtask %s attempt %d/%d failed: %s",
                    subtask.id,
                    attempt,
                    self.max_retries,
                    last_error,
                )
                if attempt < self.max_retries:
                    delay = self.base_delay * (2 ** (attempt - 1))
                    await asyncio.sleep(delay)

        # All retries exhausted.
        subtask.status = SubTaskStatus.FAILED
        ctx.results[subtask.id] = Result(
            success=False,
            error=last_error,
            metadata={"attempts": self.max_retries},
        )
        await self._emit_progress(ctx, subtask.id, SubTaskStatus.FAILED)

    async def _execute_single_step(
        self,
        description: str,
        dep_context: dict[str, str],
    ) -> str:
        """Send a subtask to the LLM and return the raw response.

        Args:
            description: What needs to be done.
            dep_context: Mapping of dependency subtask ID -> its output,
                so the LLM has access to prior results.
        """
        messages: list[dict[str, str]] = [
            {"role": "system", "content": _EXECUTE_SYSTEM_PROMPT},
        ]

        if dep_context:
            context_block = "\n\n".join(
                f"[Subtask {sid}]: {output}" for sid, output in dep_context.items()
            )
            messages.append(
                {
                    "role": "user",
                    "content": (
                        f"Context from completed subtasks:\n{context_block}\n\n"
                        f"Now execute this subtask:\n{description}"
                    ),
                }
            )
        else:
            messages.append({"role": "user", "content": description})

        return await self.llm_call(messages)

    def _gather_dependency_context(
        self,
        subtask: SubTask,
        ctx: ExecutionContext,
    ) -> dict[str, str]:
        """Collect outputs from the subtask's completed dependencies."""
        context: dict[str, str] = {}
        for dep_id in subtask.dependencies:
            result = ctx.results.get(dep_id)
            if result and result.success and result.output is not None:
                context[dep_id] = str(result.output)
        return context

    async def _emit_progress(
        self,
        ctx: ExecutionContext,
        subtask_id: str,
        status: SubTaskStatus,
    ) -> None:
        """Invoke the progress callback, if one was registered."""
        if self._on_progress is None:
            return

        event = ProgressEvent(
            subtask_id=subtask_id,
            status=status,
            completed=ctx.completed_count,
            total=ctx.total_count,
            elapsed=ctx.elapsed_seconds,
        )
        result = self._on_progress(event)
        # Support both sync and async callbacks.
        if asyncio.iscoroutine(result):
            await result

    @staticmethod
    def _success_rate(ctx: ExecutionContext) -> float:
        """Compute the percentage of subtasks that succeeded."""
        if not ctx.results:
            return 0.0
        successes = sum(1 for r in ctx.results.values() if r.success)
        return (successes / len(ctx.results)) * 100.0
