# API Reference

## Base URL

```
http://localhost:8000
```

All REST endpoints are prefixed with `/api/v1`. The WebSocket endpoint is at `/ws`.

## Authentication

Authentication is handled via API key passed in the `Authorization` header:

```
Authorization: Bearer <your-api-key>
```

For local development, authentication can be disabled by omitting the `API_KEY` environment variable. In production, always set a strong API key.

---

## REST Endpoints

### Tasks

#### POST /api/v1/tasks

Submit a new task for the agent to execute.

**Request:**

```http
POST /api/v1/tasks HTTP/1.1
Content-Type: application/json

{
  "task": "Search the web for recent AI research papers and summarize the top 5 findings.",
  "model": "gpt-4o",
  "config": {
    "max_steps": 10,
    "timeout": 300,
    "verbose": true
  }
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `task` | string | Yes | Natural-language description of the task to execute. |
| `model` | string | No | Override the default LLM model for this task. |
| `config` | object | No | Task-specific configuration overrides. |
| `config.max_steps` | integer | No | Maximum number of subtask steps (default: 20). |
| `config.timeout` | integer | No | Overall timeout in seconds (default: 600). |
| `config.verbose` | boolean | No | Enable detailed logging for this task (default: false). |

**Response (202 Accepted):**

```json
{
  "id": "task_a1b2c3d4e5f6",
  "status": "pending",
  "task": "Search the web for recent AI research papers and summarize the top 5 findings.",
  "created_at": "2025-01-15T10:30:00Z",
  "links": {
    "self": "/api/v1/tasks/task_a1b2c3d4e5f6",
    "ws": "/ws?task_id=task_a1b2c3d4e5f6"
  }
}
```

---

#### GET /api/v1/tasks/{id}

Retrieve the current status and result of a task.

**Request:**

```http
GET /api/v1/tasks/task_a1b2c3d4e5f6 HTTP/1.1
```

**Response (200 OK) -- task in progress:**

```json
{
  "id": "task_a1b2c3d4e5f6",
  "status": "executing",
  "task": "Search the web for recent AI research papers and summarize the top 5 findings.",
  "created_at": "2025-01-15T10:30:00Z",
  "updated_at": "2025-01-15T10:30:45Z",
  "progress": {
    "total_subtasks": 4,
    "completed_subtasks": 2,
    "current_subtask": "Searching for AI research papers published in 2025"
  },
  "result": null
}
```

**Response (200 OK) -- task completed:**

```json
{
  "id": "task_a1b2c3d4e5f6",
  "status": "done",
  "task": "Search the web for recent AI research papers and summarize the top 5 findings.",
  "created_at": "2025-01-15T10:30:00Z",
  "updated_at": "2025-01-15T10:32:10Z",
  "progress": {
    "total_subtasks": 4,
    "completed_subtasks": 4,
    "current_subtask": null
  },
  "result": {
    "success": true,
    "output": "Here are the top 5 AI research findings...",
    "metadata": {
      "duration_seconds": 130,
      "tokens_used": 8420,
      "subtasks_executed": 4
    }
  }
}
```

**Response (404 Not Found):**

```json
{
  "error": {
    "code": "TASK_NOT_FOUND",
    "message": "Task 'task_invalid' does not exist."
  }
}
```

---

#### GET /api/v1/tasks

List all tasks with optional filtering and pagination.

**Request:**

```http
GET /api/v1/tasks?status=done&limit=10&offset=0 HTTP/1.1
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `status` | string | (all) | Filter by status: `pending`, `executing`, `done`, `error`. |
| `limit` | integer | 20 | Maximum number of tasks to return (max: 100). |
| `offset` | integer | 0 | Number of tasks to skip for pagination. |

**Response (200 OK):**

```json
{
  "tasks": [
    {
      "id": "task_a1b2c3d4e5f6",
      "status": "done",
      "task": "Search the web for recent AI research papers...",
      "created_at": "2025-01-15T10:30:00Z",
      "updated_at": "2025-01-15T10:32:10Z"
    },
    {
      "id": "task_f6e5d4c3b2a1",
      "status": "done",
      "task": "Generate a summary of quarterly sales data...",
      "created_at": "2025-01-15T09:15:00Z",
      "updated_at": "2025-01-15T09:18:30Z"
    }
  ],
  "total": 42,
  "limit": 10,
  "offset": 0
}
```

---

### Workflows

#### POST /api/v1/workflows

Create and execute a new workflow from a YAML definition.

**Request:**

```http
POST /api/v1/workflows HTTP/1.1
Content-Type: application/json

{
  "name": "research-and-report",
  "definition": {
    "steps": [
      {
        "name": "research",
        "tool": "web_search",
        "params": {
          "query": "latest trends in renewable energy 2025"
        }
      },
      {
        "name": "analyze",
        "agent_role": "researcher",
        "task": "Analyze the search results and identify key themes.",
        "depends_on": ["research"]
      },
      {
        "name": "report",
        "agent_role": "coder",
        "task": "Write a structured Markdown report of the findings.",
        "depends_on": ["analyze"]
      }
    ]
  },
  "input": {
    "topic": "renewable energy"
  }
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | Yes | Human-readable name for the workflow. |
| `definition` | object | Yes | Workflow structure with steps. |
| `definition.steps` | array | Yes | Ordered list of workflow steps. |
| `input` | object | No | JSON input data passed to the workflow. |

**Response (202 Accepted):**

```json
{
  "id": "wf_x1y2z3",
  "name": "research-and-report",
  "status": "running",
  "created_at": "2025-01-15T11:00:00Z",
  "steps": [
    {"name": "research", "status": "pending"},
    {"name": "analyze", "status": "pending"},
    {"name": "report", "status": "pending"}
  ]
}
```

---

#### GET /api/v1/workflows

List all workflows.

**Request:**

```http
GET /api/v1/workflows?limit=10 HTTP/1.1
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `limit` | integer | 20 | Maximum number of workflows to return. |
| `offset` | integer | 0 | Pagination offset. |

**Response (200 OK):**

```json
{
  "workflows": [
    {
      "id": "wf_x1y2z3",
      "name": "research-and-report",
      "status": "completed",
      "created_at": "2025-01-15T11:00:00Z",
      "step_count": 3
    }
  ],
  "total": 5,
  "limit": 10,
  "offset": 0
}
```

---

### Tools

#### GET /api/v1/tools

List all registered tools and their specifications.

**Request:**

```http
GET /api/v1/tools HTTP/1.1
```

**Response (200 OK):**

```json
{
  "tools": [
    {
      "name": "browser",
      "description": "Automate a Chromium browser: navigate to URLs, click elements, type text, capture screenshots, extract page text, and execute JavaScript.",
      "parameters": {
        "action": {
          "type": "string",
          "description": "The browser action to perform. One of: navigate, click, type_text, screenshot, extract_text, execute_js."
        },
        "url": {
          "type": "string",
          "description": "URL for navigate action."
        },
        "selector": {
          "type": "string",
          "description": "CSS selector for click / type_text actions."
        },
        "text": {
          "type": "string",
          "description": "Text for type_text action."
        },
        "script": {
          "type": "string",
          "description": "JavaScript for execute_js action."
        }
      },
      "required_params": ["action"]
    },
    {
      "name": "web_search",
      "description": "Search the web using Serper or Tavily.",
      "parameters": {
        "query": {
          "type": "string",
          "description": "The search query."
        },
        "num_results": {
          "type": "integer",
          "description": "Number of results to return (default: 10)."
        }
      },
      "required_params": ["query"]
    },
    {
      "name": "code_sandbox",
      "description": "Execute code in an isolated sandbox environment.",
      "parameters": {
        "code": {
          "type": "string",
          "description": "The code to execute."
        },
        "language": {
          "type": "string",
          "description": "Programming language (default: python)."
        },
        "timeout": {
          "type": "integer",
          "description": "Execution timeout in seconds (default: 30)."
        }
      },
      "required_params": ["code"]
    }
  ]
}
```

---

#### POST /api/v1/tools/{name}/execute

Execute a specific tool with the given parameters.

**Request:**

```http
POST /api/v1/tools/browser/execute HTTP/1.1
Content-Type: application/json

{
  "action": "navigate",
  "url": "https://example.com"
}
```

**Response (200 OK):**

```json
{
  "success": true,
  "output": {
    "title": "Example Domain",
    "text": "This domain is for use in illustrative examples in documents...",
    "url": "https://example.com"
  },
  "error": null,
  "duration_ms": 1245.3
}
```

**Response (400 Bad Request) -- missing required parameter:**

```json
{
  "error": {
    "code": "MISSING_PARAMETER",
    "message": "Missing required parameter(s) for 'browser': action"
  }
}
```

**Response (404 Not Found) -- unknown tool:**

```json
{
  "error": {
    "code": "TOOL_NOT_FOUND",
    "message": "Unknown tool: 'nonexistent_tool'"
  }
}
```

---

### Memory

#### GET /api/v1/memory/search

Search the memory store by text query or semantic similarity.

**Request:**

```http
GET /api/v1/memory/search?query=sales%20analysis&type=episodic&limit=5&min_similarity=0.7 HTTP/1.1
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `query` | string | (required) | Search query text. |
| `type` | string | (all) | Filter by memory type: `episodic`, `semantic`, `procedural`, `working`. |
| `limit` | integer | 10 | Maximum number of results. |
| `min_similarity` | float | 0.0 | Minimum cosine similarity threshold (0.0 - 1.0). |

**Response (200 OK):**

```json
{
  "results": [
    {
      "entry": {
        "id": "550e8400-e29b-41d4-a716-446655440000",
        "content": "Sales analysis completed: Q4 revenue was $2.3M, up 15% from Q3.",
        "memory_type": "episodic",
        "metadata": {
          "skill": "data-analysis",
          "task": "Analyze Q4 sales data"
        },
        "created_at": "2025-01-14T15:20:00Z",
        "accessed_at": "2025-01-15T10:00:00Z",
        "access_count": 3,
        "importance_score": 0.8
      },
      "similarity_score": 0.92
    },
    {
      "entry": {
        "id": "6ba7b810-9dad-11d1-80b4-00c04fd430c8",
        "content": "Sales data is stored in the company Snowflake warehouse under schema analytics.sales.",
        "memory_type": "semantic",
        "metadata": {
          "source": "discovery"
        },
        "created_at": "2025-01-10T09:00:00Z",
        "accessed_at": "2025-01-14T15:18:00Z",
        "access_count": 7,
        "importance_score": 0.6
      },
      "similarity_score": 0.85
    }
  ],
  "total": 2
}
```

---

#### POST /api/v1/memory

Store a new memory entry.

**Request:**

```http
POST /api/v1/memory HTTP/1.1
Content-Type: application/json

{
  "content": "The production database connection string uses port 5432 and requires SSL.",
  "memory_type": "semantic",
  "metadata": {
    "source": "manual",
    "category": "infrastructure"
  },
  "importance": 0.7
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `content` | string | Yes | Textual content of the memory. |
| `memory_type` | string | No | One of: `episodic`, `semantic`, `procedural`, `working` (default: `working`). |
| `metadata` | object | No | Arbitrary key-value metadata. |
| `importance` | float | No | Importance score from 0.0 to 1.0 (default: 0.5). |

**Response (201 Created):**

```json
{
  "id": "7c9e6679-7425-40de-944b-e07fc1f90ae7",
  "content": "The production database connection string uses port 5432 and requires SSL.",
  "memory_type": "semantic",
  "metadata": {
    "source": "manual",
    "category": "infrastructure"
  },
  "created_at": "2025-01-15T12:00:00Z",
  "accessed_at": "2025-01-15T12:00:00Z",
  "access_count": 0,
  "importance_score": 0.7
}
```

---

#### GET /api/v1/memory/recent

Retrieve the most recently accessed memory entries.

**Request:**

```http
GET /api/v1/memory/recent?limit=5 HTTP/1.1
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `limit` | integer | 20 | Maximum number of entries to return. |

**Response (200 OK):**

```json
{
  "entries": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "content": "Sales analysis completed: Q4 revenue was $2.3M, up 15% from Q3.",
      "memory_type": "episodic",
      "metadata": {
        "skill": "data-analysis"
      },
      "created_at": "2025-01-14T15:20:00Z",
      "accessed_at": "2025-01-15T10:00:00Z",
      "access_count": 3,
      "importance_score": 0.8
    }
  ],
  "total": 1
}
```

---

## WebSocket Protocol

### Endpoint

```
ws://localhost:8000/ws
```

The WebSocket endpoint provides real-time streaming of agent activity. Connect with an optional `task_id` query parameter to subscribe to events for a specific task.

### Connection

```
ws://localhost:8000/ws?task_id=task_a1b2c3d4e5f6
```

If `task_id` is omitted, the client receives events for all active tasks.

### Message Format

All messages are JSON objects with a `type` field indicating the event kind.

#### Client -> Server Messages

**Submit a task:**

```json
{
  "type": "task.submit",
  "payload": {
    "task": "Navigate to example.com and extract the main heading.",
    "model": "gpt-4o"
  }
}
```

**Cancel a task:**

```json
{
  "type": "task.cancel",
  "payload": {
    "task_id": "task_a1b2c3d4e5f6"
  }
}
```

**Ping (keepalive):**

```json
{
  "type": "ping"
}
```

#### Server -> Client Messages

**Task accepted:**

```json
{
  "type": "task.accepted",
  "task_id": "task_a1b2c3d4e5f6",
  "timestamp": "2025-01-15T10:30:00Z"
}
```

**Agent state change:**

```json
{
  "type": "agent.state",
  "task_id": "task_a1b2c3d4e5f6",
  "agent": "Planner",
  "state": "thinking",
  "timestamp": "2025-01-15T10:30:01Z"
}
```

**Subtask progress:**

```json
{
  "type": "subtask.progress",
  "task_id": "task_a1b2c3d4e5f6",
  "subtask_id": "ab12cd34",
  "description": "Navigating to example.com",
  "status": "in_progress",
  "timestamp": "2025-01-15T10:30:05Z"
}
```

**Subtask completed:**

```json
{
  "type": "subtask.completed",
  "task_id": "task_a1b2c3d4e5f6",
  "subtask_id": "ab12cd34",
  "result": {
    "success": true,
    "output": "Page loaded successfully. Title: Example Domain"
  },
  "timestamp": "2025-01-15T10:30:12Z"
}
```

**Tool execution:**

```json
{
  "type": "tool.execute",
  "task_id": "task_a1b2c3d4e5f6",
  "tool": "browser",
  "action": "navigate",
  "params": {"url": "https://example.com"},
  "timestamp": "2025-01-15T10:30:06Z"
}
```

**Tool result:**

```json
{
  "type": "tool.result",
  "task_id": "task_a1b2c3d4e5f6",
  "tool": "browser",
  "success": true,
  "duration_ms": 1245.3,
  "timestamp": "2025-01-15T10:30:08Z"
}
```

**LLM token stream (partial output):**

```json
{
  "type": "llm.token",
  "task_id": "task_a1b2c3d4e5f6",
  "content": "Based on the page content, ",
  "timestamp": "2025-01-15T10:30:15Z"
}
```

**Task completed:**

```json
{
  "type": "task.completed",
  "task_id": "task_a1b2c3d4e5f6",
  "result": {
    "success": true,
    "output": "The main heading on example.com is 'Example Domain'.",
    "metadata": {
      "duration_seconds": 22,
      "tokens_used": 1530
    }
  },
  "timestamp": "2025-01-15T10:30:22Z"
}
```

**Task error:**

```json
{
  "type": "task.error",
  "task_id": "task_a1b2c3d4e5f6",
  "error": {
    "code": "EXECUTION_FAILED",
    "message": "Browser navigation timed out after 30000ms."
  },
  "timestamp": "2025-01-15T10:31:00Z"
}
```

**Pong (keepalive response):**

```json
{
  "type": "pong",
  "timestamp": "2025-01-15T10:30:30Z"
}
```

### WebSocket Example (Python)

```python
import asyncio
import json
import websockets


async def stream_task():
    uri = "ws://localhost:8000/ws"
    async with websockets.connect(uri) as ws:
        # Submit a task
        await ws.send(json.dumps({
            "type": "task.submit",
            "payload": {
                "task": "Navigate to example.com and extract the heading."
            }
        }))

        # Listen for events
        async for message in ws:
            event = json.loads(message)
            print(f"[{event['type']}] {json.dumps(event, indent=2)}")

            if event["type"] in ("task.completed", "task.error"):
                break


asyncio.run(stream_task())
```

### WebSocket Example (JavaScript)

```javascript
const ws = new WebSocket("ws://localhost:8000/ws");

ws.onopen = () => {
  ws.send(JSON.stringify({
    type: "task.submit",
    payload: {
      task: "Search for the latest Python release and summarize changes."
    }
  }));
};

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log(`[${data.type}]`, data);

  if (data.type === "task.completed" || data.type === "task.error") {
    ws.close();
  }
};

ws.onerror = (error) => {
  console.error("WebSocket error:", error);
};
```

---

## Error Codes

All error responses follow a consistent format:

```json
{
  "error": {
    "code": "ERROR_CODE",
    "message": "Human-readable description of what went wrong."
  }
}
```

### HTTP Status Codes

| Status | Meaning |
|--------|---------|
| 200 | Success |
| 201 | Created (new resource) |
| 202 | Accepted (async task started) |
| 400 | Bad Request (invalid input) |
| 401 | Unauthorized (missing or invalid API key) |
| 404 | Not Found (resource does not exist) |
| 409 | Conflict (duplicate resource) |
| 422 | Unprocessable Entity (validation error) |
| 429 | Too Many Requests (rate limit exceeded) |
| 500 | Internal Server Error |
| 503 | Service Unavailable (dependency down) |

### Application Error Codes

| Code | HTTP Status | Description |
|------|-------------|-------------|
| `TASK_NOT_FOUND` | 404 | The specified task ID does not exist. |
| `TASK_ALREADY_RUNNING` | 409 | A task with this ID is already in progress. |
| `WORKFLOW_NOT_FOUND` | 404 | The specified workflow ID does not exist. |
| `TOOL_NOT_FOUND` | 404 | The specified tool name is not registered. |
| `MISSING_PARAMETER` | 400 | A required parameter was not provided. |
| `INVALID_PARAMETER` | 422 | A parameter value failed validation. |
| `MEMORY_NOT_FOUND` | 404 | The specified memory ID does not exist. |
| `EXECUTION_FAILED` | 500 | Tool or agent execution failed unexpectedly. |
| `EXECUTION_TIMEOUT` | 500 | Execution exceeded the configured timeout. |
| `LLM_ERROR` | 502 | The upstream LLM provider returned an error. |
| `RATE_LIMITED` | 429 | Too many requests; retry after the indicated delay. |
| `UNAUTHORIZED` | 401 | Missing or invalid authentication credentials. |
| `SANDBOX_ERROR` | 500 | Code execution in the sandbox failed. |
| `BROWSER_ERROR` | 500 | Browser automation encountered an error. |

### Rate Limiting

When rate-limited, the response includes a `Retry-After` header:

```http
HTTP/1.1 429 Too Many Requests
Retry-After: 30
Content-Type: application/json

{
  "error": {
    "code": "RATE_LIMITED",
    "message": "Rate limit exceeded. Retry after 30 seconds."
  }
}
```
