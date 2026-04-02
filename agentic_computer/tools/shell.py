"""Shell execution tool.

Runs commands in a subprocess with configurable timeout, working directory,
and a deny-list of dangerous command patterns.  Also supports launching
background processes and killing them by PID.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import signal
from typing import Any

from agentic_computer.tools.registry import BaseTool, ToolResult, ToolSpec

logger = logging.getLogger(__name__)

# Shell command patterns that are unconditionally blocked.
# Each entry is compiled to a regex and matched against the full command string.
BLOCKED_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\brm\s+(-\w*)?r\w*\s+/\s*$"),        # rm -rf /
    re.compile(r"\brm\s+(-\w*)?r\w*\s+/\*"),           # rm -rf /*
    re.compile(r"\bmkfs\b"),                             # mkfs.*
    re.compile(r"\bdd\s+.*of=/dev/"),                    # dd to raw devices
    re.compile(r">\s*/dev/sd[a-z]"),                     # redirect to disk device
    re.compile(r"\b:\(\)\s*\{\s*:\|\:\s*&\s*\}\s*;"),   # fork bomb
    re.compile(r"\bchmod\s+(-\w+\s+)?777\s+/\s*$"),     # chmod 777 /
    re.compile(r"\bchown\s+.*\s+/\s*$"),                 # chown on root
]

# Default timeout for shell commands (seconds).
DEFAULT_TIMEOUT: int = 60


class ShellTool(BaseTool):
    """Execute shell commands with safety guardrails.

    Features
    --------
    * Command deny-list that blocks obviously destructive operations.
    * Configurable timeout (default 60 s) and working directory.
    * Background process launch and kill support.
    """

    def __init__(self) -> None:
        self._background_procs: dict[int, asyncio.subprocess.Process] = {}

    # ------------------------------------------------------------------
    # BaseTool interface
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        return "shell"

    @property
    def description(self) -> str:
        return (
            "Run shell commands with timeout, working directory, and security "
            "restrictions.  Supports foreground and background execution."
        )

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name,
            description=self.description,
            parameters={
                "action": {
                    "type": "string",
                    "description": "One of: run, run_background, kill_process.",
                },
                "command": {
                    "type": "string",
                    "description": "Shell command to execute (for run / run_background).",
                },
                "timeout": {
                    "type": "integer",
                    "description": "Timeout in seconds (default 60, for run only).",
                },
                "cwd": {
                    "type": "string",
                    "description": "Working directory for the command.",
                },
                "pid": {
                    "type": "integer",
                    "description": "Process ID to kill (for kill_process).",
                },
            },
            required_params=["action"],
        )

    async def execute(self, **kwargs: Any) -> ToolResult:
        """Dispatch to the matching shell action."""
        action = kwargs.get("action", "")
        if action == "run":
            command = kwargs.get("command")
            if not command:
                return ToolResult(success=False, error="'command' is required for run")
            return await self.run(
                command,
                timeout=kwargs.get("timeout", DEFAULT_TIMEOUT),
                cwd=kwargs.get("cwd"),
            )
        if action == "run_background":
            command = kwargs.get("command")
            if not command:
                return ToolResult(
                    success=False, error="'command' is required for run_background"
                )
            return await self.run_background(command, cwd=kwargs.get("cwd"))
        if action == "kill_process":
            pid = kwargs.get("pid")
            if pid is None:
                return ToolResult(success=False, error="'pid' is required for kill_process")
            return await self.kill_process(int(pid))
        return ToolResult(
            success=False,
            error=f"Unknown action '{action}'. Use run, run_background, or kill_process.",
        )

    # ------------------------------------------------------------------
    # Public methods
    # ------------------------------------------------------------------

    async def run(
        self,
        command: str,
        timeout: int = DEFAULT_TIMEOUT,
        cwd: str | None = None,
    ) -> ToolResult:
        """Run *command* in a shell and wait for it to finish.

        Args:
            command: Shell command string.
            timeout: Maximum wall-clock seconds.
            cwd: Working directory (defaults to the current directory).

        Returns:
            ToolResult with ``stdout``, ``stderr``, and ``return_code``.
        """
        blocked = self._check_blocked(command)
        if blocked:
            return ToolResult(
                success=False,
                error=f"Command blocked by security policy: {blocked.pattern}",
            )

        effective_cwd = cwd or os.getcwd()
        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=effective_cwd,
            )
            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    proc.communicate(), timeout=timeout
                )
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                return ToolResult(
                    success=False,
                    error=f"Command timed out after {timeout}s",
                    output={"stdout": "", "stderr": "", "return_code": -1},
                )

            stdout = stdout_bytes.decode("utf-8", errors="replace")
            stderr = stderr_bytes.decode("utf-8", errors="replace")
            return_code = proc.returncode or 0
            return ToolResult(
                success=return_code == 0,
                output={"stdout": stdout, "stderr": stderr, "return_code": return_code},
                error=stderr if return_code != 0 else None,
            )
        except Exception as exc:
            return ToolResult(success=False, error=f"Shell execution failed: {exc}")

    async def run_background(self, command: str, cwd: str | None = None) -> ToolResult:
        """Launch *command* as a background process and return its PID.

        The process is tracked internally so it can later be killed via
        :pymethod:`kill_process`.

        Args:
            command: Shell command string.
            cwd: Working directory.

        Returns:
            ToolResult whose ``output`` is the integer PID.
        """
        blocked = self._check_blocked(command)
        if blocked:
            return ToolResult(
                success=False,
                error=f"Command blocked by security policy: {blocked.pattern}",
            )

        effective_cwd = cwd or os.getcwd()
        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=effective_cwd,
            )
            pid = proc.pid
            self._background_procs[pid] = proc
            logger.info("Started background process PID=%d: %s", pid, command)
            return ToolResult(success=True, output={"pid": pid, "command": command})
        except Exception as exc:
            return ToolResult(success=False, error=f"Background launch failed: {exc}")

    async def kill_process(self, pid: int) -> ToolResult:
        """Terminate the background process identified by *pid*.

        Sends SIGTERM first, then SIGKILL if the process does not exit
        within 5 seconds.

        Args:
            pid: Process ID (as returned by :pymethod:`run_background`).

        Returns:
            ToolResult indicating success or failure.
        """
        proc = self._background_procs.pop(pid, None)
        if proc is not None:
            return await self._kill_asyncio_proc(proc, pid)

        # Not one of our tracked processes -- try the OS directly.
        try:
            os.kill(pid, signal.SIGTERM)
            # Give it a moment to terminate.
            await asyncio.sleep(0.5)
            try:
                os.kill(pid, 0)  # check if still alive
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            return ToolResult(success=True, output=f"Killed process {pid}")
        except ProcessLookupError:
            return ToolResult(success=False, error=f"No process with PID {pid}")
        except PermissionError:
            return ToolResult(success=False, error=f"Permission denied to kill PID {pid}")
        except Exception as exc:
            return ToolResult(success=False, error=f"kill_process failed: {exc}")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    async def _kill_asyncio_proc(
        proc: asyncio.subprocess.Process, pid: int
    ) -> ToolResult:
        """Terminate an asyncio subprocess, escalating to SIGKILL if needed."""
        try:
            proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
            return ToolResult(success=True, output=f"Killed process {pid}")
        except Exception as exc:
            return ToolResult(success=False, error=f"Failed to kill PID {pid}: {exc}")

    @staticmethod
    def _check_blocked(command: str) -> re.Pattern[str] | None:
        """Return the first matching blocked pattern, or ``None``."""
        for pattern in BLOCKED_PATTERNS:
            if pattern.search(command):
                return pattern
        return None
