"""Multi-agent orchestrator for agentic-computer.

The :class:`Orchestrator` is the top-level coordinator.  It owns a pool of
:class:`~agentic_computer.core.agent.BaseAgent` instances, uses the
:class:`~agentic_computer.core.planner.Planner` to decompose tasks, routes
subtasks to agents by role, drives execution through the
:class:`~agentic_computer.core.executor.Executor`, and optionally verifies
results via the :class:`~agentic_computer.core.verifier.Verifier`.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from agentic_computer.config import LLMConfig, get_settings
from agentic_computer.core.agent import (
    AgentRole,
    AgentState,
    BaseAgent,
    Plan,
    Result,
)
from agentic_computer.core.executor import ExecutionContext, Executor
from agentic_computer.core.planner import Planner, SubTask, SubTaskStatus, TaskPlan
from agentic_computer.core.verifier import VerificationResult, Verifier

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Orchestration result
# ---------------------------------------------------------------------------


@dataclass
class OrchestrationResult:
    """Aggregate outcome of an orchestrated multi-agent run.

    Attributes:
        task: The original user task.
        plan: The decomposed :class:`TaskPlan`.
        execution_context: Full :class:`ExecutionContext` from the executor.
        verification: Optional :class:`VerificationResult` if verification ran.
        success: Overall pass/fail.
        output: Merged output from all subtasks.
        elapsed_seconds: Wall-clock time for the entire run.
        metadata: Arbitrary extra context.
    """

    task: str
    plan: TaskPlan
    execution_context: ExecutionContext
    verification: VerificationResult | None = None
    success: bool = True
    output: str = ""
    elapsed_seconds: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        status = "SUCCESS" if self.success else "FAILED"
        n_subtasks = len(self.plan.subtasks)
        return (
            f"[{status}] Completed {n_subtasks} subtask(s) in "
            f"{self.elapsed_seconds:.1f}s\n\n{self.output}"
        )


# ---------------------------------------------------------------------------
# Concrete worker agent used by the orchestrator
# ---------------------------------------------------------------------------


class _WorkerAgent(BaseAgent):
    """A generic worker agent that delegates to the LLM.

    The orchestrator creates one worker per role so that subtasks can be
    dispatched based on :class:`AgentRole`.
    """

    _SYSTEM_PROMPTS: dict[AgentRole, str] = {
        AgentRole.EXECUTOR: (
            "You are a general-purpose task executor.  Complete the given "
            "subtask thoroughly and return the result."
        ),
        AgentRole.RESEARCHER: (
            "You are a research assistant.  Investigate the given topic and "
            "return a clear, well-structured summary."
        ),
        AgentRole.CODER: (
            "You are a senior software engineer.  Write clean, idiomatic, "
            "well-documented code for the given task.  Return ONLY code."
        ),
        AgentRole.PLANNER: (
            "You are a planning assistant.  Break down the task and return "
            "a structured plan."
        ),
        AgentRole.VERIFIER: (
            "You are a verification assistant.  Check the given output for "
            "correctness and completeness."
        ),
    }

    def __init__(self, role: AgentRole, llm_config: LLMConfig | None = None) -> None:
        super().__init__(
            name=f"Worker-{role.value}",
            role=role,
            llm_config=llm_config,
        )

    async def think(self, task: str) -> Plan:
        """Return a trivial plan to execute the task in one step."""
        return Plan(description=task, steps=[task])

    async def execute(self, plan: Plan) -> Result:
        """Execute the plan's steps via the LLM and return combined output."""
        self.state = AgentState.EXECUTING
        outputs: list[str] = []
        system = self._SYSTEM_PROMPTS.get(self.role, self._SYSTEM_PROMPTS[AgentRole.EXECUTOR])
        for step in plan.steps:
            messages = [
                {"role": "system", "content": system},
                {"role": "user", "content": step},
            ]
            try:
                response = await self.llm_call(messages)
                outputs.append(response)
                self.add_message("assistant", response)
            except Exception as exc:
                self.state = AgentState.ERROR
                return Result(success=False, error=str(exc))
        self.state = AgentState.DONE
        return Result(success=True, output="\n\n".join(outputs))


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


class Orchestrator:
    """Coordinate multiple agents to complete a complex task.

    Workflow:
        1. **Plan** — the :class:`Planner` decomposes the task.
        2. **Route** — subtasks are assigned to role-appropriate agents.
        3. **Execute** — the :class:`Executor` drives the plan, running
           independent subtasks in parallel.
        4. **Verify** (optional) — the :class:`Verifier` checks the combined
           result.

    Parameters:
        llm_config: Shared LLM configuration for all managed agents.
        verify: Whether to run the verification step (default ``True``).
        max_retries: Passed through to the :class:`Executor`.
    """

    def __init__(
        self,
        llm_config: LLMConfig | None = None,
        verify: bool = True,
        max_retries: int = 3,
    ) -> None:
        self._llm_config = llm_config or get_settings().llm
        self._verify = verify

        # Core agents
        self.planner: Planner = Planner(llm_config=self._llm_config)
        self.executor: Executor = Executor(
            llm_config=self._llm_config, max_retries=max_retries
        )
        self.verifier: Verifier = Verifier(llm_config=self._llm_config)

        # Worker pool keyed by role
        self._workers: dict[AgentRole, _WorkerAgent] = {}

        self._agents: list[BaseAgent] = [self.planner, self.executor, self.verifier]

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def agents(self) -> list[BaseAgent]:
        """All agents currently managed by this orchestrator."""
        return list(self._agents)

    def register_agent(self, agent: BaseAgent) -> None:
        """Add a custom agent to the orchestrator pool.

        Args:
            agent: Any :class:`BaseAgent` subclass instance.
        """
        self._agents.append(agent)
        logger.info("Registered agent %s (%s).", agent.name, agent.role.value)

    async def run(self, task: str) -> OrchestrationResult:
        """Execute the full plan-route-execute-verify pipeline.

        Args:
            task: Natural-language description of the work to be done.

        Returns:
            An :class:`OrchestrationResult` with the combined output.
        """
        start = time.monotonic()
        logger.info("Orchestrator starting task: %s", task[:120])

        # 1. Plan
        plan = await self.planner.plan(task)
        logger.info("Plan %s has %d subtask(s).", plan.id, len(plan.subtasks))

        # 2. Route — assign workers to subtasks
        self._route_subtasks(plan)

        # 3. Execute
        ctx = await self.executor.execute_plan(plan)

        # 4. Aggregate output
        output = self._aggregate_output(plan, ctx)

        # 5. Verify (optional)
        verification: VerificationResult | None = None
        overall_success = all(r.success for r in ctx.results.values())

        if self._verify:
            verification = self.verifier.verify_completeness(
                task, plan, ctx.results
            )
            if not verification.passed:
                overall_success = False

        elapsed = time.monotonic() - start
        result = OrchestrationResult(
            task=task,
            plan=plan,
            execution_context=ctx,
            verification=verification,
            success=overall_success,
            output=output,
            elapsed_seconds=elapsed,
        )

        logger.info(
            "Orchestrator finished in %.1fs — %s",
            elapsed,
            "SUCCESS" if overall_success else "FAILED",
        )
        return result

    # ------------------------------------------------------------------
    # Task decomposition helpers (delegated to Planner, exposed here for
    # callers that want finer control)
    # ------------------------------------------------------------------

    async def decompose(self, task: str) -> TaskPlan:
        """Decompose *task* into subtasks without executing them.

        This is a convenience wrapper around ``self.planner.plan()``.
        """
        return await self.planner.plan(task)

    # ------------------------------------------------------------------
    # Agent routing
    # ------------------------------------------------------------------

    def _route_subtasks(self, plan: TaskPlan) -> None:
        """Ensure a worker agent exists for every role referenced in the plan.

        Workers are created lazily and cached in ``self._workers``.
        """
        for subtask in plan.subtasks:
            role = subtask.agent_role
            if role not in self._workers:
                worker = _WorkerAgent(role=role, llm_config=self._llm_config)
                self._workers[role] = worker
                self._agents.append(worker)
                logger.debug("Created worker agent for role %s.", role.value)

    def get_worker(self, role: AgentRole) -> _WorkerAgent:
        """Return (or create) the worker agent for *role*.

        Args:
            role: The agent role to look up.

        Returns:
            The :class:`_WorkerAgent` responsible for that role.
        """
        if role not in self._workers:
            worker = _WorkerAgent(role=role, llm_config=self._llm_config)
            self._workers[role] = worker
            self._agents.append(worker)
        return self._workers[role]

    # ------------------------------------------------------------------
    # Parallel subtask execution (alternative to Executor for direct use)
    # ------------------------------------------------------------------

    async def run_subtasks_parallel(
        self,
        subtasks: list[SubTask],
    ) -> dict[str, Result]:
        """Execute a list of independent subtasks concurrently.

        Each subtask is routed to a role-appropriate worker.  No dependency
        ordering is applied — all subtasks run at once.

        Args:
            subtasks: Independent subtasks to execute.

        Returns:
            Mapping of subtask ID -> :class:`Result`.
        """

        async def _run_one(st: SubTask) -> tuple[str, Result]:
            worker = self.get_worker(st.agent_role)
            plan = await worker.think(st.description)
            result = await worker.execute(plan)
            return st.id, result

        pairs = await asyncio.gather(*[_run_one(st) for st in subtasks])
        return dict(pairs)

    # ------------------------------------------------------------------
    # Result aggregation
    # ------------------------------------------------------------------

    @staticmethod
    def _aggregate_output(plan: TaskPlan, ctx: ExecutionContext) -> str:
        """Merge individual subtask outputs into a single string.

        Completed subtasks are numbered; failed/skipped ones are noted.
        """
        sections: list[str] = []
        for idx, st in enumerate(plan.subtasks, 1):
            result = ctx.results.get(st.id)
            header = f"## Subtask {idx}: {st.description}"
            if result is None:
                body = "(no result)"
            elif result.success:
                body = str(result.output) if result.output else "(empty output)"
            else:
                body = f"FAILED: {result.error or 'unknown error'}"
            sections.append(f"{header}\n{body}")
        return "\n\n".join(sections)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """Reset all managed agents to their initial state."""
        for agent in self._agents:
            agent.reset()
        logger.debug("Orchestrator reset all agents.")
