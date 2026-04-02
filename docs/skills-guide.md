# Skills Guide: Writing Custom Skills

## What Is a Skill?

A **skill** is a focused, reusable capability that the agentic-computer framework can invoke to handle a specific category of tasks. Unlike low-level tools (browser, sandbox, search), skills operate at a higher level of abstraction -- they combine tools, LLM calls, and domain logic to accomplish meaningful work.

Examples of skills:
- **research** -- gather information from the web and synthesize findings
- **coding** -- write, debug, and refactor code
- **data-analysis** -- query databases, compute metrics, and generate visualizations
- **design** -- produce UI mockups or wireframes from descriptions

Each skill:
1. **Declares metadata** -- name, description, version, author, and tags
2. **Reports confidence** -- given a task description, returns a score from 0.0 to 1.0 indicating how well it can handle the task
3. **Lists required tools** -- so the framework can fail fast if a dependency is missing
4. **Executes** -- receives a `SkillContext` (task, memory, tools, config) and returns a `SkillResult`

The framework uses a `SkillLoader` to discover installed skills, rank them by confidence for a given task, and dispatch to the best match.

---

## SKILL.md Format Specification

Every skill directory must contain a `SKILL.md` file at its root. This file uses YAML frontmatter followed by Markdown content to define the skill's identity and behavior.

### Structure

```markdown
---
name: my-skill-name
description: A one-line summary of what this skill does.
version: 1.0.0
author: Your Name
tags:
  - category-tag
  - domain-tag
tools:
  - tool_name_1
  - tool_name_2
triggers:
  - keyword or phrase that activates this skill
---

# Skill Name

## Instructions

Detailed instructions for the agent when this skill is active.
Explain the approach, constraints, and expected behavior.

## Examples

### Example 1: Brief description
Input: ...
Expected behavior: ...
```

### Frontmatter Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | Yes | Unique machine-friendly identifier. Use lowercase with hyphens. |
| `description` | string | Yes | One-line human-readable summary (shown in listings). |
| `version` | string | Yes | Semantic version (e.g., `1.0.0`). |
| `author` | string | Yes | Author name or organization. |
| `tags` | list[string] | Yes | Labels for discovery and filtering. |
| `tools` | list[string] | No | Tool names the skill requires at runtime. |
| `triggers` | list[string] | No | Keywords/phrases that suggest this skill should handle a task. |

### Body Sections

| Section | Required | Description |
|---------|----------|-------------|
| **Instructions** | Yes | The core prompt/guidance for the agent. This is injected into the system context when the skill is active. |
| **Examples** | No | Input/output examples that help the agent understand expected behavior. |
| **Constraints** | No | Guardrails and limitations the agent must respect. |
| **Output Format** | No | Describe the expected structure of the skill's output. |

---

## Creating a Custom Skill Step by Step

### Step 1: Create the skill directory

```
skills/
  my-custom-skill/
    SKILL.md
    __init__.py
    skill.py
    hooks/
      pre_execute.py    (optional)
      post_execute.py   (optional)
```

### Step 2: Write the SKILL.md

```markdown
---
name: data-analysis
description: Analyze datasets, compute metrics, and generate visualizations.
version: 0.1.0
author: Your Name
tags:
  - data
  - analytics
  - visualization
tools:
  - code_sandbox
  - memory
triggers:
  - analyze data
  - compute metrics
  - generate chart
  - data visualization
---

# Data Analysis Skill

## Instructions

You are a data analysis agent. When given a dataset or a question about data:

1. Understand the data source (file, database, API).
2. Load and inspect the data, noting schema, types, and row counts.
3. Perform the requested analysis (aggregation, filtering, statistical tests).
4. Generate visualizations when they would clarify the results.
5. Summarize findings in plain language.

Always validate data before computing metrics. Handle missing values
explicitly. Use pandas for tabular data and matplotlib/seaborn for charts.

## Constraints

- Never modify source data in place; always work on copies.
- Cap output tables at 50 rows; use summaries for larger results.
- All generated charts must include axis labels and a title.

## Output Format

Return a SkillResult with:
- `output`: A Markdown summary of findings.
- `artifacts`: A list of dicts, each with `type` ("chart", "table", "file")
  and relevant content or file paths.
```

### Step 3: Implement the Python skill class

Create `skill.py` with a class that extends `BaseSkill`:

```python
"""Data analysis skill implementation."""

from __future__ import annotations

from agentic_computer.skills.base import (
    BaseSkill,
    SkillContext,
    SkillMetadata,
    SkillResult,
)


class DataAnalysisSkill(BaseSkill):
    """Skill for analyzing datasets and generating insights."""

    @property
    def metadata(self) -> SkillMetadata:
        return SkillMetadata(
            name="data-analysis",
            description="Analyze datasets, compute metrics, and generate visualizations.",
            version="0.1.0",
            author="Your Name",
            tags=["data", "analytics", "visualization"],
        )

    def can_handle(self, task: str) -> float:
        """Return confidence score based on keyword overlap."""
        keywords = [
            "analyze", "data", "dataset", "metrics", "chart",
            "visualization", "statistics", "aggregate", "query",
            "csv", "dataframe", "pandas", "plot", "graph",
        ]
        return self._keyword_confidence(task, keywords)

    def get_required_tools(self) -> list[str]:
        return ["code_sandbox", "memory"]

    async def execute(self, context: SkillContext) -> SkillResult:
        """Execute data analysis based on the task description."""
        task = context.task

        # 1. Plan the analysis
        plan = await self._plan_analysis(task, context)

        # 2. Execute analysis code in sandbox
        result = await self._run_analysis(plan, context)

        # 3. Generate visualizations if needed
        charts = await self._generate_charts(result, context)

        # 4. Summarize findings
        summary = await self._summarize(result, charts, context)

        return SkillResult(
            success=True,
            output=summary,
            artifacts=charts,
            metadata={"plan": plan, "row_count": result.get("row_count", 0)},
        )

    # -- private helpers (implement these based on your needs) --

    async def _plan_analysis(self, task: str, context: SkillContext) -> dict:
        """Use the LLM to plan the analysis approach."""
        # Implementation here
        return {"steps": [], "approach": ""}

    async def _run_analysis(self, plan: dict, context: SkillContext) -> dict:
        """Execute the planned analysis in a sandboxed environment."""
        # Implementation here
        return {"data": None, "row_count": 0}

    async def _generate_charts(self, result: dict, context: SkillContext) -> list[dict]:
        """Generate visualization artifacts."""
        # Implementation here
        return []

    async def _summarize(
        self, result: dict, charts: list[dict], context: SkillContext
    ) -> str:
        """Produce a human-readable summary of findings."""
        # Implementation here
        return "Analysis complete."
```

### Step 4: Create `__init__.py`

```python
"""Data analysis skill for agentic-computer."""

from .skill import DataAnalysisSkill

__all__ = ["DataAnalysisSkill"]
```

### Step 5: Register the skill

Skills are discovered automatically when placed in the `skills/` directory. The `SkillLoader` scans for `SKILL.md` files and imports the corresponding Python package. No manual registration is needed.

Alternatively, you can register programmatically:

```python
from agentic_computer.skills.loader import SkillLoader

loader = SkillLoader()
loader.load_from_directory("./skills/my-custom-skill")
```

---

## Skill Hooks (Pre/Post Execution)

Hooks let you run custom logic before and after a skill executes. They are useful for:
- Validating inputs or preconditions
- Setting up temporary resources
- Logging and telemetry
- Cleaning up after execution
- Transforming or enriching results

### Hook Directory Structure

```
my-skill/
  hooks/
    pre_execute.py     # Runs before skill.execute()
    post_execute.py    # Runs after skill.execute()
```

### Pre-Execution Hook

The `pre_execute.py` module must define an async function named `pre_execute` that receives the `SkillContext` and can modify it or raise an exception to abort.

```python
"""Pre-execution hook for the data-analysis skill."""

from __future__ import annotations

import logging
from typing import Any

from agentic_computer.skills.base import SkillContext

logger = logging.getLogger(__name__)


async def pre_execute(context: SkillContext, config: dict[str, Any] | None = None) -> SkillContext:
    """Validate and enrich the context before skill execution.

    Args:
        context: The skill context about to be passed to execute().
        config: Optional hook-specific configuration.

    Returns:
        The (possibly modified) SkillContext.

    Raises:
        ValueError: If preconditions are not met.
    """
    logger.info("pre_execute hook running for task: %s", context.task[:80])

    # Example: validate that the task is not empty
    if not context.task.strip():
        raise ValueError("Task description cannot be empty.")

    # Example: inject default configuration
    if context.config is None:
        context.config = {}
    context.config.setdefault("max_rows", 10000)
    context.config.setdefault("chart_format", "png")

    return context
```

### Post-Execution Hook

The `post_execute.py` module must define an async function named `post_execute` that receives the `SkillResult` and can modify it.

```python
"""Post-execution hook for the data-analysis skill."""

from __future__ import annotations

import logging
from typing import Any

from agentic_computer.skills.base import SkillResult

logger = logging.getLogger(__name__)


async def post_execute(result: SkillResult, config: dict[str, Any] | None = None) -> SkillResult:
    """Process and enrich the result after skill execution.

    Args:
        result: The skill result returned by execute().
        config: Optional hook-specific configuration.

    Returns:
        The (possibly modified) SkillResult.
    """
    logger.info("post_execute hook running, success=%s", result.success)

    # Example: add execution timestamp to metadata
    from datetime import datetime, timezone
    result.metadata["completed_at"] = datetime.now(timezone.utc).isoformat()

    # Example: log artifact count
    if result.artifacts:
        logger.info("Skill produced %d artifacts.", len(result.artifacts))

    return result
```

### How Hooks Are Invoked

The framework's skill runner invokes hooks in this order:

```
1. Load pre_execute hook from skills/<name>/hooks/pre_execute.py
2. Call pre_execute(context) -> modified context
3. Call skill.execute(modified_context) -> result
4. Load post_execute hook from skills/<name>/hooks/post_execute.py
5. Call post_execute(result) -> modified result
6. Return modified result to caller
```

If a hook file does not exist, that step is silently skipped. If a pre-execution hook raises an exception, execution is aborted and a `SkillResult(success=False, ...)` is returned.

---

## Example: Building a "Data Analysis" Skill

This walkthrough builds the `data-analysis` skill from scratch.

### 1. Create the directory

```bash
mkdir -p skills/data-analysis/hooks
```

### 2. Write SKILL.md

See the full SKILL.md content in Step 2 of the "Creating a Custom Skill" section above.

### 3. Implement can_handle with keyword matching

The base class provides `_keyword_confidence()` as a helper. For more sophisticated matching, you can use the LLM:

```python
def can_handle(self, task: str) -> float:
    """Score confidence using keyword matching with domain boosters."""
    # Primary keywords: strong signals
    primary = ["analyze", "data", "dataset", "metrics", "statistics"]
    # Secondary keywords: weaker signals
    secondary = ["csv", "table", "rows", "columns", "aggregate"]

    task_lower = task.lower()
    primary_hits = sum(1 for kw in primary if kw in task_lower)
    secondary_hits = sum(1 for kw in secondary if kw in task_lower)

    if primary_hits == 0 and secondary_hits == 0:
        return 0.05  # near-zero base confidence

    score = 0.3 + (primary_hits * 0.15) + (secondary_hits * 0.08)
    return min(1.0, score)
```

### 4. Implement execute with tool delegation

```python
async def execute(self, context: SkillContext) -> SkillResult:
    """Run the data analysis pipeline."""
    tools = context.tools  # ToolRegistry instance
    memory = context.memory  # MemoryStore instance

    # Step 1: Use the sandbox to run pandas code
    code = f'''
import pandas as pd
import json

# Load and analyze
df = pd.read_csv("input.csv")
summary = df.describe().to_dict()
print(json.dumps(summary))
'''
    sandbox_result = await tools.execute("code_sandbox", code=code, timeout=30)

    if not sandbox_result.success:
        return SkillResult(
            success=False,
            output=f"Analysis failed: {sandbox_result.error}",
        )

    # Step 2: Store findings in memory for future reference
    if memory is not None:
        from agentic_computer.memory.schema import MemoryType
        await memory.add(
            content=f"Analysis result: {sandbox_result.output}",
            memory_type=MemoryType.EPISODIC,
            metadata={"skill": "data-analysis", "task": context.task},
        )

    return SkillResult(
        success=True,
        output=sandbox_result.output,
        artifacts=[],
        metadata={"source": "data-analysis-skill"},
    )
```

### 5. Add a pre-execution hook for validation

Create `hooks/pre_execute.py` to ensure the task references actual data:

```python
async def pre_execute(context, config=None):
    task_lower = context.task.lower()
    data_indicators = ["csv", "data", "dataset", "table", "database", "file"]
    if not any(ind in task_lower for ind in data_indicators):
        import logging
        logging.getLogger(__name__).warning(
            "Task does not reference a data source; proceeding anyway."
        )
    return context
```

---

## Testing Skills

### Unit Testing can_handle

```python
import pytest
from skills.data_analysis.skill import DataAnalysisSkill


class TestDataAnalysisSkill:
    def setup_method(self):
        self.skill = DataAnalysisSkill()

    def test_high_confidence_for_data_tasks(self):
        assert self.skill.can_handle("analyze this CSV dataset") > 0.5

    def test_low_confidence_for_unrelated_tasks(self):
        assert self.skill.can_handle("write a poem about cats") < 0.2

    def test_metadata_is_valid(self):
        meta = self.skill.metadata
        assert meta.name == "data-analysis"
        assert meta.version  # not empty
        assert len(meta.tags) > 0

    def test_required_tools_declared(self):
        tools = self.skill.get_required_tools()
        assert "code_sandbox" in tools
```

### Integration Testing execute

```python
import pytest
from unittest.mock import AsyncMock, MagicMock

from agentic_computer.skills.base import SkillContext
from agentic_computer.tools.registry import ToolResult
from skills.data_analysis.skill import DataAnalysisSkill


@pytest.mark.asyncio
async def test_execute_success():
    skill = DataAnalysisSkill()

    # Mock the tool registry
    mock_tools = MagicMock()
    mock_tools.execute = AsyncMock(
        return_value=ToolResult(success=True, output='{"mean": 42.0}')
    )

    context = SkillContext(
        task="Analyze the sales data and compute average revenue.",
        tools=mock_tools,
        memory=None,
    )

    result = await skill.execute(context)
    assert result.success is True
    assert result.output  # non-empty


@pytest.mark.asyncio
async def test_execute_handles_sandbox_failure():
    skill = DataAnalysisSkill()

    mock_tools = MagicMock()
    mock_tools.execute = AsyncMock(
        return_value=ToolResult(success=False, error="Timeout exceeded")
    )

    context = SkillContext(task="Analyze data", tools=mock_tools)
    result = await skill.execute(context)
    assert result.success is False
```

### Testing Hooks

```python
import pytest
from agentic_computer.skills.base import SkillContext, SkillResult


@pytest.mark.asyncio
async def test_pre_execute_hook():
    from skills.data_analysis.hooks.pre_execute import pre_execute

    context = SkillContext(task="Analyze the CSV data")
    modified = await pre_execute(context)
    assert modified.config is not None
    assert "max_rows" in modified.config


@pytest.mark.asyncio
async def test_pre_execute_rejects_empty_task():
    from skills.data_analysis.hooks.pre_execute import pre_execute

    context = SkillContext(task="   ")
    with pytest.raises(ValueError, match="cannot be empty"):
        await pre_execute(context)
```

### Running Tests

```bash
# Run all skill tests
pytest tests/ -v -k "skill"

# Run with coverage
pytest tests/ -v --cov=skills --cov-report=term-missing
```

---

## Publishing to the Community Directory

The `skills/` directory at the repository root serves as the community skill directory. To share a skill:

### 1. Prepare your skill

Ensure your skill directory contains:
- `SKILL.md` with complete frontmatter and instructions
- `__init__.py` exporting the skill class
- `skill.py` (or equivalent) with the implementation
- Tests in the project's `tests/` directory

### 2. Validate your skill

```bash
# Check that the skill loads without errors
python -c "
from skills.your_skill import YourSkill
s = YourSkill()
print(f'Name: {s.metadata.name}')
print(f'Version: {s.metadata.version}')
print(f'Tags: {s.metadata.tags}')
print(f'Tools: {s.get_required_tools()}')
print(f'Confidence test: {s.can_handle(\"sample task\")}')
"
```

### 3. Submit a pull request

1. Fork the repository.
2. Add your skill directory under `skills/`.
3. Add tests under `tests/skills/`.
4. Update `skills/README.md` to list your skill in the directory table.
5. Open a PR with a clear description of what the skill does and example usage.

### Quality Guidelines

- **Naming**: Use lowercase-with-hyphens for the directory and `name` field (e.g., `data-analysis`).
- **Versioning**: Follow semantic versioning. Start at `0.1.0` for initial submissions.
- **Documentation**: The `SKILL.md` must include clear Instructions and at least one Example.
- **Testing**: Include at least one unit test for `can_handle` and one integration test for `execute`.
- **Dependencies**: If your skill requires additional Python packages, document them in the SKILL.md and consider adding them to `[project.optional-dependencies]` in `pyproject.toml`.
- **Error handling**: Skills must never raise unhandled exceptions from `execute()`. Always return a `SkillResult(success=False, ...)`.
- **Tool declarations**: `get_required_tools()` must accurately list every tool the skill calls. Missing declarations cause confusing runtime failures.
