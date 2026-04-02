"""Base agent abstractions for the agentic-computer framework.

Defines the foundational types every agent in the system builds on:
``AgentRole``, ``AgentState``, ``Message``, ``Result``, and the abstract
``BaseAgent`` class with a provider-agnostic LLM call method.
"""

from __future__ import annotations

import abc
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from agentic_computer.config import LLMConfig, get_settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class AgentRole(str, Enum):
    """Functional roles an agent can fulfil."""

    PLANNER = "planner"
    EXECUTOR = "executor"
    VERIFIER = "verifier"
    RESEARCHER = "researcher"
    CODER = "coder"


class AgentState(str, Enum):
    """Lifecycle states for an agent instance."""

    IDLE = "idle"
    THINKING = "thinking"
    EXECUTING = "executing"
    DONE = "done"
    ERROR = "error"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class Message:
    """A single message in a conversation turn.

    Attributes:
        role: The speaker role (e.g. ``"system"``, ``"user"``, ``"assistant"``).
        content: Raw text content of the message.
        timestamp: UTC timestamp of when the message was created.
    """

    role: str
    content: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class Result:
    """Outcome of an agent action.

    Attributes:
        success: Whether the action completed without errors.
        output: The primary output value (text, data, etc.).
        error: If ``success`` is ``False``, the error description.
        metadata: Arbitrary key-value metadata about the execution.
    """

    success: bool
    output: Any = None
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Plan:
    """A lightweight plan produced by the *think* phase.

    Higher-level planning structures live in :pymod:`agentic_computer.core.planner`;
    this class captures the minimal think-step output so that ``BaseAgent.think``
    has a concrete return type.

    Attributes:
        description: Human-readable summary of the plan.
        steps: Ordered list of step descriptions.
        metadata: Arbitrary key-value metadata.
    """

    description: str
    steps: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Abstract base agent
# ---------------------------------------------------------------------------

class BaseAgent(abc.ABC):
    """Abstract base class for every agent in the system.

    Subclasses must implement :pymeth:`think` and :pymeth:`execute`.  The base
    class provides identity, state management, conversation memory, and a
    provider-agnostic :pymeth:`llm_call` helper that dispatches to OpenAI,
    Anthropic, or Ollama depending on the active ``LLMConfig``.

    Parameters:
        name: Human-readable agent name.
        role: The :class:`AgentRole` this agent fulfils.
        llm_config: Optional override; falls back to ``get_settings().llm``.
    """

    def __init__(
        self,
        name: str,
        role: AgentRole,
        llm_config: LLMConfig | None = None,
    ) -> None:
        self.id: str = uuid.uuid4().hex[:12]
        self.name: str = name
        self.role: AgentRole = role
        self.state: AgentState = AgentState.IDLE
        self.memory: list[Message] = []
        self._llm_config: LLMConfig = llm_config or get_settings().llm

    # ------------------------------------------------------------------
    # Abstract interface
    # ------------------------------------------------------------------

    @abc.abstractmethod
    async def think(self, task: str) -> Plan:
        """Analyse *task* and return a :class:`Plan`.

        Implementations should set ``self.state`` to ``THINKING`` at the
        start and back to ``IDLE`` (or ``ERROR``) when done.
        """

    @abc.abstractmethod
    async def execute(self, plan: Plan) -> Result:
        """Execute *plan* and return a :class:`Result`.

        Implementations should set ``self.state`` to ``EXECUTING`` at
        the start and to ``DONE`` or ``ERROR`` when finished.
        """

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """Reset the agent to its initial idle state, clearing memory."""
        self.state = AgentState.IDLE
        self.memory.clear()
        logger.debug("Agent %s (%s) reset.", self.name, self.id)

    def add_message(self, role: str, content: str) -> Message:
        """Append a message to the agent's conversation memory.

        Args:
            role: Speaker role (``"system"``, ``"user"``, ``"assistant"``).
            content: Message text.

        Returns:
            The newly created :class:`Message`.
        """
        msg = Message(role=role, content=content)
        self.memory.append(msg)
        return msg

    # ------------------------------------------------------------------
    # Provider-agnostic LLM call
    # ------------------------------------------------------------------

    async def llm_call(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        """Send *messages* to the configured LLM and return the response text.

        Dispatches to OpenAI, Anthropic, or Ollama based on
        ``self._llm_config.provider``.

        Args:
            messages: Chat-style message dicts (``{"role": …, "content": …}``).
            temperature: Override the config temperature for this call.
            max_tokens: Override the config max_tokens for this call.

        Returns:
            The assistant's reply as a plain string.

        Raises:
            ValueError: If the provider is not supported.
            RuntimeError: If the API call fails.
        """
        cfg = self._llm_config
        temp = temperature if temperature is not None else cfg.temperature
        tokens = max_tokens if max_tokens is not None else cfg.max_tokens

        provider = cfg.provider
        logger.debug(
            "Agent %s calling %s/%s (temp=%.2f, max_tokens=%d)",
            self.name,
            provider,
            cfg.model,
            temp,
            tokens,
        )

        try:
            if provider == "openai":
                return await self._call_openai(messages, temp, tokens)
            if provider == "anthropic":
                return await self._call_anthropic(messages, temp, tokens)
            if provider == "ollama":
                return await self._call_ollama(messages, temp, tokens)
            raise ValueError(f"Unsupported LLM provider: {provider!r}")
        except Exception as exc:
            logger.error("LLM call failed for agent %s: %s", self.name, exc)
            raise RuntimeError(f"LLM call failed: {exc}") from exc

    # ---- private provider implementations ----------------------------

    async def _call_openai(
        self,
        messages: list[dict[str, str]],
        temperature: float,
        max_tokens: int,
    ) -> str:
        """Call the OpenAI chat completions API.

        Uses the ``openai`` async client.  ``api_key`` and ``model`` come
        from the active :class:`LLMConfig`.
        """
        from openai import AsyncOpenAI

        cfg = self._llm_config
        client = AsyncOpenAI(api_key=cfg.api_key or None)
        response = await client.chat.completions.create(
            model=cfg.model,
            messages=messages,  # type: ignore[arg-type]
            temperature=temperature,
            max_tokens=max_tokens,
        )
        choice = response.choices[0]
        return choice.message.content or ""

    async def _call_anthropic(
        self,
        messages: list[dict[str, str]],
        temperature: float,
        max_tokens: int,
    ) -> str:
        """Call the Anthropic messages API.

        Anthropic expects a ``system`` parameter separate from the messages
        list, so we pop the first message if its role is ``"system"``.
        """
        from anthropic import AsyncAnthropic

        cfg = self._llm_config
        client = AsyncAnthropic(api_key=cfg.api_key or None)

        system_text: str | None = None
        chat_messages: list[dict[str, str]] = []
        for msg in messages:
            if msg["role"] == "system" and system_text is None:
                system_text = msg["content"]
            else:
                chat_messages.append(msg)

        kwargs: dict[str, Any] = {
            "model": cfg.model,
            "messages": chat_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if system_text:
            kwargs["system"] = system_text

        response = await client.messages.create(**kwargs)
        # Anthropic returns a list of content blocks.
        return "".join(
            block.text for block in response.content if hasattr(block, "text")
        )

    async def _call_ollama(
        self,
        messages: list[dict[str, str]],
        temperature: float,
        max_tokens: int,
    ) -> str:
        """Call a local Ollama instance via its OpenAI-compatible API.

        Falls back to ``http://localhost:11434/v1`` when no ``base_url`` is
        configured.
        """
        from openai import AsyncOpenAI

        cfg = self._llm_config
        base = cfg.base_url or "http://localhost:11434/v1"
        client = AsyncOpenAI(api_key="ollama", base_url=base)
        response = await client.chat.completions.create(
            model=cfg.model,
            messages=messages,  # type: ignore[arg-type]
            temperature=temperature,
            max_tokens=max_tokens,
        )
        choice = response.choices[0]
        return choice.message.content or ""

    # ------------------------------------------------------------------
    # Dunder helpers
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        return (
            f"<{self.__class__.__name__} id={self.id!r} name={self.name!r} "
            f"role={self.role.value!r} state={self.state.value!r}>"
        )
