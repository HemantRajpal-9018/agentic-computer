# System Architecture

## Overview

**agentic-computer** is an open-source autonomous computer agent built on a multi-agent orchestration framework. It combines LLM-powered planning, browser automation, sandboxed code execution, and persistent memory to carry out complex computer tasks end-to-end without human intervention.

The system follows a modular, layered architecture. A central **Orchestrator** receives high-level tasks, delegates planning to a **Planner** agent, dispatches subtasks to specialized **Executor** agents, and verifies results through a **Verifier** agent. Every agent shares access to a **ToolRegistry** (browser, code sandbox, web search, etc.), a **MemoryStore** (SQLite + vector embeddings), and a **ContextManager** that prevents context-window overflow.

A **FastAPI server** exposes REST and WebSocket endpoints so that external clients -- including the bundled Next.js web UI -- can submit tasks, stream progress, and query memory.

---

## Component Diagram

```
                          +---------------------+
                          |     Web UI (Next.js) |
                          |   localhost:3000     |
                          +----------+----------+
                                     |
                              HTTP / WebSocket
                                     |
                          +----------v----------+
                          |   FastAPI Server     |
                          |   localhost:8000     |
                          |   /api/v1/*   /ws    |
                          +----------+----------+
                                     |
                     +---------------+----------------+
                     |                                |
              +------v------+                  +------v------+
              | Orchestrator |                  | Workflow    |
              | (core)       |                  | Engine      |
              +------+------+                  +------+------+
                     |                                |
        +------------+------------+                   |
        |            |            |                    |
   +----v----+ +----v----+ +----v----+          YAML workflow
   | Planner | | Executor| | Verifier|          definitions
   +---------+ +---------+ +---------+
        |            |            |
        +------+-----+-----+-----+
               |           |
        +------v------+   +------v------+
        | Tool        |   | Skill       |
        | Registry    |   | System      |
        +------+------+   +------+------+
               |                  |
     +---------+---------+       |
     |         |         |       |
  +--v--+ +---v---+ +---v---+   |
  |Brows| |Sandbox| |Search |   |
  |er   | |       | |       |   |
  +-----+ +-------+ +-------+   |
                                 |
        +------+-----------+-----+
        |                  |
   +----v----+      +------v------+
   | Context |      | Memory      |
   | Manager |      | Store       |
   +---------+      | (SQLite +   |
                    |  Embeddings)|
                    +------+------+
                           |
                    +------v------+
                    | ChromaDB    |
                    | (optional)  |
                    +-------------+
```

---

## Core Modules

### Orchestrator (`core/orchestrator.py`)

The central coordinator. It receives a natural-language task, invokes the Planner to decompose it into subtasks, dispatches each subtask to the appropriate agent based on `AgentRole`, and collects results. It manages the overall task lifecycle (idle -> thinking -> executing -> done/error) and handles retries and fallback when subtasks fail.

**Key responsibilities:**
- Task intake and lifecycle management
- Agent selection and dispatch based on role assignment
- Result aggregation and error recovery
- Coordination between Planner, Executor, and Verifier agents

### Planner (`core/planner.py`)

An LLM-powered agent that decomposes high-level tasks into ordered subtasks. Each subtask is assigned an `AgentRole` and may declare dependencies on other subtasks. The Planner builds a dependency graph and produces a topologically sorted execution order using Kahn's algorithm, so the downstream Executor processes work in the correct sequence.

**Key types:**
- `SubTask` -- a single unit of work with an ID, description, role, dependencies, and status
- `TaskPlan` -- the complete decomposition containing ordered subtasks and a dependency adjacency list
- `SubTaskStatus` -- lifecycle enum: pending, in_progress, completed, failed, skipped

### Agent Base (`core/agent.py`)

Defines the abstract `BaseAgent` class that all agents inherit from. Provides:
- Identity (`id`, `name`, `role`) and state machine (`AgentState`)
- Conversation memory (list of `Message` objects)
- Provider-agnostic `llm_call()` method that dispatches to OpenAI, Anthropic, or Ollama
- Abstract `think()` and `execute()` methods that subclasses implement

**Agent roles:** Planner, Executor, Verifier, Researcher, Coder

### Memory (`memory/`)

A dual-layer memory subsystem inspired by cognitive memory models:

| Memory Type | Analogy | Purpose |
|-------------|---------|---------|
| `EPISODIC` | Events/experiences | Records of what happened during task execution |
| `SEMANTIC` | Facts/knowledge | General knowledge and learned information |
| `PROCEDURAL` | How-to/skills | Procedures and methods for accomplishing tasks |
| `WORKING` | Scratch-pad | Short-lived items for the current context |

**MemoryStore** (`memory/store.py`) provides async SQLite-backed persistence with:
- CRUD operations for `MemoryEntry` objects
- Vector similarity search using cosine similarity (numpy) over dense embeddings
- Text-based fallback search when embeddings are unavailable
- Access tracking (access count, last accessed timestamp)
- Importance scoring for prioritized retrieval

### Tools (`tools/`)

The tool system is built around three abstractions:

- **`BaseTool`** -- abstract class requiring `name`, `description`, `spec()`, and `execute()` implementations
- **`ToolSpec`** -- declarative parameter schema (JSON-schema-style) with required parameter validation
- **`ToolRegistry`** -- central registry supporting registration, lookup, validated execution, and auto-discovery of tool classes from Python packages

**Built-in tools:**
- **Browser** (`tools/browser.py`) -- Playwright-based Chromium automation: navigate, click, type, screenshot, extract text, execute JavaScript
- **Code Sandbox** -- Isolated code execution with configurable timeout and memory limits
- **Web Search** -- Serper or Tavily-backed internet search

### Skills (`skills/`)

Skills are higher-level, task-oriented capabilities that build on top of tools. Each skill:
- Declares metadata (name, description, version, author, tags) via `SkillMetadata`
- Reports confidence for a given task via `can_handle(task) -> float`
- Executes against a `SkillContext` (task + memory + tools + config) and returns a `SkillResult`
- Declares required tools so the framework can fail fast if dependencies are missing

The skill system supports dynamic loading, keyword-based confidence scoring, and a community directory for third-party skills.

### Context Manager (`context/manager.py`)

Manages the bounded context window to prevent token overflow during long agent sessions:

- **Token budgeting** -- tracks estimated token counts per entry against a configurable ceiling (default: 128,000 tokens)
- **Priority-based eviction** -- when the window is full, the lowest-priority non-pinned entry is evicted first
- **Automatic compression** -- older, lower-priority entries in the first half of the window are summarized into a single entry (uses an external summarizer when available, otherwise truncation)
- **Anti-context-rot** -- detects when a large proportion of entries are stale (>60% older than 10 minutes relative to the newest) and triggers automatic refresh/compression
- **Pinned entries** -- system prompts and critical context can be marked as `pinned=True` to prevent eviction

### Workflows (`workflows/`)

A YAML-based workflow engine that lets users define multi-step automation pipelines declaratively. Workflows are loaded from `.yaml` files, parsed into step sequences, and executed by the `WorkflowEngine`. Each step can invoke tools, agents, or other workflows, with support for JSON input data.

### Server (`server/`)

A FastAPI application providing:
- **REST API** (`/api/v1/*`) -- task submission, task status, workflow management, tool listing and execution, memory search and storage
- **WebSocket** (`/ws`) -- real-time streaming of agent progress, state changes, and results
- **Health check** (`/health`) -- for container orchestration readiness probes
- **CORS** -- configurable allowed origins (default: `http://localhost:3000`)

---

## Data Flow

### Task Execution Flow

```
1. Client submits task via POST /api/v1/tasks or CLI
                    |
2. Orchestrator receives task, sets state to THINKING
                    |
3. Planner decomposes task into SubTasks via LLM call
   - Parses JSON response into SubTask objects
   - Builds dependency graph
   - Topologically sorts execution order
                    |
4. Orchestrator iterates through ready subtasks:
   a. Select agent by SubTask.agent_role
   b. Agent calls think() then execute()
   c. Agent uses ToolRegistry for browser/sandbox/search
   d. Agent reads/writes MemoryStore for context
   e. ContextManager enforces token budget
   f. Mark subtask as completed or failed
                    |
5. Verifier agent validates results (optional)
                    |
6. Orchestrator aggregates results, sets state to DONE
                    |
7. Result returned to client (REST response or WebSocket push)
```

### Memory Flow

```
Task Execution --> MemoryStore.add(content, type, embedding)
                         |
                    SQLite (persistence)
                         |
Retrieval  <-- MemoryStore.search(query)
                    |                |
          Text LIKE fallback    Cosine similarity
          (no embeddings)       (with embeddings)
                    |                |
                    v                v
              Sorted by         Sorted by
              importance        similarity
```

---

## Technology Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| **Language** | Python 3.10+ | Core runtime |
| **LLM Providers** | OpenAI, Anthropic, Ollama | Language model inference |
| **Web Framework** | FastAPI + Uvicorn | REST API and WebSocket server |
| **Browser Automation** | Playwright (Chromium) | Web interaction and scraping |
| **Storage** | SQLite (aiosqlite) | Memory persistence |
| **Vector DB** | ChromaDB (optional) | Embedding storage and similarity search |
| **Embeddings** | NumPy | In-process cosine similarity computation |
| **Serialization** | Pydantic 2.x | Request/response validation |
| **CLI** | Click + Rich | Interactive terminal UI |
| **Web UI** | Next.js 14 + React 18 | Browser-based dashboard |
| **Styling** | Tailwind CSS | Web UI styling |
| **Containerization** | Docker + Docker Compose | Deployment and orchestration |
| **Testing** | pytest + pytest-asyncio | Unit and integration tests |
| **Linting** | Ruff | Code formatting and linting |
| **Type Checking** | mypy | Static type analysis |

---

## Deployment Architecture

### Development (local)

```
make dev          # Install Python deps + Playwright
make server       # Start FastAPI on :8000
make web          # Start Next.js on :3000
```

The development setup runs three processes locally:
1. FastAPI server with hot-reload on port 8000
2. Next.js dev server on port 3000
3. SQLite database stored in `./data/agentic.db`

### Production (Docker Compose)

```
docker compose up -d --build
```

Docker Compose brings up three services on a shared bridge network (`agentic-net`):

| Service | Container | Port | Description |
|---------|-----------|------|-------------|
| `agent-server` | `agentic-server` | 8000 | FastAPI backend with health check |
| `web` | `agentic-web` | 3000 | Next.js frontend (depends on agent-server) |
| `chromadb` | `agentic-chromadb` | 8100 | ChromaDB vector database |

**Volumes:**
- `./data` mounted at `/app/data` for SQLite persistence
- `./skills` mounted at `/app/skills` for community skill discovery
- `chroma-data` named volume for ChromaDB persistence

**Health checks:** The `agent-server` container exposes a `/health` endpoint. The `web` service waits until `agent-server` is healthy before starting.

### Environment Configuration

All configuration is driven by environment variables (see `.env.example`). Key groups:

- **LLM** -- provider, model, temperature, max tokens, API keys
- **Browser** -- headless mode, timeout
- **Memory** -- SQLite path, ChromaDB directory, max entries
- **Search** -- provider (Serper/Tavily), API key
- **Sandbox** -- enabled flag, timeout, memory limit
- **Server** -- host, port, CORS origins
- **Logging** -- level, format (JSON or text)
