"""Core agent framework for agentic-computer.

Re-exports the five principal classes so that downstream code can do::

    from agentic_computer.core import Agent, Orchestrator, Planner, Executor, Verifier
"""

from agentic_computer.core.agent import BaseAgent as Agent
from agentic_computer.core.executor import Executor
from agentic_computer.core.orchestrator import Orchestrator
from agentic_computer.core.planner import Planner
from agentic_computer.core.verifier import Verifier

__all__ = [
    "Agent",
    "Orchestrator",
    "Planner",
    "Executor",
    "Verifier",
]
