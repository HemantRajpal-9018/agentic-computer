"""Context management subsystem for agentic-computer.

Provides tools for managing the agent's context window, loading and
persisting project documents, and summarising text to fit within
token budgets.

Public API:
    ContextManager   - Token-aware context window manager.
    DocumentManager  - Load / save / discover project documents.
    ContextSummarizer - Extractive (and optionally LLM) text summarisation.
"""

from agentic_computer.context.documents import DocumentManager
from agentic_computer.context.manager import ContextManager
from agentic_computer.context.summarizer import ContextSummarizer

__all__ = [
    "ContextManager",
    "ContextSummarizer",
    "DocumentManager",
]
