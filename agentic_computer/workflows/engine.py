"""Workflow execution engine for agentic-computer.

Loads YAML workflow definitions, resolves step dependencies into parallel
execution layers, performs variable substitution, and runs each layer
concurrently via :func:`asyncio.gather` with per-step retry logic.
"""

from __future__ import annotations

import asyncio
import copy
import logging
import re
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

import yaml

from agentic_computer.tools.registry import ToolRegistry, ToolResult

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class WorkflowStatus(str, Enum):
    """Lifecycle status of a workflow or an individual step."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class WorkflowStep:
    """A single executable step within a workflow.

    Attributes:
        id: Unique identifier within the workflow (e.g. ``"search_web"``).
        name: Human-readable label for display purposes.
        tool: Name of the registered tool to invoke for this step.
        params: Keyword arguments forwarded to the tool.  May contain
            ``{{variable}}`` placeholders resolved at execution time.
        depends_on: IDs of steps that must complete before this one starts.
        status: Current lifecycle status of the step.
        result: Output value produced by the tool, set after execution.
        retries: Maximum number of retry attempts on failure (0 = no retries).
    """

    id: str
    name: str
    tool: str
    params: dict[str, Any] = field(default_factory=dict)
    depends_on: list[str] = field(default_factory=list)
    status: WorkflowStatus = WorkflowStatus.PENDING
    result: Any = None
    retries: int = 0


@dataclass
class WorkflowDefinition:
    """Complete description of a workflow ready for execution.

    Attributes:
        name: Short name identifying the workflow (e.g. ``"research"``).
        description: Longer explanation of what the workflow accomplishes.
        steps: Ordered list of :class:`WorkflowStep` instances.
        variables: Default variable bindings available for ``{{var}}``
            substitution in step parameters.
    """

    name: str
    description: str
    steps: list[WorkflowStep] = field(default_factory=list)
    variables: dict[str, Any] = field(default_factory=dict)


@dataclass
class WorkflowResult:
    """Aggregate outcome of executing a :class:`WorkflowDefinition`.

    Attributes:
        workflow_name: Name of the workflow that was executed.
        status: Overall status — ``COMPLETED`` only if every step succeeded.
        step_results: Mapping of step IDs to their individual outputs.
        duration_seconds: Wall-clock time for the entire workflow run.
    """

    workflow_name: str
    status: WorkflowStatus
    step_results: dict[str, Any] = field(default_factory=dict)
    duration_seconds: float = 0.0


# ---------------------------------------------------------------------------
# Variable substitution pattern
# ---------------------------------------------------------------------------

_VAR_PATTERN = re.compile(r"\{\{\s*(\w[\w.]*)\s*\}\}")
"""Matches ``{{var_name}}`` or ``{{ step_id.field }}`` references."""


# ---------------------------------------------------------------------------
# Workflow engine
# ---------------------------------------------------------------------------


class WorkflowEngine:
    """Execute :class:`WorkflowDefinition` workflows with dependency-aware
    parallelism and automatic retries.

    The engine resolves step dependencies into *layers* — groups of steps
    whose dependencies are all satisfied — and runs each layer concurrently
    using :func:`asyncio.gather`.

    Parameters:
        registry: A :class:`ToolRegistry` containing the tools referenced by
            workflow steps.  If ``None`` a fresh empty registry is created.
        max_concurrency: Upper bound on the number of steps that may run in
            parallel within a single layer.  ``0`` means unlimited.
    """

    def __init__(
        self,
        registry: ToolRegistry | None = None,
        max_concurrency: int = 0,
    ) -> None:
        self._registry: ToolRegistry = registry or ToolRegistry()
        self._max_concurrency: int = max_concurrency

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def execute(self, definition: WorkflowDefinition) -> WorkflowResult:
        """Execute all steps in *definition*, respecting dependencies.

        Independent steps (those whose dependencies are already satisfied)
        are run concurrently within the same execution layer.  A failing step
        is retried up to ``WorkflowStep.retries`` times before the step is
        marked :attr:`WorkflowStatus.FAILED`.  If any step fails the overall
        workflow status is ``FAILED``; otherwise ``COMPLETED``.

        Args:
            definition: The workflow to execute.

        Returns:
            A :class:`WorkflowResult` summarising the run.
        """
        start = time.monotonic()
        context: dict[str, Any] = dict(definition.variables)
        step_results: dict[str, Any] = {}

        # Deep-copy steps so re-execution doesn't mutate the definition.
        steps = [self._copy_step(s) for s in definition.steps]

        layers = self._resolve_step_order(steps)
        overall_status = WorkflowStatus.COMPLETED

        for layer in layers:
            # Skip entire layer if workflow already failed.
            if overall_status == WorkflowStatus.FAILED:
                for step in layer:
                    step.status = WorkflowStatus.CANCELLED
                    step_results[step.id] = None
                continue

            tasks = [
                self._execute_step(step, context)
                for step in layer
            ]

            if self._max_concurrency > 0:
                results = await self._gather_with_limit(tasks, self._max_concurrency)
            else:
                results = await asyncio.gather(*tasks, return_exceptions=True)

            for step, result in zip(layer, results):
                if isinstance(result, BaseException):
                    step.status = WorkflowStatus.FAILED
                    step.result = str(result)
                    step_results[step.id] = str(result)
                    overall_status = WorkflowStatus.FAILED
                    logger.error(
                        "Workflow '%s': step '%s' raised %s",
                        definition.name,
                        step.id,
                        result,
                    )
                else:
                    step_results[step.id] = step.result
                    if step.status == WorkflowStatus.FAILED:
                        overall_status = WorkflowStatus.FAILED

                # Propagate step output into context for downstream steps.
                context[step.id] = step.result

        elapsed = time.monotonic() - start
        return WorkflowResult(
            workflow_name=definition.name,
            status=overall_status,
            step_results=step_results,
            duration_seconds=round(elapsed, 4),
        )

    async def execute_file(
        self,
        path: Path,
        input_data: dict[str, Any] | None = None,
    ) -> WorkflowResult:
        """Load a YAML workflow file, merge *input_data* into its variables,
        and execute it.

        Args:
            path: Filesystem path to the YAML workflow definition.
            input_data: Extra variable bindings merged on top of the
                definition's own ``variables`` section.

        Returns:
            A :class:`WorkflowResult` from :meth:`execute`.

        Raises:
            FileNotFoundError: If *path* does not exist.
            ValueError: If the YAML cannot be parsed into a valid workflow.
        """
        definition = self._load_yaml(path)
        if input_data:
            definition.variables.update(input_data)
        return await self.execute(definition)

    # ------------------------------------------------------------------
    # YAML loading
    # ------------------------------------------------------------------

    def _load_yaml(self, path: Path) -> WorkflowDefinition:
        """Parse a YAML file at *path* into a :class:`WorkflowDefinition`.

        Expected YAML structure::

            name: research
            description: Perform web research and produce a report.
            variables:
              topic: "default topic"
            steps:
              - id: search_web
                name: Search the Web
                tool: web_search
                params:
                  query: "{{topic}}"
                depends_on: []
                retries: 2

        Args:
            path: Path to the YAML file.

        Returns:
            A fully populated :class:`WorkflowDefinition`.

        Raises:
            FileNotFoundError: If *path* does not point to a file.
            ValueError: If required keys are missing or data is malformed.
        """
        path = Path(path)
        if not path.is_file():
            raise FileNotFoundError(f"Workflow file not found: {path}")

        with open(path, "r", encoding="utf-8") as fh:
            raw: dict[str, Any] = yaml.safe_load(fh)

        if not isinstance(raw, dict):
            raise ValueError(f"Expected a YAML mapping at top level in {path}")

        name: str = raw.get("name", path.stem)
        description: str = raw.get("description", "")
        variables: dict[str, Any] = raw.get("variables", {})

        raw_steps = raw.get("steps")
        if not isinstance(raw_steps, list):
            raise ValueError(f"'steps' must be a list in {path}")

        steps: list[WorkflowStep] = []
        for idx, raw_step in enumerate(raw_steps):
            if not isinstance(raw_step, dict):
                raise ValueError(
                    f"Step {idx} in {path} must be a mapping, got {type(raw_step).__name__}"
                )
            step_id = raw_step.get("id")
            if not step_id:
                raise ValueError(f"Step {idx} in {path} is missing required 'id' field")

            steps.append(
                WorkflowStep(
                    id=str(step_id),
                    name=str(raw_step.get("name", step_id)),
                    tool=str(raw_step.get("tool", "")),
                    params=dict(raw_step.get("params", {})),
                    depends_on=list(raw_step.get("depends_on", [])),
                    retries=int(raw_step.get("retries", 0)),
                )
            )

        return WorkflowDefinition(
            name=name,
            description=description,
            steps=steps,
            variables=variables,
        )

    # ------------------------------------------------------------------
    # Dependency resolution
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_step_order(
        steps: list[WorkflowStep],
    ) -> list[list[WorkflowStep]]:
        """Group *steps* into sequential execution layers, respecting
        ``depends_on`` edges.

        Steps whose dependencies are all in previous layers are placed in the
        same layer and may execute concurrently.  This is equivalent to a
        topological sort expressed as a level decomposition of the DAG.

        Args:
            steps: Flat list of workflow steps.

        Returns:
            A list of layers, each layer being a list of steps that can
            execute in parallel.

        Raises:
            ValueError: If a dependency cycle is detected or a step
                references an unknown dependency.
        """
        step_map: dict[str, WorkflowStep] = {s.id: s for s in steps}
        all_ids: set[str] = set(step_map)

        # Validate dependency references.
        for step in steps:
            unknown = set(step.depends_on) - all_ids
            if unknown:
                raise ValueError(
                    f"Step '{step.id}' depends on unknown step(s): {unknown}"
                )

        placed: set[str] = set()
        remaining: dict[str, WorkflowStep] = dict(step_map)
        layers: list[list[WorkflowStep]] = []

        while remaining:
            # Identify steps whose deps are fully placed.
            layer: list[WorkflowStep] = [
                step
                for step in remaining.values()
                if all(dep in placed for dep in step.depends_on)
            ]

            if not layer:
                unresolved = ", ".join(sorted(remaining))
                raise ValueError(
                    f"Dependency cycle detected among steps: {unresolved}"
                )

            layers.append(layer)
            for step in layer:
                placed.add(step.id)
                del remaining[step.id]

        return layers

    # ------------------------------------------------------------------
    # Variable substitution
    # ------------------------------------------------------------------

    @staticmethod
    def _substitute_variables(
        params: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Replace ``{{variable_name}}`` placeholders in *params* values with
        values from *context*.

        Supports nested dotted references such as ``{{step_id.field}}``.  If a
        parameter value is a string that exactly matches a single placeholder
        (and nothing else), the raw context value is injected so non-string
        types survive.  Otherwise, all placeholders in the string are replaced
        with their ``str()`` representations.

        Args:
            params: Step parameter dict, potentially containing placeholders.
            context: Variable bindings (workflow variables plus prior step
                outputs).

        Returns:
            A new dict with all resolvable placeholders expanded.  Placeholders
            whose names are not in *context* are left unchanged.
        """

        def _resolve(name: str) -> Any:
            """Walk dotted path through *context*."""
            parts = name.split(".")
            value: Any = context
            for part in parts:
                if isinstance(value, dict):
                    if part not in value:
                        return None
                    value = value[part]
                else:
                    return None
            return value

        resolved: dict[str, Any] = {}
        for key, value in params.items():
            if isinstance(value, str):
                # Check for a pure single-placeholder value.
                match = _VAR_PATTERN.fullmatch(value.strip())
                if match:
                    looked_up = _resolve(match.group(1))
                    resolved[key] = looked_up if looked_up is not None else value
                else:
                    # Replace all occurrences within the string.
                    def _replacer(m: re.Match[str]) -> str:
                        found = _resolve(m.group(1))
                        return str(found) if found is not None else m.group(0)

                    resolved[key] = _VAR_PATTERN.sub(_replacer, value)
            elif isinstance(value, dict):
                resolved[key] = WorkflowEngine._substitute_variables(value, context)
            elif isinstance(value, list):
                resolved[key] = [
                    WorkflowEngine._substitute_variables({"_": item}, context)["_"]
                    if isinstance(item, (str, dict))
                    else item
                    for item in value
                ]
            else:
                resolved[key] = value

        return resolved

    # ------------------------------------------------------------------
    # Step execution with retries
    # ------------------------------------------------------------------

    async def _execute_step(
        self,
        step: WorkflowStep,
        context: dict[str, Any],
    ) -> ToolResult:
        """Run a single step through the tool registry with retry logic.

        On each attempt the step's ``params`` are freshly resolved against
        *context* so that variables updated by earlier retries are visible.

        Args:
            step: The workflow step to execute.
            context: Live variable context for substitution.

        Returns:
            The :class:`ToolResult` from the successful (or final) attempt.
        """
        step.status = WorkflowStatus.RUNNING
        max_attempts = step.retries + 1
        last_result: ToolResult | None = None

        for attempt in range(1, max_attempts + 1):
            resolved_params = self._substitute_variables(step.params, context)

            logger.info(
                "Workflow step '%s' attempt %d/%d (tool=%s)",
                step.id,
                attempt,
                max_attempts,
                step.tool,
            )

            result = await self._registry.execute(step.tool, **resolved_params)
            last_result = result

            if result.success:
                step.status = WorkflowStatus.COMPLETED
                step.result = result.output
                logger.info("Workflow step '%s' completed successfully.", step.id)
                return result

            logger.warning(
                "Workflow step '%s' failed (attempt %d/%d): %s",
                step.id,
                attempt,
                max_attempts,
                result.error,
            )

            if attempt < max_attempts:
                # Exponential back-off: 0.5s, 1s, 2s, ...
                await asyncio.sleep(0.5 * (2 ** (attempt - 1)))

        # All attempts exhausted.
        step.status = WorkflowStatus.FAILED
        step.result = last_result.error if last_result else "Unknown error"
        return last_result  # type: ignore[return-value]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _copy_step(step: WorkflowStep) -> WorkflowStep:
        """Create a deep copy of *step* so execution does not mutate the
        original definition."""
        return WorkflowStep(
            id=step.id,
            name=step.name,
            tool=step.tool,
            params=copy.deepcopy(step.params),
            depends_on=list(step.depends_on),
            status=WorkflowStatus.PENDING,
            result=None,
            retries=step.retries,
        )

    @staticmethod
    async def _gather_with_limit(
        coros: list[Any],
        limit: int,
    ) -> list[Any]:
        """Run coroutines with a concurrency limit using a semaphore.

        Args:
            coros: Awaitable objects to execute.
            limit: Maximum number running concurrently.

        Returns:
            Results in the same order as *coros*.
        """
        semaphore = asyncio.Semaphore(limit)

        async def _bounded(coro: Any) -> Any:
            async with semaphore:
                return await coro

        return await asyncio.gather(
            *[_bounded(c) for c in coros],
            return_exceptions=True,
        )
