```
    ___                    __  _         ______                          __
   / _ | ___ ____ ___  / /_(_)___   / ____/___  __ _  ___  __ __/ /____ ____
  / __ |/ _ `/ -_) _ \/ __/ / __/  / /   / _ \/  ' \/ _ \/ // / __/ -_) __/
 /_/ |_|\_,_/\__/_//_/\__/_/\__/  /_/    \___/_/_/_/ .__/\_,_/\__/\__/_/
                                                    /_/
```

<p align="center">
  <strong>Open-source autonomous computer agent with multi-agent orchestration, browser automation, code execution, and persistent memory.</strong>
</p>

<p align="center">
  <a href="https://github.com/HemantRajpal-9018/agentic-computer/blob/main/LICENSE">
    <img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="License: MIT">
  </a>
  <a href="https://www.python.org/downloads/">
    <img src="https://img.shields.io/badge/python-3.10%2B-blue.svg" alt="Python 3.10+">
  </a>
  <a href="https://github.com/HemantRajpal-9018/agentic-computer/stargazers">
    <img src="https://img.shields.io/github/stars/HemantRajpal-9018/agentic-computer?style=social" alt="Stars">
  </a>
  <a href="https://github.com/HemantRajpal-9018/agentic-computer/actions">
    <img src="https://img.shields.io/badge/CI-passing-brightgreen.svg" alt="CI Status">
  </a>
</p>

---

## Why agentic-computer?

Most AI agent frameworks give you building blocks — but leave you to wire everything together. **agentic-computer** gives you a fully integrated autonomous agent that can:

- **Browse the web** — navigate pages, fill forms, extract data via Playwright
- **Execute code** — run Python and shell commands in a sandbox
- **Manage files** — read, write, search your filesystem
- **Remember everything** — persistent memory with SQLite + vector similarity
- **Plan complex tasks** — decompose goals into subtasks with dependency graphs
- **Orchestrate multiple agents** — specialized agents for research, coding, design
- **Run workflows** — define reusable automation as YAML DAGs
- **Expose an API** — FastAPI server with REST + WebSocket for real-time updates

All with a clean CLI, a web dashboard, and zero vendor lock-in (works with OpenAI, Anthropic, Ollama, and more).

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                         CLI / Web UI                              │
│  ┌──────────┐  ┌──────────────┐  ┌───────────┐  ┌────────────┐  │
│  │   Chat    │  │  Workflows   │  │  Memory   │  │ Dashboard  │  │
│  └────┬─────┘  └──────┬───────┘  └─────┬─────┘  └─────┬──────┘  │
└───────┼────────────────┼────────────────┼──────────────┼─────────┘
        │                │                │              │
┌───────▼────────────────▼────────────────▼──────────────▼─────────┐
│                      FastAPI Server                               │
│                   REST + WebSocket API                             │
└───────────────────────────┬──────────────────────────────────────┘
                            │
┌───────────────────────────▼──────────────────────────────────────┐
│                       Orchestrator                                │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────────┐ │
│  │ Planner  │  │ Executor │  │ Verifier │  │ Context Manager  │ │
│  └──────────┘  └──────────┘  └──────────┘  └──────────────────┘ │
└──────────┬──────────┬──────────┬──────────┬──────────────────────┘
           │          │          │          │
┌──────────▼──────────▼──────────▼──────────▼──────────────────────┐
│                        Tool Registry                              │
│  ┌────────┐ ┌──────────┐ ┌───────┐ ┌───────┐ ┌──────────────┐   │
│  │Browser │ │Code Exec │ │ Shell │ │ Files │ │  Web Search  │   │
│  └────────┘ └──────────┘ └───────┘ └───────┘ └──────────────┘   │
└──────────────────────────────────────────────────────────────────┘
           │                                        │
┌──────────▼────────────────────────────────────────▼──────────────┐
│                      Persistent Layer                             │
│  ┌─────────────────────┐  ┌──────────────────────────────────┐   │
│  │  SQLite (Structured) │  │  ChromaDB (Vector Embeddings)   │   │
│  └─────────────────────┘  └──────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────┘
```

---

## Quick Start

### Docker (recommended)

```bash
# Clone the repo
git clone https://github.com/HemantRajpal-9018/agentic-computer.git
cd agentic-computer

# Configure environment
cp .env.example .env
# Edit .env with your API keys

# Start everything
docker compose up -d

# Web UI at http://localhost:3000
# API at http://localhost:8000
```

### Manual Installation

```bash
# Clone and install
git clone https://github.com/HemantRajpal-9018/agentic-computer.git
cd agentic-computer
pip install -e ".[dev]"

# Install browser automation
playwright install chromium

# Configure
cp .env.example .env
# Edit .env with your API keys

# Run the agent
agentic-computer run

# Or start the server
agentic-computer serve
```

### Using the CLI

```bash
# Interactive mode
agentic-computer run

# Execute a single task
agentic-computer run --task "Research the latest AI papers on arxiv about tool use"

# Run a workflow
agentic-computer workflow workflows/templates/research.yaml --input '{"topic": "LLM agents"}'

# Start the API server
agentic-computer serve --port 8000
```

---

## Features

### Multi-Agent Orchestration

The orchestrator decomposes complex tasks into subtasks and routes them to specialized agents:

```python
from agentic_computer.core.orchestrator import Orchestrator

orchestrator = Orchestrator()
result = await orchestrator.run("Build a web scraper for news articles")
# Planner → decomposes into subtasks
# Researcher → finds target sites and patterns
# Coder → implements the scraper
# Verifier → validates the output
```

### Persistent Memory

SQLite for structured data + vector similarity for semantic search:

```python
from agentic_computer.memory.store import MemoryStore
from agentic_computer.memory.schema import MemoryType

store = MemoryStore()
await store.init_db()

# Store a memory
await store.add(
    content="User prefers TypeScript over JavaScript",
    memory_type=MemoryType.SEMANTIC,
    metadata={"source": "conversation"}
)

# Retrieve relevant memories
results = await store.search(MemoryQuery(
    query="programming language preferences",
    limit=5
))
```

### Tool System

Extensible tool registry with built-in browser, code executor, file manager, and more:

```python
from agentic_computer.tools.registry import ToolRegistry

registry = ToolRegistry()
registry.load_defaults()

# Execute a tool
result = await registry.execute("browser", action="navigate", url="https://example.com")
result = await registry.execute("shell", command="ls -la")
result = await registry.execute("code_executor", action="python", code="print('hello')")
```

### YAML Workflows

Define reusable automation as DAG workflows:

```yaml
# research-workflow.yaml
name: research
description: Multi-step research workflow
steps:
  - id: search
    tool: web_search
    params:
      query: "{{topic}}"
      num_results: 10

  - id: analyze
    tool: code_executor
    depends_on: [search]
    params:
      action: python
      code: |
        results = {{search.output}}
        summary = analyze(results)
        print(summary)

  - id: report
    tool: file_manager
    depends_on: [analyze]
    params:
      action: write_file
      path: "./report.md"
      content: "{{analyze.output}}"
```

### Skills System

Discoverable, composable skills — like plugins for your agent:

```
skills/
├── data-analysis/
│   ├── SKILL.md          # Skill definition
│   └── hooks/
│       └── pre_execute.py
├── web-scraping/
│   ├── SKILL.md
│   └── hooks/
└── ...
```

### Context Management

Prevents context window overflow with smart summarization:

```python
from agentic_computer.context.manager import ContextManager

ctx = ContextManager(max_tokens=128000)
ctx.add("system", "You are a helpful assistant.", priority=1.0, pinned=True)
ctx.add("user", long_conversation_text, priority=0.5)

if ctx.is_approaching_limit():
    freed = ctx.compress()  # Summarizes old entries
```

---

## Feature Comparison

| Feature | agentic-computer | AutoGen | CrewAI | OpenClaw |
|---|---|---|---|---|
| Multi-agent orchestration | ✅ | ✅ | ✅ | ❌ |
| Browser automation | ✅ Playwright | ❌ | ❌ | ✅ |
| Persistent memory | ✅ SQLite + Vector | ❌ | ❌ | ❌ |
| Code execution sandbox | ✅ | ✅ | ❌ | ✅ |
| YAML workflows | ✅ DAG-based | ❌ | ❌ | ❌ |
| Skills/plugins | ✅ Markdown-based | ❌ | ✅ | ❌ |
| Context management | ✅ Anti-rot | ❌ | ❌ | ❌ |
| Web dashboard | ✅ Next.js | ❌ | ❌ | ❌ |
| REST + WebSocket API | ✅ FastAPI | ❌ | ❌ | ✅ |
| Provider agnostic | ✅ OpenAI/Anthropic/Ollama | ✅ | ✅ | ❌ |
| Open source | ✅ MIT | ✅ | ✅ | ✅ |

---

## Project Structure

```
agentic-computer/
├── agentic_computer/          # Core Python package
│   ├── main.py                # CLI entry point
│   ├── config.py              # Configuration management
│   ├── core/                  # Agent, orchestrator, planner, executor, verifier
│   ├── memory/                # SQLite + vector memory store
│   ├── tools/                 # Browser, code executor, shell, file manager, search
│   ├── skills/                # Skill loader and built-in skills
│   ├── context/               # Context window management
│   ├── workflows/             # YAML workflow engine
│   └── server/                # FastAPI REST + WebSocket server
├── web/                       # Next.js dashboard UI
├── skills/                    # Community skills directory
├── tests/                     # Test suite
├── docs/                      # Documentation
├── docker-compose.yml         # Full stack deployment
└── Makefile                   # Common commands
```

---

## Configuration

All configuration is via environment variables. See [`.env.example`](.env.example) for the full list.

| Variable | Description | Default |
|---|---|---|
| `LLM_PROVIDER` | LLM provider: `openai`, `anthropic`, `ollama` | `openai` |
| `LLM_MODEL` | Model name | `gpt-4o` |
| `OPENAI_API_KEY` | OpenAI API key | — |
| `ANTHROPIC_API_KEY` | Anthropic API key | — |
| `BROWSER_HEADLESS` | Run browser headless | `true` |
| `SQLITE_DB_PATH` | Path to SQLite database | `./data/agentic.db` |
| `CHROMA_PERSIST_DIR` | ChromaDB persistence directory | `./data/chroma` |
| `SEARCH_PROVIDER` | Search provider: `serper`, `tavily` | `serper` |
| `SERVER_PORT` | API server port | `8000` |

---

## Development

```bash
# Install dev dependencies
make dev

# Run tests
make test

# Run with coverage
make test-cov

# Lint
make lint

# Format
make format

# Type check
make typecheck
```

---

## API Reference

See the [full API documentation](docs/api-reference.md).

### Quick Examples

```bash
# Submit a task
curl -X POST http://localhost:8000/api/v1/tasks \
  -H "Content-Type: application/json" \
  -d '{"task": "Search for latest AI news"}'

# List tools
curl http://localhost:8000/api/v1/tools

# Search memory
curl "http://localhost:8000/api/v1/memory/search?q=python+preferences"
```

### WebSocket

```javascript
const ws = new WebSocket('ws://localhost:8000/ws');
ws.send(JSON.stringify({ type: 'task', data: { task: 'Hello' } }));
ws.onmessage = (event) => {
  const msg = JSON.parse(event.data);
  // msg.type: 'progress' | 'result' | 'error'
};
```

---

## Skills Library

Skills are the extensibility layer. Each skill is a directory with a `SKILL.md` definition and optional hooks.

**Built-in skills:**
- **Research** — Multi-step web research with source synthesis
- **Coding** — Code generation, review, and refactoring
- **Design** — UI/UX design intelligence with component generation

**Writing a custom skill:**

```markdown
---
name: data-analysis
description: Analyze datasets and generate insights
version: 1.0.0
author: your-name
tags: [data, analysis, csv, statistics]
---

# Data Analysis Skill

## Instructions
Analyze the provided dataset and generate statistical insights...

## Tools Required
- code_executor
- file_manager
```

See the [Skills Guide](docs/skills-guide.md) for the full documentation.

---

## Contributing

We welcome contributions! Here's how to get started:

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/my-feature`
3. Make your changes and add tests
4. Run `make test && make lint` to verify
5. Commit with a descriptive message
6. Push to your fork and open a pull request

### Guidelines

- Write tests for new features
- Follow existing code style (enforced by `ruff`)
- Add type hints to all functions
- Update docs if adding new features
- Keep PRs focused — one feature per PR

---

## Credits

**agentic-computer** draws inspiration from several excellent projects:

- **[Superpowers](https://github.com/superpowers)** — Skill-based agent architecture and markdown-driven configuration
- **[GSD](https://github.com/gsd)** — Anti-context-rot patterns and context window management
- **[claude-mem](https://github.com/claude-mem)** — Memory compression and progressive disclosure retrieval
- **[ui-ux-pro-max](https://github.com/ui-ux-pro-max)** — Design intelligence and component generation patterns
- **[Perplexity Computer](https://perplexity.ai)** — The vision of an autonomous computer agent

---

## License

[MIT](LICENSE) — use it however you want.
