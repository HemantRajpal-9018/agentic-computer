"""Workflow tool for chaining, parallelising, and branching tool executions.

Allows the orchestrator to describe multi-step plans as structured data
and have them executed through the :class:`ToolRegistry`.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from agentic_computer.tools.registry import BaseTool, ToolRegistry, ToolResult, ToolSpec

logger = logging.getLogger(__name__)


class WorkflowTool(BaseTool):
    """Compose tool calls into sequential, parallel, or conditional workflows.

    Every workflow step is a dict with at least ``{"tool": "<name>", ...params}``.
    The ``chain`` method feeds each step's output as ``_previous_result`` into the
    next step, while ``parallel`` runs all steps concurrently.

    This tool requires a :class:`ToolRegistry` reference so it can look up and
    invoke other registered tools.
    """

    def __init__(self, registry: ToolRegistry) -> None:
        """Initialise with a live registry.

        Args:
            registry: The :class:`ToolRegistry` used to resolve tool names.
        """
        self._registry = registry

    # ------------------------------------------------------------------
    # BaseTool interface
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        return "workflow"

    @property
    def description(self) -> str:
        return (
            "Chain, parallelise, or conditionally branch tool executions. "
            "Accepts structured step definitions and routes them through the "
            "tool registry."
        )

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name,
            description=self.description,
            parameters={
                "action": {
                    "type": "string",
                    "description": "One of: chain, parallel, conditional.",
                },
                "steps": {
                    "type": "array",
                    "description": (
                        "List of step dicts, each with a 'tool' key and additional "
                        "params.  Used by chain and parallel."
                    ),
                },
                "condition": {
                    "type": "object",
                    "description": (
                        "A step dict whose ToolResult.output is evaluated as truthy/falsy "
                        "(for conditional)."
                    ),
                },
                "if_true": {
                    "type": "object",
                    "description": "Step to execute when condition is truthy.",
                },
                "if_false": {
                    "type": "object",
                    "description": "Step to execute when condition is falsy.",
                },
            },
            required_params=["action"],
        )

    async def execute(self, **kwargs: Any) -> ToolResult:
        """Dispatch to the workflow action."""
        action = kwargs.get("action", "")
        if action == "chain":
            steps = kwargs.get("steps")
            if not steps or not isinstance(steps, list):
                return ToolResult(success=False, error="'steps' (list) is required for chain")
            return await self.chain(steps)
        if action == "parallel":
            steps = kwargs.get("steps")
            if not steps or not isinstance(steps, list):
                return ToolResult(success=False, error="'steps' (list) is required for parallel")
            return await self.parallel(steps)
        if action == "conditional":
            condition = kwargs.get("condition")
            if_true = kwargs.get("if_true")
            if_false = kwargs.get("if_false")
            if condition is None or if_true is None:
                return ToolResult(
                    success=False,
                    error="'condition' and 'if_true' are required for conditional",
                )
            return await self.conditional(condition, if_true, if_false)
        return ToolResult(
            success=False,
            error=f"Unknown workflow action '{action}'. Use chain, parallel, or conditional.",
        )

    # ------------------------------------------------------------------
    # Public workflow methods
    # ------------------------------------------------------------------

    async def chain(self, steps: list[dict[str, Any]]) -> ToolResult:
        """Execute *steps* sequentially, threading outputs forward.

        Each step is executed through the tool registry.  The output of step
        *N* is injected into step *N+1* under the key ``_previous_result``.
        If any step fails the chain aborts immediately.

        Args:
            steps: Ordered list of step definitions.

        Returns:
            ToolResult from the final step, or the first failing step.
        """
        previous_output: Any = None
        last_result = ToolResult(success=True, output=None)

        for index, step in enumerate(steps):
            tool_name, params = self._parse_step(step)
            if tool_name is None:
                return ToolResult(
                    success=False,
                    error=f"Step {index} is missing the required 'tool' key",
                )

            # Inject previous step's output so the current step can use it.
            if previous_output is not None:
                params["_previous_result"] = previous_output

            logger.info("chain step %d: tool=%s", index, tool_name)
            result = await self._registry.execute(tool_name, **params)
            if not result.success:
                logger.warning("chain aborted at step %d (%s): %s", index, tool_name, result.error)
                return ToolResult(
                    success=False,
                    error=f"Chain failed at step {index} ({tool_name}): {result.error}",
                    output={"failed_step": index, "step_result": result.output},
                )
            previous_output = result.output
            last_result = result

        return ToolResult(
            success=True,
            output=previous_output,
            duration_ms=last_result.duration_ms,
        )

    async def parallel(self, steps: list[dict[str, Any]]) -> ToolResult:
        """Execute *steps* concurrently and collect all results.

        All steps run at the same time via :func:`asyncio.gather`.  The
        overall result is successful only if every individual step succeeds.

        Args:
            steps: List of step definitions (order is not significant).

        Returns:
            ToolResult whose ``output`` is a list of per-step outputs.
        """
        tasks: list[asyncio.Task[ToolResult]] = []
        tool_names: list[str] = []

        for index, step in enumerate(steps):
            tool_name, params = self._parse_step(step)
            if tool_name is None:
                return ToolResult(
                    success=False,
                    error=f"Step {index} is missing the required 'tool' key",
                )
            tool_names.append(tool_name)
            tasks.append(
                asyncio.create_task(
                    self._registry.execute(tool_name, **params),
                    name=f"parallel-{index}-{tool_name}",
                )
            )

        logger.info("parallel: launching %d tasks", len(tasks))
        results: list[ToolResult] = await asyncio.gather(*tasks)

        all_ok = all(r.success for r in results)
        outputs = [r.output for r in results]
        errors = [
            f"Step {i} ({tool_names[i]}): {r.error}"
            for i, r in enumerate(results)
            if not r.success
        ]
        return ToolResult(
            success=all_ok,
            output=outputs,
            error="; ".join(errors) if errors else None,
        )

    async def conditional(
        self,
        condition: dict[str, Any],
        if_true: dict[str, Any],
        if_false: dict[str, Any] | None = None,
    ) -> ToolResult:
        """Evaluate *condition* and branch to *if_true* or *if_false*.

        The condition step is executed first.  Its ``output`` is interpreted
        as a boolean: any truthy value selects *if_true*, falsy selects
        *if_false*.  If *if_false* is ``None`` and the condition is falsy,
        a no-op success is returned.

        Args:
            condition: Step dict whose output determines the branch.
            if_true: Step to execute when the condition is truthy.
            if_false: Optional step to execute when the condition is falsy.

        Returns:
            ToolResult from the chosen branch.
        """
        # Evaluate the condition step.
        cond_tool, cond_params = self._parse_step(condition)
        if cond_tool is None:
            return ToolResult(
                success=False, error="Condition step is missing the 'tool' key"
            )

        cond_result = await self._registry.execute(cond_tool, **cond_params)
        if not cond_result.success:
            return ToolResult(
                success=False,
                error=f"Condition evaluation failed: {cond_result.error}",
            )

        is_truthy = bool(cond_result.output)
        logger.info("conditional: condition=%s, branch=%s", cond_result.output, is_truthy)

        if is_truthy:
            branch = if_true
        elif if_false is not None:
            branch = if_false
        else:
            return ToolResult(success=True, output=None)

        branch_tool, branch_params = self._parse_step(branch)
        if branch_tool is None:
            return ToolResult(success=False, error="Branch step is missing the 'tool' key")

        # Pass the condition output into the branch step for context.
        branch_params["_condition_result"] = cond_result.output
        return await self._registry.execute(branch_tool, **branch_params)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_step(step: dict[str, Any]) -> tuple[str | None, dict[str, Any]]:
        """Extract the tool name and parameters from a step dict.

        The ``"tool"`` key is popped from a shallow copy; everything else is
        forwarded as keyword arguments.

        Returns:
            ``(tool_name, params)`` — *tool_name* is ``None`` if the key is
            missing.
        """
        step = dict(step)  # shallow copy to avoid mutating the caller's data
        tool_name = step.pop("tool", None)
        return tool_name, step
