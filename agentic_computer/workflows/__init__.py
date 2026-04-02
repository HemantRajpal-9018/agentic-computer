"""Workflow subsystem for agentic-computer.

Provides a YAML-driven workflow engine with dependency-aware parallel
execution and a DAG-based task graph for building and inspecting complex
task pipelines.

Public API
----------
WorkflowEngine
    Loads workflow definitions (from Python objects or YAML files), resolves
    step dependencies, and executes them with asyncio concurrency and retry
    logic.

TaskGraph
    Directed acyclic graph of tasks with topological ordering, cycle
    detection, serialisation, and query helpers.
"""

from agentic_computer.workflows.engine import (
    WorkflowDefinition,
    WorkflowEngine,
    WorkflowResult,
    WorkflowStatus,
    WorkflowStep,
)
from agentic_computer.workflows.graph import Edge, Node, TaskGraph

__all__ = [
    "Edge",
    "Node",
    "TaskGraph",
    "WorkflowDefinition",
    "WorkflowEngine",
    "WorkflowResult",
    "WorkflowStatus",
    "WorkflowStep",
]
