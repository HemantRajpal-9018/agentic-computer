"""File operations tool.

Provides safe, validated file system operations including reading, writing,
listing, searching, and metadata retrieval.  All paths are resolved and
validated before any I/O to prevent directory-traversal attacks.
"""

from __future__ import annotations

import logging
import mimetypes
import os
import stat
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agentic_computer.tools.registry import BaseTool, ToolResult, ToolSpec

logger = logging.getLogger(__name__)

# Maximum file size we are willing to read into memory (10 MiB).
_MAX_READ_BYTES: int = 10 * 1024 * 1024


class FileManager(BaseTool):
    """Perform common file-system operations with safety checks.

    Every public method validates its path argument, catches I/O errors,
    and returns a :class:`ToolResult` rather than raising.
    """

    def __init__(self, allowed_root: str | Path | None = None) -> None:
        """Initialise with an optional *allowed_root*.

        If *allowed_root* is given, all operations are restricted to that
        directory tree.  Pass ``None`` (the default) to allow unrestricted
        access.
        """
        self._allowed_root: Path | None = Path(allowed_root).resolve() if allowed_root else None

    # ------------------------------------------------------------------
    # BaseTool interface
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        return "file_manager"

    @property
    def description(self) -> str:
        return (
            "Read, write, list, search, and inspect files on the local file system "
            "with path validation and error handling."
        )

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name,
            description=self.description,
            parameters={
                "action": {
                    "type": "string",
                    "description": (
                        "One of: read_file, write_file, list_directory, "
                        "search_files, get_file_info."
                    ),
                },
                "path": {"type": "string", "description": "Target file or directory path."},
                "content": {
                    "type": "string",
                    "description": "Content to write (for write_file).",
                },
                "pattern": {
                    "type": "string",
                    "description": "Glob pattern for list_directory / search_files.",
                },
                "directory": {
                    "type": "string",
                    "description": "Root directory for search_files.",
                },
            },
            required_params=["action"],
        )

    async def execute(self, **kwargs: Any) -> ToolResult:
        """Dispatch to the matching file operation."""
        action = kwargs.get("action", "")
        dispatch = {
            "read_file": self._handle_read,
            "write_file": self._handle_write,
            "list_directory": self._handle_list,
            "search_files": self._handle_search,
            "get_file_info": self._handle_info,
        }
        handler = dispatch.get(action)
        if handler is None:
            return ToolResult(
                success=False,
                error=f"Unknown action '{action}'. Valid: {', '.join(dispatch)}",
            )
        return await handler(**kwargs)

    # ------------------------------------------------------------------
    # Public methods
    # ------------------------------------------------------------------

    async def read_file(self, path: str | Path) -> ToolResult:
        """Read the entire contents of a text file.

        Args:
            path: Path to the file.

        Returns:
            ToolResult whose ``output`` is the file contents as a string.
        """
        resolved = self._validate_path(path)
        if isinstance(resolved, ToolResult):
            return resolved  # validation failed
        if not resolved.is_file():
            return ToolResult(success=False, error=f"Not a file: {resolved}")
        if resolved.stat().st_size > _MAX_READ_BYTES:
            return ToolResult(
                success=False,
                error=f"File too large ({resolved.stat().st_size} bytes). Max: {_MAX_READ_BYTES}",
            )
        try:
            content = resolved.read_text(encoding="utf-8", errors="replace")
            return ToolResult(success=True, output=content)
        except Exception as exc:
            return ToolResult(success=False, error=f"Read failed: {exc}")

    async def write_file(self, path: str | Path, content: str) -> ToolResult:
        """Write *content* to a file, creating parent directories as needed.

        Args:
            path: Target file path.
            content: Text content to write.
        """
        resolved = self._validate_path(path)
        if isinstance(resolved, ToolResult):
            return resolved
        try:
            resolved.parent.mkdir(parents=True, exist_ok=True)
            resolved.write_text(content, encoding="utf-8")
            return ToolResult(success=True, output=f"Wrote {len(content)} chars to {resolved}")
        except Exception as exc:
            return ToolResult(success=False, error=f"Write failed: {exc}")

    async def list_directory(
        self, path: str | Path, pattern: str = "*"
    ) -> ToolResult:
        """List entries in a directory, optionally filtered by *pattern*.

        Args:
            path: Directory path.
            pattern: Glob pattern applied to direct children (default ``"*"``).

        Returns:
            ToolResult with a list of ``{"name", "type", "size"}`` dicts.
        """
        resolved = self._validate_path(path)
        if isinstance(resolved, ToolResult):
            return resolved
        if not resolved.is_dir():
            return ToolResult(success=False, error=f"Not a directory: {resolved}")
        try:
            entries: list[dict[str, Any]] = []
            for child in sorted(resolved.glob(pattern)):
                entry: dict[str, Any] = {
                    "name": child.name,
                    "type": "directory" if child.is_dir() else "file",
                }
                if child.is_file():
                    entry["size"] = child.stat().st_size
                entries.append(entry)
            return ToolResult(success=True, output=entries)
        except Exception as exc:
            return ToolResult(success=False, error=f"list_directory failed: {exc}")

    async def search_files(
        self, directory: str | Path, pattern: str
    ) -> ToolResult:
        """Recursively search *directory* for files matching *pattern*.

        Args:
            directory: Root directory to search.
            pattern: Glob pattern (e.g. ``"**/*.py"``).

        Returns:
            ToolResult containing a list of matching file path strings.
        """
        resolved = self._validate_path(directory)
        if isinstance(resolved, ToolResult):
            return resolved
        if not resolved.is_dir():
            return ToolResult(success=False, error=f"Not a directory: {resolved}")
        try:
            matches = [str(p) for p in sorted(resolved.glob(pattern)) if p.is_file()]
            return ToolResult(success=True, output=matches)
        except Exception as exc:
            return ToolResult(success=False, error=f"search_files failed: {exc}")

    async def get_file_info(self, path: str | Path) -> ToolResult:
        """Return metadata about a file (size, modification time, MIME type).

        Args:
            path: File path.

        Returns:
            ToolResult with a dict of metadata fields.
        """
        resolved = self._validate_path(path)
        if isinstance(resolved, ToolResult):
            return resolved
        if not resolved.exists():
            return ToolResult(success=False, error=f"Path does not exist: {resolved}")
        try:
            st = resolved.stat()
            mime, _ = mimetypes.guess_type(str(resolved))
            info: dict[str, Any] = {
                "path": str(resolved),
                "size": st.st_size,
                "modified": datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).isoformat(),
                "created": datetime.fromtimestamp(st.st_ctime, tz=timezone.utc).isoformat(),
                "type": "directory" if stat.S_ISDIR(st.st_mode) else "file",
                "mime_type": mime,
                "permissions": oct(st.st_mode)[-3:],
            }
            return ToolResult(success=True, output=info)
        except Exception as exc:
            return ToolResult(success=False, error=f"get_file_info failed: {exc}")

    # ------------------------------------------------------------------
    # Dispatch helpers (private)
    # ------------------------------------------------------------------

    async def _handle_read(self, **kwargs: Any) -> ToolResult:
        path = kwargs.get("path")
        if not path:
            return ToolResult(success=False, error="'path' is required for read_file")
        return await self.read_file(path)

    async def _handle_write(self, **kwargs: Any) -> ToolResult:
        path = kwargs.get("path")
        content = kwargs.get("content")
        if not path or content is None:
            return ToolResult(
                success=False, error="'path' and 'content' are required for write_file"
            )
        return await self.write_file(path, content)

    async def _handle_list(self, **kwargs: Any) -> ToolResult:
        path = kwargs.get("path")
        if not path:
            return ToolResult(success=False, error="'path' is required for list_directory")
        pattern = kwargs.get("pattern", "*")
        return await self.list_directory(path, pattern)

    async def _handle_search(self, **kwargs: Any) -> ToolResult:
        directory = kwargs.get("directory") or kwargs.get("path")
        pattern = kwargs.get("pattern")
        if not directory or not pattern:
            return ToolResult(
                success=False,
                error="'directory' (or 'path') and 'pattern' are required for search_files",
            )
        return await self.search_files(directory, pattern)

    async def _handle_info(self, **kwargs: Any) -> ToolResult:
        path = kwargs.get("path")
        if not path:
            return ToolResult(success=False, error="'path' is required for get_file_info")
        return await self.get_file_info(path)

    # ------------------------------------------------------------------
    # Path validation
    # ------------------------------------------------------------------

    def _validate_path(self, path: str | Path) -> Path | ToolResult:
        """Resolve *path* and enforce the allowed-root constraint.

        Returns the resolved :class:`Path` on success, or a failing
        :class:`ToolResult` if the path is invalid.
        """
        try:
            resolved = Path(os.path.expanduser(str(path))).resolve()
        except Exception as exc:
            return ToolResult(success=False, error=f"Invalid path '{path}': {exc}")

        if self._allowed_root and not str(resolved).startswith(str(self._allowed_root)):
            return ToolResult(
                success=False,
                error=f"Path '{resolved}' is outside the allowed root '{self._allowed_root}'",
            )
        return resolved
