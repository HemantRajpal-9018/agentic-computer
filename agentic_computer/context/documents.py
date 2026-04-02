"""Document management for the agentic-computer context subsystem.

Handles loading, saving, updating, and summarising project documents
such as ``PROJECT.md``, ``ROADMAP.md``, and ``README.md``.  Documents
are represented as typed dataclasses and can be fed into the context
window to give the agent grounding in project-level knowledge.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

logger = logging.getLogger(__name__)

# Well-known filenames that map to document types.
_PROJECT_FILES: dict[str, "DocumentType"] = {
    "PROJECT.md": None,   # patched below after enum definition
    "ROADMAP.md": None,
    "README.md": None,
    "NOTES.md": None,
    "CLAUDE.md": None,
    "AGENTS.md": None,
}


# ---------------------------------------------------------------------------
# Enum & data classes
# ---------------------------------------------------------------------------


class DocumentType(str, Enum):
    """Classification of a document by its purpose.

    PROJECT   - core project description / spec.
    ROADMAP   - development roadmap / milestones.
    NOTES     - free-form notes or scratchpad.
    REFERENCE - external or auxiliary reference material.
    """

    PROJECT = "project"
    ROADMAP = "roadmap"
    NOTES = "notes"
    REFERENCE = "reference"


# Patch the lookup table now that the enum exists.
_PROJECT_FILES["PROJECT.md"] = DocumentType.PROJECT
_PROJECT_FILES["ROADMAP.md"] = DocumentType.ROADMAP
_PROJECT_FILES["README.md"] = DocumentType.PROJECT
_PROJECT_FILES["NOTES.md"] = DocumentType.NOTES
_PROJECT_FILES["CLAUDE.md"] = DocumentType.REFERENCE
_PROJECT_FILES["AGENTS.md"] = DocumentType.REFERENCE


@dataclass
class Document:
    """A managed document that can be loaded into the context window.

    Attributes:
        doc_type: Semantic classification of the document.
        title: Human-readable title (often the file name stem).
        content: Full text content.
        path: Filesystem path the document was loaded from (if any).
        last_updated: Timestamp of the most recent modification.
    """

    doc_type: DocumentType
    title: str
    content: str
    path: Path | None = None
    last_updated: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


# ---------------------------------------------------------------------------
# DocumentManager
# ---------------------------------------------------------------------------


class DocumentManager:
    """Load, save, update, and summarise project documents.

    All filesystem operations use synchronous :class:`pathlib.Path` I/O,
    which is appropriate for the typically small Markdown files involved.
    For very large documents, callers can use :pymeth:`summarize_document`
    to produce a truncated view suitable for the context window.
    """

    # -- I/O ----------------------------------------------------------------

    @staticmethod
    def load(path: Path) -> Document:
        """Read a document from disk and return a :class:`Document`.

        The document type is inferred from the filename if it matches a
        well-known pattern; otherwise it defaults to ``REFERENCE``.

        Args:
            path: Path to the file to load.

        Returns:
            A :class:`Document` populated from the file.

        Raises:
            FileNotFoundError: If *path* does not exist.
            PermissionError: If the file cannot be read.
        """
        resolved = path.resolve()
        if not resolved.is_file():
            raise FileNotFoundError(f"Document not found: {resolved}")

        content = resolved.read_text(encoding="utf-8")
        doc_type = _PROJECT_FILES.get(resolved.name, DocumentType.REFERENCE)

        # Use filesystem mtime for last_updated.
        mtime = datetime.fromtimestamp(resolved.stat().st_mtime, tz=timezone.utc)

        title = resolved.stem
        logger.debug("Loaded document '%s' (%s) from %s.", title, doc_type.value, resolved)
        return Document(
            doc_type=doc_type,
            title=title,
            content=content,
            path=resolved,
            last_updated=mtime,
        )

    @staticmethod
    def save(document: Document, path: Path) -> None:
        """Write a document's content to disk.

        Parent directories are created automatically if they do not exist.

        Args:
            document: The :class:`Document` to persist.
            path: Destination file path.
        """
        resolved = path.resolve()
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(document.content, encoding="utf-8")
        document.path = resolved
        document.last_updated = datetime.now(timezone.utc)
        logger.debug("Saved document '%s' to %s.", document.title, resolved)

    # -- Discovery ----------------------------------------------------------

    @staticmethod
    def get_project_context(directory: Path) -> list[Document]:
        """Find and load well-known project documents from *directory*.

        Scans for ``PROJECT.md``, ``ROADMAP.md``, ``README.md``,
        ``NOTES.md``, ``CLAUDE.md``, and ``AGENTS.md``.

        Args:
            directory: Root directory to search.

        Returns:
            List of :class:`Document` objects for each file found.
        """
        resolved = directory.resolve()
        if not resolved.is_dir():
            logger.warning("Directory does not exist: %s", resolved)
            return []

        documents: list[Document] = []
        for filename in _PROJECT_FILES:
            candidate = resolved / filename
            if candidate.is_file():
                try:
                    documents.append(DocumentManager.load(candidate))
                except (OSError, UnicodeDecodeError) as exc:
                    logger.warning(
                        "Could not load %s: %s", candidate, exc
                    )
        return documents

    # -- Mutation -----------------------------------------------------------

    @staticmethod
    def update_document(doc: Document, new_content: str) -> Document:
        """Replace a document's content and update its timestamp.

        If the document has an associated path on disk the file is
        **not** automatically rewritten; call :pymeth:`save` explicitly
        if persistence is desired.

        Args:
            doc: The document to update.
            new_content: The replacement content string.

        Returns:
            The same :class:`Document` instance, mutated in place and
            also returned for convenience.
        """
        doc.content = new_content
        doc.last_updated = datetime.now(timezone.utc)
        logger.debug("Updated document '%s' in memory.", doc.title)
        return doc

    # -- Summarisation ------------------------------------------------------

    @staticmethod
    def summarize_document(doc: Document, max_tokens: int = 500) -> str:
        """Produce a token-budget-aware summary of a document.

        Uses a simple extractive approach: takes the title line plus the
        first *N* characters (approximated as ``max_tokens * 4`` characters)
        of the document body.  For richer summaries, feed the document
        content through :class:`ContextSummarizer`.

        Args:
            doc: The document to summarise.
            max_tokens: Approximate token budget for the summary.

        Returns:
            A truncated / summarised string representation.
        """
        char_budget = max_tokens * 4  # rough 4 chars/token heuristic
        header = f"# {doc.title} ({doc.doc_type.value})\n\n"
        remaining = max(0, char_budget - len(header))

        if len(doc.content) <= remaining:
            return header + doc.content

        # Attempt to truncate at a paragraph or sentence boundary.
        truncated = doc.content[:remaining]
        # Prefer breaking at double newline (paragraph boundary).
        para_break = truncated.rfind("\n\n")
        if para_break > remaining // 2:
            truncated = truncated[:para_break]
        else:
            # Fall back to sentence boundary.
            for sep in (". ", ".\n", "! ", "? "):
                sent_break = truncated.rfind(sep)
                if sent_break > remaining // 3:
                    truncated = truncated[: sent_break + 1]
                    break

        return header + truncated.rstrip() + "\n\n[...truncated]"
