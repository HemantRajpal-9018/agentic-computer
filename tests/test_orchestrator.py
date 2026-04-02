"""Tests for the orchestrator and planner modules."""

from __future__ import annotations

import pytest

from agentic_computer.core.agent import AgentRole, AgentState, BaseAgent, Result
from agentic_computer.core.orchestrator import Orchestrator
from agentic_computer.core.planner import Planner, SubTask, TaskPlan


class MockAgent(BaseAgent):
    """Mock agent for testing orchestration."""

    async def think(self, task: str) -> dict:
        return {"plan": task, "steps": [task]}

    async def execute(self, plan: dict) -> Result:
        return Result(
            success=True,
            output=f"Mock result for: {plan.get('plan', '')}",
            error=None,
            metadata={},
        )


class TestPlanner:
    """Tests for the task planner."""

    def test_create_subtask(self) -> None:
        subtask = SubTask(
            id="st-1",
            description="Search for information",
            agent_role=AgentRole.RESEARCHER,
            dependencies=[],
        )
        assert subtask.id == "st-1"
        assert subtask.agent_role == AgentRole.RESEARCHER
        assert subtask.status == "pending"

    def test_create_task_plan(self) -> None:
        subtasks = [
            SubTask(id="1", description="Plan", agent_role=AgentRole.PLANNER, dependencies=[]),
            SubTask(id="2", description="Code", agent_role=AgentRole.CODER, dependencies=["1"]),
            SubTask(id="3", description="Verify", agent_role=AgentRole.VERIFIER, dependencies=["2"]),
        ]
        plan = TaskPlan(
            id="plan-1",
            description="Build a feature",
            subtasks=subtasks,
            dependencies={"2": ["1"], "3": ["2"]},
        )
        assert len(plan.subtasks) == 3
        assert plan.dependencies["3"] == ["2"]

    @pytest.mark.asyncio
    async def test_planner_creates_plan(self) -> None:
        planner = Planner()
        plan = await planner.plan("Write a Python script that sorts a list")
        assert isinstance(plan, TaskPlan)
        assert len(plan.subtasks) > 0
        assert plan.description != ""

    @pytest.mark.asyncio
    async def test_planner_simple_task(self) -> None:
        planner = Planner()
        plan = await planner.plan("Print hello world")
        assert isinstance(plan, TaskPlan)
        # Simple tasks should still produce at least one subtask
        assert len(plan.subtasks) >= 1

    def test_subtask_status_transitions(self) -> None:
        subtask = SubTask(
            id="st-1",
            description="Do work",
            agent_role=AgentRole.EXECUTOR,
            dependencies=[],
        )
        assert subtask.status == "pending"
        subtask.status = "running"
        assert subtask.status == "running"
        subtask.status = "completed"
        assert subtask.status == "completed"


class TestOrchestrator:
    """Tests for the multi-agent orchestrator."""

    def test_create_orchestrator(self) -> None:
        orch = Orchestrator()
        assert orch is not None

    @pytest.mark.asyncio
    async def test_orchestrator_run_simple_task(self) -> None:
        orch = Orchestrator()
        result = await orch.run("What is 2 + 2?")
        assert result is not None

    @pytest.mark.asyncio
    async def test_orchestrator_registers_agents(self) -> None:
        orch = Orchestrator()
        # Orchestrator should have internal agents
        assert hasattr(orch, "agents") or hasattr(orch, "_agents")

    def test_orchestrator_has_planner(self) -> None:
        orch = Orchestrator()
        # Orchestrator should have a planner for task decomposition
        assert hasattr(orch, "_planner") or hasattr(orch, "planner")
