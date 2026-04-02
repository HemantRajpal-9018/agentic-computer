"""Tool registry for agentic-computer.

Provides the base abstractions (ToolSpec, ToolResult, BaseTool) and a
ToolRegistry that supports registration, lookup, auto-discovery, and
parameter validation before execution.
"""

from __future__ import annotations

import importlib
import inspect
import logging
import pkgutil
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ToolSpec:
    """Declarative specification of a tool's interface.

    Attributes:
        name: Unique identifier for the tool.
        description: Human-readable summary of what the tool does.
        parameters: Mapping of parameter names to their JSON-schema-style
            descriptions (e.g. ``{"query": {"type": "string", "description": "..."}}``)
        required_params: Names of parameters that must be provided.
    """

    name: str
    description: str
    parameters: dict[str, Any] = field(default_factory=dict)
    required_params: list[str] = field(default_factory=list)


@dataclass
class ToolResult:
    """Outcome of a single tool execution.

    Attributes:
        success: Whether the tool completed without error.
        output: Arbitrary payload returned by the tool.
        error: Human-readable error message, or ``None`` on success.
        duration_ms: Wall-clock time spent inside ``execute``, in milliseconds.
    """

    success: bool
    output: Any = None
    error: str | None = None
    duration_ms: float = 0.0


class BaseTool(ABC):
    """Abstract base class that every tool must subclass.

    Subclasses must implement :pymethod:`name`, :pymethod:`description`,
    :pymethod:`spec`, and :pymethod:`execute`.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the unique name of the tool."""

    @property
    @abstractmethod
    def description(self) -> str:
        """Return a human-readable description of the tool."""

    @abstractmethod
    def spec(self) -> ToolSpec:
        """Return the full specification (parameters, required params, etc.)."""

    @abstractmethod
    async def execute(self, **kwargs: Any) -> ToolResult:
        """Run the tool with the given keyword arguments.

        Implementations should catch their own exceptions and return a
        ``ToolResult`` with ``success=False`` rather than raising.
        """


class ToolRegistry:
    """Central registry that manages tool instances.

    Features
    --------
    * ``register`` / ``get`` / ``list_tools`` for manual management.
    * ``execute`` for validated invocation (checks required params first).
    * ``discover`` to auto-scan a Python package directory, import every
      module, and register any :class:`BaseTool` subclass found.
    """

    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}

    # ------------------------------------------------------------------
    # Registration helpers
    # ------------------------------------------------------------------

    def register(self, tool: BaseTool) -> None:
        """Register a tool instance.

        Args:
            tool: A concrete :class:`BaseTool` subclass instance.

        Raises:
            TypeError: If *tool* is not a :class:`BaseTool` instance.
            ValueError: If a tool with the same name is already registered.
        """
        if not isinstance(tool, BaseTool):
            raise TypeError(f"Expected a BaseTool instance, got {type(tool).__name__}")
        if tool.name in self._tools:
            raise ValueError(f"Tool '{tool.name}' is already registered")
        self._tools[tool.name] = tool
        logger.info("Registered tool: %s", tool.name)

    def get(self, name: str) -> BaseTool | None:
        """Return the tool registered under *name*, or ``None``."""
        return self._tools.get(name)

    def list_tools(self) -> list[ToolSpec]:
        """Return the specs for every registered tool."""
        return [tool.spec() for tool in self._tools.values()]

    # ------------------------------------------------------------------
    # Execution with validation
    # ------------------------------------------------------------------

    async def execute(self, tool_name: str, **kwargs: Any) -> ToolResult:
        """Look up *tool_name*, validate required params, and execute.

        Returns a :class:`ToolResult` — never raises on user error.
        """
        tool = self.get(tool_name)
        if tool is None:
            return ToolResult(
                success=False,
                error=f"Unknown tool: '{tool_name}'",
            )

        # Validate required parameters
        tool_spec = tool.spec()
        missing = [p for p in tool_spec.required_params if p not in kwargs]
        if missing:
            return ToolResult(
                success=False,
                error=f"Missing required parameter(s) for '{tool_name}': {', '.join(missing)}",
            )

        start = time.perf_counter()
        try:
            result = await tool.execute(**kwargs)
        except Exception as exc:
            elapsed = (time.perf_counter() - start) * 1000
            logger.exception("Tool '%s' raised an unhandled exception", tool_name)
            return ToolResult(success=False, error=str(exc), duration_ms=elapsed)

        result.duration_ms = (time.perf_counter() - start) * 1000
        return result

    # ------------------------------------------------------------------
    # Auto-discovery
    # ------------------------------------------------------------------

    def discover(self, package_path: str | Path) -> list[str]:
        """Scan *package_path* for Python modules, import them, and register
        any :class:`BaseTool` **concrete** subclasses found.

        Args:
            package_path: Filesystem path to the directory to scan.  It must
                be a valid Python package (contain ``__init__.py``).

        Returns:
            Names of newly registered tools.
        """
        package_path = Path(package_path)
        if not package_path.is_dir():
            logger.warning("discover: %s is not a directory", package_path)
            return []

        # Determine the importable package name by finding the root on sys.path.
        package_name = self._resolve_package_name(package_path)
        if package_name is None:
            logger.warning("discover: could not resolve package name for %s", package_path)
            return []

        registered: list[str] = []
        for finder, module_name, _is_pkg in pkgutil.iter_modules([str(package_path)]):
            fqn = f"{package_name}.{module_name}"
            try:
                module = importlib.import_module(fqn)
            except Exception:
                logger.warning("discover: failed to import %s", fqn, exc_info=True)
                continue

            for _attr_name, obj in inspect.getmembers(module, inspect.isclass):
                if (
                    issubclass(obj, BaseTool)
                    and obj is not BaseTool
                    and not inspect.isabstract(obj)
                    and obj.name.fget is not None  # type: ignore[attr-defined]
                ):
                    try:
                        instance = obj()
                        if instance.name not in self._tools:
                            self.register(instance)
                            registered.append(instance.name)
                    except Exception:
                        logger.warning(
                            "discover: could not instantiate %s.%s",
                            fqn,
                            obj.__name__,
                            exc_info=True,
                        )

        return registered

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_package_name(directory: Path) -> str | None:
        """Walk up from *directory* collecting package segments until we
        leave the package hierarchy (no ``__init__.py``).

        Returns the dotted package name, e.g. ``"agentic_computer.tools"``.
        """
        parts: list[str] = []
        current = directory.resolve()
        while (current / "__init__.py").exists():
            parts.append(current.name)
            current = current.parent
        if not parts:
            return None
        parts.reverse()
        return ".".join(parts)

    def __len__(self) -> int:
        return len(self._tools)

    def __contains__(self, name: str) -> bool:
        return name in self._tools

    def __repr__(self) -> str:
        names = ", ".join(sorted(self._tools))
        return f"ToolRegistry([{names}])"
