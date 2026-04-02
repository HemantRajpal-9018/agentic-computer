"""Tests for the core agent module."""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime

import pytest

from agentic_computer.core.agent import (
    AgentRole,
    AgentState,
    BaseAgent,
    Message,
    Result,
)


class ConcreteAgent(BaseAgent):
    """Concrete implementation of BaseAgent for testing."""

    async def think(self, task: str) -> dict:
        return {"plan": f"Plan for: {task}", "steps": ["step1", "step2"]}

    async def execute(self, plan: dict) -> Result:
        return Result(
            success=True,
            output=f"Executed: {plan.get('plan', '')}",
            error=None,
            metadata={"steps_completed": 2},
        )


class TestMessage:
    """Tests for the Message dataclass."""

    def test_create_message(self) -> None:
        msg = Message(role="user", content="Hello")
        assert msg.role == "user"
        assert msg.content == "Hello"
        assert isinstance(msg.timestamp, datetime)

    def test_message_default_timestamp(self) -> None:
        from datetime import timezone
        before = datetime.now(timezone.utc)
        msg = Message(role="assistant", content="Hi there")
        after = datetime.now(timezone.utc)
        assert before <= msg.timestamp <= after


class TestResult:
    """Tests for the Result dataclass."""

    def test_successful_result(self) -> None:
        result = Result(success=True, output="done", error=None, metadata={})
        assert result.success is True
        assert result.output == "done"
        assert result.error is None

    def test_failed_result(self) -> None:
        result = Result(success=False, output="", error="Something broke", metadata={})
        assert result.success is False
        assert result.error == "Something broke"

    def test_result_with_metadata(self) -> None:
        meta = {"duration_ms": 150, "tokens_used": 500}
        result = Result(success=True, output="ok", error=None, metadata=meta)
        assert result.metadata["duration_ms"] == 150
        assert result.metadata["tokens_used"] == 500


class TestAgentRole:
    """Tests for the AgentRole enum."""

    def test_all_roles_exist(self) -> None:
        roles = [AgentRole.PLANNER, AgentRole.EXECUTOR, AgentRole.VERIFIER,
                 AgentRole.RESEARCHER, AgentRole.CODER]
        assert len(roles) == 5

    def test_role_values(self) -> None:
        assert AgentRole.PLANNER.value == "planner"
        assert AgentRole.EXECUTOR.value == "executor"


class TestAgentState:
    """Tests for the AgentState enum."""

    def test_all_states_exist(self) -> None:
        states = [AgentState.IDLE, AgentState.THINKING, AgentState.EXECUTING,
                  AgentState.DONE, AgentState.ERROR]
        assert len(states) == 5


class TestBaseAgent:
    """Tests for the BaseAgent abstract class."""

    def test_create_agent(self) -> None:
        agent = ConcreteAgent(name="test-agent", role=AgentRole.EXECUTOR)
        assert agent.name == "test-agent"
        assert agent.role == AgentRole.EXECUTOR
        assert agent.state == AgentState.IDLE
        assert isinstance(agent.id, str)
        assert len(agent.memory) == 0

    def test_agent_has_unique_id(self) -> None:
        a1 = ConcreteAgent(name="agent-1", role=AgentRole.PLANNER)
        a2 = ConcreteAgent(name="agent-2", role=AgentRole.PLANNER)
        assert a1.id != a2.id

    @pytest.mark.asyncio
    async def test_agent_think(self) -> None:
        agent = ConcreteAgent(name="thinker", role=AgentRole.PLANNER)
        plan = await agent.think("Write a hello world program")
        assert "plan" in plan
        assert "steps" in plan
        assert len(plan["steps"]) == 2

    @pytest.mark.asyncio
    async def test_agent_execute(self) -> None:
        agent = ConcreteAgent(name="executor", role=AgentRole.EXECUTOR)
        plan = await agent.think("Build feature X")
        result = await agent.execute(plan)
        assert result.success is True
        assert "Executed" in result.output
        assert result.metadata["steps_completed"] == 2

    def test_agent_reset(self) -> None:
        agent = ConcreteAgent(name="resettable", role=AgentRole.CODER)
        agent.state = AgentState.ERROR
        agent.memory.append(Message(role="user", content="test"))
        agent.reset()
        assert agent.state == AgentState.IDLE
        assert len(agent.memory) == 0

    def test_agent_add_message(self) -> None:
        agent = ConcreteAgent(name="chatty", role=AgentRole.RESEARCHER)
        agent.memory.append(Message(role="user", content="Find info about X"))
        agent.memory.append(Message(role="assistant", content="Here's what I found..."))
        assert len(agent.memory) == 2
        assert agent.memory[0].role == "user"
        assert agent.memory[1].role == "assistant"
