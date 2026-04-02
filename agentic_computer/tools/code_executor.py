"""Sandboxed code execution tool.

Executes Python code and shell commands in isolated subprocess environments
with configurable timeout and memory limits.  Dangerous imports are blocked
at the AST level before execution.
"""

from __future__ import annotations

import ast
import asyncio
import logging
import os
import resource
import subprocess
import sys
import tempfile
from typing import Any

from agentic_computer.config import get_settings
from agentic_computer.tools.registry import BaseTool, ToolResult, ToolSpec

logger = logging.getLogger(__name__)

# Modules that are never allowed inside sandboxed Python execution.
BLOCKED_IMPORTS: frozenset[str] = frozenset(
    {
        "ctypes",
        "importlib",
        "multiprocessing",
        "signal",
        "socket",
        "_thread",
        "threading",
        "webbrowser",
    }
)


class CodeExecutor(BaseTool):
    """Execute Python code or shell commands in a sandboxed subprocess.

    Safety measures
    ---------------
    * **Import allow-list** -- an AST pass rejects scripts that attempt to
      import modules in :data:`BLOCKED_IMPORTS`.
    * **Timeout** -- processes are killed after the configured timeout.
    * **Memory limit** -- on Linux, ``RLIMIT_AS`` caps the virtual address
      space of the child process.
    """

    def __init__(self) -> None:
        self._settings = get_settings()

    # ------------------------------------------------------------------
    # BaseTool interface
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        return "code_executor"

    @property
    def description(self) -> str:
        return (
            "Execute Python code or shell commands in a sandboxed subprocess "
            "with timeout and memory limits."
        )

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name,
            description=self.description,
            parameters={
                "action": {
                    "type": "string",
                    "description": "Either 'python' or 'shell'.",
                },
                "code": {
                    "type": "string",
                    "description": "Python source code (for action='python').",
                },
                "command": {
                    "type": "string",
                    "description": "Shell command string (for action='shell').",
                },
                "timeout": {
                    "type": "integer",
                    "description": "Override timeout in seconds.",
                },
            },
            required_params=["action"],
        )

    async def execute(self, **kwargs: Any) -> ToolResult:
        """Dispatch to the appropriate execution mode."""
        action = kwargs.get("action", "")
        if action == "python":
            code = kwargs.get("code")
            if not code:
                return ToolResult(success=False, error="'code' is required for action='python'")
            timeout = kwargs.get("timeout", self._settings.sandbox.timeout)
            return await self.execute_python(code, timeout=timeout)
        if action == "shell":
            command = kwargs.get("command")
            if not command:
                return ToolResult(
                    success=False, error="'command' is required for action='shell'"
                )
            timeout = kwargs.get("timeout", self._settings.sandbox.timeout)
            return await self.execute_shell(command, timeout=timeout)
        return ToolResult(success=False, error=f"Unknown action '{action}'. Use 'python' or 'shell'.")

    # ------------------------------------------------------------------
    # Public execution methods
    # ------------------------------------------------------------------

    async def execute_python(self, code: str, *, timeout: int | None = None) -> ToolResult:
        """Execute *code* as a Python script in a subprocess.

        Args:
            code: Python source code to run.
            timeout: Maximum wall-clock seconds for the process.

        Returns:
            ToolResult with ``stdout`` and ``stderr`` in the output dict.
        """
        if not self._settings.sandbox.enabled:
            return ToolResult(success=False, error="Sandbox is disabled in configuration")

        # Static safety check -- reject dangerous imports.
        violation = self._check_imports(code)
        if violation:
            return ToolResult(success=False, error=f"Blocked import: {violation}")

        effective_timeout = timeout if timeout is not None else self._settings.sandbox.timeout
        max_mem_bytes = self._settings.sandbox.max_memory_mb * 1024 * 1024

        # Write code to a temp file so we can run it as a standalone script.
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as tmp:
            tmp.write(code)
            tmp_path = tmp.name

        try:
            result = await self._run_subprocess(
                [sys.executable, tmp_path],
                timeout=effective_timeout,
                max_memory=max_mem_bytes,
            )
            return result
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    async def execute_shell(self, command: str, *, timeout: int | None = None) -> ToolResult:
        """Execute *command* in a shell subprocess.

        Args:
            command: The shell command to execute.
            timeout: Maximum wall-clock seconds for the process.

        Returns:
            ToolResult with ``stdout``, ``stderr``, and ``return_code``.
        """
        if not self._settings.sandbox.enabled:
            return ToolResult(success=False, error="Sandbox is disabled in configuration")

        effective_timeout = timeout if timeout is not None else self._settings.sandbox.timeout
        max_mem_bytes = self._settings.sandbox.max_memory_mb * 1024 * 1024

        return await self._run_subprocess(
            command,
            timeout=effective_timeout,
            max_memory=max_mem_bytes,
            shell=True,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _check_imports(code: str) -> str | None:
        """Parse *code* as an AST and return the first blocked import, or ``None``.

        Args:
            code: Python source code.

        Returns:
            The name of the first disallowed module found, or ``None``.
        """
        try:
            tree = ast.parse(code)
        except SyntaxError:
            # Let the subprocess surface the real syntax error.
            return None

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root_module = alias.name.split(".")[0]
                    if root_module in BLOCKED_IMPORTS:
                        return root_module
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    root_module = node.module.split(".")[0]
                    if root_module in BLOCKED_IMPORTS:
                        return root_module
        return None

    @staticmethod
    async def _run_subprocess(
        cmd: str | list[str],
        *,
        timeout: int,
        max_memory: int,
        shell: bool = False,
    ) -> ToolResult:
        """Run *cmd* in a subprocess with resource limits.

        On Linux the child's virtual address space is capped via
        ``RLIMIT_AS``.  On other platforms the memory limit is silently
        skipped.
        """

        def _set_limits() -> None:
            """Pre-exec function to apply resource limits in the child."""
            try:
                resource.setrlimit(resource.RLIMIT_AS, (max_memory, max_memory))
            except (ValueError, AttributeError, OSError):
                # Not supported on this platform -- continue without the limit.
                pass

        loop = asyncio.get_running_loop()
        try:
            proc = await loop.run_in_executor(
                None,
                lambda: subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    shell=shell,
                    preexec_fn=_set_limits,
                ),
            )
            stdout = proc.stdout or ""
            stderr = proc.stderr or ""
            ok = proc.returncode == 0
            return ToolResult(
                success=ok,
                output={"stdout": stdout, "stderr": stderr, "return_code": proc.returncode},
                error=stderr if not ok else None,
            )
        except subprocess.TimeoutExpired:
            return ToolResult(
                success=False,
                error=f"Execution timed out after {timeout}s",
            )
        except Exception as exc:
            return ToolResult(success=False, error=str(exc))
