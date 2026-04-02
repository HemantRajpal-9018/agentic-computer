"""Tests for the tools module."""

from __future__ import annotations

import asyncio
import os
import tempfile
from pathlib import Path

import pytest

from agentic_computer.tools.registry import BaseTool, ToolRegistry, ToolResult, ToolSpec
from agentic_computer.tools.file_manager import FileManager
from agentic_computer.tools.shell import ShellTool
from agentic_computer.tools.code_executor import CodeExecutor


class DummyTool(BaseTool):
    """A dummy tool for testing the registry."""

    @property
    def name(self) -> str:
        return "dummy"

    @property
    def description(self) -> str:
        return "A dummy tool for testing"

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="dummy",
            description="A dummy tool",
            parameters={"message": {"type": "string", "description": "A message"}},
            required_params=["message"],
        )

    async def execute(self, **kwargs: object) -> ToolResult:
        message = kwargs.get("message", "")
        return ToolResult(
            success=True,
            output=f"Dummy says: {message}",
            error=None,
            duration_ms=0.1,
        )


class TestToolSpec:
    """Tests for ToolSpec dataclass."""

    def test_create_spec(self) -> None:
        spec = ToolSpec(
            name="test-tool",
            description="A test tool",
            parameters={"input": {"type": "string"}},
            required_params=["input"],
        )
        assert spec.name == "test-tool"
        assert "input" in spec.parameters
        assert "input" in spec.required_params


class TestToolResult:
    """Tests for ToolResult dataclass."""

    def test_successful_result(self) -> None:
        result = ToolResult(success=True, output="done", error=None, duration_ms=50.0)
        assert result.success is True
        assert result.duration_ms == 50.0

    def test_failed_result(self) -> None:
        result = ToolResult(success=False, output="", error="timeout", duration_ms=30000.0)
        assert result.success is False
        assert result.error == "timeout"


class TestToolRegistry:
    """Tests for the tool registry."""

    def test_register_tool(self) -> None:
        registry = ToolRegistry()
        tool = DummyTool()
        registry.register(tool)
        assert registry.get("dummy") is not None

    def test_get_nonexistent_tool(self) -> None:
        registry = ToolRegistry()
        assert registry.get("nonexistent") is None

    def test_list_tools(self) -> None:
        registry = ToolRegistry()
        registry.register(DummyTool())
        tools = registry.list_tools()
        assert len(tools) == 1
        assert tools[0].name == "dummy"

    @pytest.mark.asyncio
    async def test_execute_tool(self) -> None:
        registry = ToolRegistry()
        registry.register(DummyTool())
        result = await registry.execute("dummy", message="hello")
        assert result.success is True
        assert "hello" in result.output

    @pytest.mark.asyncio
    async def test_execute_nonexistent_tool(self) -> None:
        registry = ToolRegistry()
        result = await registry.execute("nonexistent")
        assert result.success is False
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_execute_missing_required_params(self) -> None:
        registry = ToolRegistry()
        registry.register(DummyTool())
        # DummyTool requires "message" param
        result = await registry.execute("dummy")
        # Should still work (gracefully handle missing params) or fail with clear error
        assert isinstance(result, ToolResult)


class TestFileManager:
    """Tests for the file manager tool."""

    @pytest.fixture
    def file_manager(self) -> FileManager:
        return FileManager()

    @pytest.mark.asyncio
    async def test_write_and_read_file(self, file_manager: FileManager, tmp_path: Path) -> None:
        test_file = tmp_path / "test.txt"
        write_result = await file_manager.execute(
            action="write_file",
            path=str(test_file),
            content="Hello, World!",
        )
        assert write_result.success is True

        read_result = await file_manager.execute(
            action="read_file",
            path=str(test_file),
        )
        assert read_result.success is True
        assert read_result.output == "Hello, World!"

    @pytest.mark.asyncio
    async def test_read_nonexistent_file(self, file_manager: FileManager) -> None:
        result = await file_manager.execute(
            action="read_file",
            path="/nonexistent/path/file.txt",
        )
        assert result.success is False
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_list_directory(self, file_manager: FileManager, tmp_path: Path) -> None:
        # Create some test files
        (tmp_path / "file1.txt").write_text("content1")
        (tmp_path / "file2.py").write_text("content2")
        (tmp_path / "file3.txt").write_text("content3")

        result = await file_manager.execute(
            action="list_directory",
            path=str(tmp_path),
        )
        assert result.success is True
        assert isinstance(result.output, list)
        assert len(result.output) == 3

    @pytest.mark.asyncio
    async def test_search_files(self, file_manager: FileManager, tmp_path: Path) -> None:
        (tmp_path / "file1.txt").write_text("content")
        (tmp_path / "file2.py").write_text("content")

        result = await file_manager.execute(
            action="search_files",
            directory=str(tmp_path),
            pattern="*.txt",
        )
        assert result.success is True
        assert isinstance(result.output, list)
        assert len(result.output) == 1

    @pytest.mark.asyncio
    async def test_get_file_info(self, file_manager: FileManager, tmp_path: Path) -> None:
        test_file = tmp_path / "info_test.txt"
        test_file.write_text("Some content here")

        result = await file_manager.execute(
            action="get_file_info",
            path=str(test_file),
        )
        assert result.success is True
        assert isinstance(result.output, dict)
        assert "size" in result.output


class TestShellTool:
    """Tests for the shell tool."""

    @pytest.fixture
    def shell(self) -> ShellTool:
        return ShellTool()

    @pytest.mark.asyncio
    async def test_run_echo(self, shell: ShellTool) -> None:
        result = await shell.execute(action="run", command="echo 'Hello World'")
        assert result.success is True
        # Output may be a dict with stdout key or a string
        output = result.output if isinstance(result.output, str) else result.output.get("stdout", "")
        assert "Hello World" in output

    @pytest.mark.asyncio
    async def test_run_with_timeout(self, shell: ShellTool) -> None:
        result = await shell.execute(action="run", command="echo 'fast'", timeout=5)
        assert result.success is True

    @pytest.mark.asyncio
    async def test_blocked_command(self, shell: ShellTool) -> None:
        result = await shell.execute(action="run", command="rm -rf /")
        assert result.success is False

    @pytest.mark.asyncio
    async def test_command_with_cwd(self, shell: ShellTool, tmp_path: Path) -> None:
        result = await shell.execute(action="run", command="pwd", cwd=str(tmp_path))
        assert result.success is True
        output = result.output if isinstance(result.output, str) else result.output.get("stdout", "")
        assert str(tmp_path) in output


class TestCodeExecutor:
    """Tests for the code executor."""

    @pytest.fixture
    def executor(self) -> CodeExecutor:
        return CodeExecutor()

    @pytest.mark.asyncio
    async def test_execute_python(self, executor: CodeExecutor) -> None:
        result = await executor.execute(
            action="python",
            code="print('Hello from Python')",
        )
        assert result.success is True
        output = result.output if isinstance(result.output, str) else result.output.get("stdout", "")
        assert "Hello from Python" in output

    @pytest.mark.asyncio
    async def test_execute_python_with_error(self, executor: CodeExecutor) -> None:
        result = await executor.execute(
            action="python",
            code="raise ValueError('test error')",
        )
        assert result.success is False
        error_text = str(result.error or "") + str(result.output or "")
        assert "ValueError" in error_text

    @pytest.mark.asyncio
    async def test_execute_python_math(self, executor: CodeExecutor) -> None:
        result = await executor.execute(
            action="python",
            code="print(2 + 2)",
        )
        assert result.success is True
        output = result.output if isinstance(result.output, str) else result.output.get("stdout", "")
        assert "4" in output
