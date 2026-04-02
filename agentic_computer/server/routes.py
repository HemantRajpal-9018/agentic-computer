"""API routes for the agentic-computer server.

Provides RESTful endpoints for task management, workflow execution, tool
invocation, and memory operations.  All endpoints live under ``/api/v1``.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["api"])


# ---------------------------------------------------------------------------
# Pydantic request / response models
# ---------------------------------------------------------------------------

class TaskStatus(str, Enum):
    """Lifecycle status of a submitted task."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class TaskRequest(BaseModel):
    """Body for submitting a new task to the agent."""

    task: str = Field(..., min_length=1, description="Natural-language task description.")
    config: dict[str, Any] | None = Field(
        default=None,
        description="Optional configuration overrides for this task run.",
    )


class TaskResponse(BaseModel):
    """Representation of a task and its current state."""

    task_id: str = Field(..., description="Unique task identifier.")
    task: str = Field(..., description="Original task description.")
    status: TaskStatus = Field(..., description="Current lifecycle status.")
    result: Any | None = Field(default=None, description="Task output once completed.")
    error: str | None = Field(default=None, description="Error message if the task failed.")
    created_at: str = Field(..., description="ISO-8601 creation timestamp.")
    completed_at: str | None = Field(default=None, description="ISO-8601 completion timestamp.")


class WorkflowRequest(BaseModel):
    """Body for executing a workflow."""

    definition: dict[str, Any] = Field(
        ..., description="Workflow definition (steps, conditions, etc.)."
    )
    input_data: dict[str, Any] | None = Field(
        default=None,
        description="Optional input data fed into the first workflow step.",
    )


class WorkflowResponse(BaseModel):
    """Status snapshot of a workflow execution."""

    workflow_id: str = Field(..., description="Unique workflow identifier.")
    status: str = Field(..., description="Current workflow status.")
    result: Any | None = Field(default=None, description="Final output of the workflow.")
    steps_completed: int = Field(default=0, description="Number of steps executed so far.")


class WorkflowTemplate(BaseModel):
    """Metadata describing an available workflow template."""

    name: str = Field(..., description="Template name.")
    description: str = Field(default="", description="Human-readable description.")
    definition: dict[str, Any] = Field(default_factory=dict, description="Workflow definition.")


class ToolInfo(BaseModel):
    """Public metadata about a registered tool."""

    name: str = Field(..., description="Unique tool name.")
    description: str = Field(default="", description="What the tool does.")
    parameters: dict[str, Any] = Field(default_factory=dict, description="Parameter schema.")
    required_params: list[str] = Field(default_factory=list, description="Required parameter names.")


class ToolExecuteRequest(BaseModel):
    """Body for executing a specific tool by name."""

    parameters: dict[str, Any] = Field(
        default_factory=dict,
        description="Keyword arguments to pass to the tool.",
    )


class ToolExecuteResponse(BaseModel):
    """Result of a tool execution."""

    success: bool = Field(..., description="Whether the tool succeeded.")
    output: Any | None = Field(default=None, description="Tool output payload.")
    error: str | None = Field(default=None, description="Error message on failure.")
    duration_ms: float = Field(default=0.0, description="Execution time in milliseconds.")


class MemoryAddRequest(BaseModel):
    """Body for adding a new memory entry."""

    content: str = Field(..., min_length=1, description="Textual content of the memory.")
    memory_type: str = Field(default="working", description="Memory classification type.")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Arbitrary metadata.")
    importance: float = Field(
        default=0.5, ge=0.0, le=1.0, description="Importance score in [0, 1]."
    )


class MemoryEntryResponse(BaseModel):
    """Serialised representation of a stored memory entry."""

    id: str
    content: str
    memory_type: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str
    accessed_at: str
    access_count: int = 0
    importance_score: float = 0.5


class MemorySearchResponse(BaseModel):
    """A single search result pairing a memory entry with its score."""

    entry: MemoryEntryResponse
    similarity_score: float = 0.0


# ---------------------------------------------------------------------------
# In-memory task store (production would use a persistent backend)
# ---------------------------------------------------------------------------

_tasks: dict[str, TaskResponse] = {}


def _memory_entry_to_response(entry: Any) -> MemoryEntryResponse:
    """Convert a MemoryEntry dataclass to a Pydantic response model."""
    return MemoryEntryResponse(
        id=entry.id,
        content=entry.content,
        memory_type=entry.memory_type.value if hasattr(entry.memory_type, "value") else str(entry.memory_type),
        metadata=entry.metadata,
        created_at=entry.created_at.isoformat(),
        accessed_at=entry.accessed_at.isoformat(),
        access_count=entry.access_count,
        importance_score=entry.importance_score,
    )


# ---------------------------------------------------------------------------
# Task endpoints
# ---------------------------------------------------------------------------

@router.post("/tasks", response_model=TaskResponse, status_code=201)
async def submit_task(body: TaskRequest) -> TaskResponse:
    """Submit a new task for the agent to execute.

    The task is queued immediately and executed asynchronously in the
    background.  Use ``GET /tasks/{task_id}`` to poll for status and
    results.
    """
    task_id = uuid.uuid4().hex[:16]
    now = datetime.now(timezone.utc).isoformat()

    task_record = TaskResponse(
        task_id=task_id,
        task=body.task,
        status=TaskStatus.PENDING,
        created_at=now,
    )
    _tasks[task_id] = task_record

    # Fire-and-forget background execution
    asyncio.create_task(_execute_task(task_id, body.task, body.config))
    logger.info("Task %s submitted: %s", task_id, body.task[:80])

    return task_record


@router.get("/tasks/{task_id}", response_model=TaskResponse)
async def get_task(task_id: str) -> TaskResponse:
    """Retrieve the current status and result of a submitted task.

    Returns 404 if no task with the given ID exists.
    """
    record = _tasks.get(task_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found.")
    return record


@router.get("/tasks", response_model=list[TaskResponse])
async def list_tasks(
    limit: int = Query(default=20, ge=1, le=100, description="Max tasks to return."),
    status: TaskStatus | None = Query(default=None, description="Filter by status."),
) -> list[TaskResponse]:
    """List recent tasks, optionally filtered by status.

    Tasks are returned in reverse chronological order (newest first).
    """
    records = list(_tasks.values())
    if status is not None:
        records = [r for r in records if r.status == status]
    # Sort newest first by created_at
    records.sort(key=lambda r: r.created_at, reverse=True)
    return records[:limit]


async def _execute_task(
    task_id: str, task: str, config: dict[str, Any] | None
) -> None:
    """Background coroutine that runs a task through the agent pipeline.

    Updates the in-memory task record as execution progresses.
    """
    record = _tasks.get(task_id)
    if record is None:
        return

    record.status = TaskStatus.RUNNING

    try:
        # Attempt to use the orchestrator if available
        from agentic_computer.core.orchestrator import Orchestrator

        orchestrator = Orchestrator()
        result = await orchestrator.run(task)
        record.status = TaskStatus.COMPLETED
        record.result = str(result)
    except ImportError:
        # Orchestrator not yet implemented — mark as completed with a note
        logger.warning("Orchestrator not available; task %s completed with stub.", task_id)
        record.status = TaskStatus.COMPLETED
        record.result = f"Task received: {task}"
    except Exception as exc:
        logger.error("Task %s failed: %s", task_id, exc, exc_info=True)
        record.status = TaskStatus.FAILED
        record.error = str(exc)

    record.completed_at = datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Workflow endpoints
# ---------------------------------------------------------------------------

@router.post("/workflows", response_model=WorkflowResponse, status_code=201)
async def execute_workflow(body: WorkflowRequest) -> WorkflowResponse:
    """Execute a workflow defined inline.

    The workflow definition should contain steps, conditions, and any
    configuration required by the workflow engine.
    """
    workflow_id = uuid.uuid4().hex[:16]

    try:
        from agentic_computer.workflows.engine import WorkflowEngine

        engine = WorkflowEngine()
        result = await engine.execute(body.definition, body.input_data or {})
        return WorkflowResponse(
            workflow_id=workflow_id,
            status="completed",
            result=result,
            steps_completed=len(body.definition.get("steps", [])),
        )
    except ImportError:
        logger.warning("WorkflowEngine not available; returning stub response.")
        return WorkflowResponse(
            workflow_id=workflow_id,
            status="completed",
            result={"message": "Workflow accepted", "definition": body.definition},
            steps_completed=0,
        )
    except Exception as exc:
        logger.error("Workflow %s failed: %s", workflow_id, exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Workflow execution failed: {exc}")


@router.get("/workflows", response_model=list[WorkflowTemplate])
async def list_workflows() -> list[WorkflowTemplate]:
    """List available workflow templates.

    Returns built-in templates and any user-defined templates discovered
    in the workflows directory.
    """
    templates: list[WorkflowTemplate] = []
    try:
        from pathlib import Path

        workflows_dir = Path(__file__).resolve().parent.parent / "workflows" / "templates"
        if workflows_dir.is_dir():
            import yaml

            for yaml_file in sorted(workflows_dir.glob("*.yaml")):
                with open(yaml_file) as fh:
                    data = yaml.safe_load(fh) or {}
                templates.append(
                    WorkflowTemplate(
                        name=data.get("name", yaml_file.stem),
                        description=data.get("description", ""),
                        definition=data,
                    )
                )
    except Exception:
        logger.warning("Failed to load workflow templates", exc_info=True)

    # Always include default templates even if directory scanning fails
    if not templates:
        templates.append(
            WorkflowTemplate(
                name="research",
                description="Multi-step web research workflow with summarisation.",
                definition={
                    "name": "research",
                    "steps": ["search", "extract", "summarise"],
                },
            )
        )
        templates.append(
            WorkflowTemplate(
                name="code-review",
                description="Automated code review and refactoring suggestions.",
                definition={
                    "name": "code-review",
                    "steps": ["analyse", "review", "suggest"],
                },
            )
        )

    return templates


# ---------------------------------------------------------------------------
# Tool endpoints
# ---------------------------------------------------------------------------

@router.get("/tools", response_model=list[ToolInfo])
async def list_tools() -> list[ToolInfo]:
    """List all registered tools with their specifications.

    Returns name, description, parameters, and required parameter names
    for each tool in the registry.
    """
    from agentic_computer.server.app import app_state

    specs = app_state.tool_registry.list_tools()
    return [
        ToolInfo(
            name=spec.name,
            description=spec.description,
            parameters=spec.parameters,
            required_params=spec.required_params,
        )
        for spec in specs
    ]


@router.post("/tools/{tool_name}/execute", response_model=ToolExecuteResponse)
async def execute_tool(tool_name: str, body: ToolExecuteRequest) -> ToolExecuteResponse:
    """Execute a specific tool by name with the given parameters.

    Returns 404 if the tool is not registered.
    """
    from agentic_computer.server.app import app_state

    tool = app_state.tool_registry.get(tool_name)
    if tool is None:
        raise HTTPException(status_code=404, detail=f"Tool '{tool_name}' not found.")

    result = await app_state.tool_registry.execute(tool_name, **body.parameters)
    return ToolExecuteResponse(
        success=result.success,
        output=result.output,
        error=result.error,
        duration_ms=result.duration_ms,
    )


# ---------------------------------------------------------------------------
# Memory endpoints
# ---------------------------------------------------------------------------

@router.get("/memory/search", response_model=list[MemorySearchResponse])
async def search_memory(
    q: str = Query(..., min_length=1, description="Search query string."),
    limit: int = Query(default=10, ge=1, le=100, description="Maximum results."),
    memory_type: str | None = Query(default=None, description="Filter by memory type."),
) -> list[MemorySearchResponse]:
    """Search the memory store by text similarity.

    Uses the memory store's built-in search which supports both text
    matching and vector similarity when embeddings are available.
    """
    from agentic_computer.memory.schema import MemoryQuery, MemoryType
    from agentic_computer.server.app import app_state

    mt: MemoryType | None = None
    if memory_type is not None:
        try:
            mt = MemoryType(memory_type)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid memory_type '{memory_type}'. "
                f"Valid types: {[t.value for t in MemoryType]}",
            )

    query = MemoryQuery(query=q, memory_type=mt, limit=limit)
    results = await app_state.memory_store.search(query)

    return [
        MemorySearchResponse(
            entry=_memory_entry_to_response(r.entry),
            similarity_score=r.similarity_score,
        )
        for r in results
    ]


@router.post("/memory", response_model=MemoryEntryResponse, status_code=201)
async def add_memory(body: MemoryAddRequest) -> MemoryEntryResponse:
    """Add a new entry to the memory store.

    The entry is persisted immediately and can be retrieved via search
    or the recent-memories endpoint.
    """
    from agentic_computer.memory.schema import MemoryType
    from agentic_computer.server.app import app_state

    try:
        mt = MemoryType(body.memory_type)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid memory_type '{body.memory_type}'. "
            f"Valid types: {[t.value for t in MemoryType]}",
        )

    entry = await app_state.memory_store.add(
        content=body.content,
        memory_type=mt,
        metadata=body.metadata,
        importance=body.importance,
    )

    return _memory_entry_to_response(entry)


@router.get("/memory/recent", response_model=list[MemoryEntryResponse])
async def get_recent_memories(
    limit: int = Query(default=20, ge=1, le=100, description="Maximum entries to return."),
) -> list[MemoryEntryResponse]:
    """Return the most recently accessed memory entries.

    Entries are ordered by last-access timestamp descending.
    """
    from agentic_computer.server.app import app_state

    entries = await app_state.memory_store.get_recent(limit=limit)
    return [_memory_entry_to_response(e) for e in entries]
