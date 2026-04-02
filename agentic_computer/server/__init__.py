"""Server package for agentic-computer.

Exports the FastAPI ``app`` instance so it can be referenced as
``agentic_computer.server.app`` (the module attribute) or imported
directly::

    from agentic_computer.server import app
"""

from agentic_computer.server.app import app

__all__ = ["app"]
