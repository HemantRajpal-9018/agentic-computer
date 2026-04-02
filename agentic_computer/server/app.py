"""FastAPI application for the agentic-computer server.

Provides the main ASGI application instance with CORS, lifespan management,
route inclusion, WebSocket support, health checks, and structured exception
handling.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from agentic_computer import __version__
from agentic_computer.config import get_settings
from agentic_computer.memory.store import MemoryStore
from agentic_computer.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Application state — populated during lifespan startup
# ---------------------------------------------------------------------------

class AppState:
    """Container for shared application-level resources.

    Attributes:
        memory_store: The initialised async memory store.
        tool_registry: The tool registry with all discovered tools.
        settings: The loaded application settings.
    """

    memory_store: MemoryStore
    tool_registry: ToolRegistry

    def __init__(self) -> None:
        self.memory_store = MemoryStore()
        self.tool_registry = ToolRegistry()


app_state = AppState()


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncGenerator[None, None]:
    """Manage startup and shutdown for the FastAPI application.

    On startup:
        - Load settings from environment.
        - Initialise the SQLite-backed memory store.
        - Create and populate the tool registry (auto-discover tools).

    On shutdown:
        - Close the memory store database connection.
    """
    settings = get_settings()

    # -- Memory store -------------------------------------------------------
    store = MemoryStore(db_path=settings.memory.sqlite_path)
    await store.init_db()
    app_state.memory_store = store
    logger.info("Memory store initialised at %s", settings.memory.sqlite_path)

    # -- Tool registry ------------------------------------------------------
    registry = ToolRegistry()
    try:
        from pathlib import Path

        tools_package = Path(__file__).resolve().parent.parent / "tools"
        if tools_package.is_dir():
            discovered = registry.discover(tools_package)
            logger.info("Discovered %d tool(s): %s", len(discovered), discovered)
    except Exception:
        logger.warning("Tool auto-discovery failed — continuing without tools", exc_info=True)
    app_state.tool_registry = registry
    logger.info("Tool registry ready (%d tool(s))", len(registry))

    yield

    # -- Shutdown -----------------------------------------------------------
    await app_state.memory_store.close()
    logger.info("Memory store closed.")


# ---------------------------------------------------------------------------
# FastAPI instance
# ---------------------------------------------------------------------------

app = FastAPI(
    title="agentic-computer",
    version=__version__,
    description="Open-source autonomous computer agent API",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# CORS middleware
# ---------------------------------------------------------------------------

_settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=_settings.server.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Exception handlers
# ---------------------------------------------------------------------------

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Return a consistent JSON envelope for HTTP exceptions."""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": True,
            "status_code": exc.status_code,
            "detail": exc.detail,
        },
    )


@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError) -> JSONResponse:
    """Map ``ValueError`` to a 422 Unprocessable Entity response."""
    logger.warning("ValueError in %s %s: %s", request.method, request.url.path, exc)
    return JSONResponse(
        status_code=422,
        content={
            "error": True,
            "status_code": 422,
            "detail": str(exc),
        },
    )


@app.exception_handler(RuntimeError)
async def runtime_error_handler(request: Request, exc: RuntimeError) -> JSONResponse:
    """Map ``RuntimeError`` to a 500 Internal Server Error response."""
    logger.error("RuntimeError in %s %s: %s", request.method, request.url.path, exc)
    return JSONResponse(
        status_code=500,
        content={
            "error": True,
            "status_code": 500,
            "detail": str(exc),
        },
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all for unhandled exceptions — return 500 with a safe message."""
    logger.exception("Unhandled exception in %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={
            "error": True,
            "status_code": 500,
            "detail": "An internal server error occurred.",
        },
    )


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/health", tags=["system"])
async def health_check() -> dict[str, Any]:
    """Return service health information.

    Returns basic liveness data including version, memory-store availability,
    and the number of registered tools.
    """
    memory_ok = app_state.memory_store._db is not None
    return {
        "status": "healthy" if memory_ok else "degraded",
        "version": __version__,
        "memory_store": "connected" if memory_ok else "disconnected",
        "tools_registered": len(app_state.tool_registry),
    }


# ---------------------------------------------------------------------------
# Include routers
# ---------------------------------------------------------------------------

from agentic_computer.server.routes import router as api_router  # noqa: E402
from agentic_computer.server.websocket import router as ws_router  # noqa: E402

app.include_router(api_router)
app.include_router(ws_router)
